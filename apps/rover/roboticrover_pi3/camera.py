"""Webcam USB -> FFmpeg -> latest JPEG -> HTTP MJPEG. No actuator access.

Run separately from MQTT. Timestamps refer to receipt of encoded JPEGs, not to
sensor exposure; keep that distinction when implementing perception later.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import select
import signal
import subprocess
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

LOG = logging.getLogger("roboticrover.camera")
MAX_JPEG_BYTES = 2 * 1024 * 1024


class JpegParser:
    """Bounded parser for consecutive FFmpeg image2pipe JPEGs."""

    def __init__(self, limit=MAX_JPEG_BYTES):
        self.buffer = bytearray()
        self.limit = limit

    def feed(self, chunk):
        self.buffer.extend(chunk)
        frames = []
        while self.buffer:
            start = self.buffer.find(b"\xff\xd8")
            if start < 0:
                self.buffer[:] = self.buffer[-1:] if self.buffer[-1:] == b"\xff" else b""
                break
            if start:
                del self.buffer[:start]
            end = self.buffer.find(b"\xff\xd9", 2)
            if end < 0:
                if len(self.buffer) > self.limit:
                    self.buffer.clear()
                break
            size = end + 2
            if size <= self.limit:
                frames.append(bytes(self.buffer[:size]))
            del self.buffer[:size]
        return frames


class FrameStore:
    """Only one frame is retained; slow viewers skip old frames."""

    def __init__(self, stale_after=2.0, clock=time.monotonic):
        self.condition = threading.Condition()
        self.clock = clock
        self.stale_after = stale_after
        self.session_id = uuid4().hex
        self.sequence = 0
        self.jpeg = None
        self.received_at = None
        self.received_utc = None
        self.recent = deque(maxlen=60)
        self.error = "waiting_for_camera"
        self.restarts = 0

    def publish(self, jpeg):
        with self.condition:
            self.sequence += 1
            self.jpeg = jpeg
            self.received_at = self.clock()
            self.received_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            self.recent.append(self.received_at)
            self.error = None
            self.condition.notify_all()

    def fail(self, reason):
        with self.condition:
            self.error = reason
            self.jpeg = None
            self.recent.clear()
            self.condition.notify_all()

    def healthy(self):
        return (self.jpeg is not None and self.error is None and
                self.clock() - self.received_at <= self.stale_after)

    def status(self):
        with self.condition:
            age = None if self.received_at is None else max(0, self.clock() - self.received_at)
            duration = self.recent[-1] - self.recent[0] if len(self.recent) > 1 else 0
            fps = (len(self.recent) - 1) / duration if duration > 0 else 0
            return {"online": self.healthy(), "session_id": self.session_id,
                    "frame_id": f"{self.session_id}:{self.sequence}",
                    "sequence": self.sequence, "frame_received_at": self.received_utc,
                    "timestamp_source": "encoder_output_received",
                    "frame_age_ms": None if age is None else round(age * 1000, 1),
                    "fps": round(fps, 2), "error": self.error,
                    "restarts": self.restarts}

    def latest(self, after=0, timeout=2.0):
        with self.condition:
            self.condition.wait_for(lambda: self.sequence > after or self.error is not None, timeout)
            if not self.healthy() or self.sequence <= after:
                return None
            return self.sequence, self.jpeg, self.received_utc


def competition_output(host, port, fps, transport="udp"):
    from .competition import host_address

    encoder = ["-map", "0:v:0", "-an", "-vf", f"fps={fps}",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-profile:v", "baseline", "-level:v", "3.1", "-pix_fmt", "yuv420p", "-threads", "1",
            "-bf", "0", "-g", str(fps), "-b:v", "650k", "-maxrate", "800k", "-bufsize", "180k",
            "-x264-params", f"keyint={fps}:min-keyint={fps}:scenecut=0:slices=1:repeat-headers=1"]
    destination = f"{host_address(host)}:{port}"
    if transport == "tcp":
        return encoder + ["-f", "fifo", "-fifo_format", "mpegts", "-format_opts", "flush_packets=1",
                          "-queue_size", str(max(4, fps // 2)), "-drop_pkts_on_overflow", "1",
                          "-attempt_recovery", "1", "-recover_any_error", "1", "-recovery_wait_time", "1",
                          "-restart_with_keyframe", "1",
                          f"tcp://{destination}?tcp_nodelay=1&send_buffer_size=16384&timeout=3000000"]
    return encoder + [
            "-f", "mpegts", "-muxdelay", "0", "-flush_packets", "1",
            f"udp://{destination}?pkt_size=1316"]


def ffmpeg_command(args):
    preview_fps = args.preview_fps
    if args.relay_host and preview_fps is None:
        preview_fps = min(args.fps, 8)
    command = [args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin",
            "-fflags", "+discardcorrupt", "-f", "v4l2", "-input_format", args.input_format,
            "-video_size", f"{args.width}x{args.height}", "-framerate", str(args.fps), "-i", args.device,
            "-filter_threads", "1", "-map", "0:v:0", "-an", "-threads", "1"]
    if preview_fps:
        command.extend(["-vf", f"fps={preview_fps}"])
    quality = max(args.quality, 10) if args.relay_host else args.quality
    command.extend(["-c:v", "mjpeg", "-q:v", str(quality), "-f", "image2pipe", "pipe:1"])
    if getattr(args, "relay_host", None):
        command.extend(competition_output(args.relay_host, args.relay_port, args.fps, args.relay_transport))
    return command


class Capture:
    def __init__(self, args, frames):
        self.args = args
        self.frames = frames
        self.stop_event = threading.Event()
        self.process = None
        self.thread = threading.Thread(target=self.run, name="camera-capture", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.frames.fail("camera_stopped")
        process = self.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        self.thread.join(timeout=5)

    def run(self):
        while not self.stop_event.is_set():
            try:
                LOG.info("Opening %s (%sx%s @ %s FPS)", self.args.device,
                         self.args.width, self.args.height, self.args.fps)
                self.process = subprocess.Popen(ffmpeg_command(self.args), stdout=subprocess.PIPE,
                                                stdin=subprocess.DEVNULL, bufsize=0)
                parser = JpegParser()
                last_frame = time.monotonic()
                while not self.stop_event.is_set():
                    if time.monotonic() - last_frame > 5:
                        self.frames.fail("capture_stalled")
                        break
                    readable, _, _ = select.select([self.process.stdout], [], [], 1)
                    if not readable:
                        continue
                    chunk = os.read(self.process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    for jpeg in parser.feed(chunk):
                        self.frames.publish(jpeg)
                        last_frame = time.monotonic()
                if not self.stop_event.is_set():
                    self.frames.fail("capture_disconnected")
                    LOG.warning("Capture ended; retrying in 2 seconds")
            except OSError as exc:
                self.frames.fail("capture_unavailable")
                LOG.warning("Cannot open capture: %s", exc)
            finally:
                process = self.process
                if process:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=3)
                    if process.stdout:
                        process.stdout.close()
                    self.process = None
            if not self.stop_event.is_set():
                self.frames.restarts += 1
                self.stop_event.wait(2)


class CameraServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, args, frames):
        super().__init__(address, CameraHandler)
        self.args = args
        self.frames = frames
        self.viewers = threading.BoundedSemaphore(4)


class CameraHandler(BaseHTTPRequestHandler):
    # Close completed health/snapshot connections promptly through SSH tunnels.
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, fmt, *args):
        LOG.debug(fmt, *args)

    def respond(self, status, content_type, length=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.close_connection = True
        origin = self.headers.get("Origin")
        if origin in self.server.args.allowed_origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        if length is not None:
            self.send_header("Content-Length", str(length))

    def do_GET(self):
        try:
            self.handle_get()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def handle_get(self):
        route = urlsplit(self.path).path
        frames = self.server.frames
        if route == "/health":
            status = dict(frames.status(), width=self.server.args.width, height=self.server.args.height,
                          requested_fps=(getattr(self.server.args, "preview_fps", None) or
                                         (min(self.server.args.fps, 8) if getattr(self.server.args, "relay_host", None)
                                          else self.server.args.fps)))
            body = json.dumps(status).encode()
            self.respond(200 if status["online"] else 503, "application/json", len(body))
            self.end_headers()
            self.wfile.write(body)
            return
        if route not in ("/stream.mjpg", "/snapshot.jpg"):
            self.send_error(404)
            return
        frame = frames.latest(timeout=0)
        if frame is None:
            self.send_error(503, "Camera unavailable or stale")
            return
        if route == "/snapshot.jpg":
            seq, jpeg, timestamp = frame
            self.respond(200, "image/jpeg", len(jpeg))
            self.send_header("X-Frame-Id", f"{frames.session_id}:{seq}")
            self.send_header("X-Frame-Received-At", timestamp)
            self.end_headers()
            self.wfile.write(jpeg)
            return
        if not self.server.viewers.acquire(blocking=False):
            self.send_error(503, "Too many viewers")
            return
        try:
            self.connection.settimeout(5)
            self.respond(200, "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            self.close_connection = True
            while frame is not None:
                seq, jpeg, timestamp = frame
                header = (f"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n"
                          f"X-Frame-Id: {frames.session_id}:{seq}\r\n"
                          f"X-Frame-Received-At: {timestamp}\r\n\r\n").encode()
                self.wfile.write(header + jpeg + b"\r\n")
                self.wfile.flush()
                frame = frames.latest(after=seq)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            self.server.viewers.release()


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="/dev/v4l/by-id/usb-Generic_USB2.0_PC_CAMERA-video-index0")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--quality", type=int, default=5)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--input-format", default="yuyv422", choices=("yuyv422", "mjpeg"))
    parser.add_argument("--relay-host", help="IP da estação-base para vídeo H.264/MPEG-TS")
    parser.add_argument("--relay-port", type=int, default=5000)
    parser.add_argument("--relay-transport", choices=("tcp", "udp"), default="udp")
    parser.add_argument("--preview-fps", type=int, help="Limita só o MJPEG da dashboard")
    parser.add_argument("--allowed-origin", action="append", default=["http://127.0.0.1:1880", "http://localhost:1880"])
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not (1 <= args.port <= 65535 and 1 <= args.fps <= 30 and 1 <= args.quality <= 31
            and 1 <= args.width <= 1920 and 1 <= args.height <= 1080):
        parser.error("Invalid port, frame rate, quality or frame size")
    if args.relay_host:
        if (args.width, args.height) != (640, 480) or not 1 <= args.relay_port <= 65535:
            parser.error("O relé requer 640x480 e uma porta UDP válida")
        try:
            competition_output(args.relay_host, args.relay_port, args.fps, args.relay_transport)
        except ValueError as exc:
            parser.error(str(exc))
    if args.preview_fps is not None and not 1 <= args.preview_fps <= args.fps:
        parser.error("O FPS do preview deve estar entre 1 e o FPS de captura")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    frames = FrameStore()
    capture = Capture(args, frames)
    server = CameraServer((args.host, args.port), args, frames)
    stopped = threading.Event()

    def shutdown(*_):
        if not stopped.is_set():
            stopped.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    capture.start()
    LOG.info("Camera HTTP on http://%s:%s/stream.mjpg", args.host, args.port)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        capture.stop()
        server.server_close()


if __name__ == "__main__":
    main()

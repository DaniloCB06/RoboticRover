import asyncio
import json
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

import paho.mqtt.client as mqtt
from paho.mqtt.subscribeoptions import SubscribeOptions
import pytest

from roboticrover_pi3.camera import JpegParser, build_parser, competition_output, ffmpeg_command
from roboticrover_pi3.competition import Arena, epoch_ms
from roboticrover_pi3.competition_video import TcpIngress, Whip, relay
from roboticrover_pi3.protocol import envelope
from vision.competition_detect import send_detection

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_COMPETITION_INTEGRATION") != "1",
                                                         reason="Teste opt-in com sockets locais")]
ROOT = Path(__file__).resolve().parents[1]


def free_port(kind=socket.SOCK_STREAM):
    with socket.socket(type=kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)


def start(stack, cmd, **kwargs):
    process = subprocess.Popen(cmd, **kwargs)
    stack.callback(stop, process)
    return process


def broker(stack):
    exe = shutil.which("mosquitto") or str(Path(sys.executable).with_name("mosquitto"))
    if not Path(exe).exists():
        pytest.skip("Mosquitto indisponível")
    port = free_port()
    process = start(stack, [exe, "-p", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        assert process.poll() is None
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=.1):
                return port
        except OSError:
            time.sleep(.02)
    pytest.fail("Mosquitto não abriu a porta temporária")


def monitor(stack, port, topics):
    inbox = queue.Queue()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.on_connect = lambda client, *_: client.subscribe([(topic, SubscribeOptions(qos=1, retainAsPublished=True))
                                                             for topic in topics])
    client.on_message = lambda _, __, msg: inbox.put(msg)
    client.connect("127.0.0.1", port, keepalive=5)
    client.loop_start()
    stack.callback(client.loop_stop)
    stack.callback(client.disconnect)
    return client, inbox


def await_message(inbox, topic, predicate=lambda _: True, timeout=6):
    until = time.monotonic() + timeout
    seen = []
    while time.monotonic() < until:
        try:
            msg = inbox.get(timeout=max(.001, until - time.monotonic()))
        except queue.Empty:
            break
        seen.append(msg.topic)
        if msg.topic == topic and predicate(msg.payload):
            return msg
    pytest.fail(f"Não recebeu {topic}; tópicos observados: {seen}")


def test_two_brokers_relay_commands_arena_state_and_last_will(tmp_path):
    with ExitStack() as stack:
        remote_port, local_port = broker(stack), broker(stack)
        env = dict(os.environ, PYTHONPATH=str(ROOT / "apps/rover"), COMPETITION_HOST="127.0.0.1",
                   COMPETITION_TEAM="rover04", COMPETITION_PASSWORD="test-only", COMPETITION_MOCK_BATTERY="1",
                   COMPETITION_MQTT_PORT=str(remote_port), COMPETITION_LOCAL_MQTT_PORT=str(local_port),
                   COMPETITION_TELEMETRY_DIR=str(tmp_path))
        judge, received = monitor(stack, remote_port, ["rover/rover04/#", "station/#", "rover/status"])
        station, local = monitor(stack, local_port, ["rover/#", "competition/arena/state"])
        judge.publish("arena/state", '{"round_id":19,"run":"RUNNING"}', qos=1, retain=True)
        start(stack, [sys.executable, "-m", "roboticrover_pi3.competition_station"], env=env)
        rover = start(stack, [sys.executable, "-m", "roboticrover_pi3.competition_rover"], env=env)
        online = await_message(received, "rover/rover04/status", lambda payload: payload == b"online")
        assert online.qos == 1 and online.retain
        await_message(received, "rover/rover04/state", lambda payload: json.loads(payload)["state"] == "IDLE")
        await_message(received, "rover/rover04/mode", lambda payload: json.loads(payload)["mode"] == "AUTONOMO")
        battery = await_message(received, "rover/rover04/battery")
        assert battery.qos == 0 and not battery.retain and json.loads(battery.payload)["v"] == 7.82
        await_message(local, "competition/arena/state", lambda payload: json.loads(payload)["round_id"] == 19)
        await_message(local, "rover/status", lambda payload: json.loads(payload)["data"]["online"])
        station.publish("station/heartbeat", envelope("heartbeat", {"online": True, "session_id": "local"}, True), qos=1)
        expires = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()
        def change_state(mode):
            command_id = str(uuid4())
            payload = envelope("mode_command", {"command_id": command_id, "mode": mode, "expires_at": expires}, True)
            station.publish("rover/cmd/modo", payload, qos=1)
            ack = await_message(local, "rover/cmd/ack", lambda payload: json.loads(payload)["data"]["command_id"] == command_id)
            assert json.loads(ack.payload)["data"]["accepted"]

        change_state("BUSCA")
        await_message(received, "rover/rover04/state", lambda payload: json.loads(payload)["state"] == "BUSCA")
        change_state("APROXIMACAO")
        change_state("AGUARDANDO_PEGA")
        send_detection(Arena("127.0.0.1", "rover04", "test-only", remote_port),
                       {"ts": epoch_ms(), "identification": "round19-tag3", "artifact": "cilindro", "conf": .87, "tag": 3})
        detection = await_message(received, "rover/rover04/detection")
        assert detection.qos == 1 and not detection.retain and json.loads(detection.payload)["tag"] == 3
        await_message(received, "rover/rover04/state", lambda payload: json.loads(payload)["state"] == "ARTEFATO_ENCONTRADO")
        for kind, fields in (("stop", {}), ("mode", {"mode": "MANUAL"}), ("vel", {"linear": .2, "angular": 0})):
            judge.publish(f"rover/rover04/cmd/{kind}", json.dumps({"ts": epoch_ms(), **fields}), qos=int(kind != "vel"))
        await_message(received, "rover/rover04/state", lambda payload: json.loads(payload)["state"] == "NAVEGACAO")
        await_message(received, "rover/rover04/state", lambda payload: json.loads(payload)["state"] == "IDLE", timeout=.6)
        rover.kill()
        rover.wait(timeout=3)
        last_will = await_message(received, "rover/rover04/status", lambda payload: payload == b"offline")
        assert last_will.retain and last_will.qos == 1
        await_message(local, "rover/status", lambda payload: not json.loads(payload)["data"]["online"])


@pytest.mark.parametrize("transport", ["tcp", "udp"])
def test_encoded_video_reaches_whip_peer(transport):
    aiortc = pytest.importorskip("aiortc")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("FFmpeg indisponível")

    async def scenario():
        loop = asyncio.get_running_loop()
        stop_relay = asyncio.Event()
        seen_frame = loop.create_future()
        peer = aiortc.RTCPeerConnection(aiortc.RTCConfiguration(iceServers=[]))
        deletes = []

        @peer.on("track")
        async def received(track):
            frames = [await track.recv() for _ in range(20)]
            seen_frame.set_result((frames[-1].width, frames[-1].height))

        async def answer(offer):
            await peer.setRemoteDescription(aiortc.RTCSessionDescription(sdp=offer, type="offer"))
            await peer.setLocalDescription(await peer.createAnswer())
            return peer.localDescription.sdp.encode()

        class Server(BaseHTTPRequestHandler):
            def do_POST(self):
                assert self.path == "/rover/rover04/whip"
                assert self.headers["Authorization"] == "Bearer rover04:test-only"
                assert self.headers["Content-Type"] == "application/sdp"
                offer = self.rfile.read(int(self.headers["Content-Length"])).decode()
                body = asyncio.run_coroutine_threadsafe(answer(offer), loop).result(timeout=8)
                self.send_response(201)
                self.send_header("Content-Type", "application/sdp")
                self.send_header("Location", "/rover/rover04/whip/test-session")
                self.end_headers()
                self.wfile.write(body)

            def do_DELETE(self):
                deletes.append(self.path)
                self.send_response(204)
                self.end_headers()

        with ExitStack() as stack:
            http = ThreadingHTTPServer(("127.0.0.1", 0), Server)
            stack.callback(http.server_close)
            Thread(target=lambda: http.serve_forever(poll_interval=.05), daemon=True).start()
            stack.callback(http.shutdown)
            video_port = free_port(socket.SOCK_STREAM if transport == "tcp" else socket.SOCK_DGRAM)
            command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i",
                       "testsrc2=size=640x480:rate=15"] + competition_output("127.0.0.1", video_port, 15, transport)
            source = f"{transport}://127.0.0.1:{video_port}"
            if transport == "tcp":
                source += "?listen=1&listen_timeout=3000&timeout=3000000"
            task = asyncio.create_task(relay(Whip(Arena("127.0.0.1", "rover04", "test-only"), http.server_port),
                                             source, stop_relay))
            await asyncio.sleep(.2)
            start(stack, command)
            try:
                done, _ = await asyncio.wait((task, seen_frame), return_when=asyncio.FIRST_COMPLETED, timeout=16)
                if task in done:
                    task.result()
                assert seen_frame.done() and seen_frame.result() == (640, 480)
            finally:
                stop_relay.set()
                await asyncio.wait_for(task, timeout=15)
                await peer.close()
            assert deletes == ["/rover/rover04/whip/test-session"]

    asyncio.run(scenario())


def test_competition_encoder_keeps_preview_and_contract_h264(tmp_path):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg/FFprobe indisponíveis")
    args = build_parser().parse_args(["--relay-host", "127.0.0.1", "--fps", "15"])
    camera = ffmpeg_command(args)
    outputs = camera[camera.index("-i") + 2:-1]
    clip = str(tmp_path / "camera.ts")
    synthetic = [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=15:duration=3"]
    capture = subprocess.run(synthetic + outputs + [clip], check=True, capture_output=True, timeout=15)
    assert len(JpegParser().feed(capture.stdout)) == 24
    probe = subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", clip], timeout=5)
    stream = json.loads(probe)["streams"][0]
    assert (stream["codec_name"], stream["profile"], stream["has_b_frames"]) == ("h264", "Constrained Baseline", 0)
    assert (stream["width"], stream["height"], stream["r_frame_rate"]) == (640, 480, "15/1")
    assert int(json.loads(probe)["format"]["bit_rate"]) <= 1_500_000
    h264 = subprocess.check_output([ffmpeg, "-v", "error", "-i", clip, "-c", "copy", "-f", "h264", "pipe:1"], timeout=5)
    nal_units = [part[0] & 31 for part in re.split(rb"\x00\x00(?:\x00)?\x01", h264) if part]
    pictures = [index for index, nal in enumerate(nal_units) if nal in (1, 5)]
    assert len(pictures) == 45
    assert [frame for frame, start in enumerate(pictures) if nal_units[start] == 5] == [0, 15, 30]
    for frame in (0, 15, 30):
        previous = pictures[frame - 1] if frame else 0
        assert {7, 8}.issubset(nal_units[previous:pictures[frame]])


def test_tcp_ingress_stays_open_and_reassembles_split_transport_packets():
    async def scenario():
        ingress = TcpIngress()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.setblocking(False)
            ingress.destination = receiver.getsockname()
            server = await asyncio.start_server(ingress.accept, "127.0.0.1", 0)
            try:
                async with server:
                    for _ in range(2):
                        _, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
                        writer.write(b"G" * 75)
                        await writer.drain()
                        await asyncio.sleep(.02)
                        writer.write(b"G" * (188 - 75))
                        await writer.drain()
                        packet = await asyncio.wait_for(asyncio.get_running_loop().sock_recv(receiver, 1316), 1)
                        assert packet == b"G" * 188
                        writer.close()
                        await writer.wait_closed()
            finally:
                await ingress.close()

    asyncio.run(scenario())

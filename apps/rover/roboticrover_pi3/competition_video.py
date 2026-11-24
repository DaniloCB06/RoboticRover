"""Ground station: relay encoded H.264 MPEG-TS packets over WHIP without re-encoding."""
from __future__ import annotations

import argparse
import asyncio
import base64
import logging
import re
import signal
import socket
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .competition import Arena, host_address, load_competition_env

LOG = logging.getLogger(__name__)
START_CODE = re.compile(rb"\x00\x00(?:\x00)?\x01")
MAX_QUEUE_AGE = 0.25


class TcpIngress:
    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.writer = None
        self.tasks = set()
        self.destination = None

    async def accept(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        if self.writer:
            self.writer.close()
        self.writer = writer
        pending = bytearray()
        LOG.info("Emissor TCP conectado: %s", writer.get_extra_info("peername"))
        try:
            while chunk := await reader.read(1316):
                pending.extend(chunk)
                while len(pending) >= 188:
                    size = min(1316, len(pending) // 188 * 188)
                    packet = bytes(pending[:size])
                    del pending[:size]
                    await asyncio.get_running_loop().sock_sendto(self.socket, packet, self.destination)
        except (OSError, ConnectionError):
            pass
        finally:
            writer.close()
            self.tasks.discard(task)
            if self.writer is writer:
                self.writer = None
            LOG.info("Emissor TCP desconectado; aguardando reconexão")

    async def close(self):
        if self.writer:
            self.writer.close()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.socket.close()


async def run_tcp(whip, host, port):
    ingress = TcpIngress()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as temporary:
        temporary.bind(("127.0.0.1", 0))
        udp_port = temporary.getsockname()[1]
    ingress.destination = ("127.0.0.1", udp_port)
    try:
        server = await asyncio.start_server(ingress.accept, host, port, limit=16384)
        async with server:
            LOG.info("Receptor TCP ativo em %s:%d; aguardando a câmera da Pi", host, port)
            await run(whip, f"udp://127.0.0.1:{udp_port}")
    finally:
        await ingress.close()


def h264_boundary(packet):
    if packet.is_corrupt or packet.pts is None:
        return False, False
    nals = {nal[0] & 31 for nal in START_CODE.split(bytes(packet))[1:] if nal}
    return bool(nals & {1, 5}), {5, 7, 8}.issubset(nals)


def open_input(source):
    import av

    options = {"probesize": "65536", "analyzeduration": "300000", "fflags": "+nobuffer"}
    if source.startswith("udp:"):
        options.update(buffer_size="65536", fifo_size="768", overrun_nonfatal="1", timeout="3000000")
    return av.open(source, format="mpegts", mode="r", timeout=(4, 3), options=options)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Whip:
    def __init__(self, arena, port=8889, basic=False, destination=None):
        self.url = destination or f"http://{host_address(arena.host)}:{port}/rover/{arena.team}/whip"
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.fragment:
            raise ValueError("O destino WHIP deve ser uma URL HTTP(S) válida")
        credentials = f"{arena.team}:{arena.password}"
        self.authorization = ("Basic " + base64.b64encode(credentials.encode()).decode() if basic
                              else "Bearer " + credentials)
        self.http = build_opener(NoRedirect())
        self.resource = None

    def offer(self, sdp):
        request = Request(self.url, data=sdp.encode("utf-8"), method="POST",
                          headers={"Authorization": self.authorization, "Content-Type": "application/sdp"})
        with self.http.open(request, timeout=8) as response:
            if response.status != 201 or not response.headers.get("Location"):
                raise ValueError("Resposta WHIP sem 201 e Location")
            resource = urljoin(self.url, response.headers["Location"])
            original, destination = urlsplit(self.url), urlsplit(resource)
            if (original.scheme, original.netloc) != (destination.scheme, destination.netloc):
                raise ValueError("Location WHIP fora do servidor configurado")
            self.resource = resource
            if response.headers.get_content_type() != "application/sdp":
                raise ValueError("Resposta WHIP sem application/sdp")
            answer = response.read(65537)
            if not answer or len(answer) > 65536:
                raise ValueError("SDP WHIP inválido")
            return answer.decode("utf-8")

    def close(self):
        if self.resource:
            request = Request(self.resource, method="DELETE", headers={"Authorization": self.authorization})
            self.resource = None
            try:
                with self.http.open(request, timeout=3):
                    pass
            except HTTPError as exc:
                if exc.code not in {404, 410}:
                    raise


async def relay(whip, source, stopped):
    import av
    from aiortc import MediaStreamTrack, RTCConfiguration, RTCPeerConnection, RTCRtpSender, RTCSessionDescription
    from aiortc.mediastreams import MediaStreamError

    class EncodedVideo(MediaStreamTrack):
        kind = "video"

        def __init__(self):
            super().__init__()
            self.queue = asyncio.Queue(maxsize=4)
            self.ended = asyncio.Event()
            self.need_keyframe = True
            self.output_needs_keyframe = True
            self.first_pts = None
            self.discarded = 0

        def clear(self):
            self.discarded += self.queue.qsize()
            while not self.queue.empty():
                self.queue.get_nowait()
            self.need_keyframe = self.output_needs_keyframe = True

        async def read(self, packets):
            try:
                while self.readyState == "live":
                    packet = await asyncio.to_thread(next, packets, None)
                    if packet is None or not packet.size:
                        break
                    valid, keyframe = h264_boundary(packet)
                    if not valid:
                        if packet.is_corrupt or packet.pts is None:
                            self.clear()
                            self.discarded += 1
                        continue
                    if self.queue.full():
                        self.clear()
                    if self.need_keyframe and not keyframe:
                        self.discarded += 1
                        continue
                    self.need_keyframe = False
                    self.queue.put_nowait((time.monotonic(), keyframe, packet))
            except av.FFmpegError as exc:
                LOG.warning("Entrada H.264 interrompida: %s", exc)
            finally:
                self.ended.set()

        async def recv(self):
            try:
                deadline = time.monotonic() + 3
                while self.readyState == "live" and not self.ended.is_set():
                    arrived, keyframe, packet = await asyncio.wait_for(self.queue.get(), deadline - time.monotonic())
                    stale = time.monotonic() - arrived > MAX_QUEUE_AGE
                    if stale:
                        self.output_needs_keyframe = True
                    if stale or (self.output_needs_keyframe and not keyframe):
                        self.discarded += 1
                        continue
                    self.output_needs_keyframe = False
                    if self.first_pts is None:
                        self.first_pts = packet.pts
                    packet.pts -= self.first_pts
                    return packet
                raise MediaStreamError
            except asyncio.TimeoutError:
                self.ended.set()
                raise MediaStreamError from None

    container = await asyncio.to_thread(open_input, source)
    stream = next(iter(container.streams.video), None)
    if stream is None or stream.codec_context.name != "h264":
        container.close()
        raise ValueError("A entrada MPEG-TS deve conter vídeo H.264")
    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    video = EncodedVideo()
    worker = asyncio.create_task(video.read(container.demux(stream)))
    failed = asyncio.Event()

    @peer.on("connectionstatechange")
    def connection_changed():
        if peer.connectionState in {"failed", "closed"}:
            failed.set()

    tasks = []
    try:
        transceiver = peer.addTransceiver(video, direction="sendonly")
        codecs = RTCRtpSender.getCapabilities("video").codecs
        transceiver.setCodecPreferences([codec for codec in codecs if codec.mimeType == "video/rtx" or
                                         (codec.mimeType == "video/H264" and
                                          codec.parameters.get("profile-level-id") == "42e01f")])
        await peer.setLocalDescription(await peer.createOffer())
        answer = await asyncio.to_thread(whip.offer, peer.localDescription.sdp)
        await peer.setRemoteDescription(RTCSessionDescription(sdp=answer, type="answer"))
        LOG.info("Sessão WHIP criada; aguardando conexão de mídia")
        tasks = [asyncio.create_task(event.wait()) for event in (failed, stopped, video.ended)]
        started = asyncio.get_running_loop().time()
        while not any(task.done() for task in tasks) and peer.connectionState != "connected":
            done, _ = await asyncio.wait(tasks, timeout=0.1, return_when=asyncio.FIRST_COMPLETED)
            if done:
                break
            if asyncio.get_running_loop().time() - started > 10:
                raise TimeoutError("Tempo limite para conectar mídia WebRTC")
        if peer.connectionState == "connected":
            LOG.info("H.264 ao vivo no servidor")
            while not any(task.done() for task in tasks):
                _, pending = await asyncio.wait(tasks, timeout=5, return_when=asyncio.FIRST_COMPLETED)
                if len(pending) == len(tasks):
                    inbound = [item for item in (await peer.getStats()).values() if item.type == "remote-inbound-rtp"]
                    if inbound:
                        item = inbound[0]
                        LOG.info("Vídeo: descartes na entrada=%d, RTP perdidos=%d, RTT=%s ms",
                                 video.discarded, item.packetsLost,
                                 round(item.roundTripTime * 1000) if item.roundTripTime is not None else "—")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        video.stop()
        await peer.close()
        await worker
        container.close()
        try:
            await asyncio.to_thread(whip.close)
        except OSError:
            LOG.warning("O servidor não confirmou o encerramento da sessão WHIP")


async def run(whip, source):
    from av.error import FFmpegError

    stopped = asyncio.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(signum, stopped.set)
    while not stopped.is_set():
        try:
            await relay(whip, source, stopped)
        except HTTPError as exc:
            LOG.warning("Servidor WHIP respondeu HTTP %s", exc.code)
        except (FFmpegError, OSError, ValueError, RuntimeError) as exc:
            LOG.warning("Relé indisponível: %s", exc)
        if not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass


def main():
    load_competition_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=5000)
    parser.add_argument("--transport", choices=("tcp", "udp"), default="udp")
    parser.add_argument("--whip-port", type=int, default=8889)
    parser.add_argument("--destination", help="Endpoint WHIP de entrada na estação-base")
    parser.add_argument("--basic", action="store_true")
    args = parser.parse_args()
    if not all(1 <= port <= 65535 for port in (args.listen_port, args.whip_port)):
        parser.error("Porta inválida")
    try:
        import aiortc
    except ImportError:
        parser.error("Instale a dependência do relé com pip install -e '.[competition-video]'")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aioice").setLevel(logging.WARNING)
    whip = Whip(Arena.from_env(), args.whip_port, args.basic, args.destination)
    if args.transport == "tcp":
        asyncio.run(run_tcp(whip, args.listen_host, args.listen_port))
        return
    source = f"{args.transport}://{host_address(args.listen_host)}:{args.listen_port}"
    asyncio.run(run(whip, source))


if __name__ == "__main__":
    main()

import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import pytest

from roboticrover_pi3.competition import Arena
from roboticrover_pi3.competition_forward import configuration
from roboticrover_pi3.competition_video import Whip, relay
from roboticrover_pi3.camera import competition_output


def test_forwarder_receives_and_forwards_only_the_team_path():
    arena = Arena("192.168.50.3", "rover04", "test-only")
    result = configuration(arena, "192.168.50.130")
    assert result["webrtcAdditionalHosts"] == ["192.168.50.130"]
    assert result["webrtcAddress"] == ":8890"
    assert result["webrtcLocalUDPAddress"] == ":8190"
    assert not any(result[name] for name in ("rtsp", "rtmp", "hls", "srt", "moq"))
    path = result["paths"]["rover/rover04"]
    assert path["forward"] == [{"dest": "whip://192.168.50.3:8889/rover/rover04/whip",
                                "whipBearerToken": "rover04:test-only"}]
    assert path["overridePublisher"] is False
    assert result["authInternalUsers"][0]["permissions"] == [{"action": "publish", "path": "rover/rover04"}]


def test_pi_can_publish_to_station_with_basic_authentication():
    whip = Whip(Arena("192.168.50.3", "rover04", "test-only"), basic=True,
                destination="http://192.168.50.130:8890/rover/rover04/whip")
    assert whip.url.startswith("http://192.168.50.130:8890/")
    assert whip.authorization == "Basic cm92ZXIwNDp0ZXN0LW9ubHk="


@pytest.mark.parametrize("url", ["file:///tmp/test", "http://user:password@station/whip", "https:///whip"])
def test_pi_rejects_invalid_whip_destination(url):
    with pytest.raises(ValueError):
        Whip(Arena("192.168.50.3", "rover04", "test-only"), destination=url)


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_COMPETITION_INTEGRATION") != "1", reason="WebRTC nativo opt-in")
def test_station_forwards_encoded_h264_to_second_whip_server(tmp_path):
    aiortc = pytest.importorskip("aiortc")
    from test_competition_integration import free_port, start

    binary = Path(__file__).resolve().parents[1] / ".runtime/mediamtx-v1.21.4/mediamtx"
    if not binary.is_file() or not shutil.which("ffmpeg"):
        pytest.skip("MediaMTX nativo e FFmpeg necessários")

    async def scenario():
        import socket

        http_a, http_b = free_port(), free_port()
        media_a, media_b = free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_DGRAM)
        input_port = free_port(socket.SOCK_DGRAM)
        arena = Arena("127.0.0.1", "rover04", "test-only")
        station = configuration(arena, "127.0.0.1", http_a, media_a)
        endpoint = f"http://127.0.0.1:{http_b}/rover/rover04/whip"
        station["paths"]["rover/rover04"]["forward"][0]["dest"] = endpoint.replace("http://", "whip://")
        professor = configuration(arena, "127.0.0.1", http_b, media_b)
        professor["paths"]["rover/rover04"]["forward"] = []
        professor["authInternalUsers"] = [{"user": "any", "permissions": [
            {"action": "publish", "path": "rover/rover04"}, {"action": "read", "path": "rover/rover04"}]}]
        stopped = asyncio.Event()
        peer = aiortc.RTCPeerConnection(aiortc.RTCConfiguration(iceServers=[]))
        received = asyncio.Event()
        sizes = []
        session = None

        @peer.on("track")
        async def consume(track):
            for _ in range(20):
                frame = await track.recv()
                sizes.append((frame.width, frame.height))
            received.set()

        with ExitStack() as stack:
            for name, config in (("station", station), ("professor", professor)):
                file = tmp_path / (name + ".json")
                file.write_text(json.dumps(config))
                log = stack.enter_context((tmp_path / (name + ".log")).open("w"))
                start(stack, [str(binary), str(file)], stdout=log, stderr=log)
            await asyncio.sleep(.5)
            source = f"udp://127.0.0.1:{input_port}"
            publishing = asyncio.create_task(relay(Whip(arena, basic=True,
                destination=f"http://127.0.0.1:{http_a}/rover/rover04/whip"), source, stopped))
            start(stack, ["ffmpeg", "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i",
                          "testsrc2=size=640x480:rate=15"] + competition_output("127.0.0.1", input_port, 15))
            try:
                transceiver = peer.addTransceiver("video", direction="recvonly")
                transceiver.setCodecPreferences([codec for codec in aiortc.RTCRtpReceiver.getCapabilities("video").codecs
                                                 if codec.mimeType in ("video/H264", "video/rtx")])
                await peer.setLocalDescription(await peer.createOffer())
                url = f"http://127.0.0.1:{http_b}/rover/rover04/whep"
                for attempt in range(20):
                    if publishing.done():
                        publishing.result()
                    try:
                        response = await asyncio.to_thread(urlopen, Request(url, data=peer.localDescription.sdp.encode(),
                            headers={"Content-Type": "application/sdp"}, method="POST"), None, 2)
                        break
                    except OSError:
                        if attempt == 19:
                            raise
                        await asyncio.sleep(.25)
                with response:
                    session = urljoin(url, response.headers["Location"])
                    await peer.setRemoteDescription(aiortc.RTCSessionDescription(type="answer", sdp=response.read().decode()))
                await asyncio.wait_for(received.wait(), 8)
                assert len(sizes) == 20 and set(sizes) == {(640, 480)}
            finally:
                await peer.close()
                if session:
                    try:
                        await asyncio.to_thread(urlopen, Request(session, method="DELETE"), None, 2)
                    except OSError:
                        pass
                stopped.set()
                await asyncio.wait_for(publishing, 10)

    asyncio.run(scenario())

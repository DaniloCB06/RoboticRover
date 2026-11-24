"""Station: receive WHIP, serve local WHEP and forward encoded H.264 to the arena."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .competition import Arena, host_address, load_competition_env

ROOT = Path(__file__).resolve().parents[3]
VERSION = "1.21.4"


def configuration(arena, station_host, http_port=8890, media_port=8190, *, forward=True):
    host_address(station_host)
    return {
        "logLevel": "info", "rtsp": False, "rtmp": False, "hls": False, "srt": False,
        "moq": False, "playback": False,
        "webrtc": True, "webrtcAddress": f":{http_port}",
        "webrtcLocalUDPAddress": f":{media_port}", "webrtcIPsFromInterfaces": False,
        "webrtcAdditionalHosts": [station_host], "webrtcICEServers2": [],
        "authMethod": "internal", "authInternalUsers": [
            {"user": arena.team, "pass": arena.password, "ips": [],
             "permissions": [{"action": "publish", "path": f"rover/{arena.team}"}]},
            {"user": "any", "pass": "", "ips": [],
             "permissions": [{"action": "read", "path": f"rover/{arena.team}"}]},
        ],
        "paths": {f"rover/{arena.team}": {
            "source": "publisher", "overridePublisher": False,
            "forward": [{"dest": f"whip://{host_address(arena.host)}:8889/rover/{arena.team}/whip",
                         "whipBearerToken": f"{arena.team}:{arena.password}"}] if forward else [],
        }},
    }


def main():
    load_competition_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="IP do Mac acessível pela Pi")
    parser.add_argument("--http-port", type=int, default=8890)
    parser.add_argument("--media-port", type=int, default=8190)
    parser.add_argument("--local-only", action="store_true", help="Vídeo local sem tentar encaminhar ao professor")
    parser.add_argument("--binary", type=Path, default=ROOT / f".runtime/mediamtx-v{VERSION}/mediamtx")
    args = parser.parse_args()
    if not all(1 <= port <= 65535 for port in (args.http_port, args.media_port)):
        parser.error("Porta inválida")
    if not args.binary.is_file():
        parser.error(f"Instale o binário MediaMTX v{VERSION} em {args.binary}")
    arena = Arena.from_env()
    config = configuration(arena, args.host, args.http_port, args.media_port, forward=not args.local_only)
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    target = runtime / "competition-forward.json"
    descriptor = os.open(target, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(config, handle)
    print(f"WHIP da Pi: http://{args.host}:{args.http_port}/rover/{arena.team}/whip", flush=True)
    print(f"WHEP local: http://127.0.0.1:{args.http_port}/rover/{arena.team}/whep", flush=True)
    os.execv(str(args.binary.resolve()), [str(args.binary.resolve()), str(target)])


if __name__ == "__main__":
    main()

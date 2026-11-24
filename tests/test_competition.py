import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from roboticrover_pi3.camera import build_parser, ffmpeg_command
from roboticrover_pi3.competition import Arena, command, epoch_ms
from roboticrover_pi3.competition_rover import CompetitionRover
from vision.competition_detect import LABELS, confirm, write_detection


@pytest.fixture
def arena():
    return Arena("127.0.0.1", "rover04", "test-only", 21883)


@pytest.fixture
def rover(arena, tmp_path):
    agent = CompetitionRover(arena, tmp_path)
    agent._client.publish = Mock(return_value=SimpleNamespace(rc=0))
    agent._connected.set()
    return agent


@pytest.mark.parametrize("kind,value", [
    ("vel", {"linear": True, "angular": 0}),
    ("vel", {"linear": 0, "angular": 1.01}),
    ("vel", {"linear": float("nan"), "angular": 0}),
    ("mode", {"mode": ["MANUAL"]}),
    ("arm", {"joints": [False]}),
    ("arm", {"joints": [361]}),
    ("gripper", {"action": "invalid"}),
])
def test_invalid_reference_commands_are_rejected(kind, value):
    with pytest.raises(ValueError):
        command(kind, {"ts": 10000, **value}, 10000)


def test_drive_only_after_stop_and_manual_with_fresh_nonretained_velocity(rover, arena):
    now = epoch_ms()

    def receive(kind, retained=False, ts=now, **fields):
        rover._on_message(None, None, SimpleNamespace(topic=arena.topic("cmd/" + kind), retain=retained,
                                                       payload=json.dumps({"ts": ts, **fields}).encode()))

    receive("mode", mode="MANUAL")
    assert rover.controller.state == "SEGURO_ESPERA"
    receive("stop")
    receive("mode", ts=now + 1, mode="MANUAL")
    assert rover.controller.state == "CAPTURA_MANUAL"
    receive("vel", retained=True, linear=0.4, angular=0)
    receive("vel", ts=now - 1000, linear=0.4, angular=0)
    assert rover.velocity == (0, 0)
    receive("vel", linear=0.4, angular=0)
    assert rover.velocity == (0.4, 0)
    assert rover.velocity_until - time.monotonic() <= 0.45
    assert rover.published["mode"] == {"mode": "MANUAL"}
    assert rover.published["state"] == {"state": "NAVEGACAO"}
    rover._tick(rover.velocity_until)
    assert rover.velocity == (0, 0)
    assert rover.published["state"] == {"state": "IDLE"}
    receive("arm", joints=[20, 30])
    receive("gripper", action="close")
    assert rover.joints == ((20, 30), None) and rover.gripper == "close"
    receive("vel", ts=now + 2, linear=0.2, angular=0)
    rover._on_disconnect(None, None, None, "test", None)
    assert rover.velocity == (0, 0) and rover.controller.state == "SEGURO_ESPERA"


def test_contract_telemetry_uses_qos_retain_and_fresh_measurements(rover, arena, tmp_path):
    now = epoch_ms()
    rover.controller.state = "AGUARDANDO_PEGA"
    write_detection(tmp_path / "detection.json", {"ts": now, "identification": "round9-tag4",
                                                        "artifact": "cilindro", "conf": 0.87, "tag": 4})
    write_detection(tmp_path / "mission.json", {"tags": [{"id": 4, "status": "ENCONTRADA"}]})
    write_detection(tmp_path / "battery.json", {"ts": now, "v": 7.82, "pct": 71.0, "i": 1.3})
    rover._detection(now)
    rover._detection(now + 40)
    rover._mission()
    rover._mission()
    rover._battery(now)
    rover._report_state()
    sent = {key: [] for key in ("detection", "mission", "battery", "state")}
    for call in rover._client.publish.call_args_list:
        topic, payload = call.args
        suffix = topic.removeprefix(arena.topic(""))
        if suffix in sent:
            sent[suffix].append((json.loads(payload), call.kwargs))
    assert sent["detection"] == [({"ts": now, "artifact": "cilindro", "conf": 0.87, "tag": 4},
                                  {"qos": 1, "retain": False})]
    assert sent["battery"] == [({"ts": now, "v": 7.82, "pct": 71.0, "i": 1.3}, {"qos": 0, "retain": False})]
    assert len(sent["mission"]) == 1 and sent["mission"][0][1] == {"qos": 1, "retain": True}
    assert sent["state"][0][0]["state"] == "ARTEFATO_ENCONTRADO"
    with pytest.raises(ValueError, match="timestamp"):
        rover._battery(now + 2001)


def test_yolo_confirm_requires_distinct_unambiguous_frames(monkeypatch):
    monkeypatch.setattr("vision.competition_detect.time.sleep", lambda *_: None)
    frames = iter([("a", b"first"), ("a", b"first"), ("b", b"second"), ("c", b"third")])
    assert confirm(lambda: next(frames), lambda jpeg: [("cilindro_com_base", 0.9)], LABELS, .6) == ("cilindro", .9)
    frames = iter((str(index), b"frame") for index in range(9))
    with pytest.raises(ValueError, match="não confirmou"):
        confirm(lambda: next(frames), lambda jpeg: [("argola_grande", .8), ("helice", .8)], LABELS, .6)


def test_camera_encodes_jpeg_and_h264_from_the_same_capture():
    args = build_parser().parse_args(["--relay-host", "192.168.1.2", "--fps", "15"])
    values = ffmpeg_command(args)
    assert values.count("-i") == 1
    assert values.index("pipe:1") < values.index("libx264")
    assert values[-1] == "udp://192.168.1.2:5000?pkt_size=1316"

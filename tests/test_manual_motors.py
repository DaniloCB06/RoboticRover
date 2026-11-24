"""Nenhum teste abre USB. O Mega virtual usa o núcleo C++ real do firmware."""
import json
from pathlib import Path
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from roboticrover_pi3.config import Config
from roboticrover_pi3.main import RoverMqtt
from roboticrover_pi3.motors import MotorConfig, MotorError, SerialMotors, frame, parse_frame
from roboticrover_pi3.protocol import envelope

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def firmware_binary(tmp_path_factory):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        pytest.skip("Compilador C++ necessário para verificar o núcleo real do firmware")
    target = tmp_path_factory.mktemp("mega-virtual") / "firmware"
    subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I",
                    str(ROOT / "firmware/arduino-mega/rover_manual"),
                    str(ROOT / "tests/motor_firmware_harness.cpp"), "-o", str(target)],
                   check=True, capture_output=True, text=True)
    return target


@pytest.mark.parametrize("driver", [1, 2])
def test_complete_sketch_parser_output_pins_and_independent_watchdog(tmp_path, driver):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        pytest.skip("Compilador C++ indisponível")
    binary = tmp_path / "sketch"
    subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror", f"-DROVER_DRIVER={driver}",
                    "-I", str(ROOT / "tests/firmware_stub"), str(ROOT / "tests/motor_sketch_harness.cpp"),
                    "-o", str(binary)], check=True, capture_output=True, text=True)
    subprocess.run([str(binary)], check=True, timeout=3)


def test_default_motor_backend_does_not_open_serial(monkeypatch):
    monkeypatch.delenv("MOTOR_BACKEND", raising=False)
    from roboticrover_pi3.motors import configured_motors
    assert configured_motors() is None


def test_arena_reference_commands_cannot_bypass_dashboard_manual_gate(motors, channel, tmp_path):
    from roboticrover_pi3.competition import Arena
    from roboticrover_pi3.competition_rover import CompetitionRover
    rover = CompetitionRover(Arena("127.0.0.1", "rover04", "test-only"), tmp_path, motors=motors)
    for kind, value in [("stop", None), ("mode", "MANUAL"), ("vel", (1, 0))]:
        rover._reference_command(kind, value, 0)
    assert not rover.controller.manual_authorized
    assert not any(p[2] == "WHEELS" for p in channel.sent)


class VirtualSerial:
    def __init__(self, binary):
        self.process = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.pending = bytearray()
        self.sent = []
        self.broken = self.corrupt = self.closed = False
        self.now = int(time.monotonic() * 1000) & 0xFFFFFFFF

    def request(self, packet):
        self.process.stdin.write(f"{self.now} {packet}")
        self.process.stdin.flush()
        return self.process.stdout.readline()

    def write(self, packet):
        self.sent.append(parse_frame(packet))
        if self.broken:
            raise OSError("USB disconnected")
        response = self.request(packet.decode()).encode()
        if self.corrupt:
            response = response.replace(b"ACK", b"BAD")
        self.pending.extend(response)
        return len(packet)

    def read(self, count):
        if not self.pending:
            time.sleep(.001)
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def reset_input_buffer(self):
        self.pending.clear()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.process.stdin.close()
        self.process.wait(timeout=2)


@pytest.fixture
def channel(firmware_binary):
    serial = VirtualSerial(firmware_binary)
    yield serial
    serial.close()


@pytest.fixture
def motors(channel):
    config = MotorConfig(backend="serial", port="/dev/test-mega", reset_delay=0, ack_timeout=.03)
    motor = SerialMotors(config, serial_factory=lambda *a, **kw: channel)
    motor.start()
    yield motor
    if motor.serial:
        motor.close()


def test_crc_reference_and_framing_corruption():
    packet = frame(123, 2, "WHEELS", -80, 80, 300)
    assert parse_frame(packet) == (123, 2, "WHEELS", -80, 80, 300)
    for bad in (packet[:-1], packet.replace(b"-80", b"-90"), b"garbage\n", b"A" * 129 + b"\n"):
        with pytest.raises(ValueError):
            parse_frame(bad)


@pytest.mark.parametrize("kwargs", [{"backend": "gpio"}, {"backend": "serial"}, {"pwm": 121},
                                    {"lease_ms": 501}, {"ack_timeout": float("nan")}, {"reset_delay": -1}])
def test_motor_configuration_rejects_unsafe_settings(kwargs):
    with pytest.raises(ValueError):
        MotorConfig(**kwargs)


def test_handshake_is_disarmed_and_each_direction_maps_to_two_wheels(motors, channel):
    assert [p[2] for p in channel.sent] == ["HELLO", "DISARM"]
    assert not motors.armed
    for action, expected in [("AVANCAR", (80, 80)), ("RECUAR", (-80, -80)),
                             ("ESQUERDA", (-80, 80)), ("DIREITA", (80, -80))]:
        motors.move(action, 500)
        wheel = next(p for p in reversed(channel.sent) if p[2] == "WHEELS")
        assert wheel[3:5] == expected
        assert 1 <= wheel[5] <= 300
        assert motors.armed
    motors.stop()
    assert not motors.armed and motors.left == motors.right == 0


def test_host_expiry_disarms_without_renewing_wheels(motors, channel):
    motors.move("AVANCAR", 200)
    count = sum(p[2] == "WHEELS" for p in channel.sent)
    assert motors.tick(motors.deadline + .001)
    assert not motors.armed
    assert sum(p[2] == "WHEELS" for p in channel.sent) == count


def test_firmware_watchdog_stops_independently_of_python(motors, channel):
    motors.move("AVANCAR", 200)
    channel.now = (channel.now + 201) & 0xFFFFFFFF
    assert channel.request("TICK\n").strip() == "0,0,0"
    motors.armed = True
    with pytest.raises(MotorError):
        motors.move("AVANCAR", 200)


def test_firmware_watchdog_handles_millis_rollover(channel):
    channel.now = 0xFFFFFFF0
    for seq, op, a, b, ttl in [(1, "HELLO", 0, 0, 0), (2, "ARM", 0, 0, 0), (3, "WHEELS", 80, 80, 100)]:
        assert parse_frame(channel.request(frame(1, seq, op, a, b, ttl).decode()).encode())[2] == "ACK"
    channel.now = 0x80
    assert channel.request("TICK\n").strip() == "0,0,0"


def test_firmware_rejects_bad_crc_old_sequence_stale_session_and_pwm_limit(channel):
    def send(seq, op, a=0, b=0, ttl=0, session=1):
        return parse_frame(channel.request(frame(session, seq, op, a, b, ttl).decode()).encode())
    assert send(1, "WHEELS", 80, 80, 300)[2] == "NACK"
    send(2, "HELLO")
    send(3, "ARM")
    assert send(4, "WHEELS", 80, 80, 300)[2] == "ACK"
    assert send(4, "WHEELS", 80, 80, 300)[2] == "NACK"
    assert send(5, "WHEELS", 80, 80, 300, session=2)[2] == "NACK"
    assert send(5, "WHEELS", 121, 80, 300)[2] == "NACK"
    assert channel.request("TICK\n").strip() == "0,0,0"
    send(6, "ARM")
    send(7, "WHEELS", 80, 80, 300)
    bad = frame(1, 8, "WHEELS", 80, 80, 300).replace(b"WHEELS", b"wHEELS")
    assert channel.request(bad.decode()).strip() == "INVALID"
    assert channel.request("TICK\n").strip() == "0,0,0"


@pytest.mark.parametrize("kind", ["broken", "corrupt"])
def test_usb_failure_or_missing_valid_ack_latches_fault(motors, channel, kind):
    setattr(channel, kind, True)
    with pytest.raises(MotorError):
        motors.move("AVANCAR", 200)
    assert motors.fault and not motors.armed and motors.serial is None
    count = len(channel.sent)
    with pytest.raises(MotorError):
        motors.move("AVANCAR", 200)
    assert len(channel.sent) == count


@pytest.fixture
def service(motors):
    agent = RoverMqtt(Config("127.0.0.1", 1883, "test", None, None, 5, False), motors=motors)
    agent._client.publish = Mock(return_value=SimpleNamespace(rc=0))
    agent._on_connect(agent._client, None, None, SimpleNamespace(is_failure=False), None)
    send(agent, "heartbeat", {"online": True, "session_id": str(uuid4())})
    return agent


def send(agent, kind, fields, *, retained=False, command_id=None, source="station-nodered", age=0):
    data = dict(fields)
    if kind != "heartbeat":
        data.update(command_id=command_id or str(uuid4()), expires_at=(datetime.now(timezone.utc) + timedelta(seconds=2 - age)).isoformat())
    topic = {"heartbeat": "station/heartbeat", "manual_command": "rover/cmd/manual", "mode_command": "rover/cmd/modo"}[kind]
    agent._handle_internal(topic, envelope(kind, data, True, source=source).encode(), retained)
    return data["command_id"] if kind != "heartbeat" else None


def manual(agent, action, **kw):
    return send(agent, "manual_command", {"action": action, "duration_ms": 500, **kw})


def authorize(agent):
    manual(agent, "PARAR", take_control=True)
    send(agent, "mode_command", {"mode": "CAPTURA_MANUAL", "operator_override": True})


def ack(agent):
    return next(json.loads(call.args[1]) for call in reversed(agent._client.publish.call_args_list)
                if call.args[0] == "rover/cmd/ack")


def test_dashboard_envelope_to_real_cpp_firmware_and_correlated_mega_ack(service, channel):
    manual(service, "AVANCAR")
    assert not ack(service)["data"]["accepted"]
    assert not any(p[2] == "WHEELS" for p in channel.sent)
    authorize(service)
    command_id = manual(service, "AVANCAR", target="rover")
    result = ack(service)
    assert result["data"]["command_id"] == command_id
    assert result["data"]["execution"] == "mega_accepted"
    assert result["simulated"] is False
    assert service.motors.left == service.motors.right == 80
    assert channel.request("TICK\n").strip() == "80,80,1"
    manual(service, "PARAR")
    assert channel.request("TICK\n").strip() == "0,0,0"


def test_duplicates_retained_expired_and_wrong_source_never_reexecute_wheels(service, channel):
    authorize(service)
    ident = manual(service, "AVANCAR")
    count = sum(p[2] == "WHEELS" for p in channel.sent)
    for options in ({"command_id": ident}, {"retained": True}, {"age": 3}, {"source": "other-client"}):
        send(service, "manual_command", {"action": "AVANCAR", "duration_ms": 500}, **options)
    assert sum(p[2] == "WHEELS" for p in channel.sent) == count


def test_backlogged_direction_is_rejected_even_with_legacy_long_ttl(service, channel):
    authorize(service)
    body = json.loads(envelope("manual_command", {
        "command_id": str(uuid4()), "action": "AVANCAR", "duration_ms": 500,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat(),
    }, True, source="station-nodered"))
    body["timestamp"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    service._handle_internal("rover/cmd/manual", json.dumps(body).encode(), False)
    assert ack(service)["data"]["reason"] == "command_expired_before_serial"
    assert not any(p[2] == "WHEELS" for p in channel.sent)


@pytest.mark.parametrize("cause", ["disconnect", "heartbeat", "session", "mode", "arm", "shutdown", "usb"])
def test_interlocks_stop_and_disarm_motors(service, channel, cause):
    authorize(service)
    manual(service, "AVANCAR")
    if cause == "disconnect":
        service._on_disconnect(None, None, None, "test", None)
    elif cause == "heartbeat":
        service._watchdog(time.monotonic() + 5)
    elif cause == "session":
        send(service, "heartbeat", {"online": True, "session_id": str(uuid4())})
    elif cause == "mode":
        send(service, "mode_command", {"mode": "BUSCA"})
    elif cause == "arm":
        manual(service, "SUBIR", target="manipulator")
        assert ack(service)["data"]["reason"] == "manipulator_not_implemented"
    elif cause == "shutdown":
        service._client.disconnect = Mock()
        service._client.loop_stop = Mock()
        service._client.publish.return_value.wait_for_publish = Mock()
        service.shutdown()
    else:
        channel.broken = True
        manual(service, "AVANCAR")
        assert ack(service)["data"]["execution"] == "failed"
        assert not service.controller.manual_authorized
    assert service.motors.left == service.motors.right == 0
    assert not service.motors.armed


@pytest.mark.integration
@pytest.mark.skipif(__import__("os").getenv("RUN_MOTOR_INTEGRATION") != "1",
                    reason="Opt-in: Mosquitto e Node-RED reais com Mega virtual")
def test_dashboard_http_mqtt_pi_and_mega_round_trip(motors, channel, tmp_path):
    import os
    import queue
    import socket
    import threading
    from urllib.request import Request, urlopen
    import paho.mqtt.client as mqtt

    mosquitto = ROOT / ".venv/bin/mosquitto"
    node_red = shutil.which("node-red")
    if not mosquitto.exists() or not node_red:
        pytest.skip("Mosquitto e Node-RED necessários")
    def free_port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]
    mqtt_port, http_port = free_port(), free_port()
    config = tmp_path / "mosquitto.conf"
    config.write_text(f"listener {mqtt_port} 127.0.0.1\nallow_anonymous true\npersistence false\n")
    flows = tmp_path / "flows.json"
    nodes = json.loads((ROOT / "apps/station/node-red/flows.json").read_text())
    for node in nodes:
        if node["type"] == "mqtt-broker":
            node.update(broker="127.0.0.1", port=str(mqtt_port), clientid="motor-test-station")
    flows.write_text(json.dumps(nodes))
    env = dict(os.environ, MQTT_HOST="127.0.0.1", MQTT_PORT=str(mqtt_port),
               PORT=str(http_port), NODE_RED_HOST="127.0.0.1", STATION_SOURCE="station-nodered")
    processes = []
    logs = []
    agent = None
    thread = None
    observer = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="motor-test-observer", protocol=mqtt.MQTTv5)
    records = queue.Queue()
    subscribed = threading.Event()
    observer.on_connect = lambda client, *_: client.subscribe("rover/cmd/ack", qos=1)
    observer.on_subscribe = lambda *_: subscribed.set()
    observer.on_message = lambda _, __, message: records.put(json.loads(message.payload))
    try:
        for name, command in [
            ("broker", [str(mosquitto), "-c", str(config)]),
            ("node-red", [node_red, "--userDir", str(tmp_path / "node-red"), "--settings",
                          str(ROOT / "apps/station/node-red/settings.js"), str(flows)]),
        ]:
            log = (tmp_path / (name + ".log")).open("w")
            logs.append(log)
            processes.append(subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT))
        deadline = time.monotonic() + 15
        while True:
            try:
                with urlopen(f"http://127.0.0.1:{http_port}/api/rover/snapshot", timeout=.5):
                    break
            except OSError:
                assert time.monotonic() < deadline, "Node-RED não abriu a API"
                time.sleep(.05)
        observer.connect("127.0.0.1", mqtt_port, 5)
        observer.loop_start()
        assert subscribed.wait(3)
        agent = RoverMqtt(Config("127.0.0.1", mqtt_port, "motor-test-pi", None, None, 5, False), motors=motors)
        thread = threading.Thread(target=agent.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while agent.controller.last_heartbeat is None:
            assert time.monotonic() < deadline
            time.sleep(.01)

        def dashboard(body):
            ident = str(uuid4())
            request = Request(f"http://127.0.0.1:{http_port}/api/rover/command",
                              data=json.dumps(dict(body, command_id=ident)).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=2) as response:
                assert response.status in (200, 202)
            deadline = time.monotonic() + 3
            while True:
                result = records.get(timeout=max(.01, deadline - time.monotonic()))
                if result["data"]["command_id"] == ident:
                    return result["data"]

        assert not dashboard({"kind": "manual", "action": "AVANCAR"})["accepted"]
        assert dashboard({"kind": "manual", "action": "PARAR", "take_control": True})["accepted"]
        assert dashboard({"kind": "mode", "mode": "CAPTURA_MANUAL", "operator_override": True})["accepted"]
        result = dashboard({"kind": "manual", "action": "AVANCAR", "target": "rover", "duration_ms": 500})
        assert result["execution"] == "mega_accepted" and result["accepted"]
        with agent._lock:
            assert channel.request("TICK\n").strip() == "80,80,1"
        assert dashboard({"kind": "manual", "action": "PARAR"})["execution"] == "mega_accepted"
        with agent._lock:
            assert channel.request("TICK\n").strip() == "0,0,0"
    finally:
        if agent:
            agent._stop.set()
        if thread:
            thread.join(timeout=3)
        observer.disconnect()
        observer.loop_stop()
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()

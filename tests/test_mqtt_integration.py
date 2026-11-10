"""Testes optativos contra Mosquitto e Node-RED reais em uma estação dedicada."""
from contextlib import closing
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
from uuid import uuid4

import paho.mqtt.client as mqtt
import pytest
import websocket

from rover.contracts import envelope, timestamp, utc_now, validate
from rover.config import Config
from rover.mqtt_client import RoverMQTT

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("RUN_MQTT_INTEGRATION") != "1", reason="Requer RUN_MQTT_INTEGRATION=1 e stack local")]
ROOT = Path(__file__).resolve().parents[1]
NODE_RED_URL = os.getenv("NODE_RED_URL", "http://127.0.0.1:1880").rstrip("/")


class Wire:
    def __init__(self):
        self.records = []
        self.condition = threading.Condition()
        self.ready = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="test-observer-" + uuid4().hex[:8], protocol=mqtt.MQTTv5)
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = lambda *_: self.ready.set()
        self.client.on_message = self.on_message
        if os.getenv("MQTT_USERNAME"):
            self.client.username_pw_set(os.environ["MQTT_USERNAME"], os.getenv("MQTT_PASSWORD"))
        if os.getenv("MQTT_CA_FILE"):
            self.client.tls_set(os.environ["MQTT_CA_FILE"])

    def on_connect(self, client, userdata, flags, reason_code, properties):
        assert not reason_code.is_failure
        client.subscribe([("rover/#", 1), ("station/heartbeat", 1)])

    def on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload)
        except (ValueError, UnicodeError):
            return
        with self.condition:
            self.records.append((message.topic, payload, message.retain))
            self.condition.notify_all()

    def wait(self, topic, predicate=lambda _: True, after=0, timeout=8):
        def find():
            return next((record for record in self.records[after:]
                         if record[0] == topic and predicate(record[1])), None)
        with self.condition:
            assert self.condition.wait_for(lambda: find() is not None, timeout), (
                topic, "Mensagem esperada não chegou", self.records[after:][-5:])
            return find()[1]

    def send(self, message, topic="rover/cmd/modo", retain=False, expected_source=None):
        after = len(self.records)
        self.client.publish(topic, json.dumps(message), qos=1, retain=retain).wait_for_publish(3)
        return self.wait("rover/cmd/ack", lambda p: (
            p["data"]["command_id"] == message["data"]["command_id"] and
            (expected_source is None or p["source"] == expected_source)), after)


def make_command(value="BUSCA", topic="rover/cmd/modo", source=None):
    now = utc_now()
    data = {"command_id": str(uuid4()), "expires_at": timestamp(now + timedelta(seconds=5))}
    if topic.endswith("modo"):
        data["mode"] = value
    else:
        data.update(action=value, duration_ms=500)
    return envelope(topic, source or os.getenv("STATION_SOURCE", "station-nodered"), data, now)


@pytest.fixture
def wire():
    wire = Wire()
    wire.client.connect(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")), 5)
    wire.client.loop_start()
    try:
        assert wire.ready.wait(5), "Assinatura MQTT não confirmada"
        wire.wait("station/heartbeat")
        yield wire
    finally:
        # Remove qualquer comando retained intencionalmente injetado pelo teste.
        for topic in ("rover/cmd/modo", "rover/cmd/manual"):
            wire.client.publish(topic, b"", qos=1, retain=True).wait_for_publish(3)
        wire.client.disconnect()
        wire.client.loop_stop()


@pytest.fixture
def simulator(wire, tmp_path):
    processes = []
    logs = []

    def start(*args, station_source=None):
        env = os.environ.copy()
        client_id = "rover-integration-" + uuid4().hex[:8]
        env.update(MQTT_CLIENT_ID=client_id, TELEMETRY_INTERVAL="0.2", HEARTBEAT_TIMEOUT="4")
        if station_source:
            env["STATION_SOURCE"] = station_source
        output = (tmp_path / (client_id + ".log")).open("w", encoding="utf-8")
        logs.append(output)
        process = subprocess.Popen([sys.executable, "-m", "rover", "--env-file",
                                    str(tmp_path / "absent.env"), *args], cwd=ROOT, env=env,
                                   stdout=output, stderr=subprocess.STDOUT)
        processes.append(process)
        wire.wait("rover/status", lambda p: p["source"] == client_id and p["data"]["online"])
        wire.wait("station/heartbeat", after=len(wire.records))
        return process, client_id

    yield start
    for process in processes:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(5)
    for output in logs:
        output.close()


def inject(name):
    request = Request(NODE_RED_URL + "/inject/inject-" + name.lower(), data=b"{}",
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        assert response.status == 200


def test_bidirectional_and_node_red_debug(wire, simulator):
    ws_url = NODE_RED_URL.replace("http://", "ws://").replace("https://", "wss://") + "/comms"
    with closing(websocket.create_connection(ws_url, timeout=2, http_no_proxy=["127.0.0.1", "localhost"])) as ws:
        ws.send(json.dumps({"subscribe": "debug"}))
        _, client_id = simulator()
        expected = {"debug-state", "debug-telemetry", "debug-alarm", "debug-log", "debug-status"}
        seen = set()
        deadline = time.monotonic() + 8
        while not expected <= seen and time.monotonic() < deadline:
            try:
                packets = json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            for packet in packets if isinstance(packets, list) else [packets]:
                if packet.get("topic") == "debug":
                    seen.add(packet["data"].get("id"))
        assert expected <= seen, ("Debugs Node-RED ausentes", expected - seen)

    for mode in ("BUSCA", "APROXIMACAO", "AGUARDANDO_PEGA", "CAPTURA_MANUAL"):
        after = len(wire.records)
        inject(mode)
        ack = wire.wait("rover/cmd/ack", lambda p: p["source"] == client_id, after)
        validate("rover/cmd/ack", ack)
        assert ack["data"]["accepted"] is True and ack["data"]["state"] == mode
    after = len(wire.records)
    inject("AVANCAR")
    wire.wait("rover/estado", lambda p: p["source"] == client_id and p["data"]["motion"] == "AVANCAR", after)
    wire.wait("rover/estado", lambda p: p["source"] == client_id and p["data"]["reason"] == "manual_deadline_expired", after)
    after = len(wire.records)
    inject("PARAR")
    wire.wait("rover/cmd/ack", lambda p: p["data"]["accepted"] and p["data"]["state"] == "SEGURO_ESPERA", after)


def test_invalid_retained_and_duplicate_commands(wire, simulator):
    _, client_id = simulator()
    after = len(wire.records)
    wire.client.publish("rover/cmd/modo", b"{", qos=1).wait_for_publish(3)
    result = wire.wait("rover/cmd/ack", lambda p: p["data"]["command_id"] is None, after)
    assert result["data"]["accepted"] is False
    retained = wire.send(make_command(), retain=True, expected_source=client_id)
    assert retained["data"]["reason"] == "RETAINED_FORBIDDEN"
    original = make_command()
    assert wire.send(original, expected_source=client_id)["data"]["accepted"] is True
    assert wire.send(make_command("SEGURO_ESPERA"), expected_source=client_id)["data"]["accepted"] is True
    duplicate = wire.send(original, expected_source=client_id)
    assert duplicate["data"]["accepted"] is True and duplicate["data"]["duplicate"] is True
    assert wire.send(make_command("CAPTURA_MANUAL"), expected_source=client_id)["data"]["reason"] == "TRANSITION_FORBIDDEN"


def test_last_will_after_abrupt_exit(wire, simulator):
    process, client_id = simulator("--crash-after", "3")
    assert process.wait(8) == 2
    offline = wire.wait("rover/status", lambda p: p["source"] == client_id and not p["data"]["online"])
    assert offline["data"]["reason"] == "last_will_armed_at_timestamp"


def test_fault_alarm_and_rejection(wire, simulator):
    _, client_id = simulator("--fault-after", "2")
    wire.wait("rover/alarme", lambda p: p["source"] == client_id and p["data"]["code"] == "SIMULATED_SENSOR_FAULT")
    assert wire.send(make_command(), expected_source=client_id)["data"]["reason"] == "FAULT_LATCHED"


def test_station_watchdog_over_real_mqtt(wire, simulator):
    source = "isolated-station-test"
    _, client_id = simulator(station_source=source)
    heartbeat = envelope("station/heartbeat", source, {"online": True, "session_id": str(uuid4())})
    wire.client.publish("station/heartbeat", json.dumps(heartbeat), qos=1).wait_for_publish(3)
    accepted = wire.send(make_command(source=source), expected_source=client_id)
    assert accepted["data"]["accepted"] is True, accepted
    after = len(wire.records)
    wire.wait("rover/estado", lambda p: p["source"] == client_id and
              p["data"]["reason"] == "station_heartbeat_timeout", after, timeout=6)
    assert wire.send(make_command(source=source), expected_source=client_id)["data"]["reason"] == "STATION_UNAVAILABLE"


def test_reconnect_safe_and_retained_replay_rejected(wire, simulator):
    _, client_id = simulator()
    assert wire.send(make_command(), expected_source=client_id)["data"]["accepted"] is True
    after = len(wire.records)
    competitor = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv5)
    if os.getenv("MQTT_USERNAME"):
        competitor.username_pw_set(os.environ["MQTT_USERNAME"], os.getenv("MQTT_PASSWORD"))
    if os.getenv("MQTT_CA_FILE"):
        competitor.tls_set(os.environ["MQTT_CA_FILE"])
    try:
        # O broker desconecta a sessão anterior quando o mesmo client_id conecta.
        competitor.connect(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")), 5)
        competitor.loop_start()
        wire.wait("rover/status", lambda p: p["source"] == client_id and not p["data"]["online"], after)
        retained = make_command("APROXIMACAO")
        wire.client.publish("rover/cmd/modo", json.dumps(retained), qos=1, retain=True).wait_for_publish(3)
    finally:
        competitor.disconnect()
        competitor.loop_stop()
    wire.wait("rover/status", lambda p: p["source"] == client_id and p["data"]["online"], after)
    state = wire.wait("rover/estado", lambda p: p["source"] == client_id and
                      p["data"]["reason"] == "broker_connected", after)
    assert state["data"]["state"] == "SEGURO_ESPERA"
    ack = wire.wait("rover/cmd/ack", lambda p: p["data"]["command_id"] == retained["data"]["command_id"], after)
    assert ack["data"]["reason"] == "RETAINED_FORBIDDEN"


def test_graceful_shutdown(wire):
    client_id = "rover-shutdown-" + uuid4().hex[:8]
    config = Config(host=os.getenv("MQTT_HOST", "127.0.0.1"),
                    port=int(os.getenv("MQTT_PORT", "1883")), client_id=client_id,
                    username=os.getenv("MQTT_USERNAME", ""), password=os.getenv("MQTT_PASSWORD", ""),
                    ca_file=os.getenv("MQTT_CA_FILE", ""))
    transport = RoverMQTT(config)
    transport.start()
    try:
        wire.wait("rover/status", lambda p: p["source"] == client_id and p["data"]["online"])
    finally:
        transport.stop()
    result = wire.wait("rover/status", lambda p: p["source"] == client_id and not p["data"]["online"])
    assert result["data"]["reason"] == "graceful_shutdown"


def test_dashboard_http_and_websocket(wire, simulator):
    with urlopen(NODE_RED_URL + "/dashboard", timeout=5) as resp:
        html = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "RoboticRover" in html and "WebRTC (WHEP)" in html

    ws_url = NODE_RED_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/rover"
    with closing(websocket.create_connection(ws_url, timeout=3, http_no_proxy=["127.0.0.1", "localhost"])) as ws:
        _, client_id = simulator()
        deadline = time.monotonic() + 6
        seen_types = set()
        while "telemetry" not in seen_types and time.monotonic() < deadline:
            try:
                msg = json.loads(ws.recv())
                if msg.get("source") == client_id:
                    seen_types.add(msg.get("type"))
            except websocket.WebSocketTimeoutException:
                continue
        assert "telemetry" in seen_types

        after = len(wire.records)
        ws.send(json.dumps({"kind": "mode", "mode": "BUSCA"}))
        ack = wire.wait("rover/cmd/ack", lambda p: p["source"] == client_id, after)
        assert ack["data"]["accepted"] is True and ack["data"]["state"] == "BUSCA"

    with urlopen(NODE_RED_URL + "/api/rover/snapshot", timeout=5) as resp:
        snap = json.loads(resp.read().decode("utf-8"))
        assert snap["simulated"] is True
        assert snap["telemetry"] is not None

"""Arena MQTT agent for the Pi. All controls still run in software only."""
from __future__ import annotations

import json
import logging
import os
import signal
import stat
import time
from collections import OrderedDict
from pathlib import Path

import paho.mqtt.client as mqtt

from .competition import (
    ARTIFACTS, COMMANDS, IDENTIFICATION_TOPIC, TEAM_TOPICS, VELOCITY_LEASE,
    Arena, command, epoch_ms, fresh_ts, load_competition_env, message, number,
)
from .config import Config
from .main import RoverMqtt

LOG = logging.getLogger(__name__)
REFERENCE_COMMANDS = frozenset({"vel", "stop", "mode", "arm", "gripper"})
DRIVE = {"AVANCAR": (1, 0), "RECUAR": (-1, 0), "ESQUERDA": (0, 1), "DIREITA": (0, -1)}
PHASES = {"SEGURO_ESPERA": "IDLE", "BUSCA": "BUSCA", "APROXIMACAO": "BUSCA_ARTEFATO",
          "RETORNO": "NAVEGACAO", "DEPOSITO": "IDLE"}


class CompetitionRover(RoverMqtt):
    poll_interval = 0.025

    def __init__(self, arena, telemetry_dir, *, mock_battery=False, motors=None):
        self.arena = arena
        self.telemetry_dir = Path(telemetry_dir)
        self.mock_battery = mock_battery
        self.started_ms = epoch_ms()
        self.velocity = (0, 0)
        self.velocity_until = 0.0
        self.joints = self.gripper = None
        self.collecting = False
        self.identified = False
        self.reference_manual = False
        self.manual_ready_until = 0.0
        self.last_sample = self.last_battery = float("-inf")
        self.published = {}
        self.detections = OrderedDict()
        self.last_wire_ts = {}
        self.internal_commands = {arena.topic("cmd/rr/" + suffix): topic for topic, suffix in COMMANDS.items()}
        super().__init__(Config(arena.host, arena.port, f"{arena.team}-robot", arena.team, arena.password, 5, False), motors=motors)
        self._client.max_queued_messages_set(32)

    def _configure_will(self):
        self._client.will_set(self.arena.topic("status"), "offline", qos=1, retain=True)

    def _topic(self, topic):
        return self.arena.topic("rr/" + topic.removeprefix("rover/"))

    def _subscribe(self, client, options):
        client.subscribe(self.arena.topic("cmd/#"), options=options)
        client.subscribe(self.arena.topic(IDENTIFICATION_TOPIC), options=options)

    def _arena_publish(self, kind, data, *, ts=None):
        if kind not in TEAM_TOPICS or not self._connected.is_set():
            return False
        payload = data if kind == "status" else json.dumps(
            dict(data, ts=epoch_ms() if ts is None else ts), separators=(",", ":"), allow_nan=False)
        result = self._client.publish(self.arena.topic(kind), payload, qos=0 if kind == "battery" else 1,
                                      retain=kind in {"status", "state", "mode", "mission"})
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def _publish_offline(self):
        self._arena_publish("state", {"state": "IDLE"})
        super()._publish_offline()
        return self._client.publish(self.arena.topic("status"), "offline", qos=1, retain=True)

    def _reset(self):
        self._stop_drive()
        self.manual_ready_until = 0.0
        self.collecting = self.identified = False
        self.reference_manual = False
        self.published.clear()
        self.last_battery = float("-inf")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            super()._on_connect(client, userdata, flags, reason_code, properties)
            return
        with self._lock:
            self._reset()
            self._connected.set()
            self._arena_publish("status", "online")
            super()._on_connect(client, userdata, flags, reason_code, properties)
            self._report_state()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        super()._on_disconnect(client, userdata, disconnect_flags, reason_code, properties)
        with self._lock:
            self._reset()

    def _stop_drive(self):
        self.velocity = (0, 0)
        self.velocity_until = 0.0

    def _set_drive(self, vector, duration):
        self.velocity = vector
        self.velocity_until = time.monotonic() + duration if any(vector) and duration > 0 else 0.0
        if not self.velocity_until:
            self._stop_drive()

    def _on_accepted(self, packet):
        self.reference_manual = False
        data = packet.data
        if packet.event_type == "mode_command" or data.get("action") == "PARAR":
            self._stop_drive()
            self.manual_ready_until = 0.0
            self.collecting = False
            if self.controller.state in {"SEGURO_ESPERA", "BUSCA", "APROXIMACAO"}:
                self.identified = False
        elif data.get("target", "rover") == "rover":
            self.collecting = False
            self._set_drive(DRIVE[data["action"]], min(VELOCITY_LEASE, data["duration_ms"] / 1000))
        else:
            self._stop_drive()
            self.collecting = True

    def _on_message(self, client, userdata, msg):
        if msg.retain:
            return
        if msg.topic == self.arena.topic(IDENTIFICATION_TOPIC):
            try:
                with self._lock:
                    self._detection_data(message(msg.payload), epoch_ms())
            except ValueError as exc:
                LOG.warning("Identificação descartada: %s", exc)
            return
        topic = self.internal_commands.get(msg.topic)
        if topic:
            self._handle_internal(topic, msg.payload, False)
            return
        prefix = self.arena.topic("cmd/")
        kind = msg.topic[len(prefix):] if msg.topic.startswith(prefix) else ""
        if kind not in REFERENCE_COMMANDS:
            return
        now = epoch_ms()
        try:
            data = message(msg.payload)
            value = command(kind, data, now)
            ts = data["ts"]
        except ValueError as exc:
            LOG.warning("Comando da arena ignorado (%s): %s", kind, exc)
            return
        with self._lock:
            if ts <= self.last_wire_ts.get(kind, -1):
                return
            self.last_wire_ts[kind] = ts
            self._reference_command(kind, value, age=max(0, epoch_ms() - ts) / 1000)
            self._report_state()

    def _reference_command(self, kind, value, age):
        rover = self.controller
        if self.motors is not None:
            # Nesta entrega física, somente o caminho validado pela FSM da
            # dashboard pode mover rodas. Comandos diretos da arena não o contornam.
            self._stop_motors()
            rover.state, rover.manual_authorized = "SEGURO_ESPERA", False
            self.reference_manual = False
            if kind != "stop":
                LOG.warning("Controle direto da arena não habilitado no backend serial: %s", kind)
            self._publish("rover/estado", "state", {"state": rover.state, "reason": "arena_reference_no_actuation"}, simulated=False)
            return
        if kind == "stop":
            self._stop_drive()
            rover.state, rover.manual_authorized = "SEGURO_ESPERA", False
            self.reference_manual = False
            self.manual_ready_until = time.monotonic() + 5
            self.collecting = self.identified = False
        elif kind == "mode":
            if value == "AUTONOMO":
                self._stop_drive()
                rover.state, rover.manual_authorized = "SEGURO_ESPERA", False
                self.reference_manual = False
                self.collecting = self.identified = False
                self.manual_ready_until = 0.0
            elif rover.manual_authorized or time.monotonic() < self.manual_ready_until:
                rover.state, rover.manual_authorized = "CAPTURA_MANUAL", True
                self.reference_manual = True
                self.manual_ready_until = 0.0
        elif self.reference_manual and rover.state == "CAPTURA_MANUAL" and rover.manual_authorized:
            if kind == "vel":
                if any(value):
                    rover.control_target = "rover"
                    self.collecting = False
                self._set_drive(value, VELOCITY_LEASE - age)
            elif kind in {"arm", "gripper"}:
                self._stop_drive()
                rover.control_target = "manipulator"
                self.collecting = True
                if kind == "arm":
                    self.joints = value
                else:
                    self.gripper = value
        if kind == "stop" or kind == "mode" or rover.state == "CAPTURA_MANUAL":
            self._publish("rover/estado", "state", {"state": rover.state, "hardware_actuation": False}, simulated=True)
        if kind == "mode":
            self.published.pop("mode", None)

    def _report_state(self):
        rover = self.controller
        mode = "MANUAL" if rover.state == "CAPTURA_MANUAL" or (
            rover.state == "SEGURO_ESPERA" and rover.manual_authorized) else "AUTONOMO"
        state = PHASES.get(rover.state, "BUSCA_ARTEFATO")
        if rover.state in {"AGUARDANDO_PEGA", "CAPTURA_MANUAL"}:
            if any(self.velocity):
                state = "NAVEGACAO"
            elif self.collecting and self.identified:
                state = "COLETA"
            elif self.identified:
                state = "ARTEFATO_ENCONTRADO"
            elif rover.state == "CAPTURA_MANUAL":
                state = "IDLE"
        self._changed("state", {"state": state})
        self._changed("mode", {"mode": mode})

    def _changed(self, kind, value):
        if self.published.get(kind) != value and self._arena_publish(kind, value):
            self.published[kind] = value

    def _sample(self, name):
        descriptor = os.open(self.telemetry_dir / (name + ".json"), os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("a fonte de telemetria deve ser um arquivo regular")
            return message(handle.read(4097))

    def _battery(self, now):
        if self.mock_battery:
            value, ts = {"v": 7.82, "pct": 71.0, "i": 1.3}, now
        else:
            data = self._sample("battery")
            ts = fresh_ts(data, now, 2000)
            value = {"v": number(data.get("v"), 0, 1000), "pct": number(data.get("pct"), 0, 100),
                     "i": number(data.get("i"), -1000, 1000)}
        self._arena_publish("battery", value, ts=ts)
        self._publish("rover/telemetria", "telemetry", {"battery_voltage_v": value["v"],
                      "battery_percent": value["pct"]}, simulated=self.mock_battery)

    def _detection(self, now):
        if self.controller.state not in {"APROXIMACAO", "AGUARDANDO_PEGA", "CAPTURA_MANUAL"}:
            return
        self._detection_data(self._sample("detection"), now)

    def _detection_data(self, data, now):
        if self.controller.state not in {"APROXIMACAO", "AGUARDANDO_PEGA", "CAPTURA_MANUAL"}:
            return
        ts = fresh_ts(data, now, 10000)
        identification = data.get("identification")
        if ts < self.started_ms or not isinstance(identification, str) or not 1 <= len(identification) <= 80:
            return
        if identification in self.detections:
            return
        artifact = data.get("artifact")
        if not isinstance(artifact, str) or artifact not in ARTIFACTS:
            raise ValueError("artefato inválido")
        value = {"artifact": artifact, "conf": number(data.get("conf"), 0, 1)}
        if "tag" in data:
            value["tag"] = tag_id(data["tag"])
        if self._arena_publish("detection", value, ts=ts):
            self.identified = True
            self.detections[identification] = None
            if len(self.detections) > 256:
                self.detections.popitem(last=False)

    def _mission(self):
        tags = self._sample("mission").get("tags")
        if not isinstance(tags, list) or len(tags) > 8:
            raise ValueError("lista de tags inválida")
        clean = {}
        for entry in tags:
            if not isinstance(entry, dict) or entry.get("status") not in ("ENCONTRADA", "COLETADA"):
                raise ValueError("status da tag inválido")
            ident = tag_id(entry.get("id"))
            if ident in clean:
                raise ValueError("tag duplicada")
            clean[ident] = entry["status"]
        self._changed("mission", {"tags": [{"id": ident, "status": status} for ident, status in sorted(clean.items())]})

    def _tick(self, current):
        super()._tick(current)
        if self.velocity_until and (current >= self.velocity_until or self.controller.state != "CAPTURA_MANUAL"):
            self._stop_drive()
        if self.controller.state == "SEGURO_ESPERA" and not self.controller.manual_authorized:
            self.collecting = self.identified = False
        if not self._connected.is_set():
            return
        if current - self.last_sample >= 0.2:
            self.last_sample = current
            now = epoch_ms()
            for read in (lambda: self._detection(now), self._mission):
                try:
                    read()
                except (OSError, ValueError):
                    pass
            if current - self.last_battery >= 0.8:
                self.last_battery = current
                try:
                    self._battery(now)
                except (OSError, ValueError):
                    pass
        self._report_state()

    def _watchdog(self, current):
        if self.reference_manual and self.controller.state == "CAPTURA_MANUAL":
            return False
        return super()._watchdog(current)


def tag_id(value):
    if type(value) is not int or value < 0:
        raise ValueError("tag inválida")
    return value


def main():
    load_competition_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    arena = Arena.from_env()
    mock_battery = os.getenv("COMPETITION_MOCK_BATTERY") == "1"
    if mock_battery and arena.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Bateria simulada só é permitida em broker local de teste")
    rover = CompetitionRover(arena, os.getenv("COMPETITION_TELEMETRY_DIR", ".runtime/competition"),
                             mock_battery=mock_battery)
    signal.signal(signal.SIGTERM, lambda *_: rover._stop.set())
    rover.run()


if __name__ == "__main__":
    main()

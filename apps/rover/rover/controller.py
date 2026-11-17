"""Regras de operação; sem dependência do cliente MQTT ou de hardware.

O chamador serializa callbacks e tick. Relógios e saída são injetáveis para testes.
"""
from collections import OrderedDict
from datetime import timedelta
import json
import time
from uuid import UUID

from .contracts import ContractError, decode, parse_time, utc_now, validate

SAFE = "SEGURO_ESPERA"
TRANSITIONS = {
    SAFE: {"BUSCA"},
    "BUSCA": {"APROXIMACAO"},
    "APROXIMACAO": {"AGUARDANDO_PEGA"},
    "AGUARDANDO_PEGA": {"CAPTURA_MANUAL"},
    "CAPTURA_MANUAL": {"BUSCA"},
}
COMMAND_TOPICS = ("rover/cmd/modo", "rover/cmd/manual")


class Controller:
    def __init__(self, emit, heartbeat_timeout=4, station_source="station-nodered",
                 clock=utc_now, monotonic=time.monotonic):
        self.emit = emit
        self.clock = clock
        self.monotonic = monotonic
        self.heartbeat_timeout = heartbeat_timeout
        self.station_source = station_source
        self.state = SAFE
        self.motion = "PARAR"
        self.connected = False
        self.last_heartbeat = None
        self.station_session = None
        self.motion_deadline = None
        self.faulted = False
        self.manual_authorized = False
        self.control_target = "rover"
        self.arm_motion = "PARAR"
        self.cache = OrderedDict()

    def log(self, event, message, level="INFO"):
        self.emit("rover/log", {"level": level, "event": event, "message": message})

    def set_state(self, state, reason):
        previous = self.state
        self.state = state
        self.motion = "PARAR"
        self.arm_motion = "PARAR"
        self.motion_deadline = None
        if state in ("AGUARDANDO_PEGA", "CAPTURA_MANUAL"):
            self.manual_authorized = True
            if state == "AGUARDANDO_PEGA":
                self.control_target = "manipulator"
        elif state != SAFE or reason not in ("operator_stop", "manual_deadline_expired"):
            self.manual_authorized = False
        self.emit("rover/estado", {"state": state, "previous_state": previous,
                                  "reason": reason, "motion": self.motion,
                                  "manual_enabled": self.manual_authorized,
                                  "control_target": self.control_target,
                                  "arm_motion": self.arm_motion})
        self.log("state_changed", previous + " -> " + state + ": " + reason)

    def approach_completed(self):
        """Called by navigation only after confirming the approach has stopped."""
        if self.state != "APROXIMACAO" or not self.station_alive() or self.faulted:
            return False
        self.set_state("AGUARDANDO_PEGA", "approach_completed")
        return True

    def connection_changed(self, online):
        self.connected = online
        self.last_heartbeat = None
        self.station_session = None
        self.set_state(SAFE, "broker_connected" if online else "broker_disconnected")

    def station_alive(self):
        return (self.connected and self.last_heartbeat is not None
                and self.monotonic() - self.last_heartbeat < self.heartbeat_timeout)

    def tick(self):
        if not self.station_alive() and (self.state != SAFE or self.manual_authorized):
            self.set_state(SAFE, "station_heartbeat_timeout")
            self.emit("rover/alarme", {"code": "COMMUNICATION_LOST", "severity": "critical",
                                      "message": "Heartbeat da estação ausente; parada simulada"})
        if self.motion_deadline is not None and self.monotonic() >= self.motion_deadline:
            self.set_state(SAFE, "manual_deadline_expired")

    def fault(self):
        self.faulted = True
        self.set_state(SAFE, "simulated_sensor_fault")
        self.emit("rover/alarme", {"code": "SIMULATED_SENSOR_FAULT", "severity": "critical",
                                  "message": "Falha artificial; reinicie o simulador para liberar"})
        self.log("simulated_fault", "Falha artificial latched até reinício", "ERROR")

    def _fresh(self, message, max_age):
        age = (self.clock() - parse_time(message["timestamp"])).total_seconds()
        if not -2 <= age <= max_age:
            raise ContractError("TIMESTAMP_INVALID: mensagem antiga ou futura")

    def heartbeat(self, payload, retained=False):
        try:
            message = validate("station/heartbeat", decode(payload))
            if retained or message["source"] != self.station_source:
                raise ContractError("Heartbeat retained ou origem inesperada")
            self._fresh(message, self.heartbeat_timeout)
            session = message["data"]["session_id"]
            if self.station_session is not None and session != self.station_session:
                self.set_state(SAFE, "station_restarted")
            self.station_session = session
            self.last_heartbeat = self.monotonic()
        except (ContractError, ValueError) as exc:
            self.log("invalid_heartbeat", str(exc)[:240], "WARNING")

    @staticmethod
    def _correlation(message):
        try:
            value = message["data"]["command_id"]
            UUID(value)
            return value
        except (KeyError, TypeError, ValueError, AttributeError):
            return None

    def command(self, topic, payload, retained=False):
        if topic not in COMMAND_TOPICS:
            return
        command_id = None
        message = None
        fingerprint = None
        try:
            message = decode(payload)
            command_id = self._correlation(message)
            validate(topic, message)
            if retained:
                raise ContractError("RETAINED_FORBIDDEN")
            if message["source"] != self.station_source:
                raise ContractError("SOURCE_INVALID")
            self._fresh(message, 10)
            data = message["data"]
            issued, expires = parse_time(message["timestamp"]), parse_time(data["expires_at"])
            if not issued < expires <= issued + timedelta(seconds=10) or expires <= self.clock():
                raise ContractError("COMMAND_EXPIRED_OR_INVALID_TTL")
            fingerprint = topic + json.dumps(message, sort_keys=True, ensure_ascii=True)
            if command_id in self.cache:
                original, result = self.cache[command_id]
                if original != fingerprint:
                    raise ContractError("COMMAND_ID_CONFLICT")
                self.emit("rover/cmd/ack", dict(result, duplicate=True))
                return

            stop = ((topic == "rover/cmd/manual" and data["action"] == "PARAR") or
                    (topic == "rover/cmd/modo" and data["mode"] == SAFE))
            if stop:
                takeover = topic == "rover/cmd/manual" and data.get("take_control", False)
                self.manual_authorized = ((self.manual_authorized or self.state in
                                           ("CAPTURA_MANUAL", "AGUARDANDO_PEGA") or takeover)
                                          and self.station_alive() and not self.faulted)
                if topic == "rover/cmd/manual":
                    self.control_target = data.get("target", "rover")
                self.set_state(SAFE, "operator_stop")
            else:
                if not self.station_alive():
                    self.tick()
                    raise ContractError("STATION_UNAVAILABLE")
                if self.faulted:
                    raise ContractError("FAULT_LATCHED")
                if topic == "rover/cmd/modo":
                    target = data["mode"]
                    override = data.get("operator_override", False)
                    if override and (target != "CAPTURA_MANUAL" or self.state != SAFE
                                     or not self.manual_authorized):
                        raise ContractError("MANUAL_OVERRIDE_REQUIRES_STOP")
                    if not override and target != self.state and target not in TRANSITIONS[self.state]:
                        raise ContractError("TRANSITION_FORBIDDEN")
                    self.set_state(target, "operator_manual_override" if override else "operator_mode")
                else:
                    if self.state != "CAPTURA_MANUAL":
                        raise ContractError("MANUAL_MODE_REQUIRED")
                    target = data.get("target", "rover")
                    action = data["action"]
                    if data.get("take_control", False):
                        raise ContractError("TAKE_CONTROL_REQUIRES_STOP")
                    allowed = ({"SUBIR", "DESCER", "ESQUERDA", "DIREITA"} if target == "manipulator"
                               else {"AVANCAR", "RECUAR", "ESQUERDA", "DIREITA"})
                    if action not in allowed:
                        raise ContractError("ACTION_TARGET_MISMATCH")
                    self.control_target = target
                    self.motion = action if target == "rover" else "PARAR"
                    self.arm_motion = action if target == "manipulator" else "PARAR"
                    self.motion_deadline = self.monotonic() + data["duration_ms"] / 1000
                    self.emit("rover/estado", {"state": self.state, "previous_state": self.state,
                                              "reason": "simulated_manual_action", "motion": self.motion,
                                              "manual_enabled": True, "control_target": target,
                                              "arm_motion": self.arm_motion})
                    self.log("simulated_motion", "Ação artificial: " + target + " / " + action)
            result = self._ack(command_id, topic, True, "ACCEPTED")
        except (ContractError, ValueError, OverflowError) as exc:
            result = self._ack(command_id, topic, False, str(exc)[:240])
            self.log("command_rejected", result["reason"], "WARNING")
        # Cache FIFO limitado: deduplicação em memória durante esta execução.
        # Nunca substitui o resultado original se o mesmo ID vier com outro corpo.
        if command_id and fingerprint and command_id not in self.cache:
            self.cache[command_id] = (fingerprint, result)
            if len(self.cache) > 512:
                self.cache.popitem(last=False)
        self.emit("rover/cmd/ack", result)

    def _ack(self, command_id, topic, accepted, reason):
        return {"command_id": command_id, "topic": topic, "accepted": accepted,
                "reason": reason, "state": self.state, "duplicate": False,
                "control_target": self.control_target}

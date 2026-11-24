"""Shared configuration and payload validation for the arena contract."""
from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import time
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt
from dotenv import find_dotenv, load_dotenv

TEAM_TOPICS = frozenset({"status", "state", "mode", "battery", "detection", "mission"})
ARTIFACTS = frozenset({"hiperboloide", "argola_pequena", "argola_grande", "cilindro", "exotico"})
COMMANDS = {"station/heartbeat": "heartbeat", "rover/cmd/modo": "modo", "rover/cmd/manual": "manual"}
OUTPUTS = frozenset({"status", "estado", "telemetria", "alarme", "log", "cmd/ack"})
IDENTIFICATION_TOPIC = "rr/identification"
MODES = ("MANUAL", "AUTONOMO")
VELOCITY_LEASE = 0.45


def load_competition_env():
    load_dotenv(find_dotenv(usecwd=True))


def host_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", value):
            raise ValueError("Informe somente o IP ou hostname, sem URL ou porta") from None
        return value
    return f"[{address}]" if address.version == 6 else str(address)


@dataclass(frozen=True)
class Arena:
    host: str
    team: str
    password: str = field(repr=False)
    port: int = 1883

    def __post_init__(self):
        host_address(self.host)
        if not re.fullmatch(r"rover[0-9]{2}", self.team) or not self.password or not 1 <= self.port <= 65535:
            raise ValueError("Configure COMPETITION_TEAM, COMPETITION_PASSWORD e porta MQTT válidos")

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("COMPETITION_HOST", "").strip(),
                   os.environ.get("COMPETITION_TEAM", "rover04"),
                   os.environ.get("COMPETITION_PASSWORD", ""),
                   int(os.environ.get("COMPETITION_MQTT_PORT", "1883")))

    def topic(self, suffix):
        return f"rover/{self.team}/{suffix}"

    def client(self, role):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{self.team}-{role}",
                             protocol=mqtt.MQTTv5)
        client.username_pw_set(self.team, self.password)
        client.reconnect_delay_set(1, 10)
        client.max_queued_messages_set(32)
        return client


def epoch_ms():
    return time.time_ns() // 1_000_000


def number(value, lower, upper=None):
    if (type(value) not in (float, int) or not lower <= value or
            not (upper is None or value <= upper) or not math.isfinite(value)):
        raise ValueError("valor numérico inválido")
    return value


def message(payload, limit=4096):
    if len(payload) > limit:
        raise ValueError("mensagem grande demais")
    try:
        data = json.loads(payload.decode("utf-8"))
    except RecursionError as exc:
        raise ValueError("JSON com excesso de níveis") from exc
    if not isinstance(data, dict):
        raise ValueError("mensagem deve ser objeto JSON")
    return data


def fresh_ts(data, now, max_age):
    ts = data.get("ts")
    if type(ts) is not int or not -150 <= now - ts < max_age:
        raise ValueError("timestamp expirado ou relógios dessincronizados")
    return ts


def command(kind, data, now):
    fresh_ts(data, now, int(VELOCITY_LEASE * 1000) if kind == "vel" else 2000)
    if kind == "vel":
        return (number(data.get("linear"), -1, 1), number(data.get("angular"), -1, 1))
    if kind == "mode" and data.get("mode") in MODES:
        return data["mode"]
    if kind == "stop":
        return None
    if kind == "arm":
        joints, preset = data.get("joints"), data.get("preset")
        if (not isinstance(joints, list) or len(joints) > 16 or
                (preset is not None and (not isinstance(preset, str) or not 1 <= len(preset) <= 64)) or
                (not joints and not preset)):
            raise ValueError("juntas/preset inválidos")
        return tuple(number(value, -360, 360) for value in joints), preset
    if kind == "gripper" and data.get("action") in ("open", "close"):
        return data["action"]
    raise ValueError("comando fora do contrato")

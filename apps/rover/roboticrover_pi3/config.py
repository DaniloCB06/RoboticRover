"""Configuração externa: não embutir IPs ou senhas no repositório."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    client_id: str
    username: Optional[str]
    password: Optional[str]
    status_interval: float
    mock_telemetry: bool

    @classmethod
    def from_env(cls) -> "Config":
        host = os.getenv("MQTT_HOST", "").strip()
        if not host:
            raise ValueError("Defina MQTT_HOST com o IP/hostname do notebook (broker)")
        port = int(os.getenv("MQTT_PORT", "1883"))
        if not 1 <= port <= 65535:
            raise ValueError("MQTT_PORT inválida")
        status_interval = float(os.getenv("STATUS_INTERVAL_SEC", "5"))
        if status_interval < 1:
            raise ValueError("STATUS_INTERVAL_SEC deve ser >= 1")
        user = os.getenv("MQTT_USER") or os.getenv("MQTT_USERNAME") or None
        return cls(
            host=host,
            port=port,
            client_id=os.getenv("MQTT_CLIENT_ID", "roboticrover-pi3"),
            username=user,
            password=os.getenv("MQTT_PASSWORD") or None,
            status_interval=status_interval,
            mock_telemetry=os.getenv("ENABLE_MOCK_TELEMETRY", "false").lower() in ("true", "1", "yes"),
        )

from dataclasses import dataclass
import math
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    host: str = "127.0.0.1"
    port: int = 1883
    client_id: str = "rover-sim-01"
    keepalive: int = 5
    username: str = ""
    password: str = ""
    ca_file: str = ""
    station_source: str = "station-nodered"
    telemetry_interval: float = 1.0
    heartbeat_timeout: float = 4.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env_file=".env"):
        # Caminho explícito: nunca procura .env em diretórios ancestrais.
        load_dotenv(Path(env_file), override=False)
        cfg = cls(
            host=os.getenv("MQTT_HOST", cls.host),
            port=int(os.getenv("MQTT_PORT", cls.port)),
            client_id=os.getenv("MQTT_CLIENT_ID", cls.client_id),
            keepalive=int(os.getenv("MQTT_KEEPALIVE", cls.keepalive)),
            username=os.getenv("MQTT_USERNAME", ""), password=os.getenv("MQTT_PASSWORD", ""),
            ca_file=os.getenv("MQTT_CA_FILE", ""),
            station_source=os.getenv("STATION_SOURCE", cls.station_source),
            telemetry_interval=float(os.getenv("TELEMETRY_INTERVAL", cls.telemetry_interval)),
            heartbeat_timeout=float(os.getenv("HEARTBEAT_TIMEOUT", cls.heartbeat_timeout)),
            log_level=os.getenv("LOG_LEVEL", cls.log_level).upper(),
        )
        if not 1 <= cfg.port <= 65535 or not 1 <= cfg.keepalive <= 60:
            raise ValueError("Porta ou keepalive inválido")
        if not all(math.isfinite(x) and x > 0 for x in (cfg.telemetry_interval, cfg.heartbeat_timeout)):
            raise ValueError("Intervalos devem ser positivos e finitos")
        if not cfg.host or not 1 <= len(cfg.client_id) <= 64 or not 1 <= len(cfg.station_source) <= 64:
            raise ValueError("Host, client_id ou origem inválido")
        if cfg.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError("LOG_LEVEL inválido")
        return cfg

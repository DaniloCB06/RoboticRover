"""Contratos MQTT v1 para a estação e o Rover. Não controla hardware."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

VERSION = "1.0"
MAX_PAYLOAD_BYTES = 4096
MODES = frozenset({
    "SEGURO_ESPERA", "BUSCA", "APROXIMACAO", "AGUARDANDO_PEGA",
    "CAPTURA_MANUAL", "RETORNO", "DEPOSITO",
})
MANUAL_ACTIONS = frozenset({"AVANCAR", "RECUAR", "ESQUERDA", "DIREITA", "PARAR"})
TOPICS = {
    "rover/cmd/modo": "mode_command",
    "rover/cmd/manual": "manual_command",
    "station/heartbeat": "heartbeat",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def envelope(event_type: str, data: Dict[str, Any], simulated: bool, source: str = "raspberry-pi3") -> str:
    return json.dumps({
        "version": VERSION,
        "timestamp": now_iso(),
        "source": source,
        "simulated": simulated,
        "type": event_type,
        "data": data,
    }, separators=(",", ":"), ensure_ascii=False)


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp deve ser string ISO 8601")
    try:
        normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        date = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp ISO 8601 inválido") from exc
    if date.tzinfo is None:
        raise ValueError("timestamp sem fuso horário")
    return date.astimezone(timezone.utc)


@dataclass(frozen=True)
class Received:
    topic: str
    event_type: str
    data: Dict[str, Any]
    simulated: bool
    source: str


def read_packet(topic: str, payload: bytes, *, received_at: Optional[datetime] = None) -> Received:
    """Valida envelope, tipo/tópico e prazo. Falha fechada."""
    if topic not in TOPICS:
        raise ValueError("tópico desconhecido")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("payload acima do tamanho permitido")
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("JSON inválido") from exc
    if not isinstance(obj, dict):
        raise ValueError("envelope deve ser objeto JSON")
    if obj.get("version") != VERSION or obj.get("type") != TOPICS[topic]:
        raise ValueError("versão/tipo não confere com tópico")
    if not isinstance(obj.get("source"), str) or not obj["source"].strip():
        raise ValueError("source inválido")
    if not isinstance(obj.get("simulated"), bool):
        raise ValueError("simulated deve ser booleano")
    data = obj.get("data")
    if not isinstance(data, dict):
        raise ValueError("data inválida")
    current = received_at or datetime.now(timezone.utc)
    timestamp = parse_time(obj.get("timestamp"))
    # Rejeita replay grosseiro e relógio dessincronizado.
    age = (current - timestamp).total_seconds()
    if not (-5 <= age <= 10):
        raise ValueError("timestamp fora da janela de 10 s")
    if topic.startswith("rover/cmd/"):
        command_id = data.get("command_id")
        try:
            if not isinstance(command_id, str):
                raise ValueError
            parsed_id = uuid.UUID(command_id)
            if str(parsed_id) != command_id.lower():
                raise ValueError
        except (ValueError, AttributeError) as exc:
            raise ValueError("command_id UUID inválido") from exc
        expiry = parse_time(data.get("expires_at"))
        seconds = (expiry - current).total_seconds()
        if seconds <= 0 or seconds > 10:
            raise ValueError("comando expirado ou TTL excessivo")
        if topic == "rover/cmd/modo":
            if data.get("mode") not in MODES:
                raise ValueError("modo desconhecido")
        else:
            if data.get("action") not in MANUAL_ACTIONS:
                raise ValueError("ação desconhecida")
            if isinstance(data.get("duration_ms"), bool) or not isinstance(data.get("duration_ms"), int) or not (0 < data["duration_ms"] <= 1000):
                raise ValueError("duration_ms fora de faixa")
    else:
        if data.get("online") is not True or not isinstance(data.get("session_id"), str) or not data["session_id"]:
            raise ValueError("heartbeat inválido")
    return Received(topic, obj["type"], data, obj["simulated"], obj["source"])

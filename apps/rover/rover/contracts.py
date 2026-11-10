"""Validação única para mensagens recebidas e publicadas."""
import json
from datetime import datetime, timezone
from importlib.resources import files

from jsonschema import Draft202012Validator, FormatChecker
import rover_contracts

TOPICS = {
    "rover/estado": "state",
    "rover/telemetria": "telemetry",
    "rover/alarme": "alarm",
    "rover/log": "log",
    "rover/status": "status",
    "rover/cmd/modo": "mode_command",
    "rover/cmd/manual": "manual_command",
    "rover/cmd/ack": "ack",
    "station/heartbeat": "heartbeat",
}
SCHEMA = json.loads(files(rover_contracts).joinpath("v1/messages.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
MAX_PAYLOAD_BYTES = 16384


class ContractError(ValueError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value=None):
    return (value or utc_now()).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_time(value):
    return datetime.fromisoformat(value.upper().replace("Z", "+00:00"))


def validate(topic, message):
    if topic not in TOPICS:
        raise ContractError("Tópico desconhecido")
    errors = sorted(VALIDATOR.iter_errors(message), key=lambda error: str(error.path))
    if errors:
        raise ContractError(errors[0].message[:240])
    if message["type"] != TOPICS[topic]:
        raise ContractError("Tipo incompatível com o tópico")
    return message


def _no_constant(value):
    raise ValueError("Constante JSON inválida: " + value)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Chave JSON duplicada")
        result[key] = value
    return result


def decode(payload):
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ContractError("Payload excede 16384 bytes")
    try:
        return json.loads(payload.decode("utf-8"), parse_constant=_no_constant,
                          object_pairs_hook=_unique_keys)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("JSON inválido") from exc


def envelope(topic, source, data, now=None):
    message = {"version": "1.0", "timestamp": timestamp(now), "source": source,
               "simulated": True, "type": TOPICS[topic], "data": data}
    return validate(topic, message)

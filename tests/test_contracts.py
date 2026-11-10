import copy
import json

from jsonschema import Draft202012Validator
import pytest

from rover.contracts import ContractError, SCHEMA, decode, envelope, parse_time, validate
from rover.simulator import SimulatedSensors
from conftest import command


def test_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("topic,data", [
    ("rover/estado", {"state": "BUSCA", "previous_state": "SEGURO_ESPERA", "reason": "test", "motion": "PARAR"}),
    ("rover/telemetria", SimulatedSensors(1).sample()),
    ("rover/alarme", {"code": "TEST", "severity": "warning", "message": "Artificial"}),
    ("rover/log", {"level": "INFO", "event": "test", "message": "Artificial"}),
    ("rover/status", {"online": False, "reason": "test"}),
    ("rover/cmd/ack", {"command_id": None, "topic": "rover/cmd/modo", "accepted": False,
                       "reason": "invalid", "state": "SEGURO_ESPERA", "duplicate": False}),
    ("station/heartbeat", {"online": True, "session_id": "12345678-1234-4234-8234-123456789abc"}),
])
def test_output_contracts_roundtrip(topic, data):
    original = envelope(topic, "test-source", data)
    assert validate(topic, decode(json.dumps(original).encode())) == original
    assert original["simulated"] is True


@pytest.mark.parametrize("topic,value", [("rover/cmd/modo", "BUSCA"), ("rover/cmd/manual", "AVANCAR")])
def test_command_contracts(clock, topic, value):
    validate(topic, command(clock, value, topic))


@pytest.mark.parametrize("field,value", [
    ("version", "2.0"), ("timestamp", "yesterday"), ("timestamp", "2026-11-09T12:00:00"),
    ("source", ""), ("simulated", False), ("type", "telemetry"), ("extra", True),
])
def test_invalid_envelope(clock, field, value):
    message = command(clock)
    message[field] = value
    with pytest.raises(ContractError):
        validate("rover/cmd/modo", message)


@pytest.mark.parametrize("data", [
    {"battery_percent": 101, "temperature_c": 40, "proximity_cm": {"front": 1, "left": 1, "right": 1}},
    {"battery_percent": 50, "temperature_c": 40, "proximity_cm": {"front": -1, "left": 1, "right": 1}},
    {"battery_percent": 50, "temperature_c": 40, "proximity_cm": {}},
])
def test_sensor_ranges(data):
    with pytest.raises(ContractError):
        envelope("rover/telemetria", "test", data)


@pytest.mark.parametrize("payload", [b"{", b"\xff", b'{"x":NaN}', b'{"x":Infinity}',
                                     b'{"x":1,"x":2}', b"x" * 16385])
def test_strict_json(payload):
    with pytest.raises(ContractError):
        decode(payload)


def test_wrong_topic(clock):
    with pytest.raises(ContractError):
        validate("rover/cmd/manual", command(clock))


def test_required_fields(clock):
    original = command(clock)
    for field in original:
        message = copy.deepcopy(original)
        del message[field]
        with pytest.raises(ContractError):
            validate("rover/cmd/modo", message)


def test_sensor_reproducibility():
    assert SimulatedSensors(123).sample() == SimulatedSensors(123).sample()


def test_rfc3339_lowercase_timezone(clock):
    message = command(clock)
    message["timestamp"] = message["timestamp"].lower()
    validate("rover/cmd/modo", message)
    assert parse_time(message["timestamp"]) == clock.now()

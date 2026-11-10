from datetime import timedelta
import json
from uuid import uuid4

import pytest

from rover.contracts import envelope, timestamp, validate
from rover.controller import SAFE, TRANSITIONS
from conftest import command, last_ack, send


@pytest.mark.parametrize("initial", list(TRANSITIONS))
@pytest.mark.parametrize("target", list(TRANSITIONS))
def test_all_transitions(rig, clock, initial, target):
    controller, messages = rig
    controller.state = initial
    send(controller, command(clock, target))
    accepted = target == SAFE or target == initial or target in TRANSITIONS[initial]
    assert last_ack(messages)["accepted"] is accepted
    assert controller.state == (target if accepted else initial)
    assert controller.motion == "PARAR"


def test_manual_requires_capture(rig, clock):
    controller, messages = rig
    send(controller, command(clock, "AVANCAR", "rover/cmd/manual"), "rover/cmd/manual")
    assert last_ack(messages)["reason"] == "MANUAL_MODE_REQUIRED"
    assert controller.motion == "PARAR"


def test_manual_deadline_stops_without_new_command(rig, clock):
    controller, messages = rig
    controller.state = "CAPTURA_MANUAL"
    send(controller, command(clock, "AVANCAR", "rover/cmd/manual"), "rover/cmd/manual")
    assert last_ack(messages)["accepted"] is True
    assert controller.motion == "AVANCAR"
    clock.advance(0.51)
    controller.tick()
    assert controller.state == SAFE and controller.motion == "PARAR"


def test_stop_works_without_station_heartbeat(rig, clock):
    controller, messages = rig
    controller.state = "CAPTURA_MANUAL"
    controller.last_heartbeat = None
    send(controller, command(clock, "PARAR", "rover/cmd/manual"), "rover/cmd/manual")
    assert last_ack(messages)["accepted"] is True
    assert controller.state == SAFE


def test_heartbeat_timeout_and_no_automatic_resume(rig, clock):
    controller, messages = rig
    send(controller, command(clock))
    clock.advance(4.01)
    controller.tick()
    assert controller.state == SAFE
    send(controller, command(clock))
    assert last_ack(messages)["reason"] == "STATION_UNAVAILABLE"
    assert any(topic == "rover/alarme" for topic, _ in messages)


def test_broker_disconnect_reconnect_remains_safe(rig, clock):
    controller, messages = rig
    send(controller, command(clock))
    controller.connection_changed(False)
    assert controller.state == SAFE and controller.motion == "PARAR"
    controller.connection_changed(True)
    send(controller, command(clock))
    assert last_ack(messages)["reason"] == "STATION_UNAVAILABLE"


@pytest.mark.parametrize("retained,source,age", [(True, "station-nodered", 0),
                                                (False, "intruder", 0),
                                                (False, "station-nodered", 10),
                                                (False, "station-nodered", -10)])
def test_invalid_heartbeats_do_not_renew(rig, clock, retained, source, age):
    controller, _ = rig
    previous = controller.last_heartbeat
    clock.advance(1)
    message = envelope("station/heartbeat", source, {"online": True, "session_id": str(uuid4())},
                       clock.now() - timedelta(seconds=age))
    controller.heartbeat(json.dumps(message).encode(), retained)
    assert controller.last_heartbeat == previous


def test_station_restart_stops(rig, clock):
    controller, _ = rig
    send(controller, command(clock))
    message = envelope("station/heartbeat", "station-nodered",
                       {"online": True, "session_id": str(uuid4())}, clock.now())
    controller.heartbeat(json.dumps(message).encode())
    assert controller.state == SAFE


@pytest.mark.parametrize("value", [b"{", b"[]", b"null", b"42", b'"hello"', b"\xff", b"x" * 16385])
def test_bad_command_always_acknowledged(rig, value):
    controller, messages = rig
    controller.command("rover/cmd/modo", value)
    result = last_ack(messages)
    assert result["accepted"] is False and result["command_id"] is None
    validate("rover/cmd/ack", envelope("rover/cmd/ack", "test", result))


@pytest.mark.parametrize("change", ["retained", "expired", "old", "future", "long_ttl",
                                     "bad_id", "bad_mode", "source", "missing_expiry"])
def test_invalid_commands_rejected(rig, clock, change):
    controller, messages = rig
    message = command(clock)
    if change == "expired":
        message["data"]["expires_at"] = timestamp(clock.now() - timedelta(seconds=1))
    elif change == "old":
        message["timestamp"] = timestamp(clock.now() - timedelta(seconds=11))
    elif change == "future":
        message["timestamp"] = timestamp(clock.now() + timedelta(seconds=3))
    elif change == "long_ttl":
        message["data"]["expires_at"] = timestamp(clock.now() + timedelta(seconds=11))
    elif change == "bad_id":
        message["data"]["command_id"] = "no-uuid"
    elif change == "bad_mode":
        message["data"]["mode"] = "FLY"
    elif change == "source":
        message["source"] = "other-station"
    elif change == "missing_expiry":
        del message["data"]["expires_at"]
    send(controller, message, retained=change == "retained")
    assert last_ack(messages)["accepted"] is False
    assert controller.state == SAFE


def test_duplicate_does_not_execute_after_stop(rig, clock):
    controller, messages = rig
    message = command(clock)
    send(controller, message)
    send(controller, command(clock, SAFE))
    send(controller, message)
    assert controller.state == SAFE
    assert last_ack(messages)["duplicate"] is True
    assert last_ack(messages)["accepted"] is True


def test_same_id_different_body_rejected(rig, clock):
    controller, messages = rig
    message = command(clock)
    send(controller, message)
    message["data"]["mode"] = "APROXIMACAO"
    send(controller, message)
    assert last_ack(messages)["reason"] == "COMMAND_ID_CONFLICT"
    assert controller.state == "BUSCA"


def test_fault_latched_but_stop_accepted(rig, clock):
    controller, messages = rig
    controller.fault()
    send(controller, command(clock))
    assert last_ack(messages)["reason"] == "FAULT_LATCHED"
    send(controller, command(clock, SAFE))
    assert last_ack(messages)["accepted"] is True


def test_deduplication_bounded(rig, clock):
    controller, _ = rig
    for _ in range(520):
        send(controller, command(clock, SAFE))
    assert len(controller.cache) == 512


def test_every_emission_obeys_contract(rig, clock):
    controller, messages = rig
    send(controller, command(clock))
    controller.fault()
    controller.command("rover/cmd/manual", b"{}")
    for topic, data in messages:
        validate(topic, envelope(topic, "test", data))

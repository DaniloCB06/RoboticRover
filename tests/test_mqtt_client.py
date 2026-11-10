import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import paho.mqtt.client as mqtt
import pytest

from rover.config import Config
from rover.contracts import validate
from rover.mqtt_client import RoverMQTT


@pytest.fixture
def transport(monkeypatch):
    client = MagicMock()
    client.subscribe.return_value = (mqtt.MQTT_ERR_SUCCESS, 1)
    client.publish.return_value.rc = mqtt.MQTT_ERR_SUCCESS
    monkeypatch.setattr("rover.mqtt_client.mqtt.Client", lambda *args, **kwargs: client)
    return RoverMQTT(Config())


def test_last_will_contract_and_retention(transport):
    args, kwargs = transport.client.will_set.call_args
    assert args[0] == "rover/status"
    message = validate(args[0], json.loads(args[1]))
    assert message["simulated"] is True and message["data"]["online"] is False
    assert kwargs == {"qos": 1, "retain": True}


def test_subscriptions_preserve_live_retained_flag(transport):
    transport._on_connect(transport.client, None, None, SimpleNamespace(is_failure=False), None)
    subscriptions = transport.client.subscribe.call_args.args[0]
    assert {topic for topic, _ in subscriptions} == {"rover/cmd/modo", "rover/cmd/manual", "station/heartbeat"}
    assert all(options.retainAsPublished and options.QoS == 1 for _, options in subscriptions)
    assert transport.controller.connected is False


def test_online_only_after_subscriptions_are_confirmed(transport):
    transport._on_connect(transport.client, None, None, SimpleNamespace(is_failure=False), None)
    transport.client.publish.assert_not_called()
    transport._on_subscribe(transport.client, None, 1, [SimpleNamespace(is_failure=False)], None)
    assert transport.controller.connected is True
    published_topics = [call.args[0] for call in transport.client.publish.call_args_list]
    assert published_topics == ["rover/estado", "rover/log", "rover/status",
                                "rover/log", "rover/alarme"]


@pytest.mark.parametrize("callback", ["_on_subscribe", "_on_publish"])
def test_broker_permission_failure_stops(transport, callback):
    transport.controller.connected = True
    transport.controller.state = "BUSCA"
    reason = SimpleNamespace(is_failure=True)
    getattr(transport, callback)(transport.client, None, 1, [reason] if callback == "_on_subscribe" else reason, None)
    assert transport.controller.state == "SEGURO_ESPERA"
    assert transport.controller.motion == "PARAR"
    assert transport.controller.connected is False
    transport.client.disconnect.assert_called_once()


def test_disconnected_does_not_queue_obsolete_data(transport):
    transport.emit("rover/status", {"online": False, "reason": "test"})
    transport.client.publish.assert_not_called()


def test_connection_rejection_safe(transport):
    transport.controller.state = "BUSCA"
    transport._on_connect(transport.client, None, None, SimpleNamespace(is_failure=True), None)
    assert not transport.controller.connected and transport.controller.state == "SEGURO_ESPERA"

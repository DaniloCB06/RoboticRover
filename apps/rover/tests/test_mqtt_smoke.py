import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from roboticrover_pi3.config import Config
from roboticrover_pi3.main import RoverMqtt


class Pi3MqttSmokeTests(unittest.TestCase):
    def test_config_requires_host_and_valid_ranges(self):
        with patch.dict(os.environ, {"MQTT_HOST": ""}, clear=True):
            with self.assertRaises(ValueError):
                Config.from_env()
        with patch.dict(os.environ, {"MQTT_HOST": "127.0.0.1", "MQTT_PORT": "70000"}, clear=True):
            with self.assertRaises(ValueError):
                Config.from_env()
        with patch.dict(os.environ, {"MQTT_HOST": "127.0.0.1", "STATUS_INTERVAL_SEC": "0.5"}, clear=True):
            with self.assertRaises(ValueError):
                Config.from_env()
        with patch.dict(os.environ, {"MQTT_HOST": "127.0.0.1", "MQTT_USERNAME": "rover", "ENABLE_MOCK_TELEMETRY": "true"}, clear=True):
            cfg = Config.from_env()
            self.assertEqual(cfg.host, "127.0.0.1")
            self.assertEqual(cfg.username, "rover")
            self.assertTrue(cfg.mock_telemetry)

    @patch("roboticrover_pi3.main.mqtt.Client")
    def test_lwt_and_simulated_false_status_and_retained_command_rejection(self, mock_client_cls):
        fake_client = MagicMock()
        fake_client.publish.return_value.rc = 0
        mock_client_cls.return_value = fake_client

        cfg = Config(
            host="127.0.0.1",
            port=1883,
            client_id="roboticrover-pi3",
            username=None,
            password=None,
            status_interval=5.0,
            mock_telemetry=False,
        )
        service = RoverMqtt(cfg)

        # Verifica LWT com simulated=False, online=False, retain=True
        will_topic, will_payload = fake_client.will_set.call_args.args[:2]
        will_kwargs = fake_client.will_set.call_args.kwargs
        will_obj = json.loads(will_payload)
        self.assertEqual(will_topic, "rover/status")
        self.assertFalse(will_obj["simulated"])
        self.assertFalse(will_obj["data"]["online"])
        self.assertEqual(will_kwargs, {"qos": 1, "retain": True})

        # Simula conexão ao broker
        service._on_connect(fake_client, None, None, SimpleNamespace(is_failure=False), None)
        self.assertEqual(fake_client.subscribe.call_count, 3)
        for call in fake_client.subscribe.call_args_list:
            self.assertTrue(call.kwargs["options"].retainAsPublished)

        # Recebe heartbeat válido
        now = datetime.now(timezone.utc)
        hb_payload = json.dumps({
            "version": "1.0",
            "timestamp": now.isoformat(),
            "source": "station-nodered",
            "simulated": True,
            "type": "heartbeat",
            "data": {"online": True, "session_id": str(uuid.uuid4())},
        }).encode("utf-8")
        service._on_message(fake_client, None, SimpleNamespace(topic="station/heartbeat", payload=hb_payload, retain=False))

        # Comando retained deve ser ignorado/rejeitado sem mudar estado
        cmd_id = str(uuid.uuid4())
        cmd_payload = json.dumps({
            "version": "1.0",
            "timestamp": now.isoformat(),
            "source": "station-nodered",
            "simulated": True,
            "type": "mode_command",
            "data": {
                "command_id": cmd_id,
                "expires_at": (now + timedelta(seconds=5)).isoformat(),
                "mode": "BUSCA",
            },
        }).encode("utf-8")
        service._on_message(fake_client, None, SimpleNamespace(topic="rover/cmd/modo", payload=cmd_payload, retain=True))
        self.assertEqual(service.controller.state, "SEGURO_ESPERA")

        # Comando não-retained válido transiciona estado em simulação (execution="simulated_only")
        fake_client.publish.reset_mock()
        service._on_message(fake_client, None, SimpleNamespace(topic="rover/cmd/modo", payload=cmd_payload, retain=False))
        self.assertEqual(service.controller.state, "BUSCA")
        published = {call.args[0]: json.loads(call.args[1]) for call in fake_client.publish.call_args_list}
        self.assertIn("rover/cmd/ack", published)
        ack = published["rover/cmd/ack"]
        self.assertTrue(ack["simulated"])
        self.assertTrue(ack["data"]["accepted"])
        self.assertEqual(ack["data"]["execution"], "simulated_only")
        self.assertEqual(ack["data"]["state"], "BUSCA")


if __name__ == "__main__":
    unittest.main()

import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from roboticrover_pi3.protocol import envelope, read_packet


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.data = {
            "command_id": str(uuid.uuid4()),
            "expires_at": (self.now + timedelta(seconds=5)).isoformat(),
            "mode": "BUSCA",
        }

    def packet(self, *, topic="rover/cmd/modo", fields=None, data=None):
        payload = {
            "version": "1.0", "timestamp": self.now.isoformat(),
            "source": "station-nodered", "simulated": True,
            "type": "mode_command", "data": self.data.copy() if data is None else data,
        }
        if fields:
            payload.update(fields)
        return read_packet(topic, json.dumps(payload).encode("utf-8"), received_at=self.now)

    def test_accept_mode(self):
        pkt = self.packet()
        self.assertEqual(pkt.data["mode"], "BUSCA")

    def test_reject_expired(self):
        self.data["expires_at"] = (self.now - timedelta(milliseconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "expirado"):
            self.packet()

    def test_reject_unknown_mode(self):
        self.data["mode"] = "ATUAR_MOTORES"
        with self.assertRaisesRegex(ValueError, "modo"):
            self.packet()

    def test_reject_future_timestamp(self):
        with self.assertRaisesRegex(ValueError, "timestamp"):
            self.packet(fields={"timestamp": (self.now + timedelta(seconds=30)).isoformat()})

    def test_reject_nonboolean_simulated(self):
        with self.assertRaisesRegex(ValueError, "simulated"):
            self.packet(fields={"simulated": "false"})

    def test_reject_large_message(self):
        with self.assertRaisesRegex(ValueError, "tamanho"):
            read_packet("rover/cmd/modo", b"x" * 4097)

    def test_reject_topic_type_mismatch(self):
        with self.assertRaisesRegex(ValueError, "versão/tipo"):
            self.packet(topic="rover/cmd/manual")

    def test_reject_invalid_uuid(self):
        self.data["command_id"] = "123"
        with self.assertRaisesRegex(ValueError, "UUID"):
            self.packet()

    def test_envelope_roundtrip(self):
        obj = json.loads(envelope("status", {"online": True}, simulated=False))
        self.assertEqual(obj["type"], "status")
        self.assertFalse(obj["simulated"])

    def test_accept_heartbeat(self):
        packet = self.packet(topic="station/heartbeat", data={"online": True, "session_id": "abc"},
                             fields={"type": "heartbeat"})
        self.assertEqual(packet.data["session_id"], "abc")


if __name__ == "__main__":
    unittest.main()

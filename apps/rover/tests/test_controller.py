import unittest
import uuid

from roboticrover_pi3.controller import SimulatedController
from roboticrover_pi3.protocol import Received


def mode(value):
    return Received("rover/cmd/modo", "mode_command", {"mode": value, "command_id": str(uuid.uuid4())}, True, "station-nodered")


def manual(value):
    return Received("rover/cmd/manual", "manual_command", {
        "action": value, "command_id": str(uuid.uuid4()), "duration_ms": 500}, True, "station-nodered")


def heartbeat(session="a"):
    return Received("station/heartbeat", "heartbeat", {"online": True, "session_id": session}, True, "station-nodered")


class StateTests(unittest.TestCase):
    def setUp(self):
        self.c = SimulatedController(heartbeat_timeout=4)

    def test_no_heartbeat_movement_rejected(self):
        result = self.c.command(mode("BUSCA"), at=10)
        self.assertFalse(result.accepted)
        self.assertEqual(self.c.state, "SEGURO_ESPERA")

    def test_stop_always_allowed(self):
        self.c.heartbeat(heartbeat(), at=10)
        self.c.command(mode("BUSCA"), at=11)
        result = self.c.command(manual("PARAR"), at=100)
        self.assertTrue(result.accepted)
        self.assertEqual(self.c.state, "SEGURO_ESPERA")

    def test_invalid_transition_rejected(self):
        self.c.heartbeat(heartbeat(), at=10)
        result = self.c.command(mode("CAPTURA_MANUAL"), at=11)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "invalid_transition")

    def test_watchdog_forces_safe(self):
        self.c.heartbeat(heartbeat(), at=10)
        self.c.command(mode("BUSCA"), at=11)
        self.assertFalse(self.c.watchdog(at=13))
        self.assertTrue(self.c.watchdog(at=15))
        self.assertEqual(self.c.state, "SEGURO_ESPERA")

    def test_station_restart_resets_active_mode(self):
        self.c.heartbeat(heartbeat("session-1"), at=10)
        self.assertTrue(self.c.command(mode("BUSCA"), at=11).accepted)
        self.c.heartbeat(heartbeat("session-2"), at=12)
        self.assertEqual(self.c.state, "SEGURO_ESPERA")

    def test_duplicate_command_rejected(self):
        self.c.heartbeat(heartbeat(), at=10)
        pkt = mode("BUSCA")
        self.assertTrue(self.c.command(pkt, at=11).accepted)
        self.assertEqual(self.c.command(pkt, at=12).reason, "duplicate_command")

    def test_manual_only_in_manual_state(self):
        self.c.heartbeat(heartbeat(), at=10)
        self.assertFalse(self.c.command(manual("AVANCAR"), at=11).accepted)
        for state in ["BUSCA", "APROXIMACAO", "AGUARDANDO_PEGA", "CAPTURA_MANUAL"]:
            self.assertTrue(self.c.command(mode(state), at=11).accepted)
        result = self.c.command(manual("AVANCAR"), at=11)
        self.assertTrue(result.accepted)
        self.assertEqual(result.execution, "simulated_only")


if __name__ == "__main__":
    unittest.main()

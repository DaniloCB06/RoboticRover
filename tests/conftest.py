from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest

from rover.contracts import envelope, timestamp
from rover.controller import Controller


class Clock:
    def __init__(self):
        self.wall = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
        self.elapsed = 100.0

    def now(self):
        return self.wall

    def monotonic(self):
        return self.elapsed

    def advance(self, seconds):
        self.wall += timedelta(seconds=seconds)
        self.elapsed += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def rig(clock):
    messages = []
    controller = Controller(lambda topic, data: messages.append((topic, data)),
                            clock=clock.now, monotonic=clock.monotonic)
    controller.connection_changed(True)
    beat = envelope("station/heartbeat", "station-nodered",
                    {"online": True, "session_id": str(uuid4())}, clock.now())
    controller.heartbeat(json.dumps(beat).encode())
    return controller, messages


def command(clock, value="BUSCA", topic="rover/cmd/modo", command_id=None):
    data = {"command_id": command_id or str(uuid4()),
            "expires_at": timestamp(clock.now() + timedelta(seconds=5))}
    if topic.endswith("modo"):
        data["mode"] = value
    else:
        data.update(action=value, duration_ms=500)
    return envelope(topic, "station-nodered", data, clock.now())


def send(controller, message, topic="rover/cmd/modo", retained=False):
    controller.command(topic, json.dumps(message).encode(), retained)


def last_ack(messages):
    return [data for topic, data in messages if topic == "rover/cmd/ack"][-1]

"""Bridge the existing Node-RED flow to the team's arena MQTT namespace."""
from __future__ import annotations

import logging
import os
import signal
import threading

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from paho.mqtt.subscribeoptions import SubscribeOptions

from .competition import COMMANDS, OUTPUTS, Arena, load_competition_env, message
from .protocol import envelope, read_packet

LOG = logging.getLogger(__name__)
ARENA_LOCAL = "competition/arena/state"


class CompetitionStation:
    def __init__(self, arena, local_port=1883):
        self.arena = arena
        self.local_port = local_port
        self.online = False
        self.arena_state = None
        self.stop = threading.Event()
        self.remote = arena.client("station")
        self.remote.on_connect = self._remote_connect
        self.remote.on_disconnect = self._remote_disconnect
        self.remote.on_message = self._remote_message
        self.local = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{arena.team}-bridge-local",
                                 protocol=mqtt.MQTTv5)
        self.local.will_set("rover/status", self.offline_payload(), qos=1, retain=True)
        self.local.on_connect = self._local_connect
        self.local.on_message = self._local_message

    @staticmethod
    def offline_payload():
        return envelope("status", {"online": False, "mode": "arena_bridge", "hostname": "arena",
                                   "uptime_seconds": 0}, simulated=False, source="competition-bridge")

    def _offline(self):
        return self.local.publish("rover/status", self.offline_payload(), qos=1, retain=True)

    def _local_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOG.error("Broker local recusou a ponte: %s", reason_code)
            return
        if not self.online:
            self._offline()
        if self.arena_state is not None:
            client.publish(ARENA_LOCAL, self.arena_state, qos=1, retain=True)
        for topic in COMMANDS:
            client.subscribe(topic, options=SubscribeOptions(qos=1, retainAsPublished=True, retainHandling=2))

    def _remote_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOG.error("Broker da arena recusou a ponte: %s", reason_code)
            return
        LOG.info("Ponte MQTT %s conectada a %s:%d", self.arena.team, self.arena.host, self.arena.port)
        for topic in (self.arena.topic("status"), self.arena.topic("rr/#"), "arena/state"):
            client.subscribe(topic, options=SubscribeOptions(qos=1, retainAsPublished=True))

    def _remote_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.online = False
        self.arena_state = None
        if self.local.is_connected():
            self._offline()
            self.local.publish(ARENA_LOCAL, b"", qos=1, retain=True)

    def _local_message(self, client, userdata, msg):
        suffix = COMMANDS.get(msg.topic)
        if not suffix or msg.retain or not self.remote.is_connected():
            return
        try:
            read_packet(msg.topic, msg.payload)
        except ValueError:
            return
        props = Properties(PacketTypes.PUBLISH)
        props.MessageExpiryInterval = 2
        self.remote.publish(self.arena.topic("cmd/rr/" + suffix), msg.payload,
                            qos=0 if suffix == "heartbeat" else 1, properties=props)

    def _remote_message(self, client, userdata, msg):
        if msg.topic == self.arena.topic("status"):
            self.online = msg.payload == b"online"
            if not self.online and self.local.is_connected():
                self._offline()
            return
        if msg.topic == "arena/state":
            try:
                message(msg.payload, 32768)
            except ValueError:
                return
            self.arena_state = msg.payload
            if self.local.is_connected():
                self.local.publish(ARENA_LOCAL, self.arena_state, qos=1, retain=True)
            return
        prefix = self.arena.topic("rr/")
        suffix = msg.topic[len(prefix):] if msg.topic.startswith(prefix) else ""
        if self.online and self.local.is_connected() and suffix in OUTPUTS and len(msg.payload) <= 4096:
            self.local.publish("rover/" + suffix, msg.payload, qos=1, retain=suffix == "status")

    def run(self):
        if self.arena.host in {"127.0.0.1", "localhost", "::1"} and self.local_port == self.arena.port:
            raise ValueError("Use dois brokers separados: o local e o da arena")
        self.local.connect_async("127.0.0.1", self.local_port, keepalive=5)
        self.remote.connect_async(self.arena.host, self.arena.port, keepalive=5)
        self.local.loop_start()
        self.remote.loop_start()
        try:
            self.stop.wait()
        except KeyboardInterrupt:
            pass
        finally:
            self.remote.disconnect()
            self.remote.loop_stop()
            if self.local.is_connected():
                self._offline().wait_for_publish(timeout=2)
            self.local.disconnect()
            self.local.loop_stop()


def main():
    load_competition_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    bridge = CompetitionStation(Arena.from_env(), int(os.getenv("COMPETITION_LOCAL_MQTT_PORT", "1883")))
    signal.signal(signal.SIGTERM, lambda *_: bridge.stop.set())
    bridge.run()


if __name__ == "__main__":
    main()

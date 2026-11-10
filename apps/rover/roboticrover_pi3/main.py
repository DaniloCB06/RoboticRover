"""Cliente MQTT do Rover para Raspberry Pi 3.

TODOS os comandos são reconhecidos em SIMULAÇÃO e não fazem atuação física.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time

import paho.mqtt.client as mqtt
from paho.mqtt.subscribeoptions import SubscribeOptions
from dotenv import load_dotenv

from .config import Config
from .controller import SimulatedController
from .protocol import MAX_PAYLOAD_BYTES, envelope, read_packet

LOG = logging.getLogger("roboticrover.pi3")


class RoverMqtt:
    def __init__(self, config: Config):
        self.config = config
        self.controller = SimulatedController()
        self._lock = threading.RLock()
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._started = time.monotonic()
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id,
            protocol=mqtt.MQTTv5,
        )
        if config.username:
            self._client.username_pw_set(config.username, config.password)
        self._client.will_set("rover/status", self._status(False), qos=1, retain=True)
        self._client.reconnect_delay_set(min_delay=1, max_delay=15)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def _status(self, online: bool) -> str:
        return envelope("status", {
            "online": online,
            "hostname": socket.gethostname(),
            "mode": "pi3_mqtt_smoke_test_no_hardware",
            "uptime_seconds": int(time.monotonic() - self._started),
        }, simulated=False)

    def _publish(self, topic: str, event_type: str, data: dict, *, simulated: bool, retain: bool = False) -> None:
        if not self._connected.is_set():
            return
        info = self._client.publish(topic, envelope(event_type, data, simulated), qos=1, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            LOG.warning("MQTT publish falhou: %s, rc=%s", topic, info.rc)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOG.error("Broker recusou conexão: %s", reason_code)
            return
        self._connected.set()
        options = SubscribeOptions(qos=1, retainAsPublished=True)
        for topic in ("station/heartbeat", "rover/cmd/modo", "rover/cmd/manual"):
            client.subscribe(topic, options=options)
        # MQTT é rede; restabelecer conexão não implica retomar movimento.
        with self._lock:
            self.controller.state = "SEGURO_ESPERA"
            self.controller.last_heartbeat = None
        LOG.info("Conectado ao broker %s:%s", self.config.host, self.config.port)
        self._publish("rover/status", "status", json.loads(self._status(True))["data"], simulated=False, retain=True)
        self._publish("rover/estado", "state", {"state": self.controller.state, "hardware_actuation": False}, simulated=True)
        self._publish("rover/log", "log", {
            "level": "INFO", "message": "Cliente MQTT da Raspberry conectado à estação",
        }, simulated=False)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self._connected.clear()
        with self._lock:
            self.controller.state = "SEGURO_ESPERA"
            self.controller.last_heartbeat = None
        LOG.warning("Desconectado do broker: %s", reason_code)

    def _on_message(self, client, userdata, msg):
        # O broker da estação já aplica TTL MQTT5, mas validamos expires_at novamente.
        if len(msg.payload) > MAX_PAYLOAD_BYTES:
            LOG.warning("Payload excessivo: %s", msg.topic)
            return
        try:
            packet = read_packet(msg.topic, msg.payload)
        except ValueError as exc:
            LOG.warning("Mensagem ignorada em %s: %s", msg.topic, exc)
            return
        with self._lock:
            if msg.retain:
                LOG.warning("Mensagem de controle retained rejeitada: %s", msg.topic)
                return
            if packet.event_type == "heartbeat":
                before = self.controller.state
                self.controller.heartbeat(packet)
                if before != self.controller.state:
                    self._publish("rover/estado", "state", {
                        "state": self.controller.state,
                        "hardware_actuation": False,
                    }, simulated=True)
                return
            decision = self.controller.command(packet)
            self._publish("rover/cmd/ack", "ack", {
                "command_id": decision.command_id,
                "accepted": decision.accepted,
                "reason": decision.reason,
                "state": decision.state,
                "execution": decision.execution,
            }, simulated=True)
            if decision.accepted:
                self._publish("rover/estado", "state", {
                    "state": decision.state,
                    "hardware_actuation": False,
                }, simulated=True)
            LOG.info("Comando %s: %s (%s)", decision.command_id, decision.accepted, decision.reason)
            self._publish("rover/log", "log", {
                "level": "INFO" if decision.accepted else "WARNING",
                "message": "Comando validado apenas em software",
                "command_id": decision.command_id,
                "accepted": decision.accepted,
                "reason": decision.reason,
            }, simulated=True)

    def run(self):
        LOG.info("Iniciando cliente MQTT (sem controle físico de motores)")
        self._client.connect_async(self.config.host, self.config.port, keepalive=10)
        self._client.loop_start()
        last_status = 0.0
        last_mock = 0.0
        try:
            while not self._stop.is_set():
                current = time.monotonic()
                with self._lock:
                    if self.controller.watchdog(at=current):
                        self._publish("rover/estado", "state", {
                            "state": "SEGURO_ESPERA", "hardware_actuation": False,
                        }, simulated=True)
                        self._publish("rover/alarme", "alarm", {
                            "code": "STATION_HEARTBEAT_TIMEOUT",
                            "message": "Heartbeat da estação ausente; estado seguro simulado",
                        }, simulated=True)
                    if self._connected.is_set() and current - last_status >= self.config.status_interval:
                        self._publish("rover/status", "status", json.loads(self._status(True))["data"],
                                      simulated=False, retain=True)
                        last_status = current
                    if self.config.mock_telemetry and self._connected.is_set() and current - last_mock >= 2:
                        self._publish("rover/telemetria", "telemetry", {
                            "battery_voltage_v": 11.1,
                            "temperature_c": 25.0,
                            "proximity_cm": None,
                            "hardware_actuation": False,
                            "note": "VALORES ARTIFICIAIS / SENSOR NÃO CONECTADO",
                        }, simulated=True)
                        last_mock = current
                self._stop.wait(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self):
        self._stop.set()
        if self._connected.is_set():
            info = self._client.publish("rover/status", self._status(False), qos=1, retain=True)
            try:
                info.wait_for_publish(timeout=2)
            except RuntimeError:
                pass
        self._client.disconnect()
        self._client.loop_stop()
        LOG.info("Cliente encerrado")


def main():
    load_dotenv()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    RoverMqtt(Config.from_env()).run()


if __name__ == "__main__":
    main()

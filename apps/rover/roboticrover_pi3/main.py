"""Cliente MQTT da Pi; atuação USB somente com MOTOR_BACKEND=serial explícito."""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import signal
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt
from paho.mqtt.subscribeoptions import SubscribeOptions
from dotenv import load_dotenv

from .config import Config
from .controller import SimulatedController
from .protocol import MAX_PAYLOAD_BYTES, envelope, read_packet
from .protocol import parse_time
from .motors import MotorError, configured_motors

LOG = logging.getLogger("roboticrover.pi3")


class RoverMqtt:
    def __init__(self, config: Config, *, motors=None):
        self.config = config
        self.controller = SimulatedController()
        self.motors = motors if motors is not None else configured_motors()
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
        self._configure_will()
        self._client.reconnect_delay_set(min_delay=1, max_delay=15)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def _configure_will(self):
        self._client.will_set("rover/status", self._status(False), qos=1, retain=True)

    def _topic(self, topic):
        return topic

    def _subscribe(self, client, options):
        for topic in ("station/heartbeat", "rover/cmd/modo", "rover/cmd/manual"):
            client.subscribe(topic, options=options)

    def _tick(self, current):
        if self.motors is not None and self.motors.serial is not None and not self.motors.fault:
            try:
                if self.motors.tick(current):
                    self._publish("rover/log", "log", {
                        "level": "INFO", "message": "Prazo do movimento encerrado; tração desarmada",
                    }, simulated=False)
            except MotorError as exc:
                self._motor_fault(exc)

    def _watchdog(self, current):
        expired = self.controller.watchdog(at=current)
        if expired:
            self._stop_motors()
        return expired

    def _stop_motors(self):
        if self.motors is not None and self.motors.serial is not None and not self.motors.fault:
            try:
                self.motors.stop()
            except MotorError as exc:
                self._motor_fault(exc)

    def _motor_fault(self, error):
        self.controller.state = "SEGURO_ESPERA"
        self.controller.manual_authorized = False
        self._publish("rover/alarme", "alarm", {
            "code": "MOTOR_SERIAL_FAULT", "severity": "critical", "message": str(error),
        }, simulated=False)
        self._publish("rover/estado", "state", {
            "state": "SEGURO_ESPERA", "reason": "Falha no enlace do Mega; reinicie o cliente para rearmar",
        }, simulated=False)

    def _status(self, online: bool) -> str:
        return envelope("status", {
            "online": online,
            "hostname": socket.gethostname(),
            "mode": "serial_manual_bench" if self.motors else "pi3_mqtt_smoke_test_no_hardware",
            "motor_backend": "serial" if self.motors else "simulation",
            "uptime_seconds": int(time.monotonic() - self._started),
        }, simulated=False)

    def _publish(self, topic: str, event_type: str, data: dict, *, simulated: bool, retain: bool = False) -> None:
        if not self._connected.is_set():
            return
        if event_type == "state":
            data = dict(data, manual_enabled=self.controller.manual_authorized,
                        control_target=self.controller.control_target)
            data["hardware_actuation"] = self.motors is not None and not self.motors.fault
            data["motor_backend"] = "serial" if self.motors else "simulation"
        elif event_type == "ack":
            data = dict(data, control_target=self.controller.control_target)
        if event_type in ("state", "ack"):
            simulated = self.motors is None
        info = self._client.publish(self._topic(topic), envelope(event_type, data, simulated), qos=1, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            LOG.warning("MQTT publish falhou: %s, rc=%s", topic, info.rc)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOG.error("Broker recusou conexão: %s", reason_code)
            return
        self._connected.set()
        options = SubscribeOptions(qos=1, retainAsPublished=True)
        self._subscribe(client, options)
        # MQTT é rede; restabelecer conexão não implica retomar movimento.
        with self._lock:
            self._stop_motors()
            self.controller.state = "SEGURO_ESPERA"
            self.controller.last_heartbeat = None
            self.controller.manual_authorized = False
        LOG.info("Conectado ao broker %s:%s", self.config.host, self.config.port)
        self._publish("rover/status", "status", json.loads(self._status(True))["data"], simulated=False, retain=True)
        self._publish("rover/estado", "state", {"state": self.controller.state, "hardware_actuation": False}, simulated=True)
        self._publish("rover/log", "log", {
            "level": "INFO", "message": "Cliente MQTT da Raspberry conectado à estação",
        }, simulated=False)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self._connected.clear()
        with self._lock:
            self._stop_motors()
            self.controller.state = "SEGURO_ESPERA"
            self.controller.last_heartbeat = None
            self.controller.manual_authorized = False
        LOG.warning("Desconectado do broker: %s", reason_code)

    def _on_message(self, client, userdata, msg):
        self._handle_internal(msg.topic, msg.payload, msg.retain)

    def _handle_internal(self, topic, payload, retained):
        # O broker da estação já aplica TTL MQTT5, mas validamos expires_at novamente.
        if len(payload) > MAX_PAYLOAD_BYTES:
            LOG.warning("Payload excessivo: %s", topic)
            return
        try:
            packet = read_packet(topic, payload)
        except ValueError as exc:
            LOG.warning("Mensagem ignorada em %s: %s", topic, exc)
            return
        with self._lock:
            if retained:
                LOG.warning("Mensagem de controle retained rejeitada: %s", topic)
                return
            if self.motors is not None and packet.source != os.getenv("STATION_SOURCE", "station-nodered"):
                LOG.warning("Origem não autorizada para atuação: %s", packet.source)
                return
            if packet.event_type == "heartbeat":
                before = self.controller.state
                self.controller.heartbeat(packet)
                if before != self.controller.state:
                    self._stop_motors()
                    self._publish("rover/estado", "state", {
                        "state": self.controller.state,
                        "hardware_actuation": False,
                    }, simulated=True)
                return
            decision = self.controller.command(packet)
            if decision.accepted and self.motors is not None:
                decision = self._dispatch_motors(packet, decision)
            elif self.motors is not None:
                decision = replace(decision, execution="not_dispatched")
            self._publish("rover/cmd/ack", "ack", {
                "command_id": decision.command_id,
                "accepted": decision.accepted,
                "reason": decision.reason,
                "state": decision.state,
                "execution": decision.execution,
            }, simulated=self.motors is None)
            if decision.accepted:
                self._on_accepted(packet)
                self._publish("rover/estado", "state", {
                    "state": decision.state,
                    "hardware_actuation": False,
                }, simulated=True)
            LOG.info("Comando %s: %s (%s)", decision.command_id, decision.accepted, decision.reason)
            self._publish("rover/log", "log", {
                "level": "INFO" if decision.accepted else "WARNING",
                "message": "Decisão do comando de tração" if self.motors else "Comando validado apenas em software",
                "command_id": decision.command_id,
                "accepted": decision.accepted,
                "reason": decision.reason,
            }, simulated=self.motors is None)

    def _on_accepted(self, packet):
        pass

    def _dispatch_motors(self, packet, decision):
        data = packet.data
        try:
            if packet.event_type == "mode_command" or data.get("action") == "PARAR":
                self.motors.stop()
                return replace(decision, execution="mega_accepted", reason="mega_disarmed")
            if data.get("target", "rover") != "rover":
                self.motors.stop()
                return replace(decision, accepted=False, execution="not_dispatched", reason="manipulator_not_implemented")
            if not self.controller.manual_authorized or self.controller.state != "CAPTURA_MANUAL":
                self.motors.stop()
                return replace(decision, accepted=False, execution="not_dispatched", reason="manual_authorization_required")
            remaining = int((parse_time(data["expires_at"]) - datetime.now(timezone.utc)).total_seconds() * 1000)
            # Não reproduzir direções antigas de uma fila TCP/MQTT, mesmo se
            # um cliente antigo der expires_at de vários segundos ao movimento.
            if packet.issued_at is not None:
                fresh_until = packet.issued_at + timedelta(milliseconds=min(500, data["duration_ms"]))
                remaining = min(remaining, int((fresh_until - datetime.now(timezone.utc)).total_seconds() * 1000))
            if remaining <= 0:
                self.motors.stop()
                return replace(decision, accepted=False, execution="not_dispatched", reason="command_expired_before_serial")
            self.motors.move(data["action"], min(data["duration_ms"], remaining))
            return replace(decision, execution="mega_accepted", reason="mega_pwm_accepted_no_motion_feedback")
        except MotorError as exc:
            self._motor_fault(exc)
            return replace(decision, accepted=False, state="SEGURO_ESPERA", execution="failed", reason="motor_serial_fault")

    def run(self):
        LOG.info("Iniciando cliente MQTT: %s", "tração USB de bancada" if self.motors else "simulação")
        last_status = 0.0
        last_mock = 0.0
        try:
            if self.motors is not None:
                self.motors.start()
            self._client.connect_async(self.config.host, self.config.port, keepalive=10)
            self._client.loop_start()
            while not self._stop.is_set():
                current = time.monotonic()
                with self._lock:
                    if self._watchdog(current):
                        self._publish("rover/estado", "state", {
                            "state": "SEGURO_ESPERA", "hardware_actuation": False,
                        }, simulated=True)
                        self._publish("rover/alarme", "alarm", {
                            "code": "STATION_HEARTBEAT_TIMEOUT",
                            "message": "Heartbeat da estação ausente; tração desarmada" if self.motors else "Heartbeat da estação ausente; estado seguro simulado",
                        }, simulated=True)
                    if self._connected.is_set() and current - last_status >= self.config.status_interval:
                        self._publish("rover/status", "status", json.loads(self._status(True))["data"],
                                      simulated=False, retain=True)
                        last_status = current
                    if self.config.mock_telemetry and self._connected.is_set() and current - last_mock >= 2:
                        self._publish("rover/telemetria", "telemetry", {
                            "battery_voltage_v": 11.1,
                            "temperature_c": 25.0,
                            "hardware_actuation": False,
                            "note": "VALORES ARTIFICIAIS / SENSOR NÃO CONECTADO",
                        }, simulated=True)
                        last_mock = current
                    self._tick(current)
                self._stop.wait(self.poll_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self):
        self._stop.set()
        if self.motors is not None:
            try:
                with self._lock:
                    self.motors.close()
            except MotorError:
                LOG.exception("Falha ao confirmar parada; watchdog do Mega permanece independente")
        if self._connected.is_set():
            info = self._publish_offline()
            try:
                info.wait_for_publish(timeout=2)
            except RuntimeError:
                pass
        self._client.disconnect()
        self._client.loop_stop()
        LOG.info("Cliente encerrado")

    poll_interval = 0.025

    def _publish_offline(self):
        return self._client.publish(self._topic("rover/status"), self._status(False), qos=1, retain=True)


def main():
    load_dotenv()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    rover = RoverMqtt(Config.from_env())
    signal.signal(signal.SIGTERM, lambda *_: rover._stop.set())
    rover.run()


if __name__ == "__main__":
    main()

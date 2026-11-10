"""Transporte Paho MQTT 5. Callbacks e ciclo principal usam o mesmo lock."""
import json
import logging
import threading

import paho.mqtt.client as mqtt
from paho.mqtt.subscribeoptions import SubscribeOptions

from .contracts import envelope
from .controller import COMMAND_TOPICS, Controller

LOG = logging.getLogger(__name__)
POLICY = {
    "rover/estado": (1, True), "rover/telemetria": (0, False),
    "rover/alarme": (1, False), "rover/log": (0, False),
    "rover/status": (1, True), "rover/cmd/ack": (1, False),
}


class RoverMQTT:
    def __init__(self, config):
        self.config = config
        self.lock = threading.RLock()
        self.controller = Controller(self.emit, config.heartbeat_timeout, config.station_source)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=config.client_id, protocol=mqtt.MQTTv5)
        self.client.max_queued_messages_set(100)
        self.client.max_inflight_messages_set(20)
        self.client.reconnect_delay_set(min_delay=1, max_delay=15)
        if config.username:
            self.client.username_pw_set(config.username, config.password)
        if config.ca_file:
            self.client.tls_set(ca_certs=config.ca_file)
        self.client.on_connect = self._on_connect
        self.client.on_connect_fail = self._on_connect_fail
        self.client.on_disconnect = self._on_disconnect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_publish = self._on_publish
        self.client.on_message = self._on_message
        self.client.enable_logger(LOG)
        # Timestamp é o instante de armação do Will, não da detecção pelo broker.
        will = envelope("rover/status", config.client_id,
                        {"online": False, "reason": "last_will_armed_at_timestamp"})
        self.client.will_set("rover/status", json.dumps(will), qos=1, retain=True)

    def emit(self, topic, data):
        message = envelope(topic, self.config.client_id, data)
        LOG.log(logging.WARNING if topic == "rover/alarme" else logging.INFO,
                "%s %s", topic, json.dumps(message, ensure_ascii=False))
        if not self.controller.connected:
            return None  # Não acumula dados/estado antigos durante uma queda.
        qos, retain = POLICY[topic]
        info = self.client.publish(topic, json.dumps(message, allow_nan=False), qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            LOG.error("Falha ao publicar em %s: %s", topic, mqtt.error_string(info.rc))
        return info

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        with self.lock:
            if reason_code.is_failure:
                LOG.error("Conexão rejeitada: %s", reason_code)
                self.controller.connection_changed(False)
                return
            # RAP preserva o flag retained inclusive em publicações ao vivo.
            topics = [(topic, SubscribeOptions(qos=1, retainAsPublished=True))
                      for topic in (*COMMAND_TOPICS, "station/heartbeat")]
            result, _ = client.subscribe(topics)
            if result != mqtt.MQTT_ERR_SUCCESS:
                LOG.error("Falha ao assinar tópicos: %s", result)
                self.controller.connection_changed(False)
                client.disconnect()
                return

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            LOG.error("Broker rejeitou assinatura: %s", reason_codes)
            with self.lock:
                self.controller.connection_changed(False)
            client.disconnect()
            return
        with self.lock:
            # Só anuncia disponibilidade após o broker confirmar todas as
            # assinaturas; assim o primeiro heartbeat/comando não cai numa janela.
            self.controller.connection_changed(True)
            self.emit("rover/status", {"online": True, "reason": "mqtt_connected_simulator"})
            self.controller.log("simulator_connected", "Fonte artificial conectada; nenhum hardware")
            self.emit("rover/alarme", {"code": "SIMULATION_ACTIVE", "severity": "warning",
                                      "message": "Todos os dados e ações são simulados"})

    def _on_connect_fail(self, client, userdata):
        LOG.warning("Broker indisponível; nova tentativa automática")

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        if reason_code.is_failure:
            LOG.error("Broker rejeitou publicação %s: %s", mid, reason_code)
            with self.lock:
                self.controller.connection_changed(False)
            # Falha de permissão/protocolo exige correção, sem operar às cegas.
            client.disconnect()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        with self.lock:
            LOG.warning("MQTT desconectado: %s", reason_code)
            self.controller.connection_changed(False)

    def _on_message(self, client, userdata, message):
        with self.lock:
            if message.topic == "station/heartbeat":
                self.controller.heartbeat(message.payload, message.retain)
            else:
                self.controller.command(message.topic, message.payload, message.retain)

    def start(self):
        self.client.connect_async(self.config.host, self.config.port, self.config.keepalive,
                                  clean_start=True)
        self.client.loop_start()

    def stop(self):
        with self.lock:
            self.controller.set_state("SEGURO_ESPERA", "simulator_shutdown")
            info = self.emit("rover/status", {"online": False, "reason": "graceful_shutdown"})
        if info is not None and info.rc == mqtt.MQTT_ERR_SUCCESS:
            try:
                info.wait_for_publish(timeout=2)
            except RuntimeError:
                LOG.warning("Não foi possível confirmar status de encerramento")
        self.client.disconnect()
        self.client.loop_stop()

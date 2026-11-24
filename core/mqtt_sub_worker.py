import json
import time
import uuid
import threading

import paho.mqtt.client as mqtt
from PyQt5.QtCore import QObject, pyqtSignal

from utils.config_loader import load_config
from utils.logger import logger


class MqttSubWorker(QObject):
    status_changed = pyqtSignal(str)
    message_received = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        config = load_config()

        self.broker = config.get("mqtt_sub_broker", "")
        self.port = int(config.get("mqtt_sub_port", 1883))
        self.username = config.get("mqtt_sub_username", "")
        self.password = config.get("mqtt_sub_password", "")
        self.topic = config.get("mqtt_topic_sub", "kai/acts/eta")
        self.expected_jpl = config.get("kode_jpl", "")

        self._running = False
        self._last_msg_time = 0.0
        self._timeout = 60
        self._status = "offline"

    def start(self):
        self._running = True
        logger.info("MqttSubWorker started")

        t = threading.Thread(target=self._run, daemon=True)
        t.name = "MqttSubWorker"
        t.start()

    def stop(self):
        self._running = False

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"[MQTT-SUB] Connected to {self.broker}:{self.port}")
            client.subscribe(self.topic, qos=2)
            self._last_msg_time = time.time()
            self._set_status("online")
        else:
            logger.error(f"[MQTT-SUB] Failed connect, rc={rc}")
            self._set_status("offline")

    def _on_disconnect(self, client, userdata, rc):
        logger.warning(f"[MQTT-SUB] Disconnected (rc={rc})")
        self._set_status("offline")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception as e:
            logger.warning(f"[MQTT-SUB] Invalid message: {e}")
            return

        if payload.get("kode_jpl") != self.expected_jpl:
            logger.debug(f"[MQTT-SUB] Ignored message for different JPL: {payload.get('kode_jpl')}")
            return

        self._last_msg_time = time.time()
        self._set_status("online")
        logger.info(f"[MQTT-SUB] Message on {msg.topic}: {payload}")
        self.message_received.emit(payload)

    def _set_status(self, status):
        if status != self._status:
            self._status = status
            self.status_changed.emit(status)

    def _run(self):
        client_id = f"mqt_sub_{uuid.uuid4().hex[:6]}"
        client = mqtt.Client(client_id=client_id)

        if self.username:
            client.username_pw_set(self.username, self.password)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        try:
            logger.info(f"[MQTT-SUB] Connecting to {self.broker}:{self.port}")
            client.connect(self.broker, self.port, keepalive=30)
            client.loop_start()
        except Exception as e:
            logger.error(f"[MQTT-SUB] Connection error: {e}")
            self._set_status("offline")
            return

        while self._running:
            now = time.time()
            if self._last_msg_time > 0 and now - self._last_msg_time > self._timeout:
                self._set_status("offline")
            time.sleep(5)

        client.loop_stop()
        client.disconnect()
        logger.info("[MQTT-SUB] Worker stopped")

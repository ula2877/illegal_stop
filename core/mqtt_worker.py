import json
import time
import uuid
import threading
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt
from PyQt5.QtCore import QThread

from utils.config_loader import load_config
from utils.logger import logger


class MQTTWorker(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("MQTTWorker")  # tambahan

        config = load_config()

        # =========================
        # MQTT config
        # =========================
        self.broker = config.get("mqtt_broker", "")
        self.port = int(config.get("mqtt_port", 1883))
        self.username = config.get("mqtt_username", "")
        self.password = config.get("mqtt_password", "")
        self.topic = config.get("mqtt_topic_pub", "kecelakaan/event")

        # =========================
        # JPL config
        # =========================
        self.jpl_id = config.get("kode_jpl", "UNKNOWN")
        koordinat = config.get("koordinat_jpl", {})
        self.lat = koordinat.get("lat", 0)
        self.lon = koordinat.get("lon", 0)

        # =========================
        # Runtime
        # =========================
        self._running = False
        self._status = "bebas"
        self._status_lock = threading.Lock()

        # self.zone = None

    # ======================================================
    # MQTT Callbacks
    # ======================================================

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"[MQTT] Connected to {self.broker}:{self.port}")
        else:
            logger.error(f"[MQTT] Failed connect, rc={rc}")

    def on_disconnect(self, client, userdata, rc):
        logger.warning(f"[MQTT] Disconnected (rc={rc})")

        # tambahan: auto reconnect
        if rc != 0:
            logger.warning("[MQTT] Unexpected disconnect, trying reconnect...")
            try:
                client.reconnect()
            except Exception as e:
                logger.error(f"[MQTT] Reconnect failed: {e}")

    # ======================================================
    # Public API (dipanggil dari App)
    # ======================================================

    def update_status(self, zone):
        """
        zone dari detection:
        - ada isi → MERAH
        - kosong → BEBAS
        """
        with self._status_lock:
            if "danger" in str(zone):
                self._status = "merah"
            else:
                self._status = "bebas"

    # ======================================================
    # Thread loop
    # ======================================================

    def run(self):
        threading.current_thread().name = "MQTTWorker"

        self._running = True

        client_id = f"mqtt_{uuid.uuid4().hex[:6]}"
        self.client = mqtt.Client(client_id=client_id)

        if self.username:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

        # tambahan: auto reconnect delay
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

        try:
            logger.info(f"[MQTT] Connecting to {self.broker}:{self.port}")
            self.client.connect(self.broker, self.port, keepalive=30)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"[MQTT] Connection error: {e}")
            return

        tz = timezone(timedelta(hours=7))

        while self._running:
            try:
                # tambahan: skip jika belum connect
                if not self.client.is_connected():
                    logger.warning("[MQTT] Skip publish, not connected")
                    time.sleep(5)
                    continue

                now = datetime.now(tz)
                event_id = f"{self.jpl_id}_{now.strftime('%Y%m%d%H%M%S')}"

                with self._status_lock:
                    current_status = self._status

                data = {
                    "event_id": event_id,
                    "jpl_id": self.jpl_id,
                    "location": {
                        "latitude": self.lat,
                        "longitude": self.lon
                    },
                    "datetime": now.strftime("%d-%m-%Y %H:%M:%S"),
                    "obstacle": current_status
                }

                payload = json.dumps(data)

                result = self.client.publish(self.topic, payload, qos=2)

                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.info(f"[MQTT] Sent: {event_id} | {self._status}")
                else:
                    logger.error(f"[MQTT] Publish failed: {result.rc}")

            except Exception as e:
                logger.error(f"[MQTT] Error loop: {e}")

            time.sleep(5)

        self.client.loop_stop()
        self.client.disconnect()
        logger.info("[MQTT] Worker stopped")

    def stop(self):
        self._running = False
        self.wait()
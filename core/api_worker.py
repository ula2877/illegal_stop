# core/api_worker.py
import queue
import threading
import time
import os
import requests
import datetime
import socket

from PyQt5.QtCore import QObject, pyqtSignal

from utils.config_loader import load_config
from utils.api_tester import get_real_mac, LICENSE_URL, UPLOAD_URL, OVERLOAD_URL
from utils.logger import logger


class ApiWorker(QObject):
    ping_status = pyqtSignal(str)

    def __init__(self, max_queue=50):
        super().__init__()
        self.queue = queue.Queue(maxsize=max_queue)
        self.overload_queue = queue.Queue(maxsize=max_queue)
        self.petugas_queue = queue.Queue(maxsize=max_queue)

        self.running = False

        self._last_ping = 0
        self.ping_interval = 300  # 5 menit (detik)

    # =========================
    # Public API
    # =========================
    def start(self):
        self.running = True
        logger.info("ApiWorker started")

        self._threads = []

        t1 = threading.Thread(target=self._event_loop, daemon=True)
        t1.name = "ApiWorker-Event"
        t1.start()
        self._threads.append(t1)

        t2 = threading.Thread(target=self._ping_loop, daemon=True)
        t2.name = "ApiWorker-Ping"
        t2.start()
        self._threads.append(t2)

        t3 = threading.Thread(target=self._overload_loop, daemon=True)
        t3.name = "ApiWorker-Overload"
        t3.start()
        self._threads.append(t3)

        t4 = threading.Thread(target=self._petugas_loop, daemon=True)
        t4.name = "ApiWorker-Petugas"
        t4.start()
        self._threads.append(t4)

    def stop(self):
        logger.info("Stopping ApiWorker...")
        self.running = False
        for t in self._threads:
            t.join(timeout=3)
        logger.info("ApiWorker stopped")

    def enqueue_event(self, zone, vehicle, image_path):
        event = {
            "zone": zone,
            "vehicle": vehicle,
            "image": image_path
        }

        if not self.queue.full():
            self.queue.put(event)

    # =========================
    # NEW: enqueue overload alert
    # =========================
    def enqueue_overload(self, resource, value, threshold):
        cfg = load_config()

        kode_jpl = cfg.get("kode_jpl")
        lokasi = cfg.get("lokasi", "UNKNOWN")
        alamat = cfg.get("alamat", "UNKNOWN")

        event = {
            "kode_jpl": kode_jpl,
            "lokasi": lokasi,
            "alamat": alamat,
            "type": resource,
            "value": value,
            "threshold": threshold,
            "hostname": socket.gethostname(),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        if not self.overload_queue.full():
            self.overload_queue.put(event)

    def enqueue_petugas_alert(self, image_path):
        event = {
            "image": image_path
        }

        if not self.petugas_queue.full():
            self.petugas_queue.put(event)

    # =========================
    # Event worker
    # =========================
    def _event_loop(self):
        logger.info("ApiWorker event loop started")

        while self.running:
            try:
                event = self.queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                self._send_event(event)
            except Exception as e:
                logger.error(f"API Event failed: {e}", exc_info=True)

        logger.info("ApiWorker event loop stopped")

    # =========================
    # NEW: overload worker
    # =========================
    def _overload_loop(self):
        logger.info("ApiWorker overload loop started")

        while self.running:
            try:
                event = self.overload_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                self._send_overload(event)
            except Exception as e:
                logger.error(f"OVERLOAD failed: {e}", exc_info=True)

        logger.info("ApiWorker overload loop stopped")

    # =========================
    # Petugas alert worker
    # =========================
    def _petugas_loop(self):
        logger.info("ApiWorker petugas loop started")

        while self.running:
            try:
                event = self.petugas_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                self._send_petugas_alert(event)
            except Exception as e:
                logger.error(f"PETUGAS alert failed: {e}", exc_info=True)

        logger.info("ApiWorker petugas loop stopped")

    def _send_petugas_alert(self, event):
        image_path = event["image"]
        if not os.path.exists(image_path):
            logger.warning(f"PETUGAS image not found: {image_path}")
            return

        cfg = load_config()
        kode_jpl = cfg.get("kode_jpl")
        lokasi = cfg.get("lokasi", "UNKNOWN")
        alamat = cfg.get("alamat", "UNKNOWN")

        now = datetime.datetime.now()
        payload = {
            "jenis_kendaraan": "PETUGAS",
            "kode_jpl": kode_jpl,
            "lokasi": lokasi,
            "alamat": alamat,
            "tanggal": now.strftime("%d-%m-%Y"),
            "jam": now.strftime("%H:%M:%S"),
            "zona": "PETUGAS_TIADA",
        }

        with open(image_path, "rb") as f:
            files = {"image": f}
            resp = requests.post(UPLOAD_URL, data=payload, files=files, timeout=(10, 30))

        logger.info(f"PETUGAS alert sent: {resp.status_code}")

    # =========================
    # Ping worker (5 menit sekali)
    # =========================
    def _ping_loop(self):
        logger.info("ApiWorker ping loop started")

        while self.running:
            now = time.time()

            if now - self._last_ping >= self.ping_interval:
                try:
                    self._send_ping()
                    self.ping_status.emit("online")
                except Exception as e:
                    logger.error(f"PING failed: {e}", exc_info=True)
                    self.ping_status.emit("offline")

                self._last_ping = now

            time.sleep(1)

        logger.info("ApiWorker ping loop stopped")

    # =========================
    # Actual ping request
    # =========================
    def _send_ping(self):
        cfg = load_config()

        api_url = cfg.get("api", "")
        kode_jpl = cfg.get("kode_jpl")
        api_key = cfg.get("api_key")

        if not api_url or not kode_jpl:
            logger.warning("PING missing api or kode_jpl")
            raise Exception("missing config")

        base_url = self._get_base_url(api_url)
        url = f"{base_url}add-ping"

        headers = {}
        if api_key:
            headers["x-api-key"] = api_key

        payload = {"jpl": kode_jpl}

        resp = requests.post(url, json=payload, headers=headers, timeout=5)
        logger.info(f"PING status: {resp.status_code}")

    # =========================
    # Event request (existing)
    # =========================
    def _send_event(self, event):
        cfg = load_config()

        product_key = cfg.get("product_key")
        api_url = cfg.get("api")
        api_key = cfg.get("api_key")
        kode_jpl = cfg.get("kode_jpl")

        if not api_url or not product_key:
            logger.warning("API missing config")
            return

        mac = get_real_mac()
        if not mac:
            logger.warning("API cannot get MAC")
            return

        license_payload = {
            "mac_address": mac,
            "product_key": product_key
        }

        try:
            res = requests.post(LICENSE_URL, json=license_payload, timeout=5)
            try:
                data = res.json()
            except ValueError as e:
                logger.error(f"API license invalid JSON response: {e}")
                return

            if str(data.get("status", "")).lower() not in ("ok", "valid", "success", "true", "1"):
                logger.warning("API license invalid")
                return

        except requests.RequestException as e:
            logger.error(f"API license request failed: {e}", exc_info=True)
            return

        # ===== Event request =====
        image_path = event["image"]
        if not os.path.exists(image_path):
            logger.warning(f"API image not found: {image_path}")
            return

        data = {
            "jpl": kode_jpl,
            "zone": event["zone"],
            "vehicle": event["vehicle"]
        }

        headers = {}
        if api_key:
            headers["x-api-key"] = api_key

        with open(image_path, "rb") as f:
            files = {"file": (os.path.basename(image_path), f, "image/jpeg")}

            resp = requests.post(
                api_url,
                headers=headers,
                data=data,
                files=files,
                timeout=(10, 30)
            )

        logger.info(f"API event sent: {resp.status_code} | {event['zone']}")

        with open(image_path, "rb") as f:
            lokasi = cfg.get("lokasi", "UNKNOWN")
            alamat = cfg.get("alamat", "UNKNOWN")

            sekarang = datetime.datetime.now()
            formatted_now = sekarang.strftime("%d-%m-%Y %H:%M:%S")

            payload = {
                "jenis_kendaraan": event["vehicle"],
                "kode_jpl": kode_jpl,
                "lokasi": lokasi,
                "alamat": alamat,
                "tanggal": formatted_now.split(" ")[0],
                "jam": formatted_now.split(" ")[1],
                "zona": event["zone"],
            }

            files2 = {"image": f}
            requests.post(UPLOAD_URL, data=payload, files=files2, timeout=(10, 30))

    # =========================
    # NEW: overload request
    # =========================
    def _send_overload(self, event):
        url = OVERLOAD_URL

        requests.post(url, data=event, timeout=5)

        logger.info(f"OVERLOAD sent: {event['type']} {event['value']}%")

    # =========================
    # Helper
    # =========================
    def _get_base_url(self, api_url: str) -> str:
        api_url = api_url.rstrip("/")

        if "/" not in api_url:
            return api_url + "/"

        base = api_url.rsplit("/", 1)[0]
        return base + "/"
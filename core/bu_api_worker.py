# core/api_worker.py
import queue
import threading
import time
import os
import requests
import datetime

from utils.config_loader import load_config
from utils.api_tester import get_real_mac, LICENSE_URL, UPLOAD_URL


class ApiWorker:
    def __init__(self, max_queue=50):
        self.queue = queue.Queue(maxsize=max_queue)
        self.running = False

        self._last_ping = 0
        self.ping_interval = 300  # 5 menit (detik)

    # =========================
    # Public API
    # =========================
    def start(self):
        self.running = True
        threading.Thread(target=self._event_loop, daemon=True).start()
        threading.Thread(target=self._ping_loop, daemon=True).start()

    def stop(self):
        self.running = False

    def enqueue_event(self, zone, vehicle, image_path):
        event = {
            "zone": zone,
            "vehicle": vehicle,
            "image": image_path
        }

        if not self.queue.full():
            self.queue.put(event)

    # =========================
    # Event worker
    # =========================
    def _event_loop(self):
        while self.running:
            try:
                event = self.queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                self._send_event(event)
            except Exception as e:
                print("[API] Event failed:", e)

    # =========================
    # Ping worker (5 menit sekali)
    # =========================
    def _ping_loop(self):
        while self.running:
            now = time.time()

            if now - self._last_ping >= self.ping_interval:
                try:
                    self._send_ping()
                except Exception as e:
                    print("[PING] Failed:", e)

                self._last_ping = now

            time.sleep(1)

    # =========================
    # Actual ping request
    # =========================
    def _send_ping(self):
        cfg = load_config()

        api_url = cfg.get("api", "")
        kode_jpl = cfg.get("kode_jpl")
        api_key = cfg.get("api_key")

        if not api_url or not kode_jpl:
            print("[PING] Missing api or kode_jpl")
            return

        base_url = self._get_base_url(api_url)
        url = f"{base_url}add-ping"

        headers = {}
        if api_key:
            headers["x-api-key"] = api_key

        payload = {"jpl": kode_jpl}

        resp = requests.post(url, json=payload, headers=headers,timeout=5)
        print(f"[PING] {resp.status_code}")

    # =========================
    # Actual event request
    # =========================
    def _send_event(self, event):
        cfg = load_config()

        product_key = cfg.get("product_key")
        api_url = cfg.get("api")
        api_key = cfg.get("api_key")
        kode_jpl = cfg.get("kode_jpl")

        if not api_url or not product_key:
            print("[API] Missing config")
            return

        # ===== License check =====
        mac = get_real_mac()
        if not mac:
            print("[API] Cannot get MAC")
            return

        license_payload = {
            "mac_address": mac,
            "product_key": product_key
        }

        try:
            res = requests.post(LICENSE_URL, json=license_payload, timeout=5)
            data = res.json()

            if str(data.get("status", "")).lower() not in ("ok", "valid", "success", "true", "1"):
                print("[API] License invalid")
                return

        except Exception as e:
            print(f"[API] License error: {e}")
            return

        # ===== Event request =====
        image_path = event["image"]
        if not os.path.exists(image_path):
            print("[API] Image not found:", image_path)
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

        print(f"[API] {resp.status_code} | {event['zone']}")

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

            resp = requests.post(UPLOAD_URL, data=payload, files={"image": f}, timeout=10)

    def _get_base_url(self, api_url: str) -> str:
        """
        Convert:
        https://domain/.../v1/add-illegal-stop/
        -> https://domain/.../v1/
        """
        api_url = api_url.rstrip("/")

        if "/" not in api_url:
            return api_url + "/"

        base = api_url.rsplit("/", 1)[0]
        return base + "/"


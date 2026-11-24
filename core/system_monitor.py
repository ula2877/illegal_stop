import time
import psutil
from PyQt5.QtCore import QThread, pyqtSignal
import shutil
import os, math
import threading

from utils.config_loader import load_config
from utils.logger import logger


class SystemMonitor(QThread):
    """
    Worker thread that periodically reports CPU and RAM usage.
    """

    cpu_updated = pyqtSignal(int)
    ram_updated = pyqtSignal(int)
    storage_updated = pyqtSignal(float, float, float)
    temp_updated = pyqtSignal(float)

    def __init__(self, interval: float = 1.0, parent=None, api_worker=None):
        super().__init__(parent)

        # 🔥 Nama untuk Qt + logging sinkron
        self.setObjectName("SystemMonitor")

        self.interval = interval
        self._running = False
        self.api_worker = api_worker

        self.cooldown = 300  # 5 menit

        self.last_alert = {
            "cpu": 0,
            "ram": 0,
            "disk": 0
        }

        # 🔥 Load config sekali
        try:
            self.cfg = load_config()
        except Exception as e:
            logger.error(f"Failed to load config in SystemMonitor init: {e}")
            self.cfg = {}

    # ======================================================
    # Thread entry
    # ======================================================

    def run(self):
        # 🔥 FIX: hilangkan Dummy-X
        threading.current_thread().name = self.objectName()

        self._running = True
        logger.info("SystemMonitor started")

        while self._running:
            try:
                cpu = int(psutil.cpu_percent(interval=1))
                ram = int(psutil.virtual_memory().percent)

                self.cpu_updated.emit(cpu)
                self.ram_updated.emit(ram)

                logger.debug(f"CPU: {cpu}% | RAM: {ram}%")

                # =========================
                # Storage usage
                # =========================
                try:
                    cfg = self.cfg if self.cfg else load_config()

                    evidence_path = cfg.get("evidence_path", ".")

                    usage = shutil.disk_usage(evidence_path)

                    total = usage.total / (1024**3)
                    free = usage.free / (1024**3)
                    used_percent = (usage.used / usage.total) * 100

                    self.storage_updated.emit(free, total, used_percent)

                    logger.debug(
                        f"Disk: {used_percent:.2f}% used | Free: {free:.2f} GB | Total: {total:.2f} GB"
                    )

                    cpu_th = cfg.get("cpu_usage_threshold", 90)
                    ram_th = cfg.get("ram_usage_threshold", 90)
                    disk_th = cfg.get("disk_usage_threshold", 90)

                    if self.custom_round(cpu) >= cpu_th:
                        logger.warning(f"CPU threshold exceeded: {cpu}% >= {cpu_th}%")
                        self._maybe_alert("cpu", self.custom_round(cpu), cpu_th)

                    if self.custom_round(ram) >= ram_th:
                        logger.warning(f"RAM threshold exceeded: {ram}% >= {ram_th}%")
                        self._maybe_alert("ram", self.custom_round(ram), ram_th)

                    if self.custom_round(used_percent) >= disk_th:
                        logger.warning(f"Disk threshold exceeded: {used_percent:.2f}% >= {disk_th}%")
                        self._maybe_alert("disk", self.custom_round(used_percent), disk_th)

                    temp_th = cfg.get("temp_usage_threshold", 70)

                    if self.custom_round(used_percent) >= disk_th:
                        logger.warning(f"Disk threshold exceeded: {used_percent:.2f}% >= {disk_th}%")
                        self._maybe_alert("disk", self.custom_round(used_percent), disk_th)

                except Exception as e:
                    logger.error(f"Storage monitoring error: {e}", exc_info=True)

                # =========================
                # Temperature
                # =========================
                try:
                    temps = psutil.sensors_temperatures()
                    temp_val = 0.0
                    if "coretemp" in temps:
                        temp_val = temps["coretemp"][0].current
                    elif "cpu_thermal" in temps:
                        temp_val = temps["cpu_thermal"][0].current
                    elif temps:
                        for name, entries in temps.items():
                            if entries:
                                temp_val = entries[0].current
                                break

                    self.temp_updated.emit(temp_val)

                    if temp_val >= temp_th:
                        self._maybe_alert("temp", temp_val, temp_th)

                except Exception as e:
                    logger.debug(f"Temperature not available: {e}")

            except Exception as e:
                logger.error(f"SystemMonitor main loop error: {e}", exc_info=True)

        logger.info("SystemMonitor stopped")

    def custom_round(self, n):
        if n - int(n) > 0.5:
            return math.ceil(n)
        else:
            return math.floor(n)

    # ======================================================
    # Public control
    # ======================================================

    def stop(self):
        logger.info("Stopping SystemMonitor...")
        self._running = False
        self.wait()
        logger.info("SystemMonitor fully stopped")

    def _maybe_alert(self, resource, value, threshold):
        if not self.api_worker:
            logger.debug("API worker not available, skipping alert")
            return

        now = time.time()
        last = self.last_alert.get(resource, 0)

        if now - last >= self.cooldown:
            logger.info(
                f"Triggering alert: {resource}={value}% (threshold={threshold}%)"
            )
            self.api_worker.enqueue_overload(resource, value, threshold)
            self.last_alert[resource] = now
        else:
            logger.debug(
                f"Cooldown active for {resource}, skipping alert"
            )
import socket
import time
import threading

from PyQt5.QtCore import QThread, pyqtSignal
from utils.logger import logger


class InternetWorker(QThread):
    """
    Periodically checks internet connectivity and emits status when changed.
    """

    status_changed = pyqtSignal(str)  # "ONLINE" / "OFFLINE"

    def __init__(self, interval: float = 3.0, parent=None):
        super().__init__(parent)

        # 🔥 Nama thread (Qt + logging)
        self.setObjectName("InternetWorker")

        self.interval = interval
        self._running = False

    # ======================================================
    # Core logic
    # ======================================================

    def _check_connection(self) -> bool:
        """Return True if internet is reachable, else False."""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return True
        except OSError as e:
            logger.debug(f"Internet check failed: {e}")
            return False

    # ======================================================
    # Thread entry
    # ======================================================

    def run(self):
        # 🔥 FIX Dummy-X
        threading.current_thread().name = self.objectName()

        self._running = True
        logger.info("InternetWorker started")

        last_status = None

        while self._running:
            try:
                online = self._check_connection()
                status = "ONLINE" if online else "OFFLINE"

                # Emit only when changed
                if status != last_status:
                    logger.info(f"Internet status changed: {status}")
                    self.status_changed.emit(status)
                    last_status = status

            except Exception as e:
                logger.error(f"InternetWorker loop error: {e}", exc_info=True)

            time.sleep(self.interval)

        logger.info("InternetWorker stopped")

    # ======================================================
    # Public control
    # ======================================================

    def stop(self):
        logger.info("Stopping InternetWorker...")
        self._running = False
        self.wait()
        logger.info("InternetWorker fully stopped")
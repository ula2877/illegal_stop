import time
from datetime import datetime
import threading

from PyQt5.QtCore import QThread, pyqtSignal
from utils.logger import logger


class DateTimeWorker(QThread):
    """
    Worker thread that emits current datetime string periodically.
    """

    datetime_updated = pyqtSignal(str)

    def __init__(self, interval: float = 1.0, parent=None):
        super().__init__(parent)

        # hanya tambahan naming (tidak mengubah behavior)
        self.setObjectName("DateTimeWorker")

        self.interval = interval
        self._running = False

    # ======================================================
    # Thread entry
    # ======================================================

    def run(self):
        # hanya tambahan naming untuk logging (tidak mengubah logic)
        threading.current_thread().name = self.objectName()

        self._running = True
        logger.info("DateTimeWorker started")

        while self._running:
            now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            self.datetime_updated.emit(now)
            time.sleep(self.interval)

        logger.info("DateTimeWorker stopped")

    # ======================================================
    # Public control
    # ======================================================

    def stop(self):
        logger.info("Stopping DateTimeWorker...")
        self._running = False
        self.wait()
        logger.info("DateTimeWorker fully stopped")
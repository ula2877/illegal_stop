import time
import serial
import serial.tools.list_ports
import threading

from PyQt5.QtCore import QThread, pyqtSignal
from utils.logger import logger


class SerialWorker(QThread):
    """
    Worker that continuously scans serial ports and auto-connects
    to the first available port (excluding configured ones).
    """

    status_changed = pyqtSignal(str)

    def __init__(
        self,
        baudrate: int = 9600,
        scan_interval: float = 1.0,
        excluded_ports=None,
        parent=None
    ):
        super().__init__(parent)

        self.setObjectName("SerialWorker")

        self.baudrate = baudrate
        self.scan_interval = scan_interval
        self.excluded_ports = excluded_ports or []

        self._running = False
        self._serial = None
        self._connected_port = None
        self._lock = threading.Lock()

        self.start_time = None
        self.duration = 5

    def run(self):
        threading.current_thread().name = self.objectName()

        self._running = True
        logger.info("SerialWorker started")

        while self._running:
            try:
                with self._lock:
                    serial_ref = self._serial
                if serial_ref is None:
                    self._try_connect()
                else:
                    self._check_connection()
            except Exception as e:
                logger.error(f"SerialWorker loop error: {e}", exc_info=True)

            time.sleep(self.scan_interval)

        self._disconnect()
        logger.info("SerialWorker stopped")

    def _try_connect(self):
        ports = serial.tools.list_ports.comports()

        available = [
            p.device for p in ports
            if (
                p.device not in self.excluded_ports
                and ("USB" in p.device or "COM" in p.device)
            )
        ]

        if not available:
            logger.debug("No available serial ports")
            self._emit_disconnected()
            return

        for device in available:
            try:
                logger.info(f"Trying serial port: {device}")

                ser = serial.Serial(device, self.baudrate, timeout=1)

                if ser.is_open:
                    with self._lock:
                        self._serial = ser
                        self._connected_port = device

                    logger.info(f"Connected to serial: {device}")
                    self.status_changed.emit(f"CONNECTED ({device})")
                    return

            except Exception as e:
                logger.warning(f"Failed to connect {device}: {e}")
                continue

        logger.warning("No serial device could be connected")
        self._emit_disconnected()

    def _check_connection(self):
        """Check if current serial connection is still alive."""
        try:
            with self._lock:
                ser = self._serial
            if ser:
                _ = ser.in_waiting
        except Exception as e:
            logger.warning(f"Serial connection lost: {e}")
            self._disconnect()

    def _disconnect(self):
        with self._lock:
            ser = self._serial
            port = self._connected_port
            self._serial = None
            self._connected_port = None

        if ser:
            try:
                logger.info(f"Disconnecting serial: {port}")
                ser.close()
            except Exception as e:
                logger.error(f"Error closing serial: {e}")

        self._emit_disconnected()

    def _emit_disconnected(self):
        logger.debug("Serial status: DISCONNECTED")
        self.status_changed.emit("DISCONNECTED")

    def stop(self):
        logger.info("Stopping SerialWorker...")
        self._running = False
        self.wait()
        logger.info("SerialWorker fully stopped")

    def send(self, data: str):
        with self._lock:
            ser = self._serial
            if not ser or not ser.is_open:
                logger.warning("Serial send failed: not connected")
                return

        try:
            ser.write(data.encode())
            logger.debug(f"Serial send: {data.strip()}")

        except Exception as e:
            logger.error(f"Serial send error: {e}", exc_info=True)
            self._disconnect()

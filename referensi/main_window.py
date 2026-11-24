import os
import json
import logging

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QGridLayout,
    QVBoxLayout,
    QLabel,
    QStatusBar,
    QShortcut,
)
from PyQt5.QtCore import QSize, Qt, QTimer
from PyQt5.QtGui import QPixmap, QIcon, QKeySequence

from ui.widgets import StatusCard
from core.workers import get_cpu, get_ram, get_storage, get_temp, InternetCheck, MqttWorker
from ui.dialogs.password_dialog import PasswordDialog
from ui.dialogs.settings_dialog import SettingsDialog
from utils.config import get_config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_PATH = os.path.join(BASE_DIR, "resources", "images", "logo.png")
ICON_PATH = os.path.join(BASE_DIR, "resources", "images", "icon.png")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "kai.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("KAI")


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: list[StatusCard] = []
        self._card_map: dict[str, StatusCard] = {}
        self._last_internet_status = ""
        self._last_mqtt_status = ""
        self._setup_ui()
        self._start_monitors()
        self._setup_shortcuts()

    def _setup_ui(self) -> None:
        self.setWindowTitle("JPL Early Warning System")
        self.setMinimumSize(QSize(800, 480))
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self._apply_styles()

        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        if os.path.exists(LOGO_PATH):
            logo_label = QLabel(self)
            pixmap = QPixmap(LOGO_PATH)
            scaled = pixmap.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled)
            logo_label.setFixedSize(56, 56)
            header_layout.addWidget(logo_label)

        title_label = QLabel("JPL EARLY WARNING SYSTEM", self)
        tf = title_label.font()
        tf.setPointSize(18)
        tf.setBold(True)
        title_label.setFont(tf)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        root_layout.addLayout(header_layout)

        grid = QGridLayout()
        grid.setSpacing(12)

        layout_plan = [
            # baris 1 — 4 kolom
            ("Kereta", "dekat", "", 0, 0),
            ("Petugas", "siaga", "", 0, 1),
            ("Obstacle", "bebas", "", 0, 2, 1, 2),
            ("Detection", "-", "", 0, 4, 2),
            # baris 2 — 4 kolom (kolom 3 diisi span Detection)
            ("ETA", "-", "s", 1, 0),
            ("Jarak", "-", "km", 1, 1),
            ("Kecepatan", "-", "km/j", 1, 2),
            ("Heartbeat", "20:24:22", "15-05-26", 1, 3),
            # baris 3 — 5 kolom
            ("Internet", "offline", "", 2, 0),
            ("MQTT", "offline", "", 2, 1),
            ("Cam 1", "offline", "", 2, 2),
            ("Cam 2", "offline", "", 2, 3),
            ("Cam 3 (R. Kontrol)", "offline", "", 2, 4),
            # baris 4 — 5 kolom
            ("Alarm", "ok", "", 3, 0),
            ("CPU", "-", "%", 3, 1),
            ("RAM", "-", "%", 3, 2),
            ("Storage", "-", "%", 3, 3),
            ("Temp", "-", "°C", 3, 4),
        ]

        for item in layout_plan:
            title, value, unit, row, col, *extra = item
            rowspan = extra[0] if len(extra) > 0 else 1
            colspan = extra[1] if len(extra) > 1 else 1
            card = StatusCard(title, value, unit, self)
            grid.addWidget(card, row, col, rowspan, colspan)
            self._cards.append(card)
            self._card_map[title] = card

        root_layout.addLayout(grid)
        root_layout.addStretch()

        self._status = QStatusBar(self)
        self.setStatusBar(self._status)
        self._status.showMessage("All systems nominal")

    def _start_monitors(self) -> None:
        self._sys_timer = QTimer(self)
        self._sys_timer.timeout.connect(self._refresh_system_stats)
        self._sys_timer.start(2000)

        self._net_timer = QTimer(self)
        self._net_timer.timeout.connect(self._check_internet)
        self._net_timer.start(5000)
        self._check_internet()

        config = get_config()
        mqtt_cfg = config.get("settings", {})
        self._mqtt = MqttWorker(
            host=mqtt_cfg.get("mqtt_host", "broker.emqx.io"),
            port=mqtt_cfg.get("mqtt_port", 1883),
            topic=mqtt_cfg.get("mqtt_topic", "kai/acts/eta"),
            parent=self,
        )
        self._mqtt.status_changed.connect(self._on_mqtt_status)
        self._mqtt.message_received.connect(self._on_mqtt_message)
        self._mqtt.start()

    def _setup_shortcuts(self) -> None:
        sc = QShortcut(QKeySequence("Ctrl+,"), self)
        sc.activated.connect(self._open_settings)

    def _open_settings(self) -> None:
        dialog = PasswordDialog(self)
        if dialog.exec_() == PasswordDialog.Accepted:
            settings = SettingsDialog(self)
            settings.exec_()

    def _refresh_system_stats(self) -> None:
        cpu = get_cpu()
        ram = get_ram()
        storage = get_storage()
        temp = get_temp()

        self._card_map["CPU"].set_value(cpu)
        self._card_map["RAM"].set_value(ram)
        self._card_map["Storage"].set_value(storage)
        if temp != "N/A":
            self._card_map["Temp"].set_value(temp)

        logger.info("System stats | CPU: %s%% | RAM: %s%% | Storage: %s%% | Temp: %s°C", cpu, ram, storage, temp)

    def _check_internet(self) -> None:
        thread = InternetCheck(self)
        thread.result_ready.connect(self._on_internet_result)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_internet_result(self, status: str) -> None:
        self._card_map["Internet"].set_value(status)
        color = "#22c55e" if status == "online" else "#ef4444"
        self._card_map["Internet"].set_led(color)
        if status != self._last_internet_status:
            logger.info("Internet check: %s", status)
            self._last_internet_status = status

        if status == "offline":
            self._card_map["MQTT"].set_value(status)
            self._card_map["MQTT"].set_led(color)
            if status != self._last_mqtt_status:
                logger.info("MQTT status: %s", status)
                self._last_mqtt_status = status

    def _on_mqtt_status(self, status: str) -> None:
        self._card_map["MQTT"].set_value(status)
        color = "#22c55e" if status == "online" else "#ef4444"
        self._card_map["MQTT"].set_led(color)
        if status != self._last_mqtt_status:
            logger.info("MQTT status: %s", status)
            self._last_mqtt_status = status

    def _on_mqtt_message(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("MQTT invalid JSON: %s", payload)
            return

        mapping = {
            "status_kereta": "Kereta",
            "eta": "ETA",
            "jarak": "Jarak",
            "kecepatan": "Kecepatan",
        }
        color = "#bfc8d6"
        if data["status_kereta"].lower() == "dekat":
            color = "#ef4444"

        for key, card in mapping.items():
            if key in data:
                self._card_map[card].set_value(str(data[key]))
                self._card_map[card].set_led(color)

        logger.info("MQTT message [kai/acts/eta]: %s", payload)

    def closeEvent(self, event) -> None:
        if hasattr(self, "_mqtt"):
            self._mqtt.stop()
            self._mqtt.wait(2000)
        super().closeEvent(event)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f4f5f7;
            }
            QLabel {
                color: #1e293b;
                background: transparent;
            }
            QLabel#cardTitle {
                color: #64748b;
                font-size: 11px;
            }
            QLabel#cardValue {
                color: #0f172a;
                font-size: 28px;
                font-weight: bold;
            }
            QLabel#cardUnit {
                color: #2563eb;
                font-size: 13px;
            }
            QLabel#cardLed {
                border: none;
                background: transparent;
            }
            QFrame#StatusCard {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 4px;
            }
            QFrame#StatusCard:hover {
                border: 1px solid #2563eb;
                background-color: #f8fafc;
            }
            QStatusBar {
                background-color: #e2e8f0;
                color: #475569;
                border-top: 1px solid #cbd5e1;
            }
        """)

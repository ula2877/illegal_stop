import os
import math

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QGridLayout, QVBoxLayout,
    QLabel, QStatusBar, QShortcut, QMenu
)
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QPixmap, QIcon, QKeySequence, QCursor

from ui.widgets.status_card import StatusCard
from ui.dialogs.password_dialog import PasswordDialog
from utils.config_loader import load_config, BASE_DIR


LOGO_PATH = os.path.join(BASE_DIR, "resources", "images", "logo.png")
ICON_PATH = os.path.join(BASE_DIR, "resources", "images", "icon.png")


class MainWindow(QMainWindow):
    closed = pyqtSignal()
    event_updated = pyqtSignal(str)
    show_cam_popup = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        config = load_config()
        app_name = config.get("app_name")
        version = config.get("version")

        self.setWindowTitle(f"{app_name} v{version}")
        self.setMinimumSize(QSize(800, 480))
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.resize(1280, 720)

        self._card_map: dict[str, StatusCard] = {}
        self._cam_cards: dict[str, StatusCard] = {}
        self._cam_to_title: dict[str, str] = {}
        self._cam_status = {}
        self._cam_fps = {}

        self._setup_ui()
        self._setup_shortcut()

    # ======================================================
    # UI Setup
    # ======================================================

    def _setup_ui(self):
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

        config = load_config()
        cameras = config.get("cameras", {})
        cam_list = list(cameras.keys())

        self._cam_to_title = {}
        for i, cam_name in enumerate(cam_list):
            self._cam_to_title[cam_name] = f"Cam {i + 1}"

        grid = QGridLayout()
        grid.setSpacing(12)

        layout_plan = [
            ("Kereta", "-", "", 0, 0),
            ("Petugas", "-", "", 0, 1),
            ("Obstacle", "IDLE", "", 0, 2, 1, 2),
            ("Detection", "-", "", 0, 4),
            ("ETA", "-", "s", 1, 0),
            ("Jarak", "-", "km", 1, 1),
            ("Kecepatan", "-", "km/j", 1, 2, 1, 2),
            ("Heartbeat", "-", "-", 1, 4),
            ("Internet", "-", "", 2, 0),
            ("MQTT", "-", "", 2, 1),
            ("HTTPS", "-", "", 2, 2),
            ("Cam 1", "-", "", 2, 3),
            ("Cam 2", "-", "", 2, 4),
            ("Alarm", "-", "", 3, 0),
            ("CPU", "-", "%", 3, 1),
            ("RAM", "-", "%", 3, 2),
            ("Storage", "-", "%", 3, 3),
            ("Temp", "-", "\u00b0C", 3, 4),
        ]

        for item in layout_plan:
            title, value, unit, row, col, *extra = item
            rowspan = extra[0] if len(extra) > 0 else 1
            colspan = extra[1] if len(extra) > 1 else 1
            card = StatusCard(title, value, unit, self)
            grid.addWidget(card, row, col, rowspan, colspan)
            self._card_map[title] = card

        detection_card = self._card_map.get("Detection")
        if detection_card:
            detection_card.set_bars(5, "#bfc8d6")

        root_layout.addLayout(grid)
        root_layout.addStretch()

        self._status = QStatusBar(self)
        self.setStatusBar(self._status)
        self._status.showMessage("All systems nominal")

        for cam_name, title in self._cam_to_title.items():
            card = self._card_map.get(title)
            if card:
                card.setContextMenuPolicy(Qt.CustomContextMenu)
                card.customContextMenuRequested.connect(
                    lambda pos, c=card, cn=cam_name: self._show_cam_context_menu(c, cn, pos)
                )
                self._cam_cards[cam_name] = card

    def _setup_shortcut(self):
        shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        shortcut.activated.connect(self.show_admin_dialog)

    # ======================================================
    # Slots: update from workers
    # ======================================================

    def update_camera_status_text(self, cam_name, status):
        self._cam_status[cam_name] = status
        title = self._cam_to_title.get(cam_name)
        card = self._card_map.get(title) if title else None
        if card:
            card.set_value(status.upper())
            online = status.upper() == "ONLINE"
            card.set_led("#22c55e" if online else "#ff0000")

    def update_fps_text(self, cam_name, fps):
        self._cam_fps[cam_name] = f"{fps:.2f}"
        title = self._cam_to_title.get(cam_name)
        card = self._card_map.get(title) if title else None
        if card:
            card.set_unit(f"fps:{fps:.1f}")

    def update_cpu(self, value):
        card = self._card_map.get("CPU")
        if card:
            card.set_value(f"{value}")
            cfg = load_config()
            th = cfg.get("cpu_usage_threshold", 90)
            self._set_card_alert(card, self.custom_round(value) >= th)

    def update_ram(self, value):
        card = self._card_map.get("RAM")
        if card:
            card.set_value(f"{value}")
            cfg = load_config()
            th = cfg.get("ram_usage_threshold", 90)
            self._set_card_alert(card, self.custom_round(value) >= th)

    def update_datetime(self, text):
        card = self._card_map.get("Heartbeat")
        if card:
            card.set_value(text[11:])
            card.set_unit(text[:6] + text[8:10])

    def advance_detection_bars(self):
        card = self._card_map.get("Detection")
        if not card or not hasattr(card, "_bars"):
            return
        self._detection_bar_count = getattr(self, "_detection_bar_count", 0) + 1
        if self._detection_bar_count > len(card._bars):
            self._detection_bar_count = 0
        card.fill_bars(self._detection_bar_count)

    def update_internet_status(self, status):
        card = self._card_map.get("Internet")
        if card:
            card.set_value(status.upper())
            online = status.lower() == "online"
            card.set_led("#22c55e" if online else "#ff0000")

    def update_https_status(self, status):
        card = self._card_map.get("HTTPS")
        if card:
            card.set_value(status.upper())
            card.set_led("#28a745" if status.lower() == "online" else "#ff0000")

    RESET_CARDS = ["Kereta", "ETA", "Jarak", "Kecepatan"]

    def update_mqtt_status(self, status):
        card = self._card_map.get("MQTT")
        if card:
            card.set_value(status.upper())
            online = status.lower() == "online"
            card.set_led("#28a745" if online else "#ff0000")

        if not online:
            for title in self.RESET_CARDS:
                c = self._card_map.get(title)
                if c:
                    c.set_value("-")
                    c.set_led("#bfc8d6")
            kereta = self._card_map.get("Kereta")
            if kereta:
                kereta.set_card_bg(None)

    def on_mqtt_message(self, data):
        is_dekat = str(data.get("status_kereta", "")).lower() == "dekat"

        kereta_card = self._card_map.get("Kereta")
        if kereta_card and "status_kereta" in data:
            kereta_card.set_value(str(data["status_kereta"]).upper())
            kereta_card.set_led("#ffc107" if is_dekat else "#bfc8d6")
            kereta_card.set_card_bg("#ffc107" if is_dekat else None)

        mapping = {
            "eta": ("ETA", "#ef4444" if is_dekat else "#bfc8d6"),
            "jarak": ("Jarak", "#ef4444" if is_dekat else "#bfc8d6"),
            "kecepatan": ("Kecepatan", "#ef4444" if is_dekat else "#bfc8d6"),
        }

        for key, (card_title, color) in mapping.items():
            if key in data:
                card = self._card_map.get(card_title)
                if card:
                    card.set_value(str(data[key]).upper())
                    card.set_led(color)

    def update_serial_status(self, text):
        card = self._card_map.get("Alarm")
        if card:
            connected = text.upper().startswith("CONNECTED")
            card.set_value("OK" if connected else "DC")
            card.set_led("#22c55e" if connected else "#ff0000")

    def update_storage(self, free, total, used_percent):
        card = self._card_map.get("Storage")
        if card:
            card.set_value(f"{used_percent:.0f}")
            cfg = load_config()
            th = cfg.get("disk_usage_threshold", 90)
            self._set_card_alert(card, self.custom_round(used_percent) >= th)

    def custom_round(self, n):
        if n - int(n) > 0.5:
            return math.ceil(n)
        else:
            return math.floor(n)

    # ======================================================
    # Detection card logic
    # ======================================================

    def update_temp(self, value):
        card = self._card_map.get("Temp")
        if card:
            card.set_value(f"{value:.0f}")
            cfg = load_config()
            th = cfg.get("temp_usage_threshold", 70)
            self._set_card_alert(card, self.custom_round(value) >= th)

    def update_heartbeat_timestamp(self):
        from datetime import datetime
        now = datetime.now()
        card = self._card_map.get("Heartbeat")
        if card:
            card.set_value(now.strftime("%H:%M:%S"))
            card.set_unit(now.strftime("%d-%m-%y"))

    def update_obstacle_status(self, zone: str):
        card = self._card_map.get("Obstacle")
        if not card:
            return
        if not zone:
            card.set_value("IDLE")
            card.set_led("#bfc8d6")
            card.set_card_bg(None)
            return
        z = zone.lower()
        if "danger" in z:
            card.set_value("DANGER")
            card.set_led("#ff0000")
            card.set_card_bg("#ff0000")
        elif "warning" in z:
            card.set_value("WARNING")
            card.set_led("#ffc107")
            card.set_card_bg("#ffc107")
        elif "save" in z:
            card.set_value("SAVE")
            card.set_led("#22c55e")
            card.set_card_bg("#22c55e")
        else:
            card.set_value("IDLE")
            card.set_led("#bfc8d6")
            card.set_card_bg(None)

    def _set_card_alert(self, card, alert: bool):
        card.set_led("#ff0000" if alert else "#22c55e")

    def update_petugas_status(self, status: str):
        card = self._card_map.get("Petugas")
        if card:
            card.set_value(status.upper())
            if status.upper() == "-":
                card.set_led("#bfc8d6")
                card.set_card_bg(None)
            else:
                card.set_led("#28a745" if status.lower() == "siaga" else "#ff0000")
                card.set_card_bg("#28a745" if status.lower() == "siaga" else "#ff0000")

    def _show_cam_context_menu(self, card, cam_name, pos):
        menu = QMenu(self)
        show_action = menu.addAction("Show Cam")
        action = menu.exec_(QCursor.pos())
        if action == show_action:
            self.show_cam_popup.emit(cam_name)

    # ======================================================
    # Window events
    # ======================================================

    def closeEvent(self, event):
        self.closed.emit()
        event.accept()

    # ======================================================
    # Admin dialog
    # ======================================================

    def show_admin_dialog(self):
        config = load_config()
        admin_hash = config.get("admin_password")

        if not admin_hash:
            from utils.logger import logger
            logger.warning("Admin password not set")
            return

        dialog = PasswordDialog(admin_hash, self)
        dialog.exec_()

    # ======================================================
    # Styles
    # ======================================================

    def _apply_styles(self):
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

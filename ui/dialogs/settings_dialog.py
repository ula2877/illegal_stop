import sys
import os
import subprocess
import yaml
import hashlib

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget,
    QGroupBox, QLabel, QLineEdit,
    QPushButton, QHBoxLayout, QMessageBox,
    QComboBox, QFormLayout, QTextEdit, QGridLayout,
    QFileDialog, QCheckBox, QSlider, QToolButton, QMenu
)
from PyQt5.QtCore import Qt

from utils.config_loader import load_config, BASE_DIR, reload_config
from utils.api_tester import test_api_request
from utils.mqtt_tester import test_mqtt_connection
from utils.logger import logger


class SettingsDialog(QDialog):
    """
    Application settings dialog with multiple tabs.
    """

    SIDES = ["left", "middle", "right"]

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Settings")
        self.resize(900, 500)

        self.config = load_config()

        self._setup_ui()

    # ======================================================
    # UI SETUP
    # ======================================================

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general_tab(), "Umum")
        self.tabs.addTab(self._build_detection_tab(), "Detection")
        self.tabs.addTab(self._build_camera_tab(), "Camera")
        self.tabs.addTab(self._build_api_tab(), "API")
        self.tabs.addTab(self._build_mqtt_tab(), "MQTT")
        self.tabs.addTab(self._build_log_evidence_tab(), "Log Evidence")
        self.tabs.addTab(self._build_maintenance_tab(), "Maintenance")
        self.tabs.addTab(self._build_security_tab(), "Security")

        layout.addWidget(self.tabs)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        btn_restart = QPushButton("Restart App")
        btn_config = QToolButton()
        btn_config.setText("Config")
        btn_config.setPopupMode(QToolButton.InstantPopup)

        menu = QMenu(btn_config)
        menu.addAction("Import Config", self.import_config)
        menu.addAction("Export Config", self.export_config)

        btn_config.setMenu(menu)

        btn_config.setMinimumHeight(btn_restart.sizeHint().height())
        btn_config.setStyleSheet("""
            QToolButton {
                padding: 6px 12px;
            }
            QToolButton::menu-indicator {
                image: none;
                width: 0px;
            }
        """)

        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")

        btn_restart.clicked.connect(self.restart_app)
        btn_save.clicked.connect(self.save_all)
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_restart)
        btn_layout.addWidget(btn_config)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    # ======================================================
    # TAB: GENERAL
    # ======================================================

    def _build_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Informasi Lokasi")
        g = QVBoxLayout(group)

        self.input_lokasi = QLineEdit(self.config.get("lokasi", ""))
        self.input_alamat = QLineEdit(self.config.get("alamat", ""))
        self.input_kode = QLineEdit(self.config.get("kode_jpl", ""))

        # Tambahan koordinat
        koordinat = self.config.get("koordinat_jpl", {})
        self.input_lat = QLineEdit(str(koordinat.get("lat", "")))
        self.input_lon = QLineEdit(str(koordinat.get("lon", "")))

        for label, widget in (
            ("Lokasi", self.input_lokasi),
            ("Alamat", self.input_alamat),
            ("Kode JPL", self.input_kode),
            ("Latitude", self.input_lat),
            ("Longitude", self.input_lon),
        ):
            g.addWidget(QLabel(label))
            g.addWidget(widget)

        layout.addWidget(group)
        layout.addStretch()
        return tab
    # ======================================================
    # TAB: SECURITY
    # ======================================================

    def _build_security_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Change Admin Password")
        g = QVBoxLayout(group)

        self.old_pass = QLineEdit()
        self.new_pass = QLineEdit()
        self.confirm_pass = QLineEdit()

        for w in (self.old_pass, self.new_pass, self.confirm_pass):
            w.setEchoMode(QLineEdit.Password)

        for label, widget in (
            ("Old password", self.old_pass),
            ("New password", self.new_pass),
            ("Confirm password", self.confirm_pass),
        ):
            g.addWidget(QLabel(label))
            g.addWidget(widget)

        layout.addWidget(group)
        layout.addStretch()
        return tab

    # ======================================================
    # TAB: API
    # ======================================================

    def _build_api_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ========================
        # Form API config
        # ========================
        group = QGroupBox("API Configuration")
        g = QFormLayout(group)

        self.input_api = QLineEdit(self.config.get("api", ""))
        self.input_api_key = QLineEdit(self.config.get("api_key", ""))
        self.input_product_key = QLineEdit(self.config.get("product_key", ""))

        g.addRow("API URL", self.input_api)
        g.addRow("API Key", self.input_api_key)
        g.addRow("Product Key", self.input_product_key)

        layout.addWidget(group)

        # ========================
        # Button Test
        # ========================
        btn_layout = QHBoxLayout()

        self.btn_test_api = QPushButton("Test Request")
        self.btn_test_api.clicked.connect(self.test_api_request)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_test_api)

        layout.addLayout(btn_layout)

        # ========================
        # Rich text output
        # ========================
        log_group = QGroupBox("Response / Log")
        log_layout = QVBoxLayout(log_group)

        self.api_log = QTextEdit()
        self.api_log.setReadOnly(True)
        self.api_log.setPlaceholderText("Response dari server akan muncul di sini...")

        log_layout.addWidget(self.api_log)

        layout.addWidget(log_group)

        layout.addStretch()
        return tab

    def test_api_request(self):
        self.api_log.clear()

        url = self.input_api.text().strip()
        api_key = self.input_api_key.text().strip()
        product_key = self.input_product_key.text().strip()

        logs = test_api_request(url, product_key, api_key)

        for line in logs:
            if line.startswith("ERROR"):
                self.api_log.append(f"<span style='color:red'>{line}</span>")
            else:
                self.api_log.append(line)

    # ======================================================
    # TAB: MQTT
    # ======================================================

    def _build_mqtt_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ========================
        # Publish config
        # ========================
        group = QGroupBox("MQTT Publish Configuration")
        g = QFormLayout(group)

        self.mqtt_broker = QLineEdit(self.config.get("mqtt_broker", ""))
        self.mqtt_port = QLineEdit(str(self.config.get("mqtt_port", "")))
        self.mqtt_username = QLineEdit(self.config.get("mqtt_username", ""))
        self.mqtt_password = QLineEdit(self.config.get("mqtt_password", ""))
        self.mqtt_topic_pub = QLineEdit(self.config.get("mqtt_topic_pub", ""))

        g.addRow("Broker", self.mqtt_broker)
        g.addRow("Port", self.mqtt_port)
        g.addRow("Username", self.mqtt_username)
        g.addRow("Password", self.mqtt_password)
        g.addRow("Topic Publish", self.mqtt_topic_pub)

        layout.addWidget(group)

        # ========================
        # Subscribe config
        # ========================
        sub_group = QGroupBox("MQTT Subscribe Configuration")
        sg = QFormLayout(sub_group)

        self.mqtt_sub_broker = QLineEdit(self.config.get("mqtt_sub_broker", ""))
        self.mqtt_sub_port = QLineEdit(str(self.config.get("mqtt_sub_port", "")))
        self.mqtt_sub_username = QLineEdit(self.config.get("mqtt_sub_username", ""))
        self.mqtt_sub_password = QLineEdit(self.config.get("mqtt_sub_password", ""))
        self.mqtt_topic_sub = QLineEdit(self.config.get("mqtt_topic_sub", ""))

        sg.addRow("Broker", self.mqtt_sub_broker)
        sg.addRow("Port", self.mqtt_sub_port)
        sg.addRow("Username", self.mqtt_sub_username)
        sg.addRow("Password", self.mqtt_sub_password)
        sg.addRow("Topic Subscribe", self.mqtt_topic_sub)

        layout.addWidget(sub_group)

        # ========================
        # Button Test
        # ========================
        btn_layout = QHBoxLayout()

        self.btn_test_mqtt = QPushButton("Test MQTT Connection")
        self.btn_test_mqtt.clicked.connect(self.test_mqtt_connection)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_test_mqtt)

        layout.addLayout(btn_layout)

        # ========================
        # Rich text output
        # ========================
        log_group = QGroupBox("Response / Log")
        log_layout = QVBoxLayout(log_group)

        self.mqtt_log = QTextEdit()
        self.mqtt_log.setReadOnly(True)
        self.mqtt_log.setPlaceholderText("Response dari broker akan muncul di sini...")

        log_layout.addWidget(self.mqtt_log)

        layout.addWidget(log_group)

        layout.addStretch()
        return tab

    def test_mqtt_connection(self):
        self.mqtt_log.clear()

        mqtt_broker = self.mqtt_broker.text().strip()
        mqtt_port = self.mqtt_port.text().strip()
        mqtt_username = self.mqtt_username.text().strip()
        mqtt_password = self.mqtt_password.text().strip()
        mqtt_topic_pub = self.mqtt_topic_pub.text().strip()

        logs = test_mqtt_connection(mqtt_broker, mqtt_port, mqtt_username, mqtt_password, mqtt_topic_pub)

        for line in logs:
            if line.startswith("ERROR"):
                self.mqtt_log.append(f"<span style='color:red'>{line}</span>")
            else:
                self.mqtt_log.append(line)


    # ======================================================
    # TAB: DETECTION
    # ======================================================

    def _build_detection_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ========================
        # Detection Settings
        # ========================
        group = QGroupBox("Detection Settings")
        grid = QGridLayout(group)

        defaults = {
            "confidence": 0.35,
            "alpha": 0.6,
            "device": "cpu",
            "iou": 0.5,
            "n_data": 2,
            "speed_threshold": 10.0,
            "stop_threshold": 10.0,
            "area_overlap_threshold": 0.1,
            "frame_skip": 100,
        }

        self.det_inputs = {}

        col_count = 3
        row = 0
        col = 0

        for key, default in defaults.items():
            label = QLabel(key.replace("_", " ").title())
            inp = QLineEdit(str(self.config.get(key, default)))

            self.det_inputs[key] = inp

            grid.addWidget(label, row * 2, col)
            grid.addWidget(inp, row * 2 + 1, col)

            col += 1
            if col >= col_count:
                col = 0
                row += 1

        layout.addWidget(group)

        # ========================
        # Serial Settings (NEW)
        # ========================
        serial_group = QGroupBox("Serial Settings")
        serial_layout = QVBoxLayout(serial_group)

        self.input_excluded_ports = QLineEdit()

        excluded = self.config.get("excluded_ports", [])
        self.input_excluded_ports.setText(", ".join(excluded))

        serial_layout.addWidget(QLabel("Excluded Ports (comma separated)"))
        serial_layout.addWidget(self.input_excluded_ports)

        layout.addWidget(serial_group)

        layout.addStretch()
        return tab



    # ======================================================
    # TAB: CAMERA
    # ======================================================

    def _build_camera_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.cam_inputs = {}
        for cam_name in ["cam1", "cam2"]:
            group = QGroupBox(cam_name.upper())
            form = QFormLayout(group)
            cam_cfg = self.config.get("cameras", {}).get(cam_name, {})

            current_label = cam_cfg.get("label", "")
            combo_label = QComboBox()
            combo_label.addItems(["", "street", "room"])
            combo_label.setCurrentText(current_label)

            inp_source = QLineEdit(str(cam_cfg.get("source_path", "")))
            combo_side = QComboBox()
            combo_side.addItems(self.SIDES)
            combo_side.setCurrentText(cam_cfg.get("side", "middle"))

            row = QHBoxLayout()
            btn_area = QPushButton("Edit Area")
            btn_area.clicked.connect(lambda _, n=cam_name: self.edit_area(n))
            row.addStretch()
            row.addWidget(btn_area)

            form.addRow("Label", combo_label)
            form.addRow("Source", inp_source)
            form.addRow("Side", combo_side)
            form.addRow(row)

            self.cam_inputs[cam_name] = {"label": combo_label, "source": inp_source, "side": combo_side}
            layout.addWidget(group)

        layout.addStretch()
        return tab

    def edit_area(self, cam_name):
        self.hide()

        from ui.dialogs.area_dialog import AreaDialog
        camera_manager = self.parent().app.cameras.get(cam_name)
        if camera_manager is None:
            QMessageBox.critical(self, "Error", f"Camera '{cam_name}' tidak ditemukan.")
            self.show()
            return

        dlg = AreaDialog(
            cam_name=cam_name,
            camera_manager=camera_manager,
            parent=self.parent(),
            settings_dialog=self,
        )
        dlg.exec_()

    # ======================================================
    # TAB: LOG EVIDENCE
    # ======================================================

    def _build_log_evidence_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Log Evidence Settings")
        form = QFormLayout(group)

        # Durasi penyimpanan evidence
        self.combo_evidence_duration = QComboBox()
        self.combo_evidence_duration.addItems(["5", "10", "15"])
        self.combo_evidence_duration.setCurrentText(
            str(self.config.get("evidence_duration_minutes", 5))
        )

        # Periode hapus otomatis
        self.combo_evidence_retention = QComboBox()
        self.combo_evidence_retention.addItems(["1", "3", "7"])
        self.combo_evidence_retention.setCurrentText(
            str(self.config.get("evidence_retention_days", 3))
        )

        # Path penyimpanan
        path_layout = QHBoxLayout()
        self.input_evidence_path = QLineEdit(
            self.config.get("evidence_path", "")
        )

        self.chk_draw_detection = QCheckBox("Draw detection on recorded video")
        self.chk_draw_detection.setChecked(
            self.config.get("evidence_draw_detection", True)
        )

        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self._browse_evidence_path)

        path_layout.addWidget(self.input_evidence_path)
        path_layout.addWidget(btn_browse)

        form.addRow("Durasi Evidence (menit)", self.combo_evidence_duration)
        form.addRow("Hapus setelah (hari)", self.combo_evidence_retention)
        form.addRow("Folder Penyimpanan", path_layout)
        form.addRow("", self.chk_draw_detection)

        layout.addWidget(group)
        layout.addStretch()

        return tab


    def _browse_evidence_path(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Pilih Folder Penyimpanan Evidence",
            self.input_evidence_path.text() or os.getcwd()
        )

        if folder:
            self.input_evidence_path.setText(folder)

    # ======================================================
    # TAB: MAINTENANCE
    # ======================================================

    def _build_maintenance_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("System Threshold Settings")
        form = QFormLayout(group)

        cpu_val = self.config.get("cpu_usage_threshold", 90)
        ram_val = self.config.get("ram_usage_threshold", 90)
        disk_val = self.config.get("disk_usage_threshold", 90)

        self.slider_cpu, cpu_widget = self._create_threshold_slider(cpu_val)
        self.slider_ram, ram_widget = self._create_threshold_slider(ram_val)
        self.slider_disk, disk_widget = self._create_threshold_slider(disk_val)

        form.addRow("CPU Usage Threshold", cpu_widget)
        form.addRow("RAM Usage Threshold", ram_widget)
        form.addRow("Disk Usage Threshold", disk_widget)

        layout.addWidget(group)
        layout.addStretch()

        return tab

    def _create_threshold_slider(self, value):
        layout = QHBoxLayout()

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(int(value))

        label = QLabel(f"{value}%")
        label.setFixedWidth(50)

        slider.valueChanged.connect(lambda v: label.setText(f"{v}%"))

        layout.addWidget(slider)
        layout.addWidget(label)

        container = QWidget()
        container.setLayout(layout)

        return slider, container

    # ======================================================
    # SAVE ALL SETTINGS
    # ======================================================

    def save_all(self):
        # config = load_config()
        config = self.config.copy()

        config["lokasi"] = self.input_lokasi.text()
        config["alamat"] = self.input_alamat.text()
        config["kode_jpl"] = self.input_kode.text()

        try:
            config["koordinat_jpl"] = {
                "lat": float(self.input_lat.text()),
                "lon": float(self.input_lon.text())
            }
        except ValueError:
            QMessageBox.warning(self, "Error", "Koordinat harus berupa angka")
            return

        config["api"] = self.input_api.text()
        config["api_key"] = self.input_api_key.text()
        config["product_key"] = self.input_product_key.text()

        # =========================
        # MQTT Publish settings
        # =========================
        try:
            config["mqtt_broker"] = self.mqtt_broker.text().strip()
            config["mqtt_port"] = int(self.mqtt_port.text().strip())
            config["mqtt_username"] = self.mqtt_username.text().strip()
            config["mqtt_password"] = self.mqtt_password.text().strip()
            config["mqtt_topic_pub"] = self.mqtt_topic_pub.text().strip()
        except ValueError:
            QMessageBox.warning(self, "Error", "MQTT publish port harus berupa angka")
            return

        # =========================
        # MQTT Subscribe settings
        # =========================
        try:
            config["mqtt_sub_broker"] = self.mqtt_sub_broker.text().strip()
            config["mqtt_sub_port"] = int(self.mqtt_sub_port.text().strip())
            config["mqtt_sub_username"] = self.mqtt_sub_username.text().strip()
            config["mqtt_sub_password"] = self.mqtt_sub_password.text().strip()
            config["mqtt_topic_sub"] = self.mqtt_topic_sub.text().strip()
        except ValueError:
            QMessageBox.warning(self, "Error", "MQTT subscribe port harus berupa angka")
            return

        # =========================
        # Serial settings
        # =========================
        raw = self.input_excluded_ports.text()
        ports = [p.strip() for p in raw.split(",") if p.strip()]
        config["excluded_ports"] = ports

        # =========================
        # Log evidence settings
        # =========================
        config["evidence_duration_minutes"] = int(
            self.combo_evidence_duration.currentText()
        )

        config["evidence_retention_days"] = int(
            self.combo_evidence_retention.currentText()
        )

        config["evidence_path"] = self.input_evidence_path.text().strip()
        config["evidence_draw_detection"] = self.chk_draw_detection.isChecked()

        # =========================
        # Maintenance thresholds
        # =========================
        try:
            config["cpu_usage_threshold"] = self.slider_cpu.value()
            config["ram_usage_threshold"] = self.slider_ram.value()
            config["disk_usage_threshold"] = self.slider_disk.value()
        except ValueError:
            QMessageBox.warning(self, "Error", "Maintenance threshold invalid")
            return

        try:
            for k, w in self.det_inputs.items():
                v = w.text().strip()
                if k == "device":
                    config[k] = v
                elif k == "n_data":
                    config[k] = int(v)
                else:
                    config[k] = float(v)
        except ValueError:
            QMessageBox.warning(self, "Error", "Detection values invalid")
            return

        # =========================
        # Camera settings
        # =========================
        labels = {}
        for cam_name, inputs in self.cam_inputs.items():
            label = inputs["label"].currentText().strip()
            if label:
                if label in labels:
                    QMessageBox.warning(self, "Error", f"Label '{label}' sudah dipakai di {labels[label]}. Pilih label yang berbeda.")
                    return
                labels[label] = cam_name

            source = inputs["source"].text().strip()
            if source.isdigit():
                source = int(source)
            config.setdefault("cameras", {})
            config["cameras"].setdefault(cam_name, {})
            config["cameras"][cam_name]["label"] = label
            config["cameras"][cam_name]["source_path"] = source
            config["cameras"][cam_name]["side"] = inputs["side"].currentText()

        if any([self.old_pass.text(), self.new_pass.text(), self.confirm_pass.text()]):
            old_hash = hashlib.sha256(self.old_pass.text().encode()).hexdigest()
            if old_hash != config.get("admin_password"):
                QMessageBox.warning(self, "Error", "Old password wrong")
                return
            if self.new_pass.text() != self.confirm_pass.text():
                QMessageBox.warning(self, "Error", "Password mismatch")
                return
            config["admin_password"] = hashlib.sha256(self.new_pass.text().encode()).hexdigest()

        path = os.path.join(BASE_DIR, "resources", "config.yaml")
        with open(path, "w") as f:
            yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)

        reload_config()
        QMessageBox.information(self, "OK", "Settings saved")

    # ======================================================
    # RESTART
    # ======================================================

    def restart_app(self):
        reply = QMessageBox.question(
            self,
            "Restart Application",
            "Aplikasi akan ditutup dan dijalankan ulang.\nLanjutkan?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self.accept()
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)


    def export_config(self):
        src = os.path.join(BASE_DIR, "resources", "config.yaml")

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Config",
            "config.yaml",
            "YAML Files (*.yaml)"
        )

        if not path:
            return

        with open(src, "r") as fsrc:
            data = fsrc.read()

        with open(path, "w") as fdst:
            fdst.write(data)

        QMessageBox.information(self, "OK", "Config exported")


    def import_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Config",
            "",
            "YAML Files (*.yaml)"
        )

        if not path:
            return

        dst_path = os.path.join(BASE_DIR, "resources", "config.yaml")

        try:
            with open(dst_path, "r") as f:
                current_cfg = yaml.safe_load(f) or {}

            with open(path, "r") as f:
                imported_cfg = yaml.safe_load(f) or {}

            # overwrite hanya key yang ada di import
            # kecuali version
            for key, value in imported_cfg.items():
                if key == "version":
                    continue
                current_cfg[key] = value

            with open(dst_path, "w") as f:
                yaml.safe_dump(
                    current_cfg,
                    f,
                    sort_keys=False,
                    allow_unicode=True
                )

            self.config = load_config()

            QMessageBox.information(
                self,
                "OK",
                "Config imported. Restart app to apply."
            )

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Import failed:\n{e}")

import os
import cv2
import yaml
import numpy as np

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QPushButton, QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap

from utils.config_loader import load_config, BASE_DIR
from utils.logger import logger


class AreaDialog(QDialog):
    """
    Dialog for editing polygon areas per camera.
    Receives live frames from CameraManager.
    """

    def __init__(self, cam_name, camera_manager, parent=None, settings_dialog=None):
        super().__init__(parent)

        self.cam_name = cam_name
        self.camera_manager = camera_manager
        self.settings_dialog = settings_dialog

        self.setWindowTitle(f"Edit Area - {cam_name}")
        self.setWindowState(self.windowState() | Qt.WindowMaximized)

        # Editor state
        self.edit_mode = None
        self.temp_points = []
        self.last_frame = None
        self.display_rect = None

        self.config = load_config()
        cameras = self.config.get("cameras", {})
        self.camera_cfg = cameras.get(cam_name)
        if self.camera_cfg is None:
            logger.error(f"Camera '{cam_name}' not found in config")
            QMessageBox.critical(self, "Error", f"Camera '{cam_name}' tidak ditemukan di konfigurasi.")
            self.reject()
            return
        self.areas = self.camera_cfg.get("areas", {})

        # UI
        self._setup_ui()

        # Connect camera stream
        self.camera_manager.frame_ready.connect(self.on_frame)

    # ======================================================
    # UI
    # ======================================================

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background: black;")
        layout.addWidget(self.video_label, 1)

        self.area_buttons = {
            "danger": QPushButton("Add/Edit Area Danger"),
            "warning1": QPushButton("Add/Edit Area Warning 1"),
            "warning2": QPushButton("Add/Edit Area Warning 2"),
            "save1": QPushButton("Add/Edit Area Save 1"),
            "save2": QPushButton("Add/Edit Area Save 2"),
        }

        btn_layout = QHBoxLayout()
        for name, btn in self.area_buttons.items():
            btn.clicked.connect(lambda _, n=name: self.toggle_edit(n))
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)

    # ======================================================
    # Frame from CameraManager
    # ======================================================

    def on_frame(self, cam_name, frame):
        if cam_name != self.cam_name:
            return
        if not isinstance(frame, np.ndarray):
            return

        frame = frame.copy()
        self.last_frame = frame

        h, w = frame.shape[:2]

        # Draw saved areas
        for name, points in self.areas.items():
            if self.edit_mode == name:
                continue

            pts = [(int(x * w), int(y * h)) for x, y in points]
            if len(pts) >= 2:
                pts = np.array(pts, np.int32)
                cv2.polylines(
                    frame,
                    [pts],
                    True,
                    self.get_area_color(name),
                    2
                )

        # Draw temporary edit points
        if self.edit_mode:
            for x, y in self.temp_points:
                cv2.circle(frame, (x, y), 5, (255, 255, 255), -1)

            if len(self.temp_points) >= 3:
                pts = np.array(self.temp_points, np.int32)
                cv2.polylines(frame, [pts], True, (255, 255, 255), 2)

        self._render_frame(frame)

    # ======================================================
    # Rendering
    # ======================================================

    def _render_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w

        image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)

        scaled = pixmap.scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.video_label.setPixmap(scaled)

        # Store real render rect for precise click mapping
        lw, lh = self.video_label.width(), self.video_label.height()
        pw, ph = scaled.width(), scaled.height()

        x_offset = (lw - pw) // 2
        y_offset = (lh - ph) // 2

        self.display_rect = (x_offset, y_offset, pw, ph)

    # ======================================================
    # Precise mouse mapping
    # ======================================================

    def mousePressEvent(self, event):
        if not self.edit_mode:
            return
        if event.button() != Qt.LeftButton:
            return
        if not self.display_rect or self.last_frame is None:
            return

        lx, ly, lw, lh = self.display_rect

        pos = self.video_label.mapFrom(self, event.pos())
        x, y = pos.x(), pos.y()

        if not (lx <= x <= lx + lw and ly <= y <= ly + lh):
            return

        rel_x = (x - lx) / lw
        rel_y = (y - ly) / lh

        fh, fw = self.last_frame.shape[:2]
        px = int(rel_x * fw)
        py = int(rel_y * fh)

        self.temp_points.append((px, py))

    # ======================================================
    # Button logic
    # ======================================================

    def toggle_edit(self, area_name):
        if self.edit_mode == area_name:
            self.save_area(area_name)
            return

        self.edit_mode = area_name
        self.temp_points = []

        for name, btn in self.area_buttons.items():
            if name == area_name:
                btn.setText(f"Simpan {name}")
            else:
                btn.setEnabled(False)

    def save_area(self, area_name):
        if len(self.temp_points) < 3:
            QMessageBox.warning(self, "Error", "Minimal 3 titik")
            return

        h, w = self.last_frame.shape[:2]
        norm_points = [[x / w, y / h] for x, y in self.temp_points]

        self.config["cameras"][self.cam_name].setdefault("areas", {})
        self.config["cameras"][self.cam_name]["areas"][area_name] = norm_points

        path = os.path.join(BASE_DIR, "resources", "config.yaml")
        with open(path, "w") as f:
            yaml.safe_dump(self.config, f, sort_keys=False)

        self.areas = self.config["cameras"][self.cam_name]["areas"]

        self.edit_mode = None
        self.temp_points.clear()

        for name, btn in self.area_buttons.items():
            btn.setEnabled(True)
            btn.setText(f"Add/Edit Area {name}")

        logger.info(f"{area_name} saved")

    # ======================================================
    # Helpers
    # ======================================================

    def get_area_color(self, name):
        name = name.lower()
        if "danger" in name:
            return (0, 0, 255)
        if "warning" in name:
            return (0, 255, 255)
        if "save" in name:
            return (0, 255, 0)
        return (255, 255, 255)

    # ======================================================
    # Close behavior
    # ======================================================

    def closeEvent(self, event):
        try:
            self.camera_manager.frame_ready.disconnect(self.on_frame)
        except Exception:
            pass

        # Return focus to SettingsDialog (Camera tab)
        if self.settings_dialog:
            self.settings_dialog.show()
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            self.settings_dialog.tabs.setCurrentIndex(2)

        event.accept()

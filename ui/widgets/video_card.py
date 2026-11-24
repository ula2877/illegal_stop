import time
import cv2
import numpy as np

from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap

from utils.config_loader import load_config


class VideoCard(QFrame):
    """
    Video display widget per camera.
    Responsible for:
    - Rendering frame
    - Drawing detection overlay
    - Drawing area polygons
    - Showing status text
    """

    def __init__(self, cam_name: str):
        super().__init__()

        self.cam_name = cam_name
        self.config = load_config()

        cam_cfg = self.config.get("cameras", {}).get(cam_name, {})
        self._label = cam_cfg.get("label", "")

        self._last_draw = 0.0
        self.max_ui_fps = 12

        self.detections = []

        self._setup_ui()

    # ======================================================
    # UI
    # ======================================================

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        display = self._label if self._label else self.cam_name.upper()
        self.title = QLabel(display)
        self.title.setStyleSheet("color: #ccc; font-weight: bold;")
        layout.addWidget(self.title)

        self.label = QLabel("Waiting for stream...")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background:#111;color:#aaa;")
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.label)

    # ======================================================
    # Public slots
    # ======================================================

    def update_frame(self, cam_name: str, frame):
        if cam_name != self.cam_name or frame is None:
            return

        # UI FPS limiter (important for performance)
        now = time.time()
        if now - self._last_draw < 1.0 / self.max_ui_fps:
            return
        self._last_draw = now

        frame = frame.copy()

        # self._draw_areas(frame)
        # self._draw_detections(frame)
        self._render_frame(frame)

    def update_detections(self, detections: list):
        self.detections = detections

    def reload_config(self):
        self.config = load_config()
        cam_cfg = self.config.get("cameras", {}).get(self.cam_name, {})
        label = cam_cfg.get("label", "")
        if label:
            self.title.setText(label)

    # ======================================================
    # Drawing
    # ======================================================

    def _draw_areas(self, frame):
        cameras = self.config.get("cameras", {})
        areas = cameras.get(self.cam_name, {}).get("areas", {})

        h, w = frame.shape[:2]

        for name, points in areas.items():
            if len(points) < 2:
                continue

            pts = np.array(
                [(int(x * w), int(y * h)) for x, y in points],
                dtype=np.int32
            )

            cv2.polylines(
                frame,
                [pts],
                isClosed=True,
                color=self._get_zone_color(name),
                thickness=2
            )

    def _draw_detections(self, frame):
        for det in self.detections:
            x1, y1, x2, y2 = map(int, det["bbox"])
            zone = det.get("zone", "")
            color = self._get_zone_color(zone)

            speed = det.get("speed")
            stop_dur = det.get("stop_duration")
            side = det.get("side", "middle")

            # =========================
            # Bounding box
            # =========================
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # =========================
            # Centroid sesuai side
            # =========================
            bw = abs(x2 - x1)
            bh = abs(y2 - y1)

            cx_base = (x1 + x2) / 2
            cy_base = (y1 + y2) / 2

            if side == "left":
                cx = int(cx_base + bw / 4)
                cy = int(cy_base - bh / 4)
            elif side == "right":
                cx = int(cx_base - bw / 4)
                cy = int(cy_base - bh / 4)
            else:
                cx = int(cx_base)
                cy = int(cy_base)

            cv2.circle(frame, (cx, cy), 3, color, -1)

            # =========================
            # Text lines
            # =========================
            # lines = [
            #     f"ID: {det['id']}",
            #     f"{speed:.1f} px/s" if speed is not None else "",
            #     f"STOP: {stop_dur:.1f}s" if stop_dur and stop_dur > 0 else ""
            # ]

            lines = [
                f"{det['id']}",
                f"{speed:.1f} px/s" if speed is not None else "",
                f"STOP: {stop_dur:.1f}s" if stop_dur and stop_dur > 0 else ""
            ]
            self._draw_multiline_text(frame, x1, y1, lines, color)


    # ======================================================
    # Rendering
    # ======================================================

    def _render_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape

        image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)

        self.label.setPixmap(
            pixmap.scaled(
                self.label.size(),
                Qt.KeepAspectRatio,
                Qt.FastTransformation
            )
        )

    # ======================================================
    # Helpers
    # ======================================================

    def _draw_multiline_text(self, frame, x, y, lines, color):
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 2
        line_height = 20
        padding = 2

        lines = [l for l in lines if l]
        if not lines:
            return

        total_height = len(lines) * line_height
        start_y = y - total_height - padding * 2
        if start_y < 0:
            start_y = y + padding

        for i, text in enumerate(lines):
            y_text = start_y + padding + (i + 1) * line_height - 5
            cv2.putText(
                frame,
                text,
                (x + padding, y_text),
                font,
                font_scale,
                color,
                thickness,
                cv2.LINE_AA
            )

    def _get_zone_color(self, zone: str):
        z = zone.lower()
        if "danger" in z:
            return (0, 0, 255)
        if "warning" in z:
            return (0, 255, 255)
        if "save" in z:
            return (0, 255, 0)
        return (255, 255, 255)

    # ======================================================
    # Status UI
    # ======================================================

    def set_status(self, status: str):
        if status == "ONLINE":
            return

        if status == "CONNECTING":
            self.show_placeholder("CONNECTING...")
        elif status == "OFFLINE":
            self.show_placeholder("OFFLINE")
        elif status == "ERROR":
            self.show_placeholder("ERROR")

    def show_placeholder(self, text="NO SIGNAL"):
        self.label.setPixmap(QPixmap())
        self.label.setText(text)

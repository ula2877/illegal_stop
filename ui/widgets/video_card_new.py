import time
import cv2
import numpy as np

from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap

from utils.config_loader import load_config
import os
from datetime import datetime

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

        # UI render control
        self._last_draw = 0.0
        self.max_ui_fps = 12

        # Runtime data
        self.detections = []

        self.video_writer = None
        self.record_start_time = 0

        self._setup_ui()

    # ======================================================
    # UI
    # ======================================================

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.title = QLabel(self.cam_name.upper())
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

        raw_frame = frame.copy()
        draw_frame = frame.copy()

        cam_cfg = self.config.get("cameras", {}).get(self.cam_name, {})
        is_room = cam_cfg.get("label", "") == "room"

        # gambar overlay hanya di draw_frame
        if not is_room:
            self._draw_areas(draw_frame)
        self._draw_detections(draw_frame)

        self._ensure_writer(raw_frame)

        if self.video_writer:
            if self.config.get("evidence_draw_detection", True):
                self.video_writer.write(draw_frame)
            else:
                self.video_writer.write(raw_frame)

        # UI tetap menampilkan overlay
        self._render_frame(draw_frame)

    def update_detections(self, detections: list):
        self.detections = detections

    def reload_config(self):
        self.config = load_config()

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
            print(det)

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

    def _ensure_writer(self, frame):
        cfg = self.config

        duration_min = cfg.get("evidence_duration_minutes", 5)
        base_path = cfg.get("evidence_path", "evidence")
        retention_days = cfg.get("evidence_retention_days", 3)

        os.makedirs(base_path, exist_ok=True)

        self._cleanup_old_files(base_path, retention_days)

        cam_path = os.path.join(base_path, self.cam_name)
        os.makedirs(cam_path, exist_ok=True)

        now = time.time()

        # rotate file
        if (
            self.video_writer is None
            or now - self.record_start_time > duration_min * 60
        ):
            if self.video_writer:
                self.video_writer.release()

            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = os.path.join(cam_path, f"{ts}.mp4")

            h, w = frame.shape[:2]

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.video_writer = cv2.VideoWriter(
                filename,
                fourcc,
                12,  # fps sederhana dulu
                (w, h),
            )

            self.record_start_time = now

    def _cleanup_old_files(self, base_path, retention_days):
        if retention_days <= 0:
            return

        now = time.time()
        max_age = retention_days * 24 * 3600
        
        for root, _, files in os.walk(base_path):
            for f in files:
                if not f.lower().endswith((".mp4", ".avi", ".mkv")):
                    continue

                full_path = os.path.join(root, f)

                try:
                    file_time = os.path.getmtime(full_path)
                    if now - file_time > max_age:
                        os.remove(full_path)
                        print("Deleted old evidence:", full_path)
                except Exception as e:
                    print("Cleanup error:", e)

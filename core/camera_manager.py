import cv2
import time
import os
from datetime import datetime
import threading

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from utils.config_loader import load_config
from utils.logger import logger


class CameraManager(QThread):
    """
    Camera worker (QThread) responsible for:
    - Capturing frames from camera/video source
    - Auto reconnect if source disconnected
    - Limiting UI FPS for performance
    - Sending selected frames to DetectionWorker
    - Drawing overlay
    - Recording evidence video
    """

    frame_ready = pyqtSignal(str, object)
    fps_updated = pyqtSignal(str, float)
    status_changed = pyqtSignal(str, str)

    def __init__(
        self,
        name: str,
        source=0,
        frame_skip: int = 0,
        reconnect_interval: float = 2.0,
        max_ui_fps: int = 12,
        parent=None,
        detection_worker=None,
        petugas_worker=None
    ):
        super().__init__(parent)

        # hanya naming (tidak ubah behavior)
        self.setObjectName(f"Camera-{name}")

        self.name = name
        self.source = source
        self.frame_skip = frame_skip
        self.reconnect_interval = reconnect_interval
        self.max_ui_fps = max_ui_fps
        self.detection_worker = detection_worker
        self.petugas_worker = petugas_worker

        self._running = False
        self._cap = None

        self.config = load_config()
        self.video_writer = None
        self.record_start_time = 0
        self.fps = 8

        self._latest_frame = None
        self._recording_enabled = True
        self.latest_detections = []
        self._pose_landmarks = None

    # ======================================================
    # Thread entry
    # ======================================================

    def run(self):
        # fix Dummy thread name (tidak ubah logic)
        threading.current_thread().name = self.objectName()

        self._running = True
        logger.info(f"{self.name}: Camera thread started")

        while self._running:
            try:
                self.status_changed.emit(self.name, "CONNECTING")

                self._cap = cv2.VideoCapture(self.source)

                if not self._cap.isOpened():
                    logger.warning(f"{self.name}: Failed to open source")
                    self.status_changed.emit(self.name, "OFFLINE")
                    self._safe_release()
                    time.sleep(self.reconnect_interval)
                    continue

                # ambil FPS asli kamera/video
                self.fps = self._cap.get(cv2.CAP_PROP_FPS)

                # fallback jika kamera tidak mengembalikan FPS valid
                if self.fps <= 0 or self.fps > 120:
                    self.fps = 25

                logger.info(f"{self.name}: Camera ONLINE")
                self.status_changed.emit(self.name, "ONLINE")

                self._capture_loop()

            except Exception as e:
                logger.error(f"{self.name}: Camera loop error: {e}", exc_info=True)

            time.sleep(self.reconnect_interval)

        logger.info(f"{self.name}: Camera thread stopped")
        self._safe_release()

    # ======================================================
    # Main capture loop
    # ======================================================

    def _capture_loop(self):
        prev_fps_time = time.time()
        prev_emit_time = 0.0

        frame_counter = 0
        processed_counter = 0

        logger.info(f"{self.name}: Capture loop started")

        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                logger.warning(f"{self.name}: Frame read failed")
                self.status_changed.emit(self.name, "OFFLINE")
                self._safe_release()
                break

            frame_counter += 1
            now = time.time()

            if self.detection_worker:
                if frame_counter % (self.frame_skip + 1) == 0:
                    self.detection_worker.enqueue(self.name, frame.copy())

            if self.petugas_worker:
                self.petugas_worker.enqueue(self.name, frame.copy())

            frame_out = frame.copy()
            cfg = load_config()

            cam_cfg = cfg.get("cameras", {}).get(self.name, {})
            is_room = cam_cfg.get("label", "") == "room"

            if cfg.get("evidence_draw_detection", True):
                if not is_room:
                    self._draw_areas(frame_out)
                self._draw_detections(frame_out)
                self._draw_pose_landmarks(frame_out)

            self._latest_frame = frame_out

            if self._recording_enabled:
                self._ensure_writer(frame_out)
                if self.video_writer:
                    self.video_writer.write(frame_out)
            elif self.video_writer:
                self.video_writer.release()
                self.video_writer = None
                self.record_start_time = 0

            if now - prev_emit_time >= 1.0 / self.max_ui_fps:
                self.frame_ready.emit(self.name, frame_out)
                prev_emit_time = now

            processed_counter += 1
            if now - prev_fps_time >= 1.0:
                fps = processed_counter / (now - prev_fps_time)
                self.fps_updated.emit(self.name, round(fps, 2))
                prev_fps_time = now
                processed_counter = 0

            time.sleep(0.025)

        logger.info(f"{self.name}: Capture loop stopped")

    # ======================================================
    # Public control
    # ======================================================

    def stop(self):
        logger.info(f"{self.name}: Stopping camera...")
        self._running = False
        self.wait()

        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        logger.info(f"{self.name}: Camera fully stopped")

    # ======================================================
    # Detection update
    # ======================================================

    def update_detections(self, cam_name, detections):
        if cam_name == self.name:
            self.latest_detections = detections

    def update_pose_landmarks(self, cam_name, landmarks):
        if cam_name == self.name:
            self._pose_landmarks = landmarks

    # ======================================================
    # Drawing helpers
    # ======================================================

    def _draw_areas(self, frame):
        cfg = load_config()
        cameras = cfg.get("cameras", {})
        areas = cameras.get(self.name, {}).get("areas", {})

        h, w = frame.shape[:2]

        for name, points in areas.items():
            if len(points) < 2:
                continue

            pts = np.array(
                [(int(x * w), int(y * h)) for x, y in points],
                dtype=np.int32
            )

            # cv2.polylines(frame, [pts], True, (255, 255, 255), 2)
            cv2.polylines(
                frame,
                [pts],
                isClosed=True,
                color=self._get_zone_color(name),
                thickness=2
            )

    def _draw_detections(self, frame):
        for det in self.latest_detections:
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
                # cx = int(cx_base + bw / 4)
                # cy = int(cy_base - bh / 4)
                cx = max([x1, x2])
                cy = min([y1, y2])
            elif side == "right":
                # cx = int(cx_base - bw / 4)
                # cy = int(cy_base - bh / 4)
                cx = min([x1, x2])
                cy = min([y1, y2])
            else:
                cx = int(cx_base)
                cy = int(cy_base)

            cv2.circle(frame, (cx, cy), 3, (255,255,255), -1)

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
                f"{det['label']}",
                f"{stop_dur:.1f}s" if stop_dur and stop_dur > 0 else ""
            ]
            # print(det)

            # self._draw_multiline_text(frame, x1, y1, lines, color)
            self._draw_multiline_text(frame, x1, y1, lines, (255,255,255))

    def _draw_pose_landmarks(self, frame):
        if self._pose_landmarks is None:
            return

        xy, conf = self._pose_landmarks
        if xy is None or len(xy) == 0:
            return

        h, w = frame.shape[:2]
        kpts = xy.cpu().numpy() if hasattr(xy, 'cpu') else xy
        kpts_conf = conf.cpu().numpy() if hasattr(conf, 'cpu') else conf

        skeleton = [
            (0, 1), (0, 2), (1, 3), (2, 4),
            (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
            (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16),
        ]

        # draw skeleton lines
        for start_idx, end_idx in skeleton:
            if start_idx >= len(kpts) or end_idx >= len(kpts):
                continue
            if kpts_conf[start_idx] < 0.5 or kpts_conf[end_idx] < 0.5:
                continue
            x1, y1 = int(kpts[start_idx][0]), int(kpts[start_idx][1])
            x2, y2 = int(kpts[end_idx][0]), int(kpts[end_idx][1])
            cv2.line(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # draw keypoints
        for i, kp in enumerate(kpts):
            if kpts_conf[i] < 0.5:
                continue
            x, y = int(kp[0]), int(kp[1])
            cv2.circle(frame, (x, y), 4, (0, 255, 0), -1)
            cv2.circle(frame, (x, y), 4, (255, 255, 255), 1)

    def _get_zone_color(self, zone: str):
        z = zone.lower()
        if "danger" in z:
            return (0, 0, 255)
        if "warning" in z:
            return (0, 255, 255)
        if "save" in z:
            return (0, 255, 0)
        return (255, 255, 255)

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

    # ======================================================
    # Evidence writer
    # ======================================================

    def _cleanup_old_files(self, base_path, retention_days):
        if retention_days <= 0:
            return

        now = time.time()
        max_age = retention_days * 24 * 3600

        for root, _, files in os.walk(base_path):
            for f in files:
                if not f.lower().endswith(".mp4"):
                    continue

                path = os.path.join(root, f)
                try:
                    if now - os.path.getmtime(path) > max_age:
                        os.remove(path)
                except Exception:
                    pass

    def _ensure_writer(self, frame):
        self.config = load_config()
        cfg = self.config

        duration_min = cfg.get("evidence_duration_minutes", 5)
        retention_days = cfg.get("evidence_retention_days", 3)
        base_path = cfg.get("evidence_path", "evidence")

        video_root = os.path.join(base_path, "video")
        cam_path = os.path.join(video_root, self.name)
        os.makedirs(cam_path, exist_ok=True)

        self._cleanup_old_files(video_root, retention_days)

        now = time.time()

        # ukuran asli frame
        h, w = frame.shape[:2]

        if (
            self.video_writer is None
            or now - self.record_start_time > duration_min * 60
        ):
            if self.video_writer:
                self.video_writer.release()

            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = os.path.join(cam_path, f"{ts}.mp4")

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

            self.video_writer = cv2.VideoWriter(
                filename,
                fourcc,
                self.fps,  # gunakan FPS asli kamera
                (w, h),
            )

            if not self.video_writer.isOpened():
                logger.error(f"VideoWriter failed to open: {filename}")

            self.record_start_time = now

        return frame

    # ======================================================
    # Utils
    # ======================================================

    def set_recording(self, active: bool):
        if active != self._recording_enabled:
            self._recording_enabled = active
            logger.info(f"{self.name}: recording {'enabled' if active else 'disabled'}")
            if not active and self.video_writer:
                self.video_writer.release()
                self.video_writer = None
                self.record_start_time = 0

    def save_snapshot(self, reason: str):
        if self._latest_frame is None:
            return None

        cfg = load_config()
        base_path = cfg.get("evidence_path", "evidence")
        snapshot_dir = os.path.join(base_path, "snapshots", self.name)
        os.makedirs(snapshot_dir, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{reason}.jpg"
        path = os.path.join(snapshot_dir, filename)

        cv2.imwrite(path, self._latest_frame)
        logger.info(f"{self.name}: snapshot saved ({reason}): {path}")
        return path

    def _safe_release(self):
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

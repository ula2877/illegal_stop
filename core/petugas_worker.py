import cv2
import time
import math
import queue
import os
import threading
from collections import deque

from PyQt5.QtCore import QObject, pyqtSignal
from ultralytics import YOLO

from utils.config_loader import BASE_DIR, load_config
from utils.logger import logger


POSE_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]


class PetugasWorker(QObject):
    status_changed = pyqtSignal(str)
    pose_landmarks_ready = pyqtSignal(str, object)

    def __init__(self, frame_skip=8, max_queue=10):
        super().__init__()

        self.frame_skip = frame_skip
        self.frame_counter = {}
        self.queue = queue.Queue(maxsize=max_queue)
        self._running = False

        self._model = None

        self.confidence = 0.5
        self.speed_threshold = 5.0
        self.n_data = 5
        self.track_history = {}
        self._last_status = None

        self._active = False

    # ======================================================
    # Public API
    # ======================================================

    def enqueue(self, cam_name: str, frame):
        if not self.queue.full():
            self.queue.put((cam_name, frame))

    def start(self):
        self._running = True
        logger.info("PetugasWorker started")

        try:
            model_path = os.path.join(BASE_DIR, "resources", "models", "yolo11n-pose.pt")
            self._model = YOLO(model_path)
        except Exception as e:
            logger.error(f"PetugasWorker: failed to init YOLO pose: {e}")
            return

        t = threading.Thread(target=self._loop, daemon=True)
        t.name = "PetugasWorker"
        t.start()

    def stop(self):
        logger.info("Stopping PetugasWorker...")
        self._running = False

        self._model = None

    def set_active(self, active: bool):
        if active != self._active:
            self._active = active
            logger.info(f"PetugasWorker active={active}")
            if active:
                self.frame_counter.clear()

    # ======================================================
    # Worker Loop
    # ======================================================

    def _loop(self):
        while self._running:
            try:
                cam_name, frame = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not self._active:
                continue

            try:
                self._process(cam_name, frame)
            except Exception as e:
                logger.error(f"PetugasWorker error ({cam_name}): {e}", exc_info=True)

        logger.info("PetugasWorker loop stopped")

    # ======================================================
    # Core Processing
    # ======================================================

    def _process(self, cam_name, frame):
        self.frame_counter.setdefault(cam_name, 0)
        self.frame_counter[cam_name] += 1
        if self.frame_counter[cam_name] % (self.frame_skip + 1) != 0:
            return

        cfg = load_config()
        device = cfg.get("device", "cpu")
        results = self._model(frame, verbose=False, conf=self.confidence, device=device)[0]

        person_moving = False
        kpts_data = None

        TRACKED_KEYPOINTS = [0, 7, 8, 9, 10, 13, 14, 15, 16]

        if results.keypoints is not None and len(results.keypoints) > 0:
            kpts = results.keypoints[0]
            xy = kpts.xy[0] if kpts.xy is not None else None
            conf = kpts.conf[0] if kpts.conf is not None else None

            if xy is not None:
                kpts_data = (xy, conf)

                self.pose_landmarks_ready.emit(cam_name, kpts_data)

                for kid in TRACKED_KEYPOINTS:
                    if kid >= len(xy):
                        continue
                    if conf is not None and conf[kid] < 0.5:
                        continue
                    cx, cy = int(xy[kid][0]), int(xy[kid][1])
                    speed = self._update_speed(kid, (cx, cy))
                    if speed is not None and speed > self.speed_threshold:
                        person_moving = True
        else:
            self.track_history.clear()

        status = "siaga" if person_moving else "tiada"
        if status != self._last_status:
            self._last_status = status
            logger.info(f"PetugasWorker: {status}")
            self.status_changed.emit(status)

    def _update_speed(self, tid, center):
        now = time.time()
        self.track_history.setdefault(tid, deque(maxlen=self.n_data))
        hist = self.track_history[tid]
        hist.append((center, now))

        if len(hist) < 2:
            return None

        speeds = []
        for i in range(1, len(hist)):
            (x1, y1), t1 = hist[i - 1]
            (x2, y2), t2 = hist[i]
            dt = t2 - t1
            if dt > 0:
                speeds.append(math.hypot(x2 - x1, y2 - y1) / dt)

        return sum(speeds) / len(speeds) if speeds else None

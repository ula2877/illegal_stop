import os
import cv2
import time
import queue
import threading
import math
from collections import deque
from datetime import datetime
import numpy as np

from PyQt5.QtCore import QObject, pyqtSignal
from ultralytics import YOLO

from utils.config_loader import load_config, BASE_DIR
from core.area_evaluator import AreaEvaluator
from utils.logger import logger


class DetectionWorker(QObject):
    """
    DetectionWorker handles:
    - YOLO tracking
    - Zone evaluation
    - Speed & stop calculation
    - Illegal stop event detection
    - Snapshot evidence
    """

    detections_ready = pyqtSignal(str, list)   # cam_name, detections
    event_updated = pyqtSignal(str)           # zone or None
    api_event = pyqtSignal(str, str, str)
    vehicle_in_danger_changed = pyqtSignal(bool)  # True if any vehicle in danger zone

    def __init__(self, max_queue: int = 10):
        super().__init__()

        cfg = load_config()

        # Detection config
        self.confidence = float(cfg.get("confidence", 0.3))
        self.iou = float(cfg.get("iou", 0.5))
        self.device = cfg.get("device", "cpu")

        # Behavior config
        self.n_data = int(cfg.get("n_data", 5))
        self.speed_threshold = float(cfg.get("speed_threshold", 10.0))
        self.stop_threshold = float(cfg.get("stop_threshold", 10.0))
        self.area_threshold = float(cfg.get("area_overlap_threshold", 0.1))

        # Queue
        self.queue = queue.Queue(maxsize=max_queue)
        self._running = False

        # Per-camera states
        self.models = {}
        self.area_evaluators = {}
        self.track_history = {}
        self.stop_state = {}

        # Event state (UI)
        self._last_event_time = 0.0
        self._last_emitted_zone = None

        # Unique event cache: (cam, id, zone)
        self.snapshot_history = set()

        self.obstacles = []
        self.obstacle_expired = 30  # detik (jangan 15 menit dulu)
        self.obstacle_distance_threshold = 50  # pixel

        # Event state tambahan
        self.event_hold = 7
        self._event_active_until = 0
        self._last_event_zone = None

        self.min_event_duration = 0
        self._event_start_time = 0

        # Vehicle in danger zone (regardless of stop status)
        self._cameras_in_danger = set()
        self._vehicle_in_danger = False

    # ======================================================
    # Public API
    # ======================================================

    def enqueue(self, cam_name: str, frame):
        if not self.queue.full():
            self.queue.put((cam_name, frame))
        else:
            logger.warning(f"Queue full, dropping frame from {cam_name}")

    def start(self):
        self._running = True
        logger.info("DetectionWorker started")

        t = threading.Thread(target=self._loop, daemon=True)
        t.name = "DetectionWorker"  # 🔥 FIX Dummy
        t.start()

    def stop(self):
        logger.info("Stopping DetectionWorker...")
        self._running = False

    # ======================================================
    # Worker Loop
    # ======================================================

    def _loop(self):
        logger.info("Detection loop running")

        while self._running:
            try:
                cam_name, frame = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                detections = self._process(cam_name, frame)

                if detections is not None:
                    self.detections_ready.emit(cam_name, detections)

            except Exception as e:
                logger.error(f"Detection error ({cam_name}): {e}", exc_info=True)

        logger.info("Detection loop stopped")

    # ======================================================
    # Core Processing
    # ======================================================

    def _process(self, cam_name: str, frame):
        model = self._get_model(cam_name)
        evaluator = self._get_evaluator(cam_name)

        result = model.track(
            frame,
            persist=True,
            verbose=False,
            conf=self.confidence,
            iou=self.iou,
            device=self.device
        )[0]

        if result.boxes is None:
            self._update_vehicle_in_danger(cam_name, False, [])
            return []

        detections = []
        event_candidates = []  # [(track_id, zone)]

        h, w = frame.shape[:2]

        for box in result.boxes:
            det = self._parse_box(box, w, h, model, evaluator, cam_name)
            if det is None:
                continue

            detections.append(det)

            if det['label'] == "train":
                continue

            if det["stop_duration"] is not None and det["stop_duration"] >= self.stop_threshold:
                event_candidates.append((det["id"], det["zone"]))

        self._handle_event(cam_name, frame, detections, event_candidates)

        self._cleanup(cam_name, detections)

        self._update_vehicle_in_danger(cam_name, True, detections)

        return detections

    # ======================================================
    # Parsing single detection
    # ======================================================

    def _parse_box(self, box, w, h, model, evaluator, cam_name):
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        track_id = int(box.id[0]) if box.id is not None else -1

        # Normalize bbox for area evaluator
        bbox_norm = [x1 / w, y1 / h, x2 / w, y2 / h]
        zone = evaluator.evaluate(bbox_norm)

        if zone is None:
            return None

        # =========================
        # Centroid based on side
        # =========================
        cfg = load_config()
        cam_cfg = cfg["cameras"].get(cam_name, {})
        side = cam_cfg.get("side", "middle").lower()

        bw = abs(x2 - x1)
        bh = abs(y2 - y1)

        cx_base = (x1 + x2) / 2
        cy_base = (y1 + y2) / 2

        if side == "left":
            # cx = cx_base + bw / 4
            # cy = cy_base - bh / 4
            cx = max([x1, x2])
            cy = min([y1, y2])
        elif side == "right":
            # cx = cx_base - bw / 4
            # cy = cy_base - bh / 4
            cx = min([x1, x2])
            cy = min([y1, y2])
        else:  # middle (default)
            cx = cx_base
            cy = cy_base

        # =========================
        # Speed & stop
        # =========================
        speed = self._update_speed(cam_name, track_id, (cx, cy))
        stop_duration = None

        if speed is not None:
            stop_duration = self._update_stop_duration(cam_name, track_id, speed)

        return {
            "bbox": [x1, y1, x2, y2],
            "cls": cls,
            "conf": conf,
            "id": track_id,
            "label": model.names.get(cls, str(cls)),
            "zone": zone,
            "speed": speed,
            "stop_duration": stop_duration,
            "side": side 
        }


    # ======================================================
    # Event handling
    # ======================================================

    def _handle_event(self, cam_name, frame, detections, candidates):
        now = time.time()
        event_id, event_zone = self._resolve_event(candidates)

        # =========================
        # FILTER: minimal durasi event (anti noise)
        # =========================
        if event_zone:
            if self._event_start_time == 0:
                self._event_start_time = now

            # jika belum cukup lama → anggap belum ada event
            if now - self._event_start_time < self.min_event_duration:
                event_zone = None
        else:
            self._event_start_time = 0

        # =========================
        # FALLBACK KE OBSTACLE
        # =========================
        if not event_zone and self.obstacles:
            best = sorted(
                self.obstacles,
                key=lambda x: self._zone_priority(x["zone"])
            )[0]

            event_zone = best["zone"]

        # =========================
        # Update event window (HOLD)
        # =========================
        if event_zone:
            self._last_event_time = now

            # optional: dynamic hold berdasarkan zone
            if "danger" in event_zone:
                hold = self.event_hold + 3
            elif "warning" in event_zone:
                hold = self.event_hold
            else:
                hold = max(3, self.event_hold - 2)

            self._event_active_until = now + hold
            self._last_event_zone = event_zone

        # =========================
        # OBSTACLE MATCHING (jika event asli, bukan fallback)
        # =========================
        if event_id is not None and event_zone:
            for det in detections:
                if det["id"] != event_id:
                    continue

                cx = int((det["bbox"][0] + det["bbox"][2]) / 2)
                cy = int((det["bbox"][1] + det["bbox"][3]) / 2)

                matched = False

                for obs in self.obstacles:
                    ox, oy = obs["center"]
                    dist = math.hypot(cx - ox, cy - oy)

                    if dist < self.obstacle_distance_threshold:
                        # cocok → refresh expired
                        obs["expired_at"] = now + self.obstacle_expired
                        matched = True
                        break

                if not matched:
                    self.obstacles.append({
                        "center": (cx, cy),
                        "zone": event_zone,
                        "expired_at": now + self.obstacle_expired
                    })

                break  # hanya 1 object utama

        # =========================
        # CLEANUP OBSTACLE (expired)
        # =========================
        self.obstacles = [
            obs for obs in self.obstacles
            if obs["expired_at"] > now
        ]

        # =========================
        # Optional: percepat clear jika tidak ada kandidat sama sekali
        # =========================
        if not candidates:
            if now - self._last_event_time > self.event_hold:
                self._event_active_until = 0

        # =========================
        # Emit ke UI (pakai HOLD)
        # =========================
        if now < self._event_active_until:
            if self._last_event_zone != self._last_emitted_zone:
                logger.info(f"Event detected: cam={cam_name}, zone={self._last_event_zone}, id={event_id}")
                self.event_updated.emit(self._last_event_zone)
                self._last_emitted_zone = self._last_event_zone
        else:
            if self._last_emitted_zone is not None:
                logger.info("Event cleared")
                self.event_updated.emit(None)
                self._last_emitted_zone = None

        # =========================
        # Snapshot (tetap seperti semula)
        # =========================
        if event_id is not None and event_zone:
            for det in detections:
                if det["id"] != event_id:
                    continue

                key = (cam_name, event_id, event_zone)
                if key not in self.snapshot_history:
                    logger.info(f"Saving snapshot: {key}")
                    self._save_snapshot(cam_name, frame, det, event_zone)
                    self.snapshot_history.add(key)
        logger.debug(f"Obstacles: {self.obstacles}")

    # ======================================================
    # Speed & Stop
    # ======================================================

    def _update_speed(self, cam, tid, center):
        now = time.time()

        self.track_history.setdefault(cam, {})
        self.track_history[cam].setdefault(tid, deque(maxlen=self.n_data))

        hist = self.track_history[cam][tid]
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

    def _update_stop_duration(self, cam, tid, speed):
        now = time.time()

        self.stop_state.setdefault(cam, {})
        state = self.stop_state[cam].setdefault(tid, {"start": None, "duration": 0.0})

        if speed <= self.speed_threshold:
            if state["start"] is None:
                state["start"] = now
            state["duration"] = now - state["start"]
        else:
            state["start"] = None
            state["duration"] = 0.0

        return state["duration"]

    # ======================================================
    # Helpers
    # ======================================================

    def _get_model(self, cam):
        if "_shared" not in self.models:
            path = os.path.join(BASE_DIR, "resources", "models", "best.pt")
            logger.info(f"Loading YOLO model from {path}")
            self.models["_shared"] = YOLO(path)
        return self.models["_shared"]

    def _get_evaluator(self, cam):
        if cam not in self.area_evaluators:
            cfg = load_config()
            cam_cfg = cfg["cameras"].get(cam, {})
            areas = cam_cfg.get("areas", {})
            logger.info(f"Initializing area evaluator for {cam}")
            self.area_evaluators[cam] = AreaEvaluator(areas, self.area_threshold)
        return self.area_evaluators[cam]

    def _resolve_event(self, candidates):
        if not candidates:
            return None, None

        best_id, best_zone = sorted(
            candidates,
            key=lambda x: self._zone_priority(x[1])
        )[0]

        return best_id, best_zone

    def _zone_priority(self, zone):
        z = zone.lower()
        if "danger" in z:
            return 0
        if "warning" in z:
            return 1
        if "save" in z:
            return 2
        return 99

    def _cleanup(self, cam, detections):
        active_ids = {d["id"] for d in detections}

        self._cleanup_state(self.track_history, cam, active_ids)
        self._cleanup_state(self.stop_state, cam, active_ids)

        self.snapshot_history = {
            (c, tid, z)
            for (c, tid, z) in self.snapshot_history
            if not (c == cam and tid not in active_ids)
        }

    def _cleanup_state(self, state_dict, cam, active_ids):
        if cam not in state_dict:
            return

        for tid in list(state_dict[cam].keys()):
            if tid not in active_ids:
                del state_dict[cam][tid]

    def _update_vehicle_in_danger(self, cam_name, has_detections, detections):
        this_cam_in_danger = False
        if has_detections:
            this_cam_in_danger = any(
                d.get("zone") and "danger" in d["zone"].lower()
                for d in detections
                if d.get("label") != "train"
            )

        was_in_danger = cam_name in self._cameras_in_danger
        if this_cam_in_danger and not was_in_danger:
            self._cameras_in_danger.add(cam_name)
        elif not this_cam_in_danger and was_in_danger:
            self._cameras_in_danger.discard(cam_name)

        overall = len(self._cameras_in_danger) > 0
        if overall != self._vehicle_in_danger:
            self._vehicle_in_danger = overall
            self.vehicle_in_danger_changed.emit(overall)

    def _save_snapshot(self, cam_name, frame, det, zone):
        cfg = load_config()

        base_path = cfg.get("evidence_path", "evidence")
        snapshot_dir = os.path.join(base_path, "snapshots", cam_name)
        os.makedirs(snapshot_dir, exist_ok=True)

        img = frame.copy()

        cameras = cfg.get("cameras", {})
        areas = cameras.get(cam_name, {}).get("areas", {})

        h, w = img.shape[:2]

        for name, points in areas.items():
            if len(points) < 2:
                continue

            pts = np.array(
                [(int(x * w), int(y * h)) for x, y in points],
                dtype=np.int32
            )

            cv2.polylines(
                img,
                [pts],
                isClosed=True,
                color=self._get_zone_color(name),
                thickness=2
            )

        x1, y1, x2, y2 = map(int, det["bbox"])

        if "danger" in zone.lower():
            color = (0, 0, 255)
        elif "warning" in zone.lower():
            color = (0, 255, 255)
        else:
            color = (0, 255, 0)

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        spd = det.get("speed") or 0
        stp = det.get("stop_duration") or 0
        label = f'ID:{det["id"]} SPD:{spd:.1f} STP:{stp:.1f}'

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{zone}.jpg"

        path = os.path.join(snapshot_dir, filename)
        cv2.imwrite(path, img)

        logger.info(f"Snapshot saved: {path}")

        self.api_event.emit(
            self.map_zone_type(zone),
            self.map_vehicle_type(det['label']),
            path
        )

    def map_vehicle_type(self, label):
        if label.lower() in ["bicycle", "motorbike"]:        # sepeda, motor
            return "R2"
        elif label.lower() in ["car", "bus", "truck"]:   # mobil, bus, truk
            return "R4"
        else:
            return "LAIN"

    def map_zone_type(self, label):
        if "warning" in label.lower():
            return "KUNING"
        elif "danger" in label.lower():
            return "MERAH"
        elif "save" in label.lower():
            return "HIJAU"

    def _get_zone_color(self, zone: str):
        z = zone.lower()
        if "danger" in z:
            return (0, 0, 255)
        if "warning" in z:
            return (0, 255, 255)
        if "save" in z:
            return (0, 255, 0)
        return (255, 255, 255)

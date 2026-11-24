import threading

from core.system_monitor import SystemMonitor
from core.camera_manager import CameraManager
from core.internet_worker import InternetWorker
from core.datetime_worker import DateTimeWorker
from core.serial_worker import SerialWorker
from core.detection_worker import DetectionWorker
from core.api_worker import ApiWorker
from core.mqtt_worker import MQTTWorker
from core.mqtt_sub_worker import MqttSubWorker
from core.petugas_worker import PetugasWorker

from ui.main_window import MainWindow
from ui.dialogs.camera_popup import CameraPopup
from utils.config_loader import load_config
from utils.logger import logger


class App:
    """
    Main application controller.
    Responsible for:
    - Creating UI
    - Spawning workers
    - Routing signals between workers and UI
    - Managing lifecycle
    """

    def __init__(self):
        # =========================
        # UI
        # =========================
        self.window = MainWindow()
        self.window.app = self  # used by SettingsDialog
        self._popups = {}

        # =========================
        # Config
        # =========================
        self.config = load_config()

        # =========================
        # Mode state
        # =========================
        self._mode = "common"  # "common" | "special"
        self._petugas_status = "tiada"
        self._vehicle_in_danger = False
        self._last_detection_zone = None

        # =========================
        # Petugas alert state
        # =========================
        self._petugas_alert_timer = None
        self._petugas_alert_sent = False

        # =========================
        # Detection Worker (shared) dan petugas worker
        # =========================
        self.detector = DetectionWorker(max_queue=10)
        self.petugas_worker = PetugasWorker()

        # =========================
        # Cameras
        # =========================
        self.cameras = self._init_cameras()
        self._room_cameras = [
            cam for cam_name, cam in self.cameras.items()
            if self.config.get("cameras", {}).get(cam_name, {}).get("label") == "room"
        ]
        for cam in self._room_cameras:
            cam.set_recording(False)

        self._street_cameras = [
            cam for cam_name, cam in self.cameras.items()
            if self.config.get("cameras", {}).get(cam_name, {}).get("label") == "street"
        ]

        self._special_danger_event_sent = False

        # =========================
        # Other workers
        # =========================
        self.api_worker = ApiWorker()

        self.mqtt_worker = MQTTWorker()
        self.mqtt_sub_worker = MqttSubWorker()

        self.system_monitor = SystemMonitor(api_worker=self.api_worker)
        self.internet = InternetWorker()
        self.datetime_worker = DateTimeWorker()

        excluded_ports = self.config.get("excluded_ports", [])
        self.serial_worker = SerialWorker(
            baudrate=9600,
            excluded_ports=excluded_ports
        )

        # =========================
        # Wire signals
        # =========================
        self._connect_workers()

        # =========================
        # Shutdown hook
        # =========================
        self.window.closed.connect(self.shutdown)

    # ======================================================
    # Init helpers
    # ======================================================

    def _init_cameras(self):
        cameras = {}

        for cam_name, cam_cfg in self.config.get("cameras", {}).items():
            source = cam_cfg.get("source_path", 0)
            if cam_cfg.get("label") == "street":
                cam = CameraManager(
                    name=cam_name,
                    source=source,
                    frame_skip=self.config.get("frame_skip", 5),
                    detection_worker=self.detector
                )
            else:
                cam = CameraManager(
                    name=cam_name,
                    source=source,
                    frame_skip=self.config.get("frame_skip", 5),
                    petugas_worker=self.petugas_worker
                )

            cam.frame_ready.connect(self.on_frame_ready)
            cam.fps_updated.connect(self.on_fps_updated)
            cam.status_changed.connect(self.on_status_changed)

            cameras[cam_name] = cam

        return cameras

    def _connect_workers(self):
        # =========================
        # System monitor
        # =========================
        self.system_monitor.cpu_updated.connect(self.window.update_cpu)
        self.system_monitor.ram_updated.connect(self.window.update_ram)
        self.system_monitor.storage_updated.connect(self.window.update_storage)
        self.system_monitor.temp_updated.connect(self.window.update_temp)

        # =========================
        # Network & time
        # =========================
        self.internet.status_changed.connect(self.window.update_internet_status)
        self.mqtt_sub_worker.message_received.connect(self.window.update_heartbeat_timestamp)

        # =========================
        # Serial
        # =========================
        self.serial_worker.status_changed.connect(self.window.update_serial_status)

        # =========================
        # Detection
        # =========================
        self.detector.detections_ready.connect(self._route_detections)
        self.detector.event_updated.connect(self.on_event_updated)
        self.detector.api_event.connect(self.api_event)
        self.detector.detections_ready.connect(lambda *a: self.window.advance_detection_bars())
        self.detector.vehicle_in_danger_changed.connect(self._on_vehicle_in_danger_changed)

        # =========================
        # Petugas
        # =========================
        if self.petugas_worker:
            self.petugas_worker.status_changed.connect(self._on_petugas_status_changed)
            self.petugas_worker.status_changed.connect(self.window.update_petugas_status)
            self.petugas_worker.pose_landmarks_ready.connect(self._route_pose_landmarks)

        # =========================
        # MQTT Subscribe
        # =========================
        self.mqtt_sub_worker.status_changed.connect(self.window.update_mqtt_status)
        self.mqtt_sub_worker.status_changed.connect(self._on_mqtt_sub_status_for_mode)
        self.mqtt_sub_worker.message_received.connect(self.window.on_mqtt_message)
        self.mqtt_sub_worker.message_received.connect(self._on_mqtt_message_for_mode)

        # =========================
        # API / HTTPS
        # =========================
        self.api_worker.ping_status.connect(self.window.update_https_status)

        # =========================
        # Popup
        # =========================
        self.window.show_cam_popup.connect(self._show_cam_popup)

    # ======================================================
    # Controller routing
    # ======================================================

    def on_frame_ready(self, cam_name, frame):
        popup = self._popups.get(cam_name)
        if popup:
            popup.video_card.update_frame(cam_name, frame)

    def on_fps_updated(self, cam_name, fps):
        self.window.update_fps_text(cam_name, fps)

    def on_status_changed(self, cam_name, status):
        self.window.update_camera_status_text(cam_name, status)

    def _route_detections(self, cam_name, detections):
        cam = self.cameras.get(cam_name)
        if cam:
            cam.update_detections(cam_name, detections)

    def _route_pose_landmarks(self, cam_name, landmarks):
        cam = self.cameras.get(cam_name)
        if cam:
            cam.update_pose_landmarks(cam_name, landmarks)

    def _show_cam_popup(self, cam_name):
        if cam_name in self._popups and self._popups[cam_name].isVisible():
            self._popups[cam_name].raise_()
            self._popups[cam_name].activateWindow()
            return

        popup = CameraPopup(cam_name)
        popup.destroyed.connect(lambda: self._popups.pop(cam_name, None))
        popup.show()
        self._popups[cam_name] = popup

    def on_event_updated(self, zone):
        self._last_detection_zone = zone
        self._evaluate_obstacle()

    # ======================================================
    # Mode management
    # ======================================================

    def _set_mode(self, mode):
        if self._mode != mode:
            self._mode = mode
            logger.info(f"Mode changed to: {mode}")
            self.petugas_worker.set_active(mode == "special")
            for cam in self._room_cameras:
                cam.set_recording(mode == "special")
            if mode == "common":
                self.window.update_petugas_status("-")
                self._cancel_petugas_alert()
                self._petugas_alert_sent = False
            self._evaluate_obstacle()

    def _evaluate_obstacle(self):
        if self._mode == "special":
            zone = self._last_detection_zone
            if zone and "danger" in zone.lower():
                obstacle_zone = zone
            elif self._vehicle_in_danger:
                obstacle_zone = "danger"
            else:
                obstacle_zone = None
        else:
            obstacle_zone = self._last_detection_zone

        danger_from_special = (
            self._mode == "special"
            and self._vehicle_in_danger
            and not (self._last_detection_zone and "danger" in self._last_detection_zone.lower())
        )

        if obstacle_zone and "danger" in str(obstacle_zone).lower():
            if danger_from_special and not self._special_danger_event_sent:
                self._send_special_danger_event()
                self._special_danger_event_sent = True
        else:
            self._special_danger_event_sent = False

        self.window.update_obstacle_status(obstacle_zone)
        self.mqtt_worker.update_status(obstacle_zone)
        self.serial_worker.send("1\n" if self._mode == "special" else "2\n")

    def _send_special_danger_event(self):
        for cam in self._street_cameras:
            path = cam.save_snapshot("special_danger")
            if path:
                self.api_worker.enqueue_event("MERAH", "LAIN", path)
            break

    def _on_mqtt_message_for_mode(self, data):
        status_kereta = str(data.get("status_kereta", "")).lower()
        self._set_mode("special" if status_kereta == "dekat" else "common")

    def _on_mqtt_sub_status_for_mode(self, status):
        if status.lower() != "online":
            self._set_mode("common")

    def _cancel_petugas_alert(self):
        if self._petugas_alert_timer:
            self._petugas_alert_timer.cancel()
            self._petugas_alert_timer = None

    def _send_petugas_alert_now(self):
        for cam in self._room_cameras:
            path = cam.save_snapshot("petugas_tiada")
            if path:
                self.api_worker.enqueue_petugas_alert(path)
            break
        self._petugas_alert_sent = True

    def _on_petugas_alert_timeout(self):
        self._petugas_alert_timer = None
        if self._mode == "special" and self._petugas_status == "tiada" and not self._petugas_alert_sent:
            self._send_petugas_alert_now()

    def _on_petugas_status_changed(self, status):
        self._petugas_status = status

        if status == "siaga":
            self._cancel_petugas_alert()
            self._petugas_alert_sent = False
        elif status == "tiada" and self._mode == "special" and not self._petugas_alert_sent:
            self._cancel_petugas_alert()
            self._petugas_alert_timer = threading.Timer(30.0, self._on_petugas_alert_timeout)
            self._petugas_alert_timer.daemon = True
            self._petugas_alert_timer.start()

        if self._mode == "special":
            self._evaluate_obstacle()

    def _on_vehicle_in_danger_changed(self, in_danger):
        self._vehicle_in_danger = in_danger
        if self._mode == "special":
            self._evaluate_obstacle()

    def api_event(self, zone, vehicle, path):
        self.api_worker.enqueue_event(
            zone=zone,
            vehicle=vehicle,
            image_path=path
        )

    # ======================================================
    # Lifecycle
    # ======================================================

    def run(self):
        self.window.show()

        for cam in self.cameras.values():
            cam.start()

        self.system_monitor.start()
        self.internet.start()
        self.datetime_worker.start()
        self.serial_worker.start()
        self.detector.start()
        self.api_worker.start()
        self.mqtt_worker.start()
        self.mqtt_sub_worker.start()
        if self.petugas_worker:
            self.petugas_worker.start()

    def shutdown(self):
        logger.info("Shutting down workers...")

        self._cancel_petugas_alert()

        for cam in self.cameras.values():
            cam.stop()

        self.system_monitor.stop()
        self.internet.stop()
        self.datetime_worker.stop()
        self.serial_worker.stop()
        self.detector.stop()
        self.api_worker.stop()
        self.mqtt_worker.stop()
        self.mqtt_sub_worker.stop()
        if self.petugas_worker:
            self.petugas_worker.stop()

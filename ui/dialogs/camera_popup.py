from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
from ui.widgets.video_card import VideoCard


class CameraPopup(QWidget):
    def __init__(self, cam_name: str):
        super().__init__()
        self.cam_name = cam_name
        self.setWindowTitle(cam_name.upper())
        self.setWindowFlags(Qt.Window)
        self.resize(640, 480)

        layout = QVBoxLayout(self)
        self.video_card = VideoCard(cam_name)
        layout.addWidget(self.video_card)

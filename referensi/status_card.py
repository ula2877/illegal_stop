from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class StatusCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str,
        unit: str = "",
        parent: QFrame | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._value = value
        self._unit = unit
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("StatusCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(160, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        title_label = QLabel(self._title, self)
        title_label.setObjectName("cardTitle")
        title_label.setAlignment(Qt.AlignLeft)
        f = title_label.font()
        f.setPointSize(9)
        f.setBold(False)
        title_label.setFont(f)

        self._led = QLabel(self)
        self._led.setFixedSize(12, 12)
        self._led.setObjectName("cardLed")
        self._led.setStyleSheet(
            "background-color: #bfc8d6; border-radius: 6px;"
        )

        top_layout.addWidget(title_label)
        top_layout.addStretch()
        top_layout.addWidget(self._led)

        layout.addLayout(top_layout)

        value_layout = QVBoxLayout()
        value_layout.setSpacing(0)

        value_label = QLabel(self._value, self)
        value_label.setObjectName("cardValue")
        value_label.setAlignment(Qt.AlignLeft)
        vf = value_label.font()
        vf.setPointSize(26)
        vf.setBold(True)
        value_label.setFont(vf)

        if self._unit:
            unit_label = QLabel(self._unit, self)
            unit_label.setObjectName("cardUnit")
            unit_label.setAlignment(Qt.AlignLeft)
            uf = unit_label.font()
            uf.setPointSize(11)
            unit_label.setFont(uf)
            value_layout.addWidget(value_label)
            value_layout.addWidget(unit_label)
        else:
            value_layout.addWidget(value_label)

        layout.addLayout(value_layout)
        layout.addStretch()

    def set_value(self, value: str) -> None:
        self._value = value
        label = self.findChild(QLabel, "cardValue")
        if label:
            label.setText(value)

    def set_title(self, title: str) -> None:
        self._title = title
        label = self.findChild(QLabel, "cardTitle")
        if label:
            label.setText(title)

    def set_led(self, color: str) -> None:
        self._led.setStyleSheet(
            f"background-color: {color}; border-radius: 6px;"
        )

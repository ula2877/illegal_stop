from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class StatusCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str = "-",
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

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(4)

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

        self._layout.addLayout(top_layout)

        self._value_layout = QVBoxLayout()
        self._value_layout.setSpacing(4)

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
            self._value_layout.addWidget(value_label)
            self._value_layout.addWidget(unit_label)
        else:
            self._value_layout.addWidget(value_label)

        self._layout.addLayout(self._value_layout)
        self._layout.addStretch()

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

    def set_unit(self, unit: str) -> None:
        self._unit = unit
        label = self.findChild(QLabel, "cardUnit")
        if label:
            label.setText(unit)
        else:
            value_label = self.findChild(QLabel, "cardValue")
            if value_label:
                layout = value_label.parentWidget().layout()
                unit_label = QLabel(unit, self)
                unit_label.setObjectName("cardUnit")
                unit_label.setAlignment(Qt.AlignLeft)
                uf = unit_label.font()
                uf.setPointSize(11)
                unit_label.setFont(uf)
                layout.addWidget(unit_label)

    def set_bars(self, num: int, color: str = "#bfc8d6") -> None:
        for i in reversed(range(self._value_layout.count())):
            w = self._value_layout.itemAt(i).widget()
            if w and w.objectName() in ("cardValue", "cardUnit"):
                w.hide()
        self._layout.takeAt(self._layout.count() - 1)
        self._layout.setSpacing(12)
        self._value_layout.setSpacing(0)
        self._value_layout.addStretch()
        hbox = QHBoxLayout()
        hbox.setSpacing(4)
        self._bars = []
        for _ in range(num):
            bar = QFrame(self)
            bar.setObjectName("cardBar")
            bar.setFixedHeight(12)
            bar.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            hbox.addWidget(bar)
            self._bars.append(bar)
        self._value_layout.addLayout(hbox)
        self._value_layout.addStretch()

    def fill_bars(self, count: int, filled_color: str = "#22c55e", empty_color: str = "#bfc8d6") -> None:
        for i, bar in enumerate(self._bars):
            c = filled_color if i < count else empty_color
            bar.setStyleSheet(f"background-color: {c}; border-radius: 2px;")

    def set_led(self, color: str) -> None:
        self._led.setStyleSheet(
            f"background-color: {color}; border-radius: 6px;"
        )

    def set_card_bg(self, color: str) -> None:
        if color:
            self.setStyleSheet(f"""
                QFrame#StatusCard {{
                    background-color: {color};
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    padding: 4px;
                }}
                QLabel#cardValue {{
                    color: #ffffff;
                }}
                QLabel#cardTitle {{
                    color: #ffffff;
                }}
                QLabel#cardUnit {{
                    color: #ffffff;
                }}
            """)
        else:
            self.setStyleSheet("")

import hashlib
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QHBoxLayout, QMessageBox
)


class PasswordDialog(QDialog):
    """
    Simple admin password dialog.
    If password is valid, opens SettingsDialog.
    """

    def __init__(self, expected_hash: str, parent=None):
        super().__init__(parent)

        self.expected_hash = expected_hash

        self.setWindowTitle("Admin Password")
        self.resize(300, 120)

        self._setup_ui()

    # ======================================================
    # UI
    # ======================================================

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Enter admin password:"))

        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.returnPressed.connect(self._check_password)
        layout.addWidget(self.input_password)

        btn_layout = QHBoxLayout()

        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Cancel")

        btn_ok.clicked.connect(self._check_password)
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    # ======================================================
    # Logic
    # ======================================================

    def _check_password(self):
        password = self.input_password.text()
        entered_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

        if entered_hash != self.expected_hash:
            QMessageBox.warning(self, "Error", "Wrong password")
            return

        # Close this dialog first
        self.accept()

        # Open settings dialog (modal to MainWindow)
        from ui.dialogs.settings_dialog import SettingsDialog

        settings = SettingsDialog(parent=self.parent())
        settings.exec_()

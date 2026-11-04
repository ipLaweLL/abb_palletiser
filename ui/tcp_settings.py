"""TCP/IP configuration panel shared by engineering and end-user GUIs.

The application acts as the TCP client. ABB hosts the TCP server.
Settings persist locally through Qt QSettings.
"""
import ipaddress
import socket

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

SETTINGS_ORGANIZATION = "Palletisation"
SETTINGS_APPLICATION = "ABB_Palletiser"


def _validate_ipv4(text: str, field_name: str) -> str:
    try:
        address = ipaddress.IPv4Address(text.strip())
    except ipaddress.AddressValueError as error:
        raise ValueError(f"{field_name} must be a valid IPv4 address.") from error
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        raise ValueError(f"{field_name} cannot be an unspecified or multicast address.")
    return str(address)


def detect_local_ip(target_ip: str) -> str:
    """Ask the OS which local interface it would use to reach ABB.

    UDP connect does not send a packet; it only selects the local route.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((target_ip, 9))
            return probe.getsockname()[0]
    except OSError:
        return "Unavailable (check network connection)"


class TcpSettingsTab(QWidget):
    def __init__(self, abb_client, parent=None):
        super().__init__(parent)
        self.abb_client = abb_client
        self.settings = QSettings(
            SETTINGS_ORGANIZATION, SETTINGS_APPLICATION
        )

        layout = QVBoxLayout(self)
        group = QGroupBox("TCP/IP Communication")
        form = QFormLayout(group)

        self.robot_ip = QLineEdit()
        self.robot_ip.setPlaceholderText("e.g. 192.168.125.1")
        self.robot_ip.setText(str(
            self.settings.value("tcp/abb_ip", abb_client.host)
        ))
        form.addRow("ABB controller IP:", self.robot_ip)

        self.robot_port = QSpinBox()
        self.robot_port.setRange(1, 65535)
        self.robot_port.setValue(int(
            self.settings.value("tcp/abb_port", abb_client.port)
        ))
        form.addRow("ABB TCP server port:", self.robot_port)

        self.local_ip = QLineEdit()
        self.local_ip.setPlaceholderText("Auto (recommended)")
        self.local_ip.setText(str(
            self.settings.value("tcp/local_ip", "")
        ))
        form.addRow("PC / application IP (optional):", self.local_ip)

        # Apply saved settings when the application starts, not only
        # after the user presses Save.
        self.abb_client.host = self.robot_ip.text().strip()
        self.abb_client.port = self.robot_port.value()
        self.abb_client.local_ip = self.local_ip.text().strip()

        self.detected_ip_label = QLabel()
        form.addRow("Detected PC IP for ABB route:", self.detected_ip_label)

        self.robot_ip.editingFinished.connect(self.refresh_detected_ip)
        self.refresh_detected_ip()
        layout.addWidget(group)

        note = QLabel(
            "Python connects TO the ABB controller as a TCP client. "
            "ABB must listen on the controller IP and port shown above. "
            "Leave the PC IP empty for automatic interface selection, or "
            "enter an IP assigned to this PC to bind outbound connections. "
            "Changing the PC IP does NOT start a TCP server."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        actions = QHBoxLayout()
        refresh = QPushButton("Detect PC IP")
        refresh.clicked.connect(self.refresh_detected_ip)
        actions.addWidget(refresh)

        save = QPushButton("Apply && Save")
        save.clicked.connect(self.save_settings)
        actions.addWidget(save)
        actions.addStretch()
        layout.addLayout(actions)

        self.status_label = QLabel("Settings have not been changed.")
        layout.addWidget(self.status_label)
        layout.addStretch()

    def refresh_detected_ip(self):
        target = self.robot_ip.text().strip()
        try:
            target = _validate_ipv4(target, "ABB controller IP")
        except ValueError:
            self.detected_ip_label.setText("Enter a valid ABB IP first")
            return
        self.detected_ip_label.setText(detect_local_ip(target))

    def save_settings(self):
        try:
            robot_ip = _validate_ipv4(
                self.robot_ip.text(), "ABB controller IP"
            )
            local_ip = self.local_ip.text().strip()
            if local_ip:
                local_ip = _validate_ipv4(local_ip, "PC / application IP")
                # A source address can only be used if assigned locally.
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                        probe.bind((local_ip, 0))
                except OSError as error:
                    raise ValueError(
                        f"PC IP {local_ip} cannot be bound on this machine: {error}"
                    ) from error
            port = self.robot_port.value()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid TCP/IP Settings", str(error))
            return

        self.abb_client.host = robot_ip
        self.abb_client.port = port
        self.abb_client.local_ip = local_ip

        self.settings.setValue("tcp/abb_ip", robot_ip)
        self.settings.setValue("tcp/abb_port", port)
        self.settings.setValue("tcp/local_ip", local_ip)
        self.settings.sync()
        if self.settings.status() != QSettings.NoError:
            self.status_label.setText("Warning: Could not persist settings.")
            return

        self.status_label.setText(
            f"Saved: ABB {robot_ip}:{port} | "
            f"PC: {local_ip or 'Auto'}"
        )
        self.refresh_detected_ip()

"""Read-only operator display mirroring the engineering console.

The MainWindow owns the planner, executor, and ABB connection.
This window only renders their current state; it must never send commands.
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QFrame,
)
from PySide6.QtCore import Qt

from config.products import PRODUCTS
from ui.pallet_view import Pallet3DView


class OperatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Palletisation - Operator Display")
        self.resize(1450, 880)

        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        header = QHBoxLayout()
        title = QLabel("PALLETISATION STATUS")
        font = title.font()
        font.setPointSize(15)
        font.setBold(True)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch()
        self.delivery_label = QLabel("Delivery: -")
        header.addWidget(self.delivery_label)
        layout.addLayout(header)

        self.order_label = QLabel("Order: -")
        layout.addWidget(self.order_label)

        views = QHBoxLayout()
        target_box = QGroupBox("TARGET PALLET")
        target_layout = QVBoxLayout(target_box)
        self.target_view = Pallet3DView("Target Pallet")
        target_layout.addWidget(self.target_view)
        views.addWidget(target_box)

        live_box = QGroupBox("LIVE PALLET")
        live_layout = QVBoxLayout(live_box)
        self.live_view = Pallet3DView("Live Pallet")
        live_layout.addWidget(self.live_view)
        views.addWidget(live_box)
        layout.addLayout(views, 1)

        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        self.status_label = QLabel("Status: Waiting")
        self.next_label = QLabel("Next item: -")
        self.progress_label = QLabel("Placed: 0 / 0")
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        footer_layout.addWidget(self.next_label)
        footer_layout.addWidget(self.progress_label)
        layout.addWidget(footer)

    def set_snapshot(
        self,
        *,
        slots,
        pallet_length,
        pallet_width,
        delivery_text,
        status_text,
        quantities,
        completed_count,
        current_slot,
    ):
        """Render an external snapshot without mutating execution state."""
        self.delivery_label.setText(f"Delivery: {delivery_text}")
        self.order_label.setText(
            "Order: " + "  |  ".join(
                f"{sku}: {quantities.get(sku, 0)}"
                for sku in ("20L", "10L", "1L", "4L")
            )
        )
        self.status_label.setText(status_text)
        self.progress_label.setText(
            f"Placed: {completed_count} / {len(slots)}"
        )
        if current_slot is None:
            self.next_label.setText(
                "Completed" if slots and completed_count == len(slots)
                else "Next item: -"
            )
        else:
            self.next_label.setText(
                f"Next: {PRODUCTS[current_slot.sku].name} "
                f"(slot {current_slot.id})"
            )

        self.target_view.set_data(
            slots, pallet_length, pallet_width, False
        )
        self.live_view.set_data(
            slots, pallet_length, pallet_width, True
        )

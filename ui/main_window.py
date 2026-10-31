import sys
import socket
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QGroupBox,
    QMessageBox,
    QFrame,
)


from config.products import PRODUCTS
from config.deliveries import DELIVERY_ORDERS

from planner.models import (
    PalletSlot,
    StackColumn,
    Rect,
    PlannerResult,
)

from planner.rules import can_stack
from robot.abb_client import ABBClient

from planner.new_planner import NewPalletPlanner
from planner.free_space import (
    FreeRect,
    calculate_free_rectangles,
    fitting_skus,
)
from ui.pallet_view import Pallet3DView
from execution.pallet_executor import PalletExecutor


# ============================================================
# MAIN WINDOW
# ============================================================

class MainWindow(QMainWindow):

    def __init__(
        self
    ):

        super().__init__()

        self.setWindowTitle(
            "ABB Order Based Mixed Pallet Planner"
        )

        self.resize(
            1650,
            950
        )

        self.planner = NewPalletPlanner()

        self.abb = ABBClient()

        self.executor = PalletExecutor(
            self.abb
        )

        self.slots = []

        self.current_delivery = None

        self._build_ui()

        self.load_selected_delivery()

    # ========================================================
    # BUILD UI
    # ========================================================

    def _build_ui(
        self
    ) -> None:

        root = QWidget()

        self.setCentralWidget(
            root
        )

        main_layout = (
            QVBoxLayout(
                root
            )
        )

        # ====================================================
        # TOP SECTION
        # ====================================================

        top_layout = (
            QHBoxLayout()
        )

        # ----------------------------------------------------
        # DELIVERY ORDER
        # ----------------------------------------------------

        delivery_box = (
            QGroupBox(
                "Delivery Order"
            )
        )

        delivery_grid = (
            QGridLayout(
                delivery_box
            )
        )

        self.delivery_combo = (
            QComboBox()
        )

        for index, order in enumerate(
            DELIVERY_ORDERS
        ):

            label = (

                f"{order['delivery']} "
                f"- Row {order['line']}"
            )

            self.delivery_combo.addItem(

                label,

                index
            )

        self.delivery_combo.currentIndexChanged.connect(
            self.load_selected_delivery
        )

        delivery_grid.addWidget(

            QLabel(
                "Delivery No."
            ),

            0,
            0
        )

        delivery_grid.addWidget(

            self.delivery_combo,

            0,
            1,
            1,
            3
        )

        # ----------------------------------------------------
        # QUANTITIES
        # ----------------------------------------------------

        self.quantity_inputs: Dict[
            str,
            QSpinBox
        ] = {}

        sku_order = [

            "1L",

            "4L",

            "10L",

            "20L",
        ]

        for row, sku in enumerate(

            sku_order,

            start=1

        ):

            product = (
                PRODUCTS[
                    sku
                ]
            )

            delivery_grid.addWidget(

                QLabel(
                    product.name
                ),

                row,
                0
            )

            spin = (
                QSpinBox()
            )

            spin.setRange(
                0,
                500
            )

            spin.valueChanged.connect(
                self._update_order_total
            )

            self.quantity_inputs[
                sku
            ] = spin

            delivery_grid.addWidget(

                spin,

                row,
                1
            )

        self.order_total_label = (
            QLabel(
                "Total Items: 0"
            )
        )

        delivery_grid.addWidget(

            self.order_total_label,

            5,
            0,
            1,
            2
        )

        self.free_space_label = (
            QLabel(
                "Free Floor Area: -"
            )
        )

        delivery_grid.addWidget(

            self.free_space_label,

            6,
            0,
            1,
            3
        )

        # ----------------------------------------------------
        # PALLET SETTINGS
        # ----------------------------------------------------

        pallet_box = (
            QGroupBox(
                "Pallet Settings"
            )
        )

        pallet_grid = (
            QGridLayout(
                pallet_box
            )
        )

        # LENGTH
        self.length_input = (
            QDoubleSpinBox()
        )

        self.length_input.setRange(
            100,
            5000
        )

        self.length_input.setValue(
            1300
        )

        self.length_input.setSuffix(
            " mm"
        )

        # WIDTH
        self.width_input = (
            QDoubleSpinBox()
        )

        self.width_input.setRange(
            100,
            5000
        )

        self.width_input.setValue(
            1300
        )

        self.width_input.setSuffix(
            " mm"
        )

        # HEIGHT
        self.height_input = (
            QDoubleSpinBox()
        )

        self.height_input.setRange(
            100,
            5000
        )

        self.height_input.setValue(
            1600
        )

        self.height_input.setSuffix(
            " mm"
        )

        # WEIGHT
        self.weight_input = (
            QDoubleSpinBox()
        )

        self.weight_input.setRange(
            1,
            10000
        )

        self.weight_input.setValue(
            1000
        )

        self.weight_input.setSuffix(
            " kg"
        )

        # OVERHANG
        self.overhang_input = (
            QDoubleSpinBox()
        )

        self.overhang_input.setRange(
            0,
            500
        )

        self.overhang_input.setValue(
            0
        )

        self.overhang_input.setSuffix(
            " mm"
        )

        # X GAP
        self.gap_x_input = (
            QDoubleSpinBox()
        )

        self.gap_x_input.setRange(
            0,
            500
        )

        self.gap_x_input.setValue(
            20
        )

        self.gap_x_input.setSuffix(
            " mm"
        )

        # Y GAP
        self.gap_y_input = (
            QDoubleSpinBox()
        )

        self.gap_y_input.setRange(
            0,
            500
        )

        self.gap_y_input.setValue(
            20
        )

        self.gap_y_input.setSuffix(
            " mm"
        )

        # PALLET EDGE MARGIN
        self.edge_margin_input = (
            QDoubleSpinBox()
        )

        self.edge_margin_input.setRange(
            0,
            500
        )

        self.edge_margin_input.setValue(
            20
        )

        self.edge_margin_input.setSuffix(
            " mm"
        )

        settings = [

            (
                "Length",
                self.length_input
            ),

            (
                "Width",
                self.width_input
            ),

            (
                "Max Height",
                self.height_input
            ),

            (
                "Max Weight",
                self.weight_input
            ),

            (
                "Allowed Overhang",
                self.overhang_input
            ),

            (
                "X Gap",
                self.gap_x_input
            ),

            (
                "Y Gap",
                self.gap_y_input
            ),

            (
                "Edge Margin",
                self.edge_margin_input
            ),
        ]

        for row, (
            label,
            widget
        ) in enumerate(
            settings
        ):

            pallet_grid.addWidget(

                QLabel(
                    label
                ),

                row,
                0
            )

            pallet_grid.addWidget(

                widget,

                row,
                1
            )

        top_layout.addWidget(
            delivery_box
        )

        top_layout.addWidget(
            pallet_box
        )

        main_layout.addLayout(
            top_layout
        )

        # ====================================================
        # BUTTONS
        # ====================================================

        button_layout = (
            QHBoxLayout()
        )

        self.generate_button = (
            QPushButton(
                "Generate Pallet"
            )
        )

        self.generate_button.clicked.connect(
            self.generate_pallet
        )

        self.reset_button = (
            QPushButton(
                "Reset Live Pallet"
            )
        )

        self.reset_button.clicked.connect(
            self.reset_live
        )

        button_layout.addWidget(
            self.generate_button
        )

        button_layout.addWidget(
            self.reset_button
        )

        main_layout.addLayout(
            button_layout
        )

        # ====================================================
        # 3D VIEWS
        # ====================================================

        views = (
            QHBoxLayout()
        )

        # TARGET
        target_box = (
            QGroupBox(
                "TARGET PALLET"
            )
        )

        target_layout = (
            QVBoxLayout(
                target_box
            )
        )

        self.target_view = (
            Pallet3DView(
                "Target Pallet"
            )
        )

        target_layout.addWidget(
            self.target_view
        )

        # LIVE
        live_box = (
            QGroupBox(
                "LIVE PALLET"
            )
        )

        live_layout = (
            QVBoxLayout(
                live_box
            )
        )

        self.live_view = (
            Pallet3DView(
                "Live Pallet"
            )
        )

        live_layout.addWidget(
            self.live_view
        )

        views.addWidget(
            target_box
        )

        views.addWidget(
            live_box
        )

        main_layout.addLayout(
            views
        )

        # ====================================================
        # STATUS AREA
        # ====================================================

        status_frame = (
            QFrame()
        )

        status_layout = (
            QHBoxLayout(
                status_frame
            )
        )

        self.status_label = (
            QLabel(
                "Status: Waiting"
            )
        )

        self.delivery_status_label = (
            QLabel(
                "Delivery: -"
            )
        )

        self.current_item_label = (
            QLabel(
                "Current Item: -"
            )
        )

        self.progress_label = (
            QLabel(
                "0 / 0"
            )
        )

        self.simulate_button = (
            QPushButton(
                "Place Next with ABB"
            )
        )

        self.simulate_button.setEnabled(
            False
        )

        self.simulate_button.clicked.connect(
            self.simulate_place
        )

        status_layout.addWidget(
            self.status_label
        )

        status_layout.addWidget(
            self.delivery_status_label
        )

        status_layout.addStretch()

        status_layout.addWidget(
            self.current_item_label
        )

        status_layout.addWidget(
            self.progress_label
        )

        status_layout.addWidget(
            self.simulate_button
        )

        main_layout.addWidget(
            status_frame
        )

    # ========================================================
    # LOAD DELIVERY
    # ========================================================

    def load_selected_delivery(
        self
    ) -> None:

        index = (
            self.delivery_combo.currentData()
        )

        if index is None:
            return

        order = (
            DELIVERY_ORDERS[
                index
            ]
        )

        self.current_delivery = (
            order
        )

        for sku in [

            "1L",

            "4L",

            "10L",

            "20L",

        ]:

            self.quantity_inputs[
                sku
            ].setValue(

                order.get(
                    sku,
                    0
                )
            )

        self.delivery_status_label.setText(

            f"Delivery: "
            f"{order['delivery']} "
            f"(Row {order['line']})"
        )

        self._update_order_total()

    # ========================================================
    # UPDATE TOTAL
    # ========================================================

    def _update_order_total(
        self
    ) -> None:

        total = sum(

            spin.value()

            for spin
            in self.quantity_inputs.values()
        )

        self.order_total_label.setText(

            f"Total Items: "
            f"{total}"
        )

    # ========================================================
    # GENERATE PALLET
    # ========================================================

        # ========================================================
    # GENERATE PALLET
    # ========================================================

    def generate_pallet(self) -> None:

        # Force Qt spinboxes to accept whatever is currently typed
        for spin in self.quantity_inputs.values():
            spin.interpretText()

        quantities = {
            sku: spin.value()
            for sku, spin in self.quantity_inputs.items()
        }

        print("GENERATING:", quantities)

        self._update_order_total()

        if sum(quantities.values()) == 0:

            QMessageBox.warning(
                self,
                "Empty Order",
                "Enter at least one product quantity."
            )

            return

        result = self.planner.generate(
            quantities=quantities,
            pallet_length=self.length_input.value(),
            pallet_width=self.width_input.value(),
            max_height=self.height_input.value(),
            max_weight=self.weight_input.value(),
            overhang=self.overhang_input.value(),
            gap_x=self.gap_x_input.value(),
            gap_y=self.gap_y_input.value(),
            edge_margin_x=self.edge_margin_input.value(),
            edge_margin_y=self.edge_margin_input.value(),
        )

        if not result.success:

            self.slots = []

            self.simulate_button.setEnabled(False)

            self.current_item_label.setText(
                "Current Item: -"
            )

            self.progress_label.setText(
                "0 / 0"
            )

            self.free_space_label.setText(
                "Free Floor Area: -"
            )

            self.status_label.setText(
                "Status: Cannot build pallet"
            )

            self._refresh_views()

            QMessageBox.warning(
                self,
                "Cannot Build Pallet",
                result.error
            )

            return

        self.slots = result.slots

        self.executor.load_plan(
            self.slots
        )

        self.simulate_button.setEnabled(True)

        self.status_label.setText(
            "Status: Pallet generated"
        )

        self._update_free_space()
        self.update_status()
        self._refresh_views()

    # ========================================================
    # MARK NEXT ITEM ACTIVE
    # ========================================================
    def simulate_place(self) -> None:

        current = self.executor.current_slot()

        if current is None:
            return

        self.status_label.setText(
            f"Status: Sending slot {current.id} to ABB..."
        )

        QApplication.processEvents()

        try:
            reply = self.executor.place_next()

        except (OSError, socket.timeout) as exc:

            self.status_label.setText(
                "Status: ABB communication failed"
            )

            QMessageBox.critical(
                self,
                "ABB Communication Error",
                (
                    f"Could not complete slot {current.id}.\n\n"
                    f"{exc}"
                ),
            )

            return

        if reply != "PLACED":

            self.status_label.setText(
                f"Status: ABB returned {reply or 'no reply'}"
            )

            QMessageBox.warning(
                self,
                "ABB Placement Not Confirmed",
                (
                    f"Slot {current.id} was not marked DONE.\n\n"
                    f"ABB reply: {reply!r}"
                ),
            )

            return

        if self.executor.is_complete():

            self.status_label.setText(
                "Status: PALLET COMPLETE"
            )

            self.current_item_label.setText(
                "Current Item: -"
            )

            self.simulate_button.setEnabled(
                False
            )

        else:

            self.status_label.setText(
                "Status: ABB placement confirmed"
            )

        self.update_status()
        self._refresh_views()


    # ========================================================
    # UPDATE FREE FLOOR SPACE
    # ========================================================

    def _update_free_space(self) -> None:

        pallet_length = self.length_input.value()
        pallet_width = self.width_input.value()
        edge_margin = self.edge_margin_input.value()
        gap_x = self.gap_x_input.value()
        gap_y = self.gap_y_input.value()

        stack_bases = {}

        for slot in self.slots:

            if slot.stack_id in stack_bases:
                continue

            stack_bases[slot.stack_id] = FreeRect(
                x=slot.x - slot.length / 2.0,
                y=slot.y - slot.width / 2.0,
                width=slot.length,
                height=slot.width,
            )

        pockets = calculate_free_rectangles(
            pallet_length=pallet_length,
            pallet_width=pallet_width,
            edge_margin_x=edge_margin,
            edge_margin_y=edge_margin,
            gap_x=gap_x,
            gap_y=gap_y,
            occupied_rectangles=stack_bases.values(),
        )

        usable_area = max(
            0.0,
            (pallet_length - 2.0 * edge_margin)
            * (pallet_width - 2.0 * edge_margin),
        )

        free_area = sum(
            pocket.area
            for pocket in pockets
        )

        free_percent = (
            free_area / usable_area * 100.0
            if usable_area > 0
            else 0.0
        )

        if pockets:

            largest = pockets[0]

            largest_fits = fitting_skus(
                pocket=largest,
                products=PRODUCTS,
                gap_x=gap_x,
                gap_y=gap_y,
            )

            fit_text = (
                ", ".join(largest_fits)
                if largest_fits
                else "none"
            )

            self.free_space_label.setText(
                f"Free Pockets: {len(pockets)} | "
                f"Free Area: {free_area:,.0f} mm² "
                f"({free_percent:.1f}%) | "
                f"Largest: "
                f"{largest.width:.0f}×"
                f"{largest.height:.0f} mm | "
                f"Fits: {fit_text}"
            )

        else:

            self.free_space_label.setText(
                "Free Pockets: 0 | "
                "Free Area: 0 mm² (0.0%)"
            )

        print("\nFREE PALLET POCKETS")

        for index, pocket in enumerate(
            pockets,
            start=1,
        ):

            fits = fitting_skus(
                pocket=pocket,
                products=PRODUCTS,
                gap_x=gap_x,
                gap_y=gap_y,
            )

            fit_text = (
                ", ".join(fits)
                if fits
                else "none"
            )

            print(
                f"{index}: "
                f"X={pocket.x:.0f} "
                f"Y={pocket.y:.0f} "
                f"W={pocket.width:.0f} "
                f"H={pocket.height:.0f} "
                f"Area={pocket.area:,.0f} "
                f"Fits=[{fit_text}]"
            )

    # ========================================================
    # UPDATE STATUS
    # ========================================================

    def update_status(self) -> None:

        total = len(self.slots)

        completed = self.executor.completed_count()

        self.progress_label.setText(
            f"{completed} / {total}"
        )

        slot = self.executor.current_slot()

        if slot is not None:

            product = PRODUCTS[
                slot.sku
            ]

            self.current_item_label.setText(
                f"Next: "
                f"{product.name} | "
                f"Slot {slot.id} | "
                f"X={slot.x:.0f} "
                f"Y={slot.y:.0f} "
                f"Z={slot.z:.0f} | "
                f"R={slot.rotation:.0f}°"
            )

        else:

            self.current_item_label.setText(
                "Current Item: -"
            )

    # ========================================================
    # REFRESH 3D VIEWS
    # ========================================================

    def _refresh_views(
        self
    ) -> None:

        length = (
            self.length_input.value()
        )

        width = (
            self.width_input.value()
        )

        # TARGET = FULL PLANNED PALLET
        self.target_view.set_data(

            self.slots,

            length,
            width,

            False
        )

        # LIVE = DONE ITEMS ONLY
        self.live_view.set_data(

            self.slots,

            length,
            width,

            True
        )

    # ========================================================
    # RESET LIVE PALLET
    # ========================================================

    def reset_live(self) -> None:

        self.executor.reset()

        if self.slots:

            self.simulate_button.setEnabled(
                True
            )

            self.status_label.setText(
                "Status: Live pallet reset"
            )

        else:

            self.simulate_button.setEnabled(
                False
            )

            self.status_label.setText(
                "Status: Waiting"
            )

        self.update_status()
        self._refresh_views()

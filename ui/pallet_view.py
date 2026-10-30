from typing import List

import numpy as np

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
)

from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)

from config.products import PRODUCTS
from planner.models import PalletSlot




# ============================================================
# MATPLOTLIB 3D PALLET VIEW
# ============================================================

class Pallet3DView(QWidget):

    def __init__(
        self,
        title: str
    ):

        super().__init__()

        self.title = title

        self.slots: List[
            PalletSlot
        ] = []

        self.pallet_length = 1300.0
        self.pallet_width = 1300.0

        self.show_only_done = False

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        self.figure = Figure(
            figsize=(
                7,
                5
            )
        )

        self.canvas = (
            FigureCanvas(
                self.figure
            )
        )

        self.toolbar = (
            NavigationToolbar(

                self.canvas,

                self
            )
        )

        layout.addWidget(
            self.toolbar
        )

        layout.addWidget(
            self.canvas
        )

    # ========================================================
    # SET DATA
    # ========================================================

    def set_data(
        self,
        slots: List[PalletSlot],
        pallet_length: float,
        pallet_width: float,
        show_only_done: bool = False,
    ) -> None:

        self.slots = slots

        self.pallet_length = (
            pallet_length
        )

        self.pallet_width = (
            pallet_width
        )

        self.show_only_done = (
            show_only_done
        )

        self.redraw()

    # ========================================================
    # REDRAW
    # ========================================================

    def redraw(
        self
    ) -> None:

        self.figure.clear()

        ax = (
            self.figure.add_subplot(

                111,

                projection="3d"
            )
        )

        self.figure.patch.set_facecolor(
            "white"
        )

        ax.set_facecolor(
            "white"
        )

        visible = [

            slot

            for slot in self.slots

            if (

                not self.show_only_done

                or

                slot.status
                == "DONE"
            )
        ]

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        if self.show_only_done:

            title_text = (

                f"{self.title} "
                f"({len(visible)} placed)"
            )

        else:

            title_text = (

                f"{self.title} "
                f"({len(self.slots)} items)"
            )

        ax.set_title(

            title_text,

            fontsize=11,

            pad=10
        )

        # ----------------------------------------------------
        # AXES
        # ----------------------------------------------------

        ax.set_xlabel(
            "X (mm)"
        )

        ax.set_ylabel(
            "Y (mm)"
        )

        ax.set_zlabel(
            "Z / Height (mm)"
        )

        margin = 80

        ax.set_xlim(

            -margin,

            self.pallet_length
            + margin
        )

        ax.set_ylim(

            -margin,

            self.pallet_width
            + margin
        )

        max_height = (
            self._max_height()
        )

        z_limit = max(

            1000.0,

            max_height
            * 1.20
        )

        ax.set_zlim(
            0,
            z_limit
        )

        try:

            ax.set_box_aspect(

                (

                    self.pallet_length,

                    self.pallet_width,

                    z_limit
                )
            )

        except Exception:

            pass

        # ----------------------------------------------------
        # PALLET
        # ----------------------------------------------------

        self._draw_pallet(
            ax
        )

        # ----------------------------------------------------
        # PRODUCTS
        # ----------------------------------------------------

        for slot in visible:

            product = (
                PRODUCTS[
                    slot.sku
                ]
            )

            if product.shape == "box":

                self._draw_box(
                    ax,
                    slot
                )

            else:

                self._draw_bucket(
                    ax,
                    slot
                )

        # ----------------------------------------------------
        # CAMERA
        # ----------------------------------------------------

        ax.view_init(

            elev=27,

            azim=-58
        )

        self._draw_legend(
            ax
        )

        self.figure.tight_layout()

        self.canvas.draw_idle()

    # ========================================================
    # MAX HEIGHT
    # ========================================================

    def _max_height(
        self
    ) -> float:

        if not self.slots:

            return 0.0

        return max(

            slot.z
            + slot.height / 2

            for slot in self.slots
        )

    # ========================================================
    # PALLET BASE
    # ========================================================

    def _draw_pallet(
        self,
        ax
    ) -> None:

        thickness = 80

        ax.bar3d(

            0,
            0,
            -thickness,

            self.pallet_length,
            self.pallet_width,
            thickness,

            color="burlywood",

            edgecolor="saddlebrown",

            alpha=0.40,

            shade=True
        )

    # ========================================================
    # PRODUCT COLOR
    # ========================================================

    @staticmethod
    def _color_for_slot(
        slot: PalletSlot
    ) -> str:

        if slot.status == "ACTIVE":

            return "gold"

        colors = {

            "1L": "red",

            "4L": "orange",

            "10L": "blue",

            "20L": "green",
        }

        return colors.get(
            slot.sku,
            "gray"
        )

    # ========================================================
    # DRAW BOX
    # ========================================================

    def _draw_box(
        self,
        ax,
        slot: PalletSlot
    ) -> None:

        x0 = (

            slot.x
            - slot.length / 2
        )

        y0 = (

            slot.y
            - slot.width / 2
        )

        z0 = (

            slot.z
            - slot.height / 2
        )

        ax.bar3d(

            x0,
            y0,
            z0,

            slot.length,
            slot.width,
            slot.height,

            color=(
                self._color_for_slot(
                    slot
                )
            ),

            edgecolor="black",

            linewidth=0.8,

            alpha=0.85,

            shade=True
        )

    # ========================================================
    # DRAW BUCKET
    # ========================================================

    def _draw_bucket(
        self,
        ax,
        slot: PalletSlot
    ) -> None:

        color = (
            self._color_for_slot(
                slot
            )
        )

        radius = (
            slot.length
            / 2
        )

        z_bottom = (

            slot.z
            - slot.height / 2
        )

        z_top = (

            slot.z
            + slot.height / 2
        )

        # ----------------------------------------------------
        # CYLINDER SIDE
        # ----------------------------------------------------

        theta = np.linspace(

            0,

            2 * np.pi,

            30
        )

        z_values = np.linspace(

            z_bottom,

            z_top,

            5
        )

        theta_grid, z_grid = (
            np.meshgrid(

                theta,

                z_values
            )
        )

        x_grid = (

            slot.x

            + radius
            * np.cos(
                theta_grid
            )
        )

        y_grid = (

            slot.y

            + radius
            * np.sin(
                theta_grid
            )
        )

        ax.plot_surface(

            x_grid,
            y_grid,
            z_grid,

            color=color,

            alpha=0.84,

            edgecolor="black",

            linewidth=0.18,

            shade=True
        )

        # ----------------------------------------------------
        # TOP CIRCLE
        # ----------------------------------------------------

        radial = np.linspace(

            0,

            radius,

            7
        )

        top_theta = np.linspace(

            0,

            2 * np.pi,

            30
        )

        r_grid, t_grid = (
            np.meshgrid(

                radial,

                top_theta
            )
        )

        top_x = (

            slot.x

            + r_grid
            * np.cos(
                t_grid
            )
        )

        top_y = (

            slot.y

            + r_grid
            * np.sin(
                t_grid
            )
        )

        top_z = np.full_like(

            top_x,

            z_top
        )

        ax.plot_surface(

            top_x,
            top_y,
            top_z,

            color=color,

            alpha=0.88,

            edgecolor="black",

            linewidth=0.16,

            shade=True
        )

    # ========================================================
    # LEGEND
    # ========================================================

    @staticmethod
    def _draw_legend(
        ax
    ) -> None:

        legend_items = [

            Patch(

                facecolor="red",

                edgecolor="black",

                label="1 Ltr Carton"
            ),

            Patch(

                facecolor="orange",

                edgecolor="black",

                label="4 Ltr Carton"
            ),

            Patch(

                facecolor="blue",

                edgecolor="black",

                label="10 Ltr Bucket"
            ),

            Patch(

                facecolor="green",

                edgecolor="black",

                label="20 Ltr Bucket"
            ),

            Patch(

                facecolor="gold",

                edgecolor="black",

                label="Next Placement"
            ),
        ]

        ax.legend(

            handles=legend_items,

            loc="upper left",

            fontsize=8
        )

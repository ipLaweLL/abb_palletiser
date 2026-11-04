"""Experimental GPU pallet viewer (PyQtGraph OpenGL).

Optional packages: pyqtgraph, PyOpenGL.
The public API intentionally matches ui.pallet_view.Pallet3DView.
Only use via gpu_main.py; main.py and user_main.py remain unchanged.
"""
import numpy as np
import pyqtgraph.opengl as gl

from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from planner.models import PalletSlot


COLORS = {
    "1L": (0.95, 0.17, 0.17, 0.98),
    "4L": (1.00, 0.59, 0.08, 0.98),
    "10L": (0.16, 0.37, 0.97, 0.98),
    "20L": (0.12, 0.64, 0.31, 0.98),
}


def _box_triangles(cx, cy, cz, dx, dy, dz):
    x0, x1 = cx - dx / 2, cx + dx / 2
    y0, y1 = cy - dy / 2, cy + dy / 2
    z0, z1 = cz - dz / 2, cz + dz / 2
    vertices = np.array([
        (x0, y0, z0), (x1, y0, z0),
        (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1),
        (x1, y1, z1), (x0, y1, z1),
    ], dtype=float)
    faces = [
        (0, 2, 1), (0, 3, 2),  # bottom
        (4, 5, 6), (4, 6, 7),  # top
        (0, 1, 5), (0, 5, 4),
        (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6),
        (3, 0, 4), (3, 4, 7),
    ]
    return vertices[np.asarray(faces)]


def _cylinder_triangles(cx, cy, cz, radius, height, segments=32):
    z0, z1 = cz - height / 2, cz + height / 2
    pieces = []
    for i in range(segments):
        t0 = 2 * np.pi * i / segments
        t1 = 2 * np.pi * (i + 1) / segments
        p0 = (cx + radius * np.cos(t0), cy + radius * np.sin(t0))
        p1 = (cx + radius * np.cos(t1), cy + radius * np.sin(t1))
        a, b = (*p0, z0), (*p1, z0)
        c, d = (*p1, z1), (*p0, z1)
        pieces.extend([
            (a, b, c), (a, c, d),
            ((cx, cy, z1), d, c),
            ((cx, cy, z0), b, a),
        ])
    return np.asarray(pieces, dtype=float)


class GpuPallet3DView(QWidget):
    """GPU-accelerated 3D visualization; no planner or ABB logic."""

    def __init__(self, title: str):
        super().__init__()
        self.title = title
        self.slots = []
        self.pallet_length = 1300.0
        self.pallet_width = 1300.0
        self.show_only_done = False
        self._items = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.heading = QLabel(title)
        layout.addWidget(self.heading)

        self.view = gl.GLViewWidget()
        self.view.setBackgroundColor("white")
        self.view.setCameraPosition(distance=2500, elevation=27, azimuth=45)
        layout.addWidget(self.view, 1)

        self.legend = QLabel(
            "20L: green   10L: blue   1L: red   4L: orange   Next: yellow"
        )
        layout.addWidget(self.legend)

    def set_data(
        self,
        slots: list[PalletSlot],
        pallet_length: float,
        pallet_width: float,
        show_only_done: bool = False,
    ) -> None:
        self.slots = slots
        self.pallet_length = pallet_length
        self.pallet_width = pallet_width
        self.show_only_done = show_only_done
        self.redraw()

    def _add_mesh(self, triangles, color):
        mesh = gl.GLMeshItem(
            vertexes=np.asarray(triangles, dtype=np.float32),
            color=color,
            smooth=False,
            drawEdges=True,
            edgeColor=(0.10, 0.12, 0.15, 0.70),
            shader="shaded",
            glOptions="translucent",
        )
        self.view.addItem(mesh)
        self._items.append(mesh)

    def redraw(self) -> None:
        # Recreate geometry only when placements change. Mouse-driven
        # rotation and camera distance are preserved.
        for item in self._items:
            self.view.removeItem(item)
        self._items.clear()

        if self.show_only_done:
            visible = [s for s in self.slots if s.status == "DONE"]
            self.heading.setText(f"{self.title} ({len(visible)} placed)")
        else:
            visible = list(self.slots)
            self.heading.setText(f"{self.title} ({len(visible)} items)")

        self._add_mesh(
            _box_triangles(
                self.pallet_length / 2, self.pallet_width / 2, -40,
                self.pallet_length, self.pallet_width, 80,
            ),
            (0.61, 0.46, 0.28, 0.27),
        )
        for slot in visible:
            color = (1.0, 0.84, 0.02, 1.0) if slot.status == "ACTIVE" else COLORS[slot.sku]
            if slot.sku in ("10L", "20L"):
                triangles = _cylinder_triangles(
                    slot.x, slot.y, slot.z, slot.length / 2, slot.height,
                )
            else:
                triangles = _box_triangles(
                    slot.x, slot.y, slot.z, slot.length, slot.width, slot.height,
                )
            self._add_mesh(triangles, color)

        # Center initial and subsequent orbiting on the pallet itself.
        self.view.opts["center"] = QVector3D(
            self.pallet_length / 2, self.pallet_width / 2, 300
        )
        self.view.update()

    def rotate_camera(self, delta_degrees: float = 1.5) -> None:
        # Orbit only; there is no geometry rebuild per camera tick.
        self.view.setCameraPosition(
            azimuth=(float(self.view.opts["azimuth"]) + delta_degrees) % 360
        )

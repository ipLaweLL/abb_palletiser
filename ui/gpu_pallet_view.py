"""Experimental GPU pallet viewer (PyQtGraph OpenGL).

Optional packages: pyqtgraph, PyOpenGL.
The public API intentionally matches ui.pallet_view.Pallet3DView.
Only use via gpu_main.py; main.py and user_main.py remain unchanged.
"""
import numpy as np
import pyqtgraph.opengl as gl

from PySide6.QtCore import Signal
from PySide6.QtGui import QVector3D, QVector4D
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from planner.models import PalletSlot


# Bright, opaque SKU colors for clear contrast on the white canvas.
COLORS = {
    "1L": (0.86, 0.22, 0.22, 1.0),  # muted red
    "4L": (0.90, 0.55, 0.10, 1.0),  # softer orange
    "10L": (0.20, 0.42, 0.88, 1.0),  # calmer blue
    "20L": (0.12, 0.62, 0.30, 1.0),  # balanced green
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


class HoverGLViewWidget(gl.GLViewWidget):
    """Emit mouse positions without interfering with built-in orbit/zoom."""

    cursor_moved = Signal(float, float)
    cursor_left = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        position = event.position()
        self.cursor_moved.emit(float(position.x()), float(position.y()))

    def leaveEvent(self, event):
        self.cursor_left.emit()
        super().leaveEvent(event)


def _mouse_world_ray(view, pixel_x, pixel_y):
    """Unproject the cursor using the actual OpenGL camera matrices.

    This does not read the GPU depth buffer, so it remains inexpensive
    during live pallet animation and while dragging the camera.
    """
    width, height = view.width(), view.height()
    if width <= 0 or height <= 0:
        return None

    region = (0, 0, width, height)
    try:
        projection = view.projectionMatrix(region, region)
    except TypeError:
        # Compatibility with PyQtGraph 0.13 and 0.14 releases.
        projection = view.projectionMatrix(region)
    view_projection = projection * view.viewMatrix()
    inverse, invertible = view_projection.inverted()
    if not invertible:
        return None

    x_ndc = 2.0 * pixel_x / width - 1.0
    y_ndc = 1.0 - 2.0 * pixel_y / height

    def point(ndc_z):
        # PySide6's overloaded QMatrix4x4 * QVector4D operator can
        # raise a binding SyntaxError on some Windows builds. Use the
        # documented map(QVector4D) overload instead.
        value = inverse.map(QVector4D(x_ndc, y_ndc, ndc_z, 1.0))
        if abs(value.w()) < 1e-9:
            return None
        return np.array([
            value.x() / value.w(),
            value.y() / value.w(),
            value.z() / value.w(),
        ], dtype=float)

    near, far = point(-1.0), point(1.0)
    if near is None or far is None:
        return None
    direction = far - near
    norm = np.linalg.norm(direction)
    if norm < 1e-9:
        return None
    return near, direction / norm


def _ray_box_intersection(origin, direction, slot):
    """Return distance along ray to a slot's bounding volume, or None."""
    half_x, half_y, half_z = slot.length / 2, slot.width / 2, slot.height / 2
    low = np.array([slot.x - half_x, slot.y - half_y, slot.z - half_z])
    high = np.array([slot.x + half_x, slot.y + half_y, slot.z + half_z])

    t_enter, t_exit = -float("inf"), float("inf")
    for axis in range(3):
        if abs(direction[axis]) < 1e-9:
            if origin[axis] < low[axis] or origin[axis] > high[axis]:
                return None
            continue
        t1 = (low[axis] - origin[axis]) / direction[axis]
        t2 = (high[axis] - origin[axis]) / direction[axis]
        t_enter = max(t_enter, min(t1, t2))
        t_exit = min(t_exit, max(t1, t2))
        if t_exit < t_enter:
            return None
    return max(t_enter, 0.0) if t_exit >= 0 else None


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

        self.view = HoverGLViewWidget()
        self.view.cursor_moved.connect(self._update_hover_readout)
        self.view.cursor_left.connect(self._clear_hover_readout)
        self.view.setBackgroundColor("white")
        self.view.setCameraPosition(distance=2500, elevation=27, azimuth=45)
        layout.addWidget(self.view, 1)

        self.coordinate_label = QLabel(
            "Pallet origin: (0, 0, 0) mm | "
            "Move over the pallet to inspect XYZ"
        )
        self.coordinate_label.setToolTip(
            "Coordinates are pallet-local, in millimetres. "
            "Item centres are the XYZ values used by the planner."
        )
        layout.addWidget(self.coordinate_label)

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

    def _add_mesh(self, triangles, color, translucent=False):
        mesh = gl.GLMeshItem(
            vertexes=np.asarray(triangles, dtype=np.float32),
            color=color,
            smooth=False,
            drawEdges=True,
            edgeColor=(0.20, 0.20, 0.20, 0.55),
            shader=None,
            glOptions="translucent" if translucent else "opaque",
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
            (0.72, 0.74, 0.77, 0.35),
            translucent=True,
        )
        for slot in visible:
            color = (0.92, 0.78, 0.10, 1.0) if slot.status == "ACTIVE" else COLORS[slot.sku]
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

    def _clear_hover_readout(self) -> None:
        self.coordinate_label.setText(
            "Pallet origin: (0, 0, 0) mm | "
            "Move over the pallet to inspect XYZ"
        )

    def _update_hover_readout(self, pixel_x: float, pixel_y: float) -> None:
        try:
            ray = _mouse_world_ray(self.view, pixel_x, pixel_y)
        except Exception:
            # Hover is informational: never flood stderr or interrupt
            # pallet simulation if a graphics driver / Qt binding fails.
            self._clear_hover_readout()
            return
        if ray is None:
            self._clear_hover_readout()
            return
        origin, direction = ray
        visible = (
            [slot for slot in self.slots if slot.status == "DONE"]
            if self.show_only_done else self.slots
        )

        # Find the first displayed object the cursor ray intersects.
        # Buckets use their bounding square for picking, so the value
        # shown is explicitly the slot centre, not a surface measurement.
        hit = None
        best_distance = float("inf")
        for slot in visible:
            distance = _ray_box_intersection(origin, direction, slot)
            if distance is not None and distance < best_distance:
                best_distance = distance
                hit = slot
        if hit is not None:
            self.coordinate_label.setText(
                f"Slot {hit.id} ({hit.sku}) centre: "
                f"X={hit.x:.1f}  Y={hit.y:.1f}  Z={hit.z:.1f} mm"
            )
            return

        # When no product is under the cursor, show the intersection
        # with the top of the pallet (Z = 0), if it is on the pallet.
        if abs(direction[2]) > 1e-9:
            distance = -origin[2] / direction[2]
            if distance >= 0:
                point = origin + distance * direction
                x, y = float(point[0]), float(point[1])
                if 0 <= x <= self.pallet_length and 0 <= y <= self.pallet_width:
                    self.coordinate_label.setText(
                        f"Pallet surface: X={x:.1f}  "
                        f"Y={y:.1f}  Z=0.0 mm"
                    )
                    return
        self._clear_hover_readout()

    def rotate_camera(self, delta_degrees: float = 1.5) -> None:
        # Orbit only; there is no geometry rebuild per camera tick.
        self.view.setCameraPosition(
            azimuth=(float(self.view.opts["azimuth"]) + delta_degrees) % 360
        )

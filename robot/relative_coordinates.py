"""ABB target translation relative to the first planned placement.

The robot's workobject must have been taught at the physical position
corresponding to the first slot's target (including the agreed TCP/tool
reference). All slots, including the first, retain their original XYZ
in the planner and 3D viewer.
"""


def relative_place_xyz(slot, first_slot):
    """Return slot XYZ minus the fixed first-slot XYZ in millimetres."""
    if first_slot is None:
        raise ValueError("Cannot send relative ABB XYZ without a first slot")
    coords = (
        slot.x - first_slot.x,
        slot.y - first_slot.y,
        slot.z - first_slot.z,
    )
    # Avoid -0.000 being shown/sent for floating-point roundoff.
    return tuple(0.0 if abs(value) < 0.0005 else value for value in coords)

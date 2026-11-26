"""Wire format for ABB pallet placement commands.

R is the planned absolute carton orientation in degrees relative to the
pallet X/Y axes, not a joint-angle increment or an angle relative to
Photoneo's pick pose.
"""

PLACED_RESPONSE = "PLACED"


def build_place_message(
    slot_id: int,
    x: float,
    y: float,
    z: float,
    rotation: float,
) -> str:
    return (
        f"PLACE;"
        f"{int(slot_id)};"
        f"{x:.3f};"
        f"{y:.3f};"
        f"{z:.3f};"
        f"{rotation:.3f}"
    )

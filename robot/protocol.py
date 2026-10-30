PLACED_RESPONSE = "PLACED"


def build_place_message(
    slot_id: int,
    x: float,
    y: float,
    z: float,
) -> str:

    return (
        f"PLACE;"
        f"{int(slot_id)};"
        f"{x:.3f};"
        f"{y:.3f};"
        f"{z:.3f}"
    )
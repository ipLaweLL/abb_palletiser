"""Convert a planner slot's product centre into a suction-contact TCP target.

Planner slots and 3D views remain product-centre coordinates. The ABB
interface currently uses the contact point on the product's top face.
The active RAPID tooldata must represent that same contact point.
"""
from config.products import PRODUCTS


def top_contact_xyz(slot):
    """Return workobject-local (x, y, z) for a top-centre vacuum TCP.

    Assumes a level product, top-centre pick, and no extra grip offset.
    The planner gives the centre of the product; the contact surface
    is exactly half its height above that centre.
    """
    if slot.sku not in PRODUCTS:
        raise ValueError(f"Unknown SKU for ABB placement: {slot.sku!r}")
    configured_height = PRODUCTS[slot.sku].height
    if abs(slot.height - configured_height) > 1e-6:
        raise ValueError(
            f"Slot {slot.id} {slot.sku} height {slot.height} mm differs "
            f"from SKU configuration {configured_height} mm"
        )
    return (slot.x, slot.y, slot.z + configured_height / 2.0)

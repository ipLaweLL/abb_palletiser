"""Translate planner product-centre slots to ABB vacuum-contact targets.

Commissioning convention:
- Workobject Z=0 is taught with a 1L carton resting on the pallet
  and the calibrated vacuum TCP touching the carton's top surface.
- X/Y remain offsets from the first slot in each plan (existing protocol).
- Z is NOT relative to the first SKU: it is relative to the fixed
  1L suction-contact reference, even when the first SKU is 20L.
- Physical gripper contact heights must match configured SKU heights.
"""
from config.products import PRODUCTS

REFERENCE_SKU = "1L"
REFERENCE_CONTACT_HEIGHT_MM = PRODUCTS[REFERENCE_SKU].height

# Temporary commissioning correction: 10L buckets were releasing high.
# Applied once to the outgoing ABB target only; never to stacking geometry.
SKU_CONTACT_Z_CORRECTION_MM = {"10L": -5.0}


def relative_place_xyz(slot, first_slot):
    """Return ABB XYZ in mm for the fixed taught 1L contact-height reference."""
    if first_slot is None:
        raise ValueError("Cannot send ABB XYZ without a first slot")
    if slot.sku not in PRODUCTS:
        raise ValueError(f"Unknown SKU in ABB placement: {slot.sku!r}")
    if abs(slot.height - PRODUCTS[slot.sku].height) > 1e-6:
        raise ValueError(
            f"Slot {slot.id} height {slot.height} mm does not match "
            f"configured height for {slot.sku}"
        )

    xyz = (
        slot.x - first_slot.x,
        slot.y - first_slot.y,
        # Planner Z is at product centre; vacuum contact is at its top.
        slot.z + slot.height / 2.0 - REFERENCE_CONTACT_HEIGHT_MM
        + SKU_CONTACT_Z_CORRECTION_MM.get(slot.sku, 0.0),
    )
    return tuple(0.0 if abs(value) < 0.0005 else value for value in xyz)

"""Explicit one-side, single-pallet commissioning layouts.

Only called by the engineering GUI's labelled Site Trial presets.
Never changes the general packing algorithm or ordinary deliveries.
"""
from config.products import PRODUCTS
from planner.models import PalletSlot, PlannerResult

SITE_TRIAL_CASES = [
    {"name": "Site Trial 01 - 5 x 1L (one-side 3+2)",
     "trial_layout": "cartons_5_edge", "1L": 5, "4L": 0, "10L": 0, "20L": 0},
    {"name": "Site Trial 02 - 4 x 10L (one-side row)",
     "trial_layout": "buckets_4_edge", "1L": 0, "4L": 0, "10L": 4, "20L": 0},
    {"name": "Site Trial 03 - 12 x 1L (3+3 bottom, 3+3 top)",
     "trial_layout": "cartons_12_two_layers", "1L": 12, "4L": 0, "10L": 0, "20L": 0},
    {"name": "Site Trial 04 - 12 x 10L (3+3+3+3 single layer)",
     "trial_layout": "buckets_12_four_rows", "1L": 0, "4L": 0, "10L": 12, "20L": 0},
]


def make_site_trial_layout(
    trial_layout, quantities, pallet_length, pallet_width, max_height,
    max_weight, overhang=0.0, gap_x=20.0, gap_y=20.0,
    edge_margin_x=20.0, edge_margin_y=20.0,
):
    """Construct fixed XY placement centres close to the pallet X/Y origin.

    1L: 3+2 floor-only compact strip, because 5 cartons in a straight
        row cannot fit a 1300 mm pallet at 20 mm margins and gaps.
    1L: twelve cartons, 3+3 per layer, with six on top of six.
    10L: four buckets in one floor-level row, or twelve buckets
         in four rows of three on the first layer.
    """
    if trial_layout == "cartons_5_edge":
        sku, rows, layers = "1L", (3, 2), 1
    elif trial_layout == "buckets_4_edge":
        sku, rows, layers = "10L", (4,), 1
    elif trial_layout == "cartons_12_two_layers":
        sku, rows, layers = "1L", (3, 3), 2
    elif trial_layout == "buckets_12_four_rows":
        sku, rows, layers = "10L", (3, 3, 3, 3), 1
    else:
        return PlannerResult(success=False, error="Unknown site trial layout.")

    required = {key: (sum(rows) * layers if key == sku else 0) for key in PRODUCTS}
    if any(int(quantities.get(key, 0)) != count
           for key, count in required.items()):
        return PlannerResult(
            success=False,
            error="Trial quantities changed; reselect the site trial case.",
        )
    product = PRODUCTS[sku]
    total_mass = sum(rows) * layers * product.weight
    if total_mass > max_weight:
        return PlannerResult(success=False, error="Trial exceeds pallet weight limit.")
    if layers > product.max_layers:
        return PlannerResult(success=False, error="Trial exceeds SKU stacking limit.")
    if layers * product.height > max_height:
        return PlannerResult(success=False, error="Trial exceeds pallet height limit.")
    if min(gap_x, gap_y, edge_margin_x, edge_margin_y) < 0:
        return PlannerResult(success=False, error="Negative gaps/margins not supported.")

    # The same conservative box-based footprint used by the planner.
    # Origin remains at the physical pallet corner; no centering.
    x0 = edge_margin_x + product.length / 2
    y0 = edge_margin_y + product.width / 2
    slots = []
    # Place the entire bottom layer first, then repeat the same six
    # XY positions on top. Each vertical column shares a stack_id.
    for level in range(1, layers + 1):
        column_id = 0
        for row_index, row_count in enumerate(rows):
            for column in range(row_count):
                column_id += 1
                x = x0 + column * (product.length + gap_x)
                y = y0 + row_index * (product.width + gap_y)
                if x + product.length / 2 > pallet_length + overhang - edge_margin_x:
                    return PlannerResult(
                        success=False,
                        error="Trial row is too long for pallet X dimension, gap and margin.",
                    )
                if y + product.width / 2 > pallet_width + overhang - edge_margin_y:
                    return PlannerResult(
                        success=False,
                        error="Trial strip is too wide for pallet Y dimension, gap and margin.",
                    )
                slot_id = len(slots) + 1
                slots.append(PalletSlot(
                    id=slot_id, sku=sku, x=x, y=y,
                    z=(level - 0.5) * product.height,
                    length=product.length, width=product.width,
                    height=product.height, rotation=0.0,
                    stack_id=column_id, level=level,
                ))
    return PlannerResult(success=True, slots=slots)

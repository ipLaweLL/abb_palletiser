# ============================================================
# STACKING RULES
# Bottom SKU -> SKU allowed directly above it
# ============================================================
from config.products import PRODUCTS

STACK_RULES = {
    # Execution order is fixed as 20L -> 10L -> 1L -> 4L.
    # Therefore 1L must NOT depend on a 4L being placed first.
    # Keep 1L and 4L in separate vertical stacks.
    "4L": {
        "4L",
    },

    "1L": {
        "1L",
    },

    "20L": {
        "20L",
        "10L",
    },

    "10L": {
        "10L",
    },
}


def can_stack(
    bottom_sku: str,
    top_sku: str
) -> bool:

    bottom = PRODUCTS[bottom_sku]
    top = PRODUCTS[top_sku]

    # Cartons and buckets can be on same pallet horizontally,
    # but CANNOT be stacked vertically on each other.
    if bottom.family != top.family:
        return False

    return top_sku in STACK_RULES.get(
        bottom_sku,
        set()
    )

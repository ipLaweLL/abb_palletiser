"""Regression test for general mixed-load search recovery.

The order is a test fixture, NOT a special case in the planner.
Run: python -m planner.mixed_recovery_test
"""
from collections import Counter

from planner.new_planner import NewPalletPlanner
from planner.validation_test import validate_success


def run():
    quantities = {"20L": 3, "10L": 4, "1L": 0, "4L": 16}
    pallet = {
        "length": 1300.0,
        "width": 1300.0,
        "height": 800.0,
        "weight": 1000.0,
    }
    result = NewPalletPlanner().generate(
        quantities=quantities,
        pallet_length=pallet["length"],
        pallet_width=pallet["width"],
        max_height=pallet["height"],
        max_weight=pallet["weight"],
        gap_x=20.0,
        gap_y=20.0,
        edge_margin_x=20.0,
        edge_margin_y=20.0,
    )
    assert result.success, result.error
    errors = validate_success(result, quantities, pallet)
    assert not errors, errors

    assert Counter(slot.sku for slot in result.slots) == Counter(
        {"20L": 3, "10L": 4, "4L": 16}
    )
    priority = {"20L": 0, "10L": 1, "1L": 2, "4L": 3}
    order = [priority[slot.sku] for slot in result.slots]
    assert order == sorted(order), "SKU execution order changed"

    for i, slot in enumerate(result.slots):
        earlier = result.slots[:i]
        if slot.level > 1:
            assert any(
                p.stack_id == slot.stack_id
                and p.level == slot.level - 1
                for p in earlier
            ), f"Unsupported execution order for slot {slot.id}"

    print(
        "PASS mixed recovery: 3x20L + 4x10L + 16x4L, "
        f"slots={len(result.slots)}, "
        f"floor_positions={len({s.stack_id for s in result.slots})}"
    )


if __name__ == "__main__":
    run()

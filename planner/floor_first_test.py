"""Regression tests for floor-first pallet allocation.

Run: python -m planner.floor_first_test
Also run: python -m planner.validation_test
"""

from collections import Counter

from config.products import PRODUCTS
from planner.new_planner import NewPalletPlanner
from planner.validation_test import validate_success


PALLET = {
    "length": 1300.0,
    "width": 1300.0,
    "height": 800.0,
    "weight": 1000.0,
}
PRIORITY = {"20L": 0, "10L": 1, "1L": 2, "4L": 3}


def plan(quantities):
    result = NewPalletPlanner().generate(
        quantities=quantities,
        pallet_length=PALLET["length"],
        pallet_width=PALLET["width"],
        max_height=PALLET["height"],
        max_weight=PALLET["weight"],
        gap_x=20.0,
        gap_y=20.0,
        edge_margin_x=20.0,
        edge_margin_y=20.0,
    )
    assert result.success, result.error
    errors = validate_success(result, quantities, PALLET)
    assert not errors, errors

    # Same-SKU columns and valid bottom-to-top dependencies.
    stacks = {}
    for slot in result.slots:
        stacks.setdefault(slot.stack_id, []).append(slot)
    for slots in stacks.values():
        assert len({slot.sku for slot in slots}) == 1
        assert sorted(slot.level for slot in slots) == list(range(1, len(slots) + 1))
        assert len(slots) <= PRODUCTS[slots[0].sku].max_layers

    assert [PRIORITY[s.sku] for s in result.slots] == sorted(
        PRIORITY[s.sku] for s in result.slots
    )
    for i, slot in enumerate(result.slots):
        assert all(
            previous.level < slot.level
            for previous in result.slots[:i]
            if previous.stack_id == slot.stack_id
        )
    return result


def run():
    # 3x3 base fits on 1300x1300 with 20mm gaps and margins.
    for quantity in (4, 7, 9, 10, 12, 13, 14, 18):
        order = {"20L": quantity, "10L": 0, "1L": 0, "4L": 0}
        result = plan(order)
        base = [s for s in result.slots if s.level == 1]
        upper = [s for s in result.slots if s.level == 2]
        assert len(base) == min(quantity, 9), (
            quantity, "floor positions", len(base)
        )
        assert len(upper) == max(0, quantity - 9), (
            quantity, "upper positions", len(upper)
        )
        print(f"PASS {quantity} x 20L: floor={len(base)}, upper={len(upper)}")

    # A mixed order with a feasible one-level solution should not stack.
    mixed = {"20L": 4, "10L": 4, "1L": 0, "4L": 0}
    result = plan(mixed)
    assert all(s.level == 1 for s in result.slots)
    assert Counter(s.sku for s in result.slots) == Counter(
        {"20L": 4, "10L": 4}
    )
    print("PASS mixed 4x20L + 4x10L: floor-only")
    print("FLOOR FIRST REGRESSION: PASS")


if __name__ == "__main__":
    run()

"""Verify first-placement-relative ABB coordinates without robot motion.

Run: python -m robot.relative_coordinates_test
"""
from planner.site_trial_layouts import make_site_trial_layout
from config.products import PRODUCTS
from planner.models import PalletSlot
from robot.relative_coordinates import relative_place_xyz
from robot.protocol import build_place_message
from execution.pallet_executor import PalletExecutor


class FakeABB:
    def __init__(self):
        self.commands = []

    def place(self, slot_id, x, y, z):
        self.commands.append((slot_id, x, y, z))
        return "PLACED"


def trial(kind, quantities):
    result = make_site_trial_layout(
        kind, quantities, 1300, 1300, 1000, 1000,
        gap_x=20, gap_y=20, edge_margin_x=20, edge_margin_y=20,
    )
    assert result.success, result.error
    return result.slots


def check(slots, expected):
    assert [relative_place_xyz(slot, slots[0]) for slot in slots] == expected
    client = FakeABB()
    executor = PalletExecutor(client)
    executor.load_plan(slots)
    for _ in slots:
        assert executor.place_next() == "PLACED"
    assert client.commands == [
        (slots[i].id, *coordinates)
        for i, coordinates in enumerate(expected)
    ]
    assert executor.is_complete()
    executor.reset()
    assert executor.place_next() == "PLACED"
    assert client.commands[-1] == (slots[0].id, *expected[0])


def main():
    assert build_place_message(27, 608, 1139, 230) == (
        'PLACE;27;608.000;1139.000;230.000'
    )
    check(
        trial("cartons_5_edge", {"1L": 5, "4L": 0, "10L": 0, "20L": 0}),
        [(0, 0, 0), (387, 0, 0), (774, 0, 0),
         (0, 267, 0), (387, 267, 0)],
    )
    check(
        trial("buckets_4_edge", {"1L": 0, "4L": 0, "10L": 4, "20L": 0}),
        [(0, 0, 152), (287, 0, 152), (574, 0, 152), (861, 0, 152)],
    )
    # Four rows of three 10L buckets: all first-layer ABB Z=152mm.
    rows_of_3 = trial("buckets_12_four_rows",
                      {"1L": 0, "4L": 0, "10L": 12, "20L": 0})
    expected_buckets = [
        (x, y, 152)
        for y in (0, 287, 574, 861)
        for x in (0, 287, 574)
    ]
    check(rows_of_3, expected_buckets)

    # Two layers of six 10L buckets: 3+3 bottom, then 3+3 on top.
    # Contact Z includes the -5mm 10L correction on BOTH layers.
    stacked_buckets = trial("buckets_12_two_layers",
                            {"1L": 0, "4L": 0, "10L": 12, "20L": 0})
    expected_stacked_buckets = [
        (x, y, z)
        for z in (152, 462)
        for y in (0, 287)
        for x in (0, 287, 574)
    ]
    check(stacked_buckets, expected_stacked_buckets)
    assert [s.level for s in stacked_buckets] == [1] * 6 + [2] * 6
    assert [s.stack_id for s in stacked_buckets] == list(range(1, 7)) * 2

    # New two-layer 1L trial: first layer remains at relative Z=0;
    # the top layer is exactly one carton height above it.
    stacked = trial("cartons_12_two_layers",
                    {"1L": 12, "4L": 0, "10L": 0, "20L": 0})
    expected_stacked = [
        (x, y, z)
        for z in (0, 153)
        for y in (0, 267)
        for x in (0, 387, 774)
    ]
    check(stacked, expected_stacked)
    # Fixed 1L Z datum remains unchanged when the first SKU is 20L.
    # Each top-contact target is measured from the taught 1L contact.
    # Verify canonical priority: 20L -> 10L -> 1L -> 4L.
    priorities = ("20L", "10L", "1L", "4L")
    mixed = []
    for i, sku in enumerate(priorities, 1):
        product = PRODUCTS[sku]
        mixed.append(PalletSlot(
            id=i, sku=sku, x=200.0 + (i-1)*200, y=200.0,
            z=product.height/2, length=product.length, width=product.width,
            height=product.height, rotation=0.0, stack_id=i, level=1,
        ))
    check(mixed, [(0, 0, 237), (200, 0, 152),
                  (400, 0, 0), (600, 0, 67)])
    # Upper level 20L: two full 390mm units, top-contact Z=780-153.
    two_high = PalletSlot(
        id=5, sku="20L", x=200, y=200, z=585,
        length=306, width=306, height=390,
        rotation=0.0, stack_id=1, level=2,
    )
    assert relative_place_xyz(two_high, mixed[0]) == (0.0, 0.0, 627.0)

    # Reject geometry drift rather than silently sending a wrong TCP height.
    two_high.height = 400
    try:
        relative_place_xyz(two_high, mixed[0])
    except ValueError:
        pass
    else:
        raise AssertionError("Mismatched SKU height was not rejected")
    print("PASS 1L Z datum, 10L -5mm, both 12-bucket layouts, stacked 1L, mixed SKUs, and reset")


if __name__ == "__main__":
    main()

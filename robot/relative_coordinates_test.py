"""Verify first-placement-relative ABB coordinates without robot motion.

Run: python -m robot.relative_coordinates_test
"""
from planner.site_trial_layouts import make_site_trial_layout
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
    assert client.commands[-1] == (slots[0].id, 0.0, 0.0, 0.0)


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
        [(0, 0, 0), (287, 0, 0), (574, 0, 0), (861, 0, 0)],
    )
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
    print("PASS first-slot-relative XYZ + 12-carton two-layer trial")


if __name__ == "__main__":
    main()

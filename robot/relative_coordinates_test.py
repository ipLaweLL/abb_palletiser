"""Verify first-placement-relative ABB coordinates without robot motion.

Run: python -m robot.relative_coordinates_test
"""
from planner.site_trial_layouts import make_site_trial_layout
from robot.relative_coordinates import relative_place_xyz
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
        (i + 1, *coordinates) for i, coordinates in enumerate(expected)
    ]
    assert executor.is_complete()
    executor.reset()
    assert executor.place_next() == "PLACED"
    assert client.commands[-1] == (1, 0.0, 0.0, 0.0)


def main():
    check(
        trial("cartons_5_edge", {"1L": 5, "4L": 0, "10L": 0, "20L": 0}),
        [(0, 0, 0), (387, 0, 0), (774, 0, 0),
         (0, 267, 0), (387, 267, 0)],
    )
    check(
        trial("buckets_4_edge", {"1L": 0, "4L": 0, "10L": 4, "20L": 0}),
        [(0, 0, 0), (287, 0, 0), (574, 0, 0), (861, 0, 0)],
    )
    print("PASS first-slot-relative XYZ for both site trials and executor reset")


if __name__ == "__main__":
    main()

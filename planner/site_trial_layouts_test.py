"""Tests for deterministic single-pallet, one-side commissioning presets.

Run: python -m planner.site_trial_layouts_test
"""
from config.products import PRODUCTS
from planner.site_trial_layouts import SITE_TRIAL_CASES, make_site_trial_layout
from planner.validation_test import validate_success


PALLET = {"length": 1300.0, "width": 1300.0,
          "height": 1000.0, "weight": 1000.0}


def test_trial(trial):
    quantities = {sku: trial[sku] for sku in PRODUCTS}
    result = make_site_trial_layout(
        trial["trial_layout"], quantities, 1300, 1300, 1000, 1000,
        gap_x=20, gap_y=20, edge_margin_x=20, edge_margin_y=20,
    )
    assert result.success, result.error
    assert len(result.slots) == sum(quantities.values())
    assert not validate_success(result, quantities, PALLET)
    assert all(slot.level == 1 for slot in result.slots)
    assert all(slot.status == "PENDING" for slot in result.slots)
    assert all(slot.z == PRODUCTS[slot.sku].height / 2 for slot in result.slots)
    assert all(slot.x >= 0 and slot.y >= 0 for slot in result.slots)

    if trial["trial_layout"] == "buckets_4_edge":
        assert len({slot.y for slot in result.slots}) == 1
        assert len({slot.x for slot in result.slots}) == 4
    else:
        assert sorted(
            sum(s.y == y for s in result.slots)
            for y in set(s.y for s in result.slots)
        ) == [2, 3]
    print(trial["name"], [(s.x, s.y, s.z) for s in result.slots])


def main():
    for trial in SITE_TRIAL_CASES:
        test_trial(trial)
    too_narrow = make_site_trial_layout(
        "buckets_4_edge", {"10L": 4}, 900, 1300, 1000, 1000
    )
    assert not too_narrow.success
    print("SITE TRIAL LAYOUT TESTS PASS")


if __name__ == "__main__":
    main()

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
    two_layers = trial["trial_layout"] == "cartons_12_two_layers"
    assert {slot.level for slot in result.slots} == ({1, 2} if two_layers else {1})
    assert all(slot.status == "PENDING" for slot in result.slots)
    assert all(slot.z == (slot.level - 0.5) * PRODUCTS[slot.sku].height
               for slot in result.slots)
    assert all(slot.x >= 0 and slot.y >= 0 for slot in result.slots)

    if two_layers:
        assert len(result.slots) == 12
        assert [s.level for s in result.slots] == [1] * 6 + [2] * 6
        assert len({(s.x, s.y) for s in result.slots}) == 6
        assert len({s.stack_id for s in result.slots}) == 6
        assert [s.stack_id for s in result.slots] == list(range(1, 7)) * 2
        assert sorted(sum(s.y == y for s in result.slots[:6])
                      for y in {s.y for s in result.slots[:6]}) == [3, 3]
        assert [s.z for s in result.slots] == [76.5] * 6 + [229.5] * 6
    elif trial["trial_layout"] == "buckets_4_edge":
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
        if trial.get('trial_layout'):
            test_trial(trial)
        else:
            assert (trial['20L'], trial['10L'], trial['1L'], trial['4L']) == (3, 3, 3, 3)
            assert sum(trial[sku] for sku in PRODUCTS) == 12
    too_narrow = make_site_trial_layout(
        "buckets_4_edge", {"10L": 4}, 900, 1300, 1000, 1000
    )
    assert not too_narrow.success
    too_short = make_site_trial_layout(
        "cartons_12_two_layers", {"1L": 12}, 1300, 1300, 300, 1000
    )
    assert not too_short.success
    print("SITE TRIAL LAYOUT TESTS PASS")


if __name__ == "__main__":
    main()

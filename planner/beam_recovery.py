"""Bounded alternative-layout recovery for Frontier Lookahead.

Used only when normal planning rejects a geometrically plausible mixed load.
The candidate SKU order is unchanged: 20L -> 10L -> 1L -> 4L.
This searches alternative XY placements, not special-case order layouts.
"""

from planner.frontier_lookahead import FrontierLookaheadPlanner
from planner.lookahead_area_fit import EXECUTION_ORDER, LookaheadAreaFitState


def recover_layout(
    planner: FrontierLookaheadPlanner,
    quantities,
    beam_width: int = 160,
    max_columns: int = 18,
):
    """Return a fully placed state or None without accepting partial loads.

    The beam retains several complete partial layouts per depth. This
    avoids treating a single greedy lookahead rollout as a proof that
    an order does not fit. Bounded to avoid exponential GUI stalls.
    """
    candidates = []
    for sku in EXECUTION_ORDER:
        candidates.extend(
            planner._build_sku_columns(sku, int(quantities.get(sku, 0)))
        )

    if not candidates or len(candidates) > max_columns:
        return None

    states = [[]]
    for candidate in candidates:
        next_states = []
        for placed in states:
            placements = planner.placer.feasible_placements(
                candidate=candidate,
                placed=placed,
            )
            for option in placements:
                next_states.append(placed + [option])

        if not next_states:
            return None

        def rank(placed):
            min_x = min(item.x for item in placed)
            min_y = min(item.y for item in placed)
            max_x = max(item.right for item in placed)
            max_y = max(item.top for item in placed)
            box_length = max_x - min_x
            box_width = max_y - min_y
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            cog_offset = (
                (center_x - planner.pallet_length / 2) ** 2
                + (center_y - planner.pallet_width / 2) ** 2
            )
            return (
                round(box_length * box_width, 5),
                round(box_length + box_width, 5),
                round(cog_offset, 5),
                round(max_y, 5),
                round(max_x, 5),
                tuple((round(s.y, 5), round(s.x, 5), s.rotation) for s in placed),
            )

        # Rank deterministically and retain multiple competing layouts.
        next_states.sort(key=rank)
        states = next_states[:beam_width]

    return LookaheadAreaFitState(
        placed=states[0],
        remaining={sku: 0 for sku in EXECUTION_ORDER},
    )

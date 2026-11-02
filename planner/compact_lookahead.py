from math import hypot
from typing import Dict, List

from planner.extreme_points import PlacedStack
from planner.free_space import FreeRect
from planner.lookahead_area_fit import (
    LookaheadAreaFitPlanner,
)


class CompactLookaheadAreaFitPlanner(
    LookaheadAreaFitPlanner
):
    """
    Lookahead planner with compactness-aware tie-breaking.

    Priority:
      1. Minimize future unplaced items.
      2. Minimize a normalized composite of:
           - occupied bounding-box area
           - CoG distance from pallet center
           - free-pocket waste
      3. Deterministic row-major tie-breakers.

    The feasibility rollout remains the dominant rule, so compactness
    is never allowed to sacrifice future placeability just to make the
    current partial layout look tighter.
    """

    COMPACTNESS_WEIGHT = 0.55
    COG_WEIGHT = 0.35
    WASTE_WEIGHT = 0.10

    def _placement_key(
        self,
        option: PlacedStack,
        pockets: List[FreeRect],
        placed: List[PlacedStack],
        remaining_after: Dict[str, int],
    ):
        trial = placed + [option]

        future_unplaced = (
            self._rollout_unplaced(
                placed=trial,
                remaining=remaining_after,
            )
        )

        containing = self._containing_pockets(
            option,
            pockets,
        )

        candidate_area = (
            option.length + self.gap_x
        ) * (
            option.width + self.gap_y
        )

        if containing:
            pocket = min(
                containing,
                key=lambda rect: (
                    rect.area,
                    rect.y,
                    rect.x,
                ),
            )

            waste = max(
                0.0,
                pocket.area - candidate_area,
            )

            waste_ratio = (
                waste / pocket.area
                if pocket.area > 0
                else 0.0
            )
        else:
            waste = float("inf")
            waste_ratio = 1.0

        bbox_area = (
            self._bounding_box_area(
                trial
            )
        )

        usable_width = max(
            1.0,
            self.pallet_length
            - 2.0 * self.edge_margin_x,
        )
        usable_height = max(
            1.0,
            self.pallet_width
            - 2.0 * self.edge_margin_y,
        )
        usable_area = (
            usable_width
            * usable_height
        )

        bbox_ratio = (
            bbox_area / usable_area
        )

        cog_distance = (
            self._cog_distance(
                trial
            )
        )

        max_cog_distance = max(
            1.0,
            hypot(
                self.pallet_length / 2.0,
                self.pallet_width / 2.0,
            ),
        )

        cog_ratio = (
            cog_distance
            / max_cog_distance
        )

        composite = (
            self.COMPACTNESS_WEIGHT
            * bbox_ratio
            +
            self.COG_WEIGHT
            * cog_ratio
            +
            self.WASTE_WEIGHT
            * waste_ratio
        )

        return (
            future_unplaced,
            round(composite, 9),
            round(bbox_ratio, 9),
            round(cog_ratio, 9),
            round(waste, 6),
            round(option.y, 6),
            round(option.x, 6),
            option.rotation,
        )

    @staticmethod
    def _bounding_box_area(
        placed: List[PlacedStack],
    ) -> float:
        if not placed:
            return 0.0

        min_x = min(
            stack.x
            for stack in placed
        )
        min_y = min(
            stack.y
            for stack in placed
        )
        max_x = max(
            stack.right
            for stack in placed
        )
        max_y = max(
            stack.top
            for stack in placed
        )

        return (
            max_x - min_x
        ) * (
            max_y - min_y
        )


if __name__ == "__main__":
    planner = CompactLookaheadAreaFitPlanner(
        pallet_length=1500,
        pallet_width=1500,
        max_height=1600,
        gap_x=20,
        gap_y=20,
        edge_margin_x=20,
        edge_margin_y=20,
    )

    result = planner.search(
        quantities={
            "1L": 3,
            "4L": 6,
            "10L": 16,
            "20L": 0,
        }
    )

    print()
    print("=" * 60)
    print("COMPACT LOOKAHEAD RESULT")
    print("=" * 60)
    print("Remaining:", result.remaining)
    print(
        "Floor positions:",
        result.floor_positions(),
    )

    for index, stack in enumerate(
        result.placed,
        start=1,
    ):
        print(
            f"Stack {index}: "
            f"{stack.candidate.items} | "
            f"X={stack.x:.0f} "
            f"Y={stack.y:.0f} "
            f"L={stack.length:.0f} "
            f"W={stack.width:.0f} "
            f"R={stack.rotation:.0f} "
            f"H={stack.candidate.height:.0f}"
        )

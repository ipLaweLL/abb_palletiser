from typing import Dict, List

from planner.extreme_points import PlacedStack
from planner.free_space import FreeRect
from planner.lookahead_area_fit import (
    LookaheadAreaFitPlanner,
)


class FrontierLookaheadPlanner(
    LookaheadAreaFitPlanner
):
    """
    Corner-sweep planner with lookahead as a guardrail.

    The old deterministic row-major pattern is preserved whenever that
    move can still complete the remaining order. The planner only moves
    away from the corner/frontier pattern when lookahead predicts that
    the normal sweep choice will leave more items unplaced.

    Priority:
      1. Minimize future unplaced items.
      2. Preserve row-major corner sweep (Y, then X).
      3. Prefer smaller occupied bounding boxes.
      4. Prefer lower CoG distance.
      5. Deterministic orientation tie-breaker.
    """

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

        bbox_area = (
            self._bounding_box_area(
                trial
            )
        )

        cog_distance = (
            self._cog_distance(
                trial
            )
        )

        return (
            future_unplaced,
            round(option.y, 6),
            round(option.x, 6),
            round(bbox_area, 6),
            round(cog_distance, 6),
            round(option.length, 6),
            round(option.width, 6),
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
    planner = FrontierLookaheadPlanner(
        pallet_length=1300,
        pallet_width=1300,
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
    print("FRONTIER LOOKAHEAD RESULT")
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

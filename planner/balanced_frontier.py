from typing import Dict, List

from planner.extreme_points import PlacedStack
from planner.free_space import FreeRect
from planner.frontier_lookahead import (
    FrontierLookaheadPlanner,
)


class BalancedFrontierPlanner(
    FrontierLookaheadPlanner
):
    """
    Frontier-preserving lookahead with soft balance improvement.

    Hard priorities:
      1. Minimize future unplaced items.
      2. Keep the layout connected to the current occupied frontier.
      3. Minimize occupied bounding-box growth.

    Soft priorities:
      4. Improve pallet CoG.
      5. Keep deterministic row-major ordering.

    This keeps the visual/robot-friendly pattern of corner sweep while
    allowing balance improvements among equally safe compact moves.
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

        adjacency_penalty = (
            self._adjacency_penalty(
                option=option,
                placed=placed,
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
            adjacency_penalty,
            round(bbox_area, 6),
            round(cog_distance, 6),
            round(option.y, 6),
            round(option.x, 6),
            round(option.length, 6),
            round(option.width, 6),
            option.rotation,
        )

    def _adjacency_penalty(
        self,
        option: PlacedStack,
        placed: List[PlacedStack],
    ) -> int:
        if not placed:
            return 0

        eps = 1e-6

        for other in placed:
            x_overlap = (
                option.x < other.right - eps
                and option.right > other.x + eps
            )

            y_overlap = (
                option.y < other.top - eps
                and option.top > other.y + eps
            )

            horizontal_touch = (
                abs(
                    option.x
                    - (
                        other.right
                        + self.gap_x
                    )
                ) < eps
                or
                abs(
                    other.x
                    - (
                        option.right
                        + self.gap_x
                    )
                ) < eps
            )

            vertical_touch = (
                abs(
                    option.y
                    - (
                        other.top
                        + self.gap_y
                    )
                ) < eps
                or
                abs(
                    other.y
                    - (
                        option.top
                        + self.gap_y
                    )
                ) < eps
            )

            if (
                horizontal_touch
                and y_overlap
            ):
                return 0

            if (
                vertical_touch
                and x_overlap
            ):
                return 0

        return 1


if __name__ == "__main__":
    planner = BalancedFrontierPlanner(
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
    print("BALANCED FRONTIER RESULT")
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

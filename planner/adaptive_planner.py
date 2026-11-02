from math import hypot
from typing import Dict, Tuple

from planner.compact_lookahead import (
    CompactLookaheadAreaFitPlanner,
)
from planner.lookahead_area_fit import (
    LookaheadAreaFitPlanner,
)
from planner.ordered_sweep import (
    OrderedSweepPlanner,
)


class AdaptivePlanner:
    """
    Select the best result from multiple deterministic planners.

    Candidate planners:
      - pure corner sweep
      - lookahead area fit
      - compact lookahead

    Selection policy:
      1. Successful layouts always beat failed layouts.
      2. A layout is "balanced" when its CoG is within 15% of the
         smaller pallet dimension from pallet center.
      3. If balanced successful layouts exist, choose the one with the
         smallest occupied bounding box, then lower CoG.
      4. If none are inside the balance limit, choose the successful
         layout with the lowest CoG.
      5. If every planner fails, choose the layout with the fewest
         unplaced items, then lower CoG and smaller bounding box.

    This avoids forcing one scoring personality onto every pallet/order.
    """

    BALANCE_LIMIT_RATIO = 0.15

    def __init__(
        self,
        pallet_length: float,
        pallet_width: float,
        max_height: float,
        gap_x: float = 20.0,
        gap_y: float = 20.0,
        edge_margin_x: float = 20.0,
        edge_margin_y: float = 20.0,
    ) -> None:
        self.pallet_length = pallet_length
        self.pallet_width = pallet_width
        self.max_height = max_height
        self.gap_x = gap_x
        self.gap_y = gap_y
        self.edge_margin_x = edge_margin_x
        self.edge_margin_y = edge_margin_y
        self.selected_name = ""

        common = dict(
            pallet_length=pallet_length,
            pallet_width=pallet_width,
            max_height=max_height,
            gap_x=gap_x,
            gap_y=gap_y,
            edge_margin_x=edge_margin_x,
            edge_margin_y=edge_margin_y,
        )

        self.planners = {
            "Corner Sweep": OrderedSweepPlanner(
                **common,
                enable_last_sku_relocation=False,
            ),
            "Lookahead Fit": LookaheadAreaFitPlanner(
                **common,
            ),
            "Compact Look": CompactLookaheadAreaFitPlanner(
                **common,
            ),
        }

    def search(
        self,
        quantities: Dict[str, int],
    ):
        results = {
            name: planner.search(quantities)
            for name, planner in self.planners.items()
        }

        successful = [
            (name, result)
            for name, result in results.items()
            if self._unplaced(result) == 0
        ]

        if successful:
            balance_limit = (
                self.BALANCE_LIMIT_RATIO
                * min(
                    self.pallet_length,
                    self.pallet_width,
                )
            )

            balanced = [
                (name, result)
                for name, result in successful
                if self._cog_distance(
                    result.placed
                ) <= balance_limit
            ]

            if balanced:
                name, result = min(
                    balanced,
                    key=lambda item: (
                        self._bounding_area(
                            item[1].placed
                        ),
                        self._cog_distance(
                            item[1].placed
                        ),
                        item[0],
                    ),
                )
            else:
                name, result = min(
                    successful,
                    key=lambda item: (
                        self._cog_distance(
                            item[1].placed
                        ),
                        self._bounding_area(
                            item[1].placed
                        ),
                        item[0],
                    ),
                )

            self.selected_name = name
            return result

        name, result = min(
            results.items(),
            key=lambda item: (
                self._unplaced(item[1]),
                self._cog_distance(
                    item[1].placed
                ),
                self._bounding_area(
                    item[1].placed
                ),
                item[0],
            ),
        )

        self.selected_name = name
        return result

    @staticmethod
    def _unplaced(result) -> int:
        return sum(
            max(0, int(value))
            for value in result.remaining.values()
        )

    def _cog_distance(
        self,
        placed,
    ) -> float:
        if not placed:
            return float("inf")

        total_weight = sum(
            stack.candidate.weight
            for stack in placed
        )

        if total_weight <= 0:
            return float("inf")

        cog_x = sum(
            (
                stack.x
                + stack.length / 2.0
            )
            * stack.candidate.weight
            for stack in placed
        ) / total_weight

        cog_y = sum(
            (
                stack.y
                + stack.width / 2.0
            )
            * stack.candidate.weight
            for stack in placed
        ) / total_weight

        return hypot(
            cog_x - self.pallet_length / 2.0,
            cog_y - self.pallet_width / 2.0,
        )

    @staticmethod
    def _bounding_area(
        placed,
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
    planner = AdaptivePlanner(
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
            "1L": 35,
            "4L": 8,
            "10L": 3,
            "20L": 0,
        }
    )

    print()
    print("=" * 60)
    print("ADAPTIVE PLANNER RESULT")
    print("=" * 60)
    print("Selected:", planner.selected_name)
    print("Remaining:", result.remaining)
    print("Floor positions:", len(result.placed))

from dataclasses import dataclass, field
from math import floor
from typing import Dict, List

from config.products import PRODUCTS
from planner.extreme_points import (
    ExtremePointPlacer,
    PlacedStack,
)
from planner.models import StackCandidate


EXECUTION_ORDER = (
    "20L",
    "10L",
    "1L",
    "4L",
)


@dataclass
class OrderedSweepState:
    placed: List[PlacedStack] = field(
        default_factory=list
    )
    remaining: Dict[str, int] = field(
        default_factory=dict
    )

    def unplaced_count(self) -> int:
        return sum(
            self.remaining.values()
        )

    def floor_positions(self) -> int:
        return len(
            self.placed
        )


class OrderedSweepPlanner:
    """
    Deterministic pallet planner.

    Behaviour:
      1. Start at one pallet corner.
      2. Sweep in +X, then continue in +Y.
      3. Place SKU groups strictly in:
            20L -> 10L -> 1L -> 4L
      4. Use only same-SKU vertical columns.
      5. Respect configured X/Y gaps and edge margins.

    This intentionally prioritizes a predictable robot-friendly
    pattern over free-form beam-search layouts.
    """

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

        self.pallet_length = (
            pallet_length
        )
        self.pallet_width = (
            pallet_width
        )
        self.max_height = (
            max_height
        )

        self.gap_x = gap_x
        self.gap_y = gap_y
        self.edge_margin_x = (
            edge_margin_x
        )
        self.edge_margin_y = (
            edge_margin_y
        )

        self.placer = (
            ExtremePointPlacer(
                pallet_length=pallet_length,
                pallet_width=pallet_width,
                gap_x=gap_x,
                gap_y=gap_y,
                edge_margin_x=edge_margin_x,
                edge_margin_y=edge_margin_y,
            )
        )

    def search(
        self,
        quantities: Dict[str, int],
    ) -> OrderedSweepState:

        remaining = {
            sku: max(
                0,
                int(
                    quantities.get(
                        sku,
                        0,
                    )
                ),
            )
            for sku in PRODUCTS
        }

        placed: List[
            PlacedStack
        ] = []

        for sku in EXECUTION_ORDER:

            candidates = (
                self._build_sku_columns(
                    sku=sku,
                    quantity=remaining[
                        sku
                    ],
                )
            )

            for candidate in candidates:

                options = (
                    self.placer.feasible_placements(
                        candidate=candidate,
                        placed=placed,
                    )
                )

                if not options:
                    return OrderedSweepState(
                        placed=placed,
                        remaining=remaining,
                    )

                chosen = min(
                    options,
                    key=self._placement_key,
                )

                placed.append(
                    chosen
                )

                remaining[sku] -= len(
                    candidate.items
                )

        optimized = (
            self._second_pass_optimize(
                placed
            )
        )

        return OrderedSweepState(
            placed=optimized,
            remaining=remaining,
        )

    def _second_pass_optimize(
        self,
        placed: List[PlacedStack],
    ) -> List[PlacedStack]:
        """
        Pass 2 performs local relocation.

        Stack composition and list order never change, so execution
        remains 20L -> 10L -> 1L -> 4L.

        A move is accepted only when it improves the floor-layout
        objective:
          - better spread across pallet quadrants
          - center of footprint nearer pallet center
          - more balanced occupied extent in X and Y
        """

        if len(placed) <= 1:
            return placed

        current = list(placed)
        current_score = (
            self._layout_balance_score(
                current
            )
        )

        # A few deterministic improvement sweeps are enough here.
        for _ in range(4):

            improved = False

            for index in range(
                len(current)
            ):

                moving = current[index]

                fixed = [
                    stack
                    for position, stack
                    in enumerate(current)
                    if position != index
                ]

                options = (
                    self.placer.feasible_placements(
                        candidate=(
                            moving.candidate
                        ),
                        placed=fixed,
                    )
                )

                # Always include the current location as a valid
                # candidate so the optimizer never makes things worse.
                options.append(
                    moving
                )

                best_stack = moving
                best_score = (
                    current_score
                )

                for option in options:

                    trial = list(current)
                    trial[index] = option

                    score = (
                        self._layout_balance_score(
                            trial
                        )
                    )

                    if score < best_score:
                        best_score = score
                        best_stack = option

                if best_stack is not moving:
                    current[index] = (
                        best_stack
                    )
                    current_score = (
                        best_score
                    )
                    improved = True

            if not improved:
                break

        return current

    def _layout_balance_score(
        self,
        placed: List[PlacedStack],
    ):
        """
        Lower is better.

        The first term measures how unevenly floor area is distributed
        between the four pallet quadrants. This prevents one-side
        clustering.

        The remaining terms keep the occupied footprint centered and
        reasonably well spread without forcing every stack into the
        middle.
        """

        if not placed:
            return (
                0.0,
                0.0,
                0.0,
            )

        center_x = (
            self.pallet_length
            / 2.0
        )
        center_y = (
            self.pallet_width
            / 2.0
        )

        quadrant_areas = [
            0.0,
            0.0,
            0.0,
            0.0,
        ]

        for stack in placed:

            rectangles = (
                (
                    self.edge_margin_x,
                    self.edge_margin_y,
                    center_x,
                    center_y,
                ),
                (
                    center_x,
                    self.edge_margin_y,
                    (
                        self.pallet_length
                        - self.edge_margin_x
                    ),
                    center_y,
                ),
                (
                    self.edge_margin_x,
                    center_y,
                    center_x,
                    (
                        self.pallet_width
                        - self.edge_margin_y
                    ),
                ),
                (
                    center_x,
                    center_y,
                    (
                        self.pallet_length
                        - self.edge_margin_x
                    ),
                    (
                        self.pallet_width
                        - self.edge_margin_y
                    ),
                ),
            )

            for quadrant_index, (
                qx0,
                qy0,
                qx1,
                qy1,
            ) in enumerate(
                rectangles
            ):

                overlap_x = max(
                    0.0,
                    min(
                        stack.right,
                        qx1,
                    )
                    - max(
                        stack.x,
                        qx0,
                    ),
                )

                overlap_y = max(
                    0.0,
                    min(
                        stack.top,
                        qy1,
                    )
                    - max(
                        stack.y,
                        qy0,
                    ),
                )

                quadrant_areas[
                    quadrant_index
                ] += (
                    overlap_x
                    * overlap_y
                )

        total_area = sum(
            quadrant_areas
        )

        if total_area > 0:

            target_area = (
                total_area / 4.0
            )

            quadrant_variance = (
                sum(
                    (
                        (
                            area
                            - target_area
                        )
                        / total_area
                    ) ** 2
                    for area in quadrant_areas
                )
            )

        else:
            quadrant_variance = 0.0

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

        occupied_center_x = (
            min_x
            + max_x
        ) / 2.0

        occupied_center_y = (
            min_y
            + max_y
        ) / 2.0

        center_offset = (
            (
                (
                    occupied_center_x
                    - center_x
                )
                / self.pallet_length
            ) ** 2
            +
            (
                (
                    occupied_center_y
                    - center_y
                )
                / self.pallet_width
            ) ** 2
        )

        span_x = (
            max_x - min_x
        )
        span_y = (
            max_y - min_y
        )

        usable_x = max(
            1.0,
            self.pallet_length
            - 2.0
            * self.edge_margin_x,
        )

        usable_y = max(
            1.0,
            self.pallet_width
            - 2.0
            * self.edge_margin_y,
        )

        spread_x = (
            span_x / usable_x
        )
        spread_y = (
            span_y / usable_y
        )

        spread_underuse = (
            (
                1.0
                - min(
                    spread_x,
                    1.0,
                )
            ) ** 2
            +
            (
                1.0
                - min(
                    spread_y,
                    1.0,
                )
            ) ** 2
        )

        return (
            round(
                quadrant_variance,
                8,
            ),
            round(
                center_offset,
                8,
            ),
            round(
                spread_underuse,
                8,
            ),
        )

    def _build_sku_columns(
        self,
        sku: str,
        quantity: int,
    ) -> List[StackCandidate]:

        if quantity <= 0:
            return []

        product = PRODUCTS[sku]

        vertical_by_height = floor(
            self.max_height
            / product.height
        )

        max_items = max(
            1,
            min(
                product.max_layers,
                vertical_by_height,
            ),
        )

        columns: List[
            StackCandidate
        ] = []

        remaining = quantity

        while remaining > 0:

            count = min(
                max_items,
                remaining,
            )

            items = [
                sku
            ] * count

            columns.append(
                StackCandidate(
                    items=items,
                    base_length=(
                        product.length
                    ),
                    base_width=(
                        product.width
                    ),
                    height=(
                        product.height
                        * count
                    ),
                    weight=(
                        product.weight
                        * count
                    ),
                    rotation=0.0,
                )
            )

            remaining -= count

        return columns

    @staticmethod
    def _placement_key(
        placement: PlacedStack,
    ):
        """
        Deterministic row-major sweep.

        Y decides the row.
        X decides progress across the row.
        At the same point, prefer the orientation using less X.
        """

        return (
            round(
                placement.y,
                6,
            ),
            round(
                placement.x,
                6,
            ),
            round(
                placement.length,
                6,
            ),
            round(
                placement.width,
                6,
            ),
            placement.rotation,
        )


if __name__ == "__main__":

    planner = OrderedSweepPlanner(
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
            "1L": 27,
            "4L": 0,
            "10L": 0,
            "20L": 17,
        }
    )

    print()
    print("=" * 60)
    print("ORDERED SWEEP RESULT")
    print("=" * 60)
    print(
        "Remaining:",
        result.remaining,
    )
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

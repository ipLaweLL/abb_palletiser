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
        Pass 2:
          - keep the exact stack order produced by Pass 1
          - re-place those columns into the best available empty pockets
          - center the finished footprint inside the usable pallet area

        SKU execution order therefore remains:
            20L -> 10L -> 1L -> 4L
        """

        if not placed:
            return placed

        repacked: List[
            PlacedStack
        ] = []

        for original in placed:

            options = (
                self.placer.feasible_placements(
                    candidate=original.candidate,
                    placed=repacked,
                )
            )

            if not options:
                # Pass 1 already proved the layout fits.
                # If optimization ever cannot reproduce it,
                # keep the known-good original layout.
                return self._center_layout(
                    placed
                )

            chosen = min(
                options,
                key=lambda option:
                self._gap_fill_key(
                    option,
                    repacked,
                ),
            )

            repacked.append(
                chosen
            )

        return self._center_layout(
            repacked
        )

    def _gap_fill_key(
        self,
        option: PlacedStack,
        placed: List[PlacedStack],
    ):
        """
        Prefer placements that use existing empty pockets before
        expanding the occupied pallet footprint.

        Lower tuple is better.
        """

        trial = (
            placed
            + [option]
        )

        min_x = min(
            stack.x
            for stack in trial
        )
        min_y = min(
            stack.y
            for stack in trial
        )
        max_x = max(
            stack.right
            for stack in trial
        )
        max_y = max(
            stack.top
            for stack in trial
        )

        span_x = (
            max_x - min_x
        )
        span_y = (
            max_y - min_y
        )

        bounding_area = (
            span_x * span_y
        )

        used_area = sum(
            stack.length
            * stack.width
            for stack in trial
        )

        hole_area = max(
            0.0,
            bounding_area
            - used_area,
        )

        previous_area = 0.0

        if placed:

            prev_min_x = min(
                stack.x
                for stack in placed
            )
            prev_min_y = min(
                stack.y
                for stack in placed
            )
            prev_max_x = max(
                stack.right
                for stack in placed
            )
            prev_max_y = max(
                stack.top
                for stack in placed
            )

            previous_area = (
                (
                    prev_max_x
                    - prev_min_x
                )
                *
                (
                    prev_max_y
                    - prev_min_y
                )
            )

        expansion = max(
            0.0,
            bounding_area
            - previous_area,
        )

        center_x = (
            min_x
            + span_x / 2.0
        )
        center_y = (
            min_y
            + span_y / 2.0
        )

        target_x = (
            self.pallet_length
            / 2.0
        )
        target_y = (
            self.pallet_width
            / 2.0
        )

        center_offset_sq = (
            (
                center_x
                - target_x
            ) ** 2
            +
            (
                center_y
                - target_y
            ) ** 2
        )

        return (
            round(
                expansion,
                6,
            ),
            round(
                hole_area,
                6,
            ),
            round(
                bounding_area,
                6,
            ),
            round(
                center_offset_sq,
                6,
            ),
            round(
                option.y,
                6,
            ),
            round(
                option.x,
                6,
            ),
        )

    def _center_layout(
        self,
        placed: List[PlacedStack],
    ) -> List[PlacedStack]:
        """
        Translate the whole finished layout so unused edge space is
        shared on both sides. Relative geometry and all gaps remain
        unchanged.
        """

        if not placed:
            return placed

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

        span_x = (
            max_x - min_x
        )
        span_y = (
            max_y - min_y
        )

        usable_length = max(
            0.0,
            self.pallet_length
            - 2.0
            * self.edge_margin_x,
        )
        usable_width = max(
            0.0,
            self.pallet_width
            - 2.0
            * self.edge_margin_y,
        )

        target_min_x = (
            self.edge_margin_x
            + max(
                0.0,
                (
                    usable_length
                    - span_x
                )
                / 2.0,
            )
        )

        target_min_y = (
            self.edge_margin_y
            + max(
                0.0,
                (
                    usable_width
                    - span_y
                )
                / 2.0,
            )
        )

        dx = (
            target_min_x
            - min_x
        )
        dy = (
            target_min_y
            - min_y
        )

        centered = []

        for stack in placed:

            centered.append(
                PlacedStack(
                    candidate=(
                        stack.candidate
                    ),
                    x=(
                        stack.x + dx
                    ),
                    y=(
                        stack.y + dy
                    ),
                    length=(
                        stack.length
                    ),
                    width=(
                        stack.width
                    ),
                    rotation=(
                        stack.rotation
                    ),
                )
            )

        return centered

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

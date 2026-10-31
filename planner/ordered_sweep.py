from dataclasses import dataclass, field
from math import floor
from typing import Dict, List

from config.products import PRODUCTS
from planner.extreme_points import (
    ExtremePointPlacer,
    PlacedStack,
)
from planner.models import StackCandidate
from planner.free_space import (
    FreeRect,
    calculate_free_rectangles,
)


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

        repacked = self._staged_pocket_repack(
            placed
        )

        return OrderedSweepState(
            placed=repacked,
            remaining=remaining,
        )

    def _staged_pocket_repack(
        self,
        placed: List[PlacedStack],
    ) -> List[PlacedStack]:
        """
        Rebuild the floor layout one SKU stage at a time.

        Earlier execution stages are frozen permanently:
            20L -> 10L -> 1L -> 4L

        For the current stage, choose legal Extreme Point placements
        that make best use of the actual free rectangular pockets left
        by the already-frozen stages.
        """

        if not placed:
            return placed

        by_sku = {
            sku: []
            for sku in EXECUTION_ORDER
        }

        for stack in placed:
            sku = stack.candidate.items[0]

            if sku in by_sku:
                by_sku[sku].append(
                    stack.candidate
                )

        frozen: List[
            PlacedStack
        ] = []

        for sku in EXECUTION_ORDER:

            for candidate in by_sku[sku]:

                options = (
                    self.placer.feasible_placements(
                        candidate=candidate,
                        placed=frozen,
                    )
                )

                if not options:
                    # Keep the original known-good layout if the
                    # staged pocket pass cannot reproduce a full fit.
                    return placed

                pockets = (
                    self._free_pockets(
                        frozen
                    )
                )

                chosen = min(
                    options,
                    key=lambda option:
                    self._pocket_placement_key(
                        option,
                        pockets,
                    ),
                )

                frozen.append(
                    chosen
                )

        return frozen

    def _free_pockets(
        self,
        placed: List[PlacedStack],
    ) -> List[FreeRect]:

        occupied = [
            FreeRect(
                x=stack.x,
                y=stack.y,
                width=stack.length,
                height=stack.width,
            )
            for stack in placed
        ]

        return calculate_free_rectangles(
            pallet_length=(
                self.pallet_length
            ),
            pallet_width=(
                self.pallet_width
            ),
            edge_margin_x=(
                self.edge_margin_x
            ),
            edge_margin_y=(
                self.edge_margin_y
            ),
            gap_x=self.gap_x,
            gap_y=self.gap_y,
            occupied_rectangles=occupied,
        )

    def _pocket_placement_key(
        self,
        option: PlacedStack,
        pockets: List[FreeRect],
    ):
        """
        Prefer a placement that sits inside the smallest useful free
        pocket. This consumes leftover pockets before opening up new
        pallet territory.

        Ties remain deterministic and follow the original corner sweep.
        """

        half_gap_x = (
            self.gap_x / 2.0
        )
        half_gap_y = (
            self.gap_y / 2.0
        )

        required_x0 = (
            option.x
            - half_gap_x
        )
        required_y0 = (
            option.y
            - half_gap_y
        )
        required_x1 = (
            option.right
            + half_gap_x
        )
        required_y1 = (
            option.top
            + half_gap_y
        )

        containing = []

        for pocket in pockets:

            if (
                required_x0
                >= pocket.x - 1e-6
                and
                required_y0
                >= pocket.y - 1e-6
                and
                required_x1
                <= pocket.right + 1e-6
                and
                required_y1
                <= pocket.top + 1e-6
            ):
                containing.append(
                    pocket
                )

        if containing:

            best_pocket = min(
                containing,
                key=lambda pocket: (
                    pocket.area,
                    pocket.y,
                    pocket.x,
                ),
            )

            required_area = (
                (
                    option.length
                    + self.gap_x
                )
                *
                (
                    option.width
                    + self.gap_y
                )
            )

            leftover_area = max(
                0.0,
                best_pocket.area
                - required_area,
            )

            return (
                0,
                round(
                    leftover_area,
                    6,
                ),
                round(
                    best_pocket.area,
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
                option.rotation,
            )

        return (
            1,
            float("inf"),
            float("inf"),
            round(
                option.y,
                6,
            ),
            round(
                option.x,
                6,
            ),
            option.rotation,
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

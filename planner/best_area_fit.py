from dataclasses import dataclass, field
from math import floor
from typing import Dict, List

from config.products import PRODUCTS
from planner.extreme_points import (
    ExtremePointPlacer,
    PlacedStack,
)
from planner.free_space import (
    FreeRect,
    calculate_free_rectangles,
)
from planner.models import StackCandidate


EXECUTION_ORDER = (
    "20L",
    "10L",
    "1L",
    "4L",
)


@dataclass
class BestAreaFitState:
    placed: List[PlacedStack] = field(
        default_factory=list
    )
    remaining: Dict[str, int] = field(
        default_factory=dict
    )

    def unplaced_count(self) -> int:
        return sum(self.remaining.values())

    def floor_positions(self) -> int:
        return len(self.placed)


class BestAreaFitPlanner:
    """
    Deterministic Best Area Fit planner.

    Stack order is fixed:
        20L -> 10L -> 1L -> 4L

    For each stack, enumerate legal Extreme Point placements and choose
    the placement that leaves the smallest containing free rectangle.
    Balance and corner-sweep coordinates are deterministic tie-breakers.
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
        self.pallet_length = pallet_length
        self.pallet_width = pallet_width
        self.max_height = max_height
        self.gap_x = gap_x
        self.gap_y = gap_y
        self.edge_margin_x = edge_margin_x
        self.edge_margin_y = edge_margin_y

        self.placer = ExtremePointPlacer(
            pallet_length=pallet_length,
            pallet_width=pallet_width,
            gap_x=gap_x,
            gap_y=gap_y,
            edge_margin_x=edge_margin_x,
            edge_margin_y=edge_margin_y,
        )

    def search(
        self,
        quantities: Dict[str, int],
    ) -> BestAreaFitState:
        remaining = {
            sku: max(
                0,
                int(quantities.get(sku, 0)),
            )
            for sku in PRODUCTS
        }

        placed: List[PlacedStack] = []

        for sku in EXECUTION_ORDER:
            candidates = self._build_sku_columns(
                sku=sku,
                quantity=remaining[sku],
            )

            for candidate in candidates:
                options = self.placer.feasible_placements(
                    candidate=candidate,
                    placed=placed,
                )

                if not options:
                    return BestAreaFitState(
                        placed=placed,
                        remaining=remaining,
                    )

                pockets = self._free_pockets(
                    placed
                )

                chosen = min(
                    options,
                    key=lambda option:
                    self._placement_key(
                        option,
                        pockets,
                        placed,
                    ),
                )

                placed.append(chosen)
                remaining[sku] -= len(
                    candidate.items
                )

        return BestAreaFitState(
            placed=placed,
            remaining=remaining,
        )

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
            pallet_length=self.pallet_length,
            pallet_width=self.pallet_width,
            edge_margin_x=self.edge_margin_x,
            edge_margin_y=self.edge_margin_y,
            gap_x=self.gap_x,
            gap_y=self.gap_y,
            occupied_rectangles=occupied,
        )

    def _placement_key(
        self,
        option: PlacedStack,
        pockets: List[FreeRect],
        placed: List[PlacedStack],
    ):
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
            pocket_area = pocket.area
        else:
            waste = float("inf")
            pocket_area = float("inf")

        cog_distance = self._trial_cog_distance(
            placed,
            option,
        )

        return (
            waste,
            pocket_area,
            cog_distance,
            round(option.y, 6),
            round(option.x, 6),
            option.rotation,
        )

    def _containing_pockets(
        self,
        option: PlacedStack,
        pockets: List[FreeRect],
    ) -> List[FreeRect]:
        half_gap_x = self.gap_x / 2.0
        half_gap_y = self.gap_y / 2.0

        x0 = option.x - half_gap_x
        y0 = option.y - half_gap_y
        x1 = option.right + half_gap_x
        y1 = option.top + half_gap_y

        return [
            pocket
            for pocket in pockets
            if (
                x0 >= pocket.x - 1e-6
                and y0 >= pocket.y - 1e-6
                and x1 <= pocket.right + 1e-6
                and y1 <= pocket.top + 1e-6
            )
        ]

    def _trial_cog_distance(
        self,
        placed: List[PlacedStack],
        option: PlacedStack,
    ) -> float:
        trial = placed + [option]

        total_weight = sum(
            stack.candidate.weight
            for stack in trial
        )

        if total_weight <= 0:
            return 0.0

        cog_x = sum(
            (
                stack.x
                + stack.length / 2.0
            )
            * stack.candidate.weight
            for stack in trial
        ) / total_weight

        cog_y = sum(
            (
                stack.y
                + stack.width / 2.0
            )
            * stack.candidate.weight
            for stack in trial
        ) / total_weight

        target_x = self.pallet_length / 2.0
        target_y = self.pallet_width / 2.0

        return (
            (cog_x - target_x) ** 2
            + (cog_y - target_y) ** 2
        ) ** 0.5

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

        columns: List[StackCandidate] = []
        remaining = quantity

        while remaining > 0:
            count = min(
                max_items,
                remaining,
            )

            columns.append(
                StackCandidate(
                    items=[sku] * count,
                    base_length=product.length,
                    base_width=product.width,
                    height=product.height * count,
                    weight=product.weight * count,
                    rotation=0.0,
                )
            )

            remaining -= count

        return columns


if __name__ == "__main__":
    planner = BestAreaFitPlanner(
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
    print("BEST AREA FIT RESULT")
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

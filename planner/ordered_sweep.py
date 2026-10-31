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

        optimized = (
            self._relocate_last_sku(
                placed=placed,
                sku="4L",
            )
        )

        return OrderedSweepState(
            placed=optimized,
            remaining=remaining,
        )

    def _relocate_last_sku(
        self,
        placed: List[PlacedStack],
        sku: str,
    ) -> List[PlacedStack]:
        """
        Controlled experiment:
          - only move stacks belonging to the requested final SKU
          - all earlier SKU stacks remain fixed
          - accept a move only if the complete pallet balance improves
        """

        if not placed:
            return placed

        current = list(placed)

        for index, stack in enumerate(
            list(current)
        ):

            stack_sku = (
                stack.candidate.items[0]
            )

            if stack_sku != sku:
                continue

            fixed = [
                other
                for position, other
                in enumerate(current)
                if position != index
            ]

            pockets = (
                self._free_pockets(
                    fixed
                )
            )

            options = (
                self.placer.feasible_placements(
                    candidate=stack.candidate,
                    placed=fixed,
                )
            )

            current_score = (
                self._relocation_score(
                    current
                )
            )

            current_bbox_area = (
                self._bounding_box_area(
                    current
                )
            )

            current_cog = (
                self._center_of_mass_xy(
                    current
                )
            )

            print(
                f"\n4L RELOCATION CHECK "
                f"stack_index={index}"
            )

            print(
                f"Current position: "
                f"X={stack.x:.0f} "
                f"Y={stack.y:.0f} | "
                f"BBox={current_bbox_area:,.0f} | "
                f"CoG=({current_cog[0]:.1f}, "
                f"{current_cog[1]:.1f})"
            )

            best_stack = stack
            best_score = current_score

            for option in options:

                inside_pocket = (
                    self._option_inside_pocket(
                        option,
                        pockets,
                    )
                )

                trial = list(current)
                trial[index] = option

                trial_bbox_area = (
                    self._bounding_box_area(
                        trial
                    )
                )

                trial_cog = (
                    self._center_of_mass_xy(
                        trial
                    )
                )

                score = (
                    self._relocation_score(
                        trial
                    )
                )

                reasons = []

                if not inside_pocket:
                    reasons.append(
                        "not inside free pocket"
                    )

                if (
                    trial_bbox_area
                    > current_bbox_area
                    + 1e-6
                ):
                    reasons.append(
                        "bounding box increased"
                    )

                if (
                    inside_pocket
                    and
                    trial_bbox_area
                    <= current_bbox_area
                    + 1e-6
                    and
                    score >= best_score
                ):
                    reasons.append(
                        "score not improved"
                    )

                accepted_candidate = (
                    inside_pocket
                    and
                    trial_bbox_area
                    <= current_bbox_area
                    + 1e-6
                    and
                    score < best_score
                )

                print(
                    f"  Candidate "
                    f"X={option.x:.0f} "
                    f"Y={option.y:.0f} "
                    f"R={option.rotation:.0f} | "
                    f"BBox={trial_bbox_area:,.0f} "
                    f"({trial_bbox_area - current_bbox_area:+,.0f}) | "
                    f"CoG=({trial_cog[0]:.1f}, "
                    f"{trial_cog[1]:.1f}) | "
                    f"{'ACCEPT' if accepted_candidate else 'REJECT'}"
                    + (
                        ""
                        if accepted_candidate
                        else
                        f": {', '.join(reasons)}"
                    )
                )

                if accepted_candidate:
                    best_score = score
                    best_stack = option

            current[index] = best_stack

        return current

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

    def _option_inside_pocket(
        self,
        option: PlacedStack,
        pockets: List[FreeRect],
    ) -> bool:

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

        return any(
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
            for pocket in pockets
        )

    def _bounding_box_area(
        self,
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

    def _relocation_score(
        self,
        placed: List[PlacedStack],
    ):

        bbox_area = (
            self._bounding_box_area(
                placed
            )
        )

        balance = (
            self._balance_score(
                placed
            )
        )

        return (
            round(
                bbox_area,
                6,
            ),
            balance[0],
            balance[1],
        )

    def _center_of_mass_xy(
        self,
        placed: List[PlacedStack],
    ):

        if not placed:
            return (
                self.pallet_length / 2.0,
                self.pallet_width / 2.0,
            )

        total_weight = sum(
            stack.candidate.weight
            for stack in placed
        )

        if total_weight <= 0:
            return (
                self.pallet_length / 2.0,
                self.pallet_width / 2.0,
            )

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

        return (
            cog_x,
            cog_y,
        )

    def _balance_score(
        self,
        placed: List[PlacedStack],
    ):
        """
        Lower is better.

        Use stack weight to measure pallet center-of-mass balance,
        then use occupied footprint center as a secondary tie-breaker.
        """

        if not placed:
            return (
                0.0,
                0.0,
            )

        total_weight = sum(
            stack.candidate.weight
            for stack in placed
        )

        target_x = (
            self.pallet_length
            / 2.0
        )
        target_y = (
            self.pallet_width
            / 2.0
        )

        if total_weight > 0:

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

        else:
            cog_x = target_x
            cog_y = target_y

        cog_offset = (
            (
                cog_x
                - target_x
            ) ** 2
            +
            (
                cog_y
                - target_y
            ) ** 2
        )

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

        footprint_center_x = (
            min_x + max_x
        ) / 2.0

        footprint_center_y = (
            min_y + max_y
        ) / 2.0

        footprint_offset = (
            (
                footprint_center_x
                - target_x
            ) ** 2
            +
            (
                footprint_center_y
                - target_y
            ) ** 2
        )

        return (
            round(
                cog_offset,
                6,
            ),
            round(
                footprint_offset,
                6,
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

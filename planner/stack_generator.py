from typing import Dict, List, Tuple

from config.products import PRODUCTS
from planner.models import StackCandidate
from planner.rules import can_stack


class StackGenerator:
    """
    Generate legal vertical stack patterns without positioning them
    on the pallet.

    A candidate describes only the vertical structure. Horizontal
    placement will be handled later by the Extreme Point planner.
    """

    def generate(
        self,
        quantities: Dict[str, int],
        max_height: float,
        max_slenderness: float = 3.0,
    ) -> List[StackCandidate]:

        available = {
            sku: max(0, int(quantities.get(sku, 0)))
            for sku in PRODUCTS
        }

        candidates: List[StackCandidate] = []
        seen: set[Tuple[str, ...]] = set()

        for bottom_sku, quantity in available.items():

            if quantity <= 0:
                continue

            remaining = dict(available)
            remaining[bottom_sku] -= 1

            self._extend_stack(
                items=[bottom_sku],
                remaining=remaining,
                max_height=max_height,
                max_slenderness=max_slenderness,
                candidates=candidates,
                seen=seen,
            )

        candidates.sort(
            key=lambda candidate: (
                -len(candidate.items),
                -candidate.weight,
                candidate.base_length * candidate.base_width,
                tuple(candidate.items),
            )
        )

        return candidates

    def _extend_stack(
        self,
        items: List[str],
        remaining: Dict[str, int],
        max_height: float,
        max_slenderness: float,
        candidates: List[StackCandidate],
        seen: set[Tuple[str, ...]],
    ) -> None:

        key = tuple(items)

        if key not in seen:
            seen.add(key)
            candidates.append(
                self._build_candidate(items)
            )

        top_sku = items[-1]

        for next_sku, quantity_left in remaining.items():

            if quantity_left <= 0:
                continue

            if not can_stack(
                top_sku,
                next_sku,
            ):
                continue

            if not self._respects_layer_limit(
                items,
                next_sku,
            ):
                continue

            if not self._fits_on_support(
                top_sku,
                next_sku,
            ):
                continue

            next_height = (
                self._stack_height(items)
                + PRODUCTS[next_sku].height
            )

            if next_height > max_height:
                continue

            base = PRODUCTS[items[0]]
            base_min_dimension = min(
                base.length,
                base.width,
            )

            family_slenderness = (
                4.0
                if base.family == "carton"
                else max_slenderness
            )

            if (
                base_min_dimension > 0
                and
                next_height / base_min_dimension
                > family_slenderness
            ):
                continue

            next_remaining = dict(remaining)
            next_remaining[next_sku] -= 1

            self._extend_stack(
                items=items + [next_sku],
                remaining=next_remaining,
                max_height=max_height,
                max_slenderness=max_slenderness,
                candidates=candidates,
                seen=seen,
            )

    @staticmethod
    def _respects_layer_limit(
        items: List[str],
        next_sku: str,
    ) -> bool:

        next_count = (
            items.count(next_sku)
            + 1
        )

        return (
            next_count
            <= PRODUCTS[next_sku].max_layers
        )

    @staticmethod
    def _fits_on_support(
        bottom_sku: str,
        top_sku: str,
    ) -> bool:

        bottom = PRODUCTS[bottom_sku]
        top = PRODUCTS[top_sku]

        normal_fit = (
            top.length <= bottom.length
            and
            top.width <= bottom.width
        )

        rotated_fit = (
            top.allow_rotation
            and
            top.width <= bottom.length
            and
            top.length <= bottom.width
        )

        return normal_fit or rotated_fit

    @staticmethod
    def _stack_height(
        items: List[str],
    ) -> float:

        return sum(
            PRODUCTS[sku].height
            for sku in items
        )

    @staticmethod
    def _stack_weight(
        items: List[str],
    ) -> float:

        return sum(
            PRODUCTS[sku].weight
            for sku in items
        )

    def _build_candidate(
        self,
        items: List[str],
    ) -> StackCandidate:

        bottom = PRODUCTS[
            items[0]
        ]

        return StackCandidate(
            items=list(items),
            base_length=bottom.length,
            base_width=bottom.width,
            height=self._stack_height(items),
            weight=self._stack_weight(items),
            rotation=0.0,
        )


if __name__ == "__main__":

    generator = StackGenerator()

    candidates = generator.generate(
        quantities={
            "1L": 3,
            "4L": 6,
            "10L": 16,
            "20L": 2,
        },
        max_height=1600,
        max_slenderness=3.0,
    )

    for candidate in candidates:
        print(
            f"{candidate.items} | "
            f"footprint="
            f"{candidate.base_length:.0f}x"
            f"{candidate.base_width:.0f} | "
            f"H={candidate.height:.0f} | "
            f"W={candidate.weight:.1f}"
        )

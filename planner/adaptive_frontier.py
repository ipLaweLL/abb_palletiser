from typing import Dict

from config.products import PRODUCTS
from planner.balanced_frontier import (
    BalancedFrontierPlanner,
)
from planner.frontier_lookahead import (
    FrontierLookaheadPlanner,
)
from planner.lookahead_area_fit import (
    LookaheadAreaFitPlanner,
)


class AdaptiveFrontierPlanner:
    """
    Pressure-aware planner selector.

    Pressure is estimated as:
        required stack-column footprint area
        / usable pallet floor area

    Modes:
      - ROOMY  : pressure < 0.55
                 use Frontier Lookahead for the cleanest corner-grown pattern
      - MEDIUM : pressure < 0.75
                 use Balanced Frontier for a cleaner balance/compactness tradeoff
      - TIGHT  : pressure >= 0.75
                 use Lookahead Area Fit to maximize future feasibility

    The application-facing interface stays the same: search() returns
    a planner state with placed and remaining.
    """

    ROOMY_LIMIT = 0.55
    TIGHT_LIMIT = 0.75

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

        self.pressure = 0.0
        self.mode = "ROOMY"
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

        self.frontier = FrontierLookaheadPlanner(
            **common,
        )
        self.balanced = BalancedFrontierPlanner(
            **common,
        )
        self.lookahead = LookaheadAreaFitPlanner(
            **common,
        )

    def search(
        self,
        quantities: Dict[str, int],
    ):
        self.pressure = self._packing_pressure(
            quantities
        )

        if self.pressure < self.ROOMY_LIMIT:
            self.mode = "ROOMY"
            self.selected_name = "Frontier Look"
            planner = self.frontier

        elif self.pressure < self.TIGHT_LIMIT:
            self.mode = "MEDIUM"
            self.selected_name = "Balanced Front"
            planner = self.balanced

        else:
            self.mode = "TIGHT"
            self.selected_name = "Lookahead Fit"
            planner = self.lookahead

        return planner.search(
            quantities
        )

    def _packing_pressure(
        self,
        quantities: Dict[str, int],
    ) -> float:
        usable_length = max(
            0.0,
            self.pallet_length
            - 2.0 * self.edge_margin_x,
        )
        usable_width = max(
            0.0,
            self.pallet_width
            - 2.0 * self.edge_margin_y,
        )

        usable_area = (
            usable_length
            * usable_width
        )

        if usable_area <= 0.0:
            return float("inf")

        required_area = 0.0

        # Use the same stack-column construction as the underlying
        # planners so pressure reflects floor positions, not raw items.
        for sku in (
            "20L",
            "10L",
            "1L",
            "4L",
        ):
            quantity = max(
                0,
                int(
                    quantities.get(
                        sku,
                        0,
                    )
                ),
            )

            for candidate in self.frontier._build_sku_columns(
                sku=sku,
                quantity=quantity,
            ):
                required_area += (
                    candidate.base_length
                    + self.gap_x
                ) * (
                    candidate.base_width
                    + self.gap_y
                )

        return (
            required_area
            / usable_area
        )


if __name__ == "__main__":
    for pallet_length, pallet_width in (
        (1300, 1300),
        (1500, 1500),
        (1200, 1000),
    ):
        planner = AdaptiveFrontierPlanner(
            pallet_length=pallet_length,
            pallet_width=pallet_width,
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
        print(
            f"ADAPTIVE FRONTIER "
            f"{pallet_length}x{pallet_width}"
        )
        print("=" * 60)
        print(
            "Pressure:",
            f"{planner.pressure:.3f}",
            "| Mode:",
            planner.mode,
            "| Selected:",
            planner.selected_name,
        )
        print(
            "Remaining:",
            result.remaining,
        )
        print(
            "Floor positions:",
            result.floor_positions(),
        )

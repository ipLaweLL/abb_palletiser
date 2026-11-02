from typing import Dict, List

from config.products import PRODUCTS
from planner.extreme_points import PlacedStack
from planner.free_space import FreeRect
from planner.frontier_lookahead import (
    FrontierLookaheadPlanner,
)


class AdaptiveFrontierPlanner(
    FrontierLookaheadPlanner
):
    """
    Frontier lookahead whose placement style adapts to packing pressure.

    Pressure is estimated as:
        required stack-column footprint area
        / usable pallet floor area

    Modes:
      - ROOMY  : pressure < 0.55
                 preserve row-major frontier aggressively
      - MEDIUM : pressure < 0.75
                 preserve feasibility, then compact growth
      - TIGHT  : pressure >= 0.75
                 prioritize future fit and compact space use

    The planner never sacrifices future feasibility for appearance.
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
        super().__init__(
            pallet_length=pallet_length,
            pallet_width=pallet_width,
            max_height=max_height,
            gap_x=gap_x,
            gap_y=gap_y,
            edge_margin_x=edge_margin_x,
            edge_margin_y=edge_margin_y,
        )

        self.pressure = 0.0
        self.mode = "ROOMY"

    def search(
        self,
        quantities: Dict[str, int],
    ):
        self.pressure = (
            self._packing_pressure(
                quantities
            )
        )

        if self.pressure < self.ROOMY_LIMIT:
            self.mode = "ROOMY"
        elif self.pressure < self.TIGHT_LIMIT:
            self.mode = "MEDIUM"
        else:
            self.mode = "TIGHT"

        return super().search(
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

            for candidate in self._build_sku_columns(
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

        y = round(
            option.y,
            6,
        )
        x = round(
            option.x,
            6,
        )
        bbox = round(
            bbox_area,
            6,
        )
        cog = round(
            cog_distance,
            6,
        )

        common_tail = (
            round(option.length, 6),
            round(option.width, 6),
            option.rotation,
        )

        if self.mode == "ROOMY":
            return (
                future_unplaced,
                y,
                x,
                bbox,
                cog,
                *common_tail,
            )

        if self.mode == "MEDIUM":
            return (
                future_unplaced,
                bbox,
                y,
                x,
                cog,
                *common_tail,
            )

        return (
            future_unplaced,
            bbox,
            cog,
            y,
            x,
            *common_tail,
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
        )
        print(
            "Remaining:",
            result.remaining,
        )
        print(
            "Floor positions:",
            result.floor_positions(),
        )

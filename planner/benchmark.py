from dataclasses import dataclass
from math import hypot
from typing import Dict, List

from config.deliveries import DELIVERY_ORDERS
from planner.best_area_fit import BestAreaFitPlanner
from planner.free_space import (
    FreeRect,
    calculate_free_rectangles,
)
from planner.ordered_sweep import OrderedSweepPlanner


PALLET_LENGTH = 1300.0
PALLET_WIDTH = 1300.0
MAX_HEIGHT = 1600.0
GAP_X = 20.0
GAP_Y = 20.0
EDGE_MARGIN_X = 20.0
EDGE_MARGIN_Y = 20.0


@dataclass
class Metrics:
    success: bool
    unplaced: int
    floor_positions: int
    cog_distance: float
    bounding_area: float
    free_area: float
    free_percent: float
    largest_pocket_area: float
    largest_pocket_width: float
    largest_pocket_height: float
    max_height: float


def evaluate(
    placed,
    remaining: Dict[str, int],
) -> Metrics:

    unplaced = sum(
        max(0, int(value))
        for value in remaining.values()
    )

    success = (
        unplaced == 0
    )

    if not placed:
        usable_area = (
            PALLET_LENGTH
            - 2.0 * EDGE_MARGIN_X
        ) * (
            PALLET_WIDTH
            - 2.0 * EDGE_MARGIN_Y
        )

        return Metrics(
            success=success,
            unplaced=unplaced,
            floor_positions=0,
            cog_distance=float("inf"),
            bounding_area=0.0,
            free_area=usable_area,
            free_percent=100.0,
            largest_pocket_area=usable_area,
            largest_pocket_width=(
                PALLET_LENGTH
                - 2.0 * EDGE_MARGIN_X
            ),
            largest_pocket_height=(
                PALLET_WIDTH
                - 2.0 * EDGE_MARGIN_Y
            ),
            max_height=0.0,
        )

    total_weight = sum(
        stack.candidate.weight
        for stack in placed
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

    target_x = (
        PALLET_LENGTH / 2.0
    )
    target_y = (
        PALLET_WIDTH / 2.0
    )

    cog_distance = hypot(
        cog_x - target_x,
        cog_y - target_y,
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

    bounding_area = (
        max_x - min_x
    ) * (
        max_y - min_y
    )

    occupied = [
        FreeRect(
            x=stack.x,
            y=stack.y,
            width=stack.length,
            height=stack.width,
        )
        for stack in placed
    ]

    pockets = calculate_free_rectangles(
        pallet_length=PALLET_LENGTH,
        pallet_width=PALLET_WIDTH,
        edge_margin_x=EDGE_MARGIN_X,
        edge_margin_y=EDGE_MARGIN_Y,
        gap_x=GAP_X,
        gap_y=GAP_Y,
        occupied_rectangles=occupied,
    )

    free_area = sum(
        pocket.area
        for pocket in pockets
    )

    usable_area = (
        PALLET_LENGTH
        - 2.0 * EDGE_MARGIN_X
    ) * (
        PALLET_WIDTH
        - 2.0 * EDGE_MARGIN_Y
    )

    free_percent = (
        free_area
        / usable_area
        * 100.0
        if usable_area > 0
        else 0.0
    )

    largest = (
        pockets[0]
        if pockets
        else FreeRect(
            x=0.0,
            y=0.0,
            width=0.0,
            height=0.0,
        )
    )

    max_height = max(
        stack.candidate.height
        for stack in placed
    )

    return Metrics(
        success=success,
        unplaced=unplaced,
        floor_positions=len(placed),
        cog_distance=cog_distance,
        bounding_area=bounding_area,
        free_area=free_area,
        free_percent=free_percent,
        largest_pocket_area=(
            largest.area
        ),
        largest_pocket_width=(
            largest.width
        ),
        largest_pocket_height=(
            largest.height
        ),
        max_height=max_height,
    )


def format_metrics(
    name: str,
    metrics: Metrics,
) -> str:

    status = (
        "OK"
        if metrics.success
        else f"FAIL({metrics.unplaced})"
    )

    return (
        f"{name:<16} "
        f"{status:<10} "
        f"Floor={metrics.floor_positions:<3} "
        f"CoG={metrics.cog_distance:>7.1f} mm  "
        f"BBox={metrics.bounding_area:>10,.0f}  "
        f"Free={metrics.free_percent:>5.1f}%  "
        f"Largest="
        f"{metrics.largest_pocket_width:.0f}x"
        f"{metrics.largest_pocket_height:.0f}  "
        f"MaxH={metrics.max_height:.0f}"
    )


def quantities_from_order(
    order: Dict,
) -> Dict[str, int]:

    return {
        "1L": int(
            order.get("1L", 0)
        ),
        "4L": int(
            order.get("4L", 0)
        ),
        "10L": int(
            order.get("10L", 0)
        ),
        "20L": int(
            order.get("20L", 0)
        ),
    }


def run_one(
    order: Dict,
):

    quantities = (
        quantities_from_order(
            order
        )
    )

    corner = OrderedSweepPlanner(
        pallet_length=PALLET_LENGTH,
        pallet_width=PALLET_WIDTH,
        max_height=MAX_HEIGHT,
        gap_x=GAP_X,
        gap_y=GAP_Y,
        edge_margin_x=EDGE_MARGIN_X,
        edge_margin_y=EDGE_MARGIN_Y,
        enable_last_sku_relocation=False,
    )

    baf = BestAreaFitPlanner(
        pallet_length=PALLET_LENGTH,
        pallet_width=PALLET_WIDTH,
        max_height=MAX_HEIGHT,
        gap_x=GAP_X,
        gap_y=GAP_Y,
        edge_margin_x=EDGE_MARGIN_X,
        edge_margin_y=EDGE_MARGIN_Y,
    )

    corner_result = (
        corner.search(
            quantities
        )
    )

    baf_result = (
        baf.search(
            quantities
        )
    )

    corner_metrics = evaluate(
        corner_result.placed,
        corner_result.remaining,
    )

    baf_metrics = evaluate(
        baf_result.placed,
        baf_result.remaining,
    )

    return (
        corner_metrics,
        baf_metrics,
    )


def main() -> None:

    corner_success = 0
    baf_success = 0

    corner_cog: List[float] = []
    baf_cog: List[float] = []

    corner_free: List[float] = []
    baf_free: List[float] = []

    for order in DELIVERY_ORDERS:

        print()
        print("=" * 100)
        print(
            f"ROW {order['line']} | "
            f"Delivery "
            f"{order['delivery']}"
        )
        print(
            "Order:",
            quantities_from_order(
                order
            ),
        )
        print("=" * 100)

        (
            corner_metrics,
            baf_metrics,
        ) = run_one(order)

        print(
            format_metrics(
                "Corner Sweep",
                corner_metrics,
            )
        )

        print(
            format_metrics(
                "Best Area Fit",
                baf_metrics,
            )
        )

        if corner_metrics.success:
            corner_success += 1
            corner_cog.append(
                corner_metrics.cog_distance
            )
            corner_free.append(
                corner_metrics.free_percent
            )

        if baf_metrics.success:
            baf_success += 1
            baf_cog.append(
                baf_metrics.cog_distance
            )
            baf_free.append(
                baf_metrics.free_percent
            )

    print()
    print("=" * 100)
    print("OVERALL")
    print("=" * 100)

    corner_avg_cog = (
        sum(corner_cog) / len(corner_cog)
        if corner_cog
        else float("nan")
    )
    corner_avg_free = (
        sum(corner_free) / len(corner_free)
        if corner_free
        else float("nan")
    )
    baf_avg_cog = (
        sum(baf_cog) / len(baf_cog)
        if baf_cog
        else float("nan")
    )
    baf_avg_free = (
        sum(baf_free) / len(baf_free)
        if baf_free
        else float("nan")
    )

    print(
        f"Corner Sweep  "
        f"success={corner_success}/{len(DELIVERY_ORDERS)}  "
        f"avg_CoG={corner_avg_cog:.1f} mm  "
        f"avg_free={corner_avg_free:.1f}%"
    )

    print(
        f"Best Area Fit "
        f"success={baf_success}/{len(DELIVERY_ORDERS)}  "
        f"avg_CoG={baf_avg_cog:.1f} mm  "
        f"avg_free={baf_avg_free:.1f}%"
    )


if __name__ == "__main__":
    main()

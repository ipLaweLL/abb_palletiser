from dataclasses import dataclass
from math import hypot
from typing import Dict, List, Tuple

from config.deliveries import DELIVERY_ORDERS
from planner.adaptive_planner import AdaptivePlanner
from planner.best_area_fit import BestAreaFitPlanner
from planner.compact_lookahead import CompactLookaheadAreaFitPlanner
from planner.free_space import FreeRect, calculate_free_rectangles
from planner.lookahead_area_fit import LookaheadAreaFitPlanner
from planner.ordered_sweep import OrderedSweepPlanner


MAX_HEIGHT = 1600.0
GAP_X = 20.0
GAP_Y = 20.0
EDGE_MARGIN_X = 20.0
EDGE_MARGIN_Y = 20.0

PALLET_SIZES: List[Tuple[str, float, float]] = [
    ("1300x1300", 1300.0, 1300.0),
    ("1500x1500", 1500.0, 1500.0),
    ("1200x1000", 1200.0, 1000.0),
]


@dataclass
class Metrics:
    success: bool
    unplaced: int
    floor_positions: int
    cog_distance: float
    bounding_area: float
    free_percent: float
    largest_pocket_width: float
    largest_pocket_height: float
    max_height: float


def quantities_from_order(order: Dict) -> Dict[str, int]:
    return {
        "1L": int(order.get("1L", 0)),
        "4L": int(order.get("4L", 0)),
        "10L": int(order.get("10L", 0)),
        "20L": int(order.get("20L", 0)),
    }


def evaluate(
    placed,
    remaining: Dict[str, int],
    pallet_length: float,
    pallet_width: float,
) -> Metrics:
    unplaced = sum(
        max(0, int(value))
        for value in remaining.values()
    )
    success = unplaced == 0

    usable_width = max(
        0.0,
        pallet_length - 2.0 * EDGE_MARGIN_X,
    )
    usable_height = max(
        0.0,
        pallet_width - 2.0 * EDGE_MARGIN_Y,
    )
    usable_area = usable_width * usable_height

    if not placed:
        return Metrics(
            success=success,
            unplaced=unplaced,
            floor_positions=0,
            cog_distance=float("inf"),
            bounding_area=0.0,
            free_percent=100.0 if usable_area > 0 else 0.0,
            largest_pocket_width=usable_width,
            largest_pocket_height=usable_height,
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

    target_x = pallet_length / 2.0
    target_y = pallet_width / 2.0

    cog_distance = hypot(
        cog_x - target_x,
        cog_y - target_y,
    )

    min_x = min(stack.x for stack in placed)
    min_y = min(stack.y for stack in placed)
    max_x = max(stack.right for stack in placed)
    max_y = max(stack.top for stack in placed)

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
        pallet_length=pallet_length,
        pallet_width=pallet_width,
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

    free_percent = (
        free_area / usable_area * 100.0
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
        free_percent=free_percent,
        largest_pocket_width=largest.width,
        largest_pocket_height=largest.height,
        max_height=max_height,
    )


def build_planners(
    pallet_length: float,
    pallet_width: float,
):
    common = dict(
        pallet_length=pallet_length,
        pallet_width=pallet_width,
        max_height=MAX_HEIGHT,
        gap_x=GAP_X,
        gap_y=GAP_Y,
        edge_margin_x=EDGE_MARGIN_X,
        edge_margin_y=EDGE_MARGIN_Y,
    )

    return {
        "Corner Sweep": OrderedSweepPlanner(
            **common,
            enable_last_sku_relocation=False,
        ),
        "Best Area Fit": BestAreaFitPlanner(
            **common,
        ),
        "Lookahead Fit": LookaheadAreaFitPlanner(
            **common,
        ),
        "Compact Look": CompactLookaheadAreaFitPlanner(
            **common,
        ),
        "Adaptive Select": AdaptivePlanner(
            **common,
        ),
    }


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


def run_pallet(
    label: str,
    pallet_length: float,
    pallet_width: float,
) -> None:
    print()
    print("#" * 110)
    print(
        f"PALLET {label} | "
        f"{pallet_length:.0f} x "
        f"{pallet_width:.0f} mm"
    )
    print("#" * 110)

    summary = {
        "Corner Sweep": {
            "success": 0,
            "cog": [],
        },
        "Best Area Fit": {
            "success": 0,
            "cog": [],
        },
        "Lookahead Fit": {
            "success": 0,
            "cog": [],
        },
        "Compact Look": {
            "success": 0,
            "cog": [],
        },
        "Adaptive Select": {
            "success": 0,
            "cog": [],
        },
    }

    for order in DELIVERY_ORDERS:
        quantities = quantities_from_order(
            order
        )

        print()
        print("=" * 110)
        print(
            f"ROW {order['line']} | "
            f"Order={quantities}"
        )
        print("=" * 110)

        planners = build_planners(
            pallet_length,
            pallet_width,
        )

        for name, planner in planners.items():
            result = planner.search(
                quantities
            )

            metrics = evaluate(
                result.placed,
                result.remaining,
                pallet_length,
                pallet_width,
            )

            print(
                format_metrics(
                    name,
                    metrics,
                )
            )

            if metrics.success:
                summary[name]["success"] += 1
                summary[name]["cog"].append(
                    metrics.cog_distance
                )

    print()
    print("-" * 110)
    print(
        f"SUMMARY | PALLET {label}"
    )
    print("-" * 110)

    for name in (
        "Corner Sweep",
        "Best Area Fit",
        "Lookahead Fit",
        "Compact Look",
        "Adaptive Select",
    ):
        values = summary[name]
        cogs = values["cog"]
        avg_cog = (
            sum(cogs) / len(cogs)
            if cogs
            else float("nan")
        )

        print(
            f"{name:<16} "
            f"success="
            f"{values['success']}/"
            f"{len(DELIVERY_ORDERS)}  "
            f"avg_CoG="
            f"{avg_cog:.1f} mm"
        )


def main() -> None:
    for (
        label,
        pallet_length,
        pallet_width,
    ) in PALLET_SIZES:
        run_pallet(
            label=label,
            pallet_length=pallet_length,
            pallet_width=pallet_width,
        )


if __name__ == "__main__":
    main()

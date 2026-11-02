from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from config.products import PRODUCTS
from planner.new_planner import NewPalletPlanner


from config.validation_cases import VALIDATION_ORDERS


TEST_ORDERS = VALIDATION_ORDERS


PALLETS: List[Dict[str, float]] = [
    {
        "name": "1300x1300",
        "length": 1300.0,
        "width": 1300.0,
        "height": 1000.0,
        "weight": 1000.0,
    },
    {
        "name": "1500x1500",
        "length": 1500.0,
        "width": 1500.0,
        "height": 1000.0,
        "weight": 1000.0,
    },
    {
        "name": "1200x1000",
        "length": 1200.0,
        "width": 1000.0,
        "height": 1000.0,
        "weight": 1000.0,
    },
    {
        "name": "1300x1300-low-height",
        "length": 1300.0,
        "width": 1300.0,
        "height": 700.0,
        "weight": 1000.0,
    },
    {
        "name": "1300x1300-low-weight",
        "length": 1300.0,
        "width": 1300.0,
        "height": 1000.0,
        "weight": 300.0,
    },
]


GAP_X = 20.0
GAP_Y = 20.0
EDGE_MARGIN_X = 20.0
EDGE_MARGIN_Y = 20.0
EPS = 1e-6


def order_quantities(order: Dict[str, int]) -> Dict[str, int]:
    return {
        sku: int(order.get(sku, 0))
        for sku in ("1L", "4L", "10L", "20L")
    }


def stack_rectangles(slots) -> List[Tuple[int, float, float, float, float]]:
    """
    Return one conservative XY rectangle per vertical stack.

    Slot coordinates are item centres. Using the maximum item dimensions
    in a stack safely covers every level of that stack.
    """
    grouped = defaultdict(list)

    for slot in slots:
        grouped[slot.stack_id].append(slot)

    rectangles = []

    for stack_id, stack_slots in grouped.items():
        center_x = stack_slots[0].x
        center_y = stack_slots[0].y
        length = max(slot.length for slot in stack_slots)
        width = max(slot.width for slot in stack_slots)

        rectangles.append(
            (
                stack_id,
                center_x - length / 2.0,
                center_y - width / 2.0,
                center_x + length / 2.0,
                center_y + width / 2.0,
            )
        )

    return rectangles


def validate_success(
    result,
    requested: Dict[str, int],
    pallet: Dict[str, float],
) -> List[str]:
    errors: List[str] = []

    actual = Counter(slot.sku for slot in result.slots)
    expected = Counter(
        {
            sku: max(0, int(quantity))
            for sku, quantity in requested.items()
            if quantity > 0
        }
    )

    if actual != expected:
        errors.append(
            f"quantity mismatch: expected={dict(expected)}, "
            f"actual={dict(actual)}"
        )

    ids = [slot.id for slot in result.slots]
    expected_ids = list(range(1, len(result.slots) + 1))

    if ids != expected_ids:
        errors.append("slot IDs are not sequential from 1")

    total_weight = sum(
        PRODUCTS[slot.sku].weight
        for slot in result.slots
    )

    if total_weight > pallet["weight"] + EPS:
        errors.append(
            f"weight {total_weight:.1f} kg exceeds "
            f"{pallet['weight']:.1f} kg"
        )

    for slot in result.slots:
        left = slot.x - slot.length / 2.0
        right = slot.x + slot.length / 2.0
        bottom = slot.y - slot.width / 2.0
        top = slot.y + slot.width / 2.0
        z_bottom = slot.z - slot.height / 2.0
        z_top = slot.z + slot.height / 2.0

        if left < -EPS or right > pallet["length"] + EPS:
            errors.append(
                f"slot {slot.id} ({slot.sku}) exceeds X bounds"
            )

        if bottom < -EPS or top > pallet["width"] + EPS:
            errors.append(
                f"slot {slot.id} ({slot.sku}) exceeds Y bounds"
            )

        if z_bottom < -EPS or z_top > pallet["height"] + EPS:
            errors.append(
                f"slot {slot.id} ({slot.sku}) exceeds Z bounds"
            )

    rectangles = stack_rectangles(result.slots)

    for i in range(len(rectangles)):
        id_a, ax1, ay1, ax2, ay2 = rectangles[i]

        for j in range(i + 1, len(rectangles)):
            id_b, bx1, by1, bx2, by2 = rectangles[j]

            overlap_x = (
                min(ax2, bx2)
                - max(ax1, bx1)
            )
            overlap_y = (
                min(ay2, by2)
                - max(ay1, by1)
            )

            if overlap_x > EPS and overlap_y > EPS:
                errors.append(
                    f"stack overlap: {id_a} and {id_b}"
                )

    return errors


def run_case(
    order: Dict[str, int],
    pallet: Dict[str, float],
) -> Tuple[str, str]:
    quantities = order_quantities(order)
    planner = NewPalletPlanner()

    result = planner.generate(
        quantities=quantities,
        pallet_length=pallet["length"],
        pallet_width=pallet["width"],
        max_height=pallet["height"],
        max_weight=pallet["weight"],
        overhang=0.0,
        gap_x=GAP_X,
        gap_y=GAP_Y,
        edge_margin_x=EDGE_MARGIN_X,
        edge_margin_y=EDGE_MARGIN_Y,
    )

    if not result.success:
        # A clean planner rejection is valid behaviour. The purpose of
        # this harness is to catch crashes, silent item loss, invalid
        # geometry, or success results that violate constraints.
        return "REJECT", result.error

    errors = validate_success(
        result=result,
        requested=quantities,
        pallet=pallet,
    )

    if errors:
        return "INVALID", " | ".join(errors)

    return (
        "PASS",
        f"slots={len(result.slots)} "
        f"planner={planner.last_selected_planner}",
    )


def main() -> None:
    counts = Counter()
    total_cases = 0

    for pallet in PALLETS:
        print()
        print("=" * 120)
        print(
            f"PALLET {pallet['name']} | "
            f"{pallet['length']:.0f} x "
            f"{pallet['width']:.0f} x "
            f"{pallet['height']:.0f} mm | "
            f"max {pallet['weight']:.0f} kg"
        )
        print("=" * 120)

        for order in TEST_ORDERS:
            quantities = order_quantities(order)
            total_cases += 1

            try:
                status, detail = run_case(
                    order=order,
                    pallet=pallet,
                )
            except Exception as exc:
                status = "CRASH"
                detail = (
                    f"{type(exc).__name__}: {exc}"
                )

            counts[status] += 1

            print(
                f"Row {order['line']:02d} | "
                f"{quantities} | "
                f"{status:<7} | "
                f"{detail}"
            )

    print()
    print("=" * 120)
    print("VALIDATION SUMMARY")
    print("=" * 120)
    print(f"Total cases : {total_cases}")
    print(f"PASS        : {counts['PASS']}")
    print(f"REJECT      : {counts['REJECT']}")
    print(f"INVALID     : {counts['INVALID']}")
    print(f"CRASH       : {counts['CRASH']}")

    print()
    if counts["INVALID"] == 0 and counts["CRASH"] == 0:
        print(
            "RESULT: geometry/accounting validation passed. "
            "REJECT cases were handled cleanly by the planner."
        )
    else:
        print(
            "RESULT: validation found a real problem. "
            "Inspect INVALID/CRASH rows above."
        )


if __name__ == "__main__":
    main()

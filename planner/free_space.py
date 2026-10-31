from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class FreeRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height


def fitting_skus(
    pocket: FreeRect,
    products,
    gap_x: float,
    gap_y: float,
) -> List[str]:
    """
    Return SKUs whose floor footprint can fit inside this free pocket.

    The pocket already reserves half the configured gap around existing
    stacks. The candidate reserves its own half-gap on each side, so
    the required pocket size is footprint + full configured gap.
    """

    fits = []

    for sku, product in products.items():

        required_length = (
            product.length
            + gap_x
        )

        required_width = (
            product.width
            + gap_y
        )

        normal_fit = (
            required_length
            <= pocket.width
            and
            required_width
            <= pocket.height
        )

        rotated_fit = False

        if product.allow_rotation:

            rotated_fit = (
                product.width
                + gap_x
                <= pocket.width
                and
                product.length
                + gap_y
                <= pocket.height
            )

        if normal_fit or rotated_fit:
            fits.append(sku)

    return fits


def calculate_free_rectangles(
    pallet_length: float,
    pallet_width: float,
    edge_margin_x: float,
    edge_margin_y: float,
    gap_x: float,
    gap_y: float,
    occupied_rectangles: Iterable[FreeRect],
) -> List[FreeRect]:
    """
    Return non-overlapping free rectangular pockets inside the usable
    pallet area.

    Each occupied footprint consumes half the configured inter-item gap
    on each side. Two neighbouring stacks therefore consume the full
    requested gap between them.

    The usable pallet already excludes edge margins.
    """

    usable_x0 = edge_margin_x
    usable_y0 = edge_margin_y
    usable_x1 = pallet_length - edge_margin_x
    usable_y1 = pallet_width - edge_margin_y

    if usable_x1 <= usable_x0 or usable_y1 <= usable_y0:
        return []

    free_rects = [
        FreeRect(
            x=usable_x0,
            y=usable_y0,
            width=usable_x1 - usable_x0,
            height=usable_y1 - usable_y0,
        )
    ]

    half_gap_x = gap_x / 2.0
    half_gap_y = gap_y / 2.0

    for occupied in occupied_rectangles:

        blocked = FreeRect(
            x=max(
                usable_x0,
                occupied.x - half_gap_x,
            ),
            y=max(
                usable_y0,
                occupied.y - half_gap_y,
            ),
            width=0.0,
            height=0.0,
        )

        blocked_right = min(
            usable_x1,
            occupied.right + half_gap_x,
        )
        blocked_top = min(
            usable_y1,
            occupied.top + half_gap_y,
        )

        blocked = FreeRect(
            x=blocked.x,
            y=blocked.y,
            width=max(
                0.0,
                blocked_right - blocked.x,
            ),
            height=max(
                0.0,
                blocked_top - blocked.y,
            ),
        )

        if blocked.width <= 0 or blocked.height <= 0:
            continue

        next_free = []

        for rect in free_rects:
            next_free.extend(
                _subtract_rectangle(
                    rect,
                    blocked,
                )
            )

        free_rects = _merge_adjacent(
            next_free
        )

    return sorted(
        (
            rect
            for rect in free_rects
            if rect.width > 0
            and rect.height > 0
        ),
        key=lambda rect: (
            -rect.area,
            rect.y,
            rect.x,
        ),
    )


def _subtract_rectangle(
    source: FreeRect,
    blocked: FreeRect,
) -> List[FreeRect]:

    overlap_x0 = max(
        source.x,
        blocked.x,
    )
    overlap_y0 = max(
        source.y,
        blocked.y,
    )
    overlap_x1 = min(
        source.right,
        blocked.right,
    )
    overlap_y1 = min(
        source.top,
        blocked.top,
    )

    if (
        overlap_x0 >= overlap_x1
        or overlap_y0 >= overlap_y1
    ):
        return [source]

    pieces = []

    # Left strip
    if source.x < overlap_x0:
        pieces.append(
            FreeRect(
                x=source.x,
                y=source.y,
                width=overlap_x0 - source.x,
                height=source.height,
            )
        )

    # Right strip
    if overlap_x1 < source.right:
        pieces.append(
            FreeRect(
                x=overlap_x1,
                y=source.y,
                width=source.right - overlap_x1,
                height=source.height,
            )
        )

    middle_x0 = overlap_x0
    middle_x1 = overlap_x1

    # Bottom strip in the overlap's X span
    if source.y < overlap_y0:
        pieces.append(
            FreeRect(
                x=middle_x0,
                y=source.y,
                width=middle_x1 - middle_x0,
                height=overlap_y0 - source.y,
            )
        )

    # Top strip in the overlap's X span
    if overlap_y1 < source.top:
        pieces.append(
            FreeRect(
                x=middle_x0,
                y=overlap_y1,
                width=middle_x1 - middle_x0,
                height=source.top - overlap_y1,
            )
        )

    return [
        piece
        for piece in pieces
        if piece.width > 0
        and piece.height > 0
    ]


def _merge_adjacent(
    rectangles: List[FreeRect],
) -> List[FreeRect]:

    rects = list(rectangles)
    changed = True

    while changed:
        changed = False

        for i in range(len(rects)):
            if changed:
                break

            for j in range(i + 1, len(rects)):

                first = rects[i]
                second = rects[j]

                merged = _try_merge(
                    first,
                    second,
                )

                if merged is None:
                    continue

                rects = [
                    rect
                    for index, rect
                    in enumerate(rects)
                    if index not in (i, j)
                ]
                rects.append(merged)
                changed = True
                break

    return rects


def _try_merge(
    first: FreeRect,
    second: FreeRect,
):
    eps = 1e-6

    same_y_span = (
        abs(first.y - second.y) < eps
        and
        abs(first.height - second.height) < eps
    )

    if same_y_span:

        if abs(first.right - second.x) < eps:
            return FreeRect(
                x=first.x,
                y=first.y,
                width=(
                    first.width
                    + second.width
                ),
                height=first.height,
            )

        if abs(second.right - first.x) < eps:
            return FreeRect(
                x=second.x,
                y=second.y,
                width=(
                    second.width
                    + first.width
                ),
                height=second.height,
            )

    same_x_span = (
        abs(first.x - second.x) < eps
        and
        abs(first.width - second.width) < eps
    )

    if same_x_span:

        if abs(first.top - second.y) < eps:
            return FreeRect(
                x=first.x,
                y=first.y,
                width=first.width,
                height=(
                    first.height
                    + second.height
                ),
            )

        if abs(second.top - first.y) < eps:
            return FreeRect(
                x=second.x,
                y=second.y,
                width=second.width,
                height=(
                    second.height
                    + first.height
                ),
            )

    return None

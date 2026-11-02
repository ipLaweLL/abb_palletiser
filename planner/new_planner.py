from math import ceil, floor, sqrt
from typing import Dict, List

from config.products import PRODUCTS
from planner.frontier_lookahead import FrontierLookaheadPlanner
from planner.models import PalletSlot, PlannerResult


class NewPalletPlanner:
    """
    Application-facing planner adapter.

    FrontierLookaheadPlanner preserves the deterministic corner-grown
    pattern while using lookahead to avoid future packing traps. This
    class preserves the PlannerResult/PalletSlot interface
    used by the GUI and ABB execution path.
    """

    def __init__(self) -> None:
        self.last_selected_planner = ""

    def generate(
        self,
        quantities: Dict[str, int],
        pallet_length: float,
        pallet_width: float,
        max_height: float,
        max_weight: float,
        overhang: float = 0.0,
        gap_x: float = 20.0,
        gap_y: float = 20.0,
        edge_margin_x: float = 20.0,
        edge_margin_y: float = 20.0,
        beam_width: int = 30,
    ) -> PlannerResult:

        total_weight = sum(
            PRODUCTS[sku].weight
            * max(0, int(quantity))
            for sku, quantity
            in quantities.items()
            if sku in PRODUCTS
        )

        if total_weight > max_weight:
            return PlannerResult(
                success=False,
                error=(
                    f"Order weight {total_weight:.1f} kg "
                    f"exceeds pallet limit "
                    f"{max_weight:.1f} kg."
                ),
            )

        total_items = sum(
            max(0, int(quantity))
            for quantity
            in quantities.values()
        )

        if total_items <= 0:
            return PlannerResult(
                success=False,
                error="Order contains no items.",
            )

        effective_length = (
            pallet_length
            + 2.0 * overhang
        )
        effective_width = (
            pallet_width
            + 2.0 * overhang
        )

        active_skus = [
            sku
            for sku, quantity
            in quantities.items()
            if quantity > 0
        ]

        if len(active_skus) == 1:
            sku = active_skus[0]
            capacity = self._single_sku_capacity(
                sku=sku,
                pallet_length=effective_length,
                pallet_width=effective_width,
                max_height=max_height,
                gap_x=gap_x,
                gap_y=gap_y,
                edge_margin_x=edge_margin_x,
                edge_margin_y=edge_margin_y,
            )

            requested = int(
                quantities[sku]
            )

            if requested > capacity:
                return PlannerResult(
                    success=False,
                    error=(
                        f"Requested {requested} x {sku}, but the "
                        f"current pallet/gap settings can hold at most "
                        f"{capacity}. Reduce gaps/margins, increase pallet "
                        f"size, or split the order across pallets."
                    ),
                )

        sparse_single_items = (
            total_items <= 8
            and len(active_skus) == 1
        )

        planner = FrontierLookaheadPlanner(
            pallet_length=effective_length,
            pallet_width=effective_width,
            max_height=max_height,
            gap_x=gap_x,
            gap_y=gap_y,
            edge_margin_x=edge_margin_x,
            edge_margin_y=edge_margin_y,
            single_item_columns=sparse_single_items,
        )

        state = planner.search(
            quantities=quantities,
        )

        # Sparse orders should prefer one item per floor position.
        # If that cannot fit, fall back to normal vertical stacking
        # rather than rejecting an otherwise feasible order.
        if (
            sparse_single_items
            and state.unplaced_count() != 0
        ):
            planner = FrontierLookaheadPlanner(
                pallet_length=effective_length,
                pallet_width=effective_width,
                max_height=max_height,
                gap_x=gap_x,
                gap_y=gap_y,
                edge_margin_x=edge_margin_x,
                edge_margin_y=edge_margin_y,
                single_item_columns=False,
            )

            state = planner.search(
                quantities=quantities,
            )

        self.last_selected_planner = (
            "Frontier Look"
        )

        if state.unplaced_count() != 0:
            remaining = {
                sku: quantity
                for sku, quantity
                in state.remaining.items()
                if quantity > 0
            }

            return PlannerResult(
                success=False,
                error=(
                    "Could not place all requested items. "
                    f"Remaining: {remaining}"
                ),
            )

        spread_applied = False

        if len(active_skus) == 1:
            spread_applied = self._spread_sparse_footprint(
                placed=state.placed,
                pallet_length=effective_length,
                pallet_width=effective_width,
                gap_x=gap_x,
                gap_y=gap_y,
                edge_margin_x=edge_margin_x,
                edge_margin_y=edge_margin_y,
            )

        if not spread_applied:
            self._center_placed_footprint(
                placed=state.placed,
                pallet_length=effective_length,
                pallet_width=effective_width,
                edge_margin_x=edge_margin_x,
                edge_margin_y=edge_margin_y,
            )

        slots = self._placed_to_slots(
            state.placed,
            coordinate_offset=overhang,
        )

        return PlannerResult(
            success=True,
            slots=slots,
        )

    @staticmethod
    def _spread_sparse_footprint(
        placed,
        pallet_length: float,
        pallet_width: float,
        gap_x: float,
        gap_y: float,
        edge_margin_x: float,
        edge_margin_y: float,
    ) -> bool:
        """
        Spread genuinely sparse floor stacks across the usable pallet area.

        This is a post-process only: stack contents, rotations, heights,
        and execution order remain unchanged. If a safe distributed grid
        cannot be created, return False so normal footprint centering is
        used instead.
        """
        count = len(placed)

        if count < 2 or count > 8:
            return False

        usable_length = max(
            0.0,
            pallet_length
            - 2.0 * edge_margin_x,
        )
        usable_width = max(
            0.0,
            pallet_width
            - 2.0 * edge_margin_y,
        )
        usable_area = (
            usable_length
            * usable_width
        )

        if usable_area <= 0.0:
            return False

        footprint_area = sum(
            stack.length * stack.width
            for stack in placed
        )

        occupancy = (
            footprint_area / usable_area
        )

        if occupancy >= 0.45:
            return False

        aspect = (
            usable_length / usable_width
            if usable_width > 0.0
            else 1.0
        )

        columns = max(
            1,
            min(
                count,
                ceil(
                    sqrt(
                        count * aspect
                    )
                ),
            ),
        )
        rows = ceil(
            count / columns
        )

        # Keep sparse stacks in separate floor positions, but form
        # a compact group in the center instead of pushing them to
        # the outer edges of the pallet.
        max_length = max(stack.length for stack in placed)
        max_width = max(stack.width for stack in placed)

        group_length = (
            columns * max_length
            + (columns - 1) * gap_x
        )
        group_width = (
            rows * max_width
            + (rows - 1) * gap_y
        )

        if (
            group_length > usable_length + 1e-6
            or group_width > usable_width + 1e-6
        ):
            return False

        group_x = (pallet_length - group_length) / 2.0
        group_y = (pallet_width - group_width) / 2.0

        proposed = []

        # IMPORTANT:
        # placed is already generated in strict execution-family order:
        # 20L -> 10L -> 1L -> 4L.
        # Preserve that order spatially as well. Do not re-sort by size.
        ordered = list(placed)

        # Preserve row-major placement order (+X, then +Y).
        # Grid positions are relative to the centered group.
        x_slots = [
            group_x + column * (max_length + gap_x)
            for column in range(columns)
        ]
        y_slots = [
            group_y + row * (max_width + gap_y)
            for row in range(rows)
        ]

        for index, stack in enumerate(
            ordered
        ):
            row = (
                index // columns
            )
            column = (
                index % columns
            )

            # Center each footprint within its grid cell.
            x = x_slots[column] + (max_length - stack.length) / 2.0
            y = y_slots[row] + (max_width - stack.width) / 2.0

            proposed.append(
                (
                    stack,
                    x,
                    y,
                )
            )

        eps = 1e-6

        for stack, x, y in proposed:
            if (
                x
                < edge_margin_x - eps
                or y
                < edge_margin_y - eps
                or x + stack.length
                > pallet_length
                - edge_margin_x + eps
                or y + stack.width
                > pallet_width
                - edge_margin_y + eps
            ):
                return False

        for i in range(
            len(proposed)
        ):
            a, ax, ay = proposed[i]
            ar = ax + a.length
            at = ay + a.width

            for j in range(
                i + 1,
                len(proposed),
            ):
                b, bx, by = proposed[j]
                br = bx + b.length
                bt = by + b.width

                separated_x = (
                    ar + gap_x
                    <= bx + eps
                    or br + gap_x
                    <= ax + eps
                )
                separated_y = (
                    at + gap_y
                    <= by + eps
                    or bt + gap_y
                    <= ay + eps
                )

                if not (
                    separated_x
                    or separated_y
                ):
                    return False

        for stack, x, y in proposed:
            stack.x = x
            stack.y = y

        return True

    @staticmethod
    def _center_placed_footprint(
        placed,
        pallet_length: float,
        pallet_width: float,
        edge_margin_x: float,
        edge_margin_y: float,
    ) -> None:
        """
        Translate the completed layout so its XY footprint is centered
        inside the usable pallet area.

        Relative stack positions, gaps, rotations, execution order, and
        packing feasibility are unchanged.
        """
        if not placed:
            return

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

        usable_center_x = (
            edge_margin_x
            + (
                pallet_length
                - 2.0 * edge_margin_x
            ) / 2.0
        )

        usable_center_y = (
            edge_margin_y
            + (
                pallet_width
                - 2.0 * edge_margin_y
            ) / 2.0
        )

        shift_x = (
            usable_center_x
            - footprint_center_x
        )

        shift_y = (
            usable_center_y
            - footprint_center_y
        )

        for stack in placed:
            stack.x += shift_x
            stack.y += shift_y

    @staticmethod
    def _single_sku_capacity(
        sku: str,
        pallet_length: float,
        pallet_width: float,
        max_height: float,
        gap_x: float,
        gap_y: float,
        edge_margin_x: float,
        edge_margin_y: float,
    ) -> int:

        product = PRODUCTS[sku]

        usable_length = max(
            0.0,
            pallet_length
            - 2.0 * edge_margin_x,
        )
        usable_width = max(
            0.0,
            pallet_width
            - 2.0 * edge_margin_y,
        )

        def positions(
            item_length: float,
            item_width: float,
        ) -> int:

            count_x = floor(
                (
                    usable_length
                    + gap_x
                )
                /
                (
                    item_length
                    + gap_x
                )
            )

            count_y = floor(
                (
                    usable_width
                    + gap_y
                )
                /
                (
                    item_width
                    + gap_y
                )
            )

            return max(
                0,
                count_x,
            ) * max(
                0,
                count_y,
            )

        floor_positions = positions(
            product.length,
            product.width,
        )

        if product.allow_rotation:
            floor_positions = max(
                floor_positions,
                positions(
                    product.width,
                    product.length,
                ),
            )

        vertical_by_height = floor(
            max_height
            / product.height
        )

        family_slenderness = (
            4.0
            if product.family == "carton"
            else 3.0
        )

        vertical_by_slenderness = floor(
            (
                family_slenderness
                * min(
                    product.length,
                    product.width,
                )
            )
            / product.height
        )

        vertical_count = max(
            1,
            min(
                product.max_layers,
                vertical_by_height,
                vertical_by_slenderness,
            ),
        )

        return (
            floor_positions
            * vertical_count
        )

    def _placed_to_slots(
        self,
        placed,
        coordinate_offset: float,
    ) -> List[PalletSlot]:

        slots: List[PalletSlot] = []

        stack_id = 1

        for stack in placed:

            z_bottom = 0.0

            center_x = (
                stack.x
                - coordinate_offset
                + stack.length / 2.0
            )

            center_y = (
                stack.y
                - coordinate_offset
                + stack.width / 2.0
            )

            for level, sku in enumerate(
                stack.candidate.items,
                start=1,
            ):

                product = PRODUCTS[sku]

                item_length = product.length
                item_width = product.width
                rotation = 0.0

                if level == 1:

                    rotation = stack.rotation

                    if rotation == 90.0:
                        item_length = product.width
                        item_width = product.length

                else:

                    normal_fit = (
                        item_length
                        <= stack.length
                        and
                        item_width
                        <= stack.width
                    )

                    if (
                        not normal_fit
                        and
                        product.allow_rotation
                    ):

                        rotated_length = (
                            product.width
                        )
                        rotated_width = (
                            product.length
                        )

                        if (
                            rotated_length
                            <= stack.length
                            and
                            rotated_width
                            <= stack.width
                        ):
                            item_length = (
                                rotated_length
                            )
                            item_width = (
                                rotated_width
                            )
                            rotation = 90.0

                z_center = (
                    z_bottom
                    + product.height / 2.0
                )

                slots.append(
                    PalletSlot(
                        id=0,
                        sku=sku,
                        x=center_x,
                        y=center_y,
                        z=z_center,
                        length=item_length,
                        width=item_width,
                        height=product.height,
                        rotation=rotation,
                        stack_id=stack_id,
                        level=level,
                        status="PENDING",
                    )
                )

                z_bottom += product.height

            stack_id += 1

        execution_priority = {
            "20L": 0,
            "10L": 1,
            "1L": 2,
            "4L": 3,
        }

        slots.sort(
            key=lambda slot: (
                execution_priority.get(
                    slot.sku,
                    99,
                ),
                slot.level,
                slot.stack_id,
            )
        )

        for slot_id, slot in enumerate(
            slots,
            start=1,
        ):
            slot.id = slot_id

        return slots

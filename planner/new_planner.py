from typing import Dict, List

from config.products import PRODUCTS
from planner.beam_search import BeamSearchPlanner
from planner.models import PalletSlot, PlannerResult


class NewPalletPlanner:
    """
    Adapter that exposes the new beam-search planner through the same
    PlannerResult/PalletSlot interface used by the GUI and executor.
    """

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

        planner = BeamSearchPlanner(
            pallet_length=effective_length,
            pallet_width=effective_width,
            max_height=max_height,
            beam_width=beam_width,
            gap_x=gap_x,
            gap_y=gap_y,
            edge_margin_x=edge_margin_x,
            edge_margin_y=edge_margin_y,
        )

        state = planner.search(
            quantities=quantities,
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

        slots = self._placed_to_slots(
            state.placed,
            coordinate_offset=overhang,
        )

        return PlannerResult(
            success=True,
            slots=slots,
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

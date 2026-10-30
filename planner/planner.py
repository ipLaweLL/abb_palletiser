from typing import Dict

from config.products import PRODUCTS
from planner.models import (
    PalletSlot,
    StackColumn,
    PlannerResult,
)
from planner.rules import can_stack
# ============================================================
# PALLET PLANNER
# ============================================================



class PalletPlanner:

    # ========================================================
    # MAIN GENERATION
    # ========================================================

    def generate(
        self,
        quantities: Dict[str, int],
        pallet_length: float,
        pallet_width: float,
        max_height: float,
        max_weight: float,
        overhang: float,
    ) -> PlannerResult:

        quantities = {
            sku: max(
                0,
                int(quantities.get(sku, 0))
            )
            for sku in PRODUCTS
        }

        # ----------------------------------------------------
        # EMPTY ORDER
        # ----------------------------------------------------

        if sum(quantities.values()) == 0:

            return PlannerResult(
                success=False,
                error="No products entered."
            )

        # ----------------------------------------------------
        # TOTAL WEIGHT
        # ----------------------------------------------------

        total_weight = sum(
            PRODUCTS[sku].weight * qty
            for sku, qty in quantities.items()
        )

        if total_weight > max_weight:

            return PlannerResult(
                success=False,
                error=(
                    f"Order weight = {total_weight:.1f} kg\n\n"
                    f"Maximum pallet weight = {max_weight:.1f} kg"
                )
            )

        usable_length = (
            pallet_length
            + 2 * overhang
        )

        usable_width = (
            pallet_width
            + 2 * overhang
        )

        # ====================================================
        # CARTON FAMILY
        #
        # 4L BASE
        # 1L ABOVE
        # ====================================================

        carton_candidates = (
            self._generate_family_candidates(
                lower_sku="4L",
                upper_sku="1L",
                lower_qty=quantities["4L"],
                upper_qty=quantities["1L"],
                pallet_length=usable_length,
                pallet_width=usable_width,
                max_height=max_height,
            )
        )

        # ====================================================
        # BUCKET FAMILY
        #
        # 20L BASE
        # 10L ABOVE
        # ====================================================

        bucket_candidates = (
            self._generate_family_candidates(
                lower_sku="20L",
                upper_sku="10L",
                lower_qty=quantities["20L"],
                upper_qty=quantities["10L"],
                pallet_length=usable_length,
                pallet_width=usable_width,
                max_height=max_height,
            )
        )

        if not carton_candidates:

            return PlannerResult(
                success=False,
                error="No valid carton arrangement found."
            )

        if not bucket_candidates:

            return PlannerResult(
                success=False,
                error="No valid bucket arrangement found."
            )

        print()
        print(
            "CARTON CANDIDATES:",
            len(carton_candidates)
        )

        print(
            "BUCKET CANDIDATES:",
            len(bucket_candidates)
        )

        # ====================================================
        # TRY EVERY USEFUL CARTON + BUCKET COMBINATION
        # ====================================================

        best_layout = None
        best_score = None

        for carton in carton_candidates:

            for bucket in bucket_candidates:

                layouts = (
                    self._combine_zones(
                        carton,
                        bucket,
                        usable_length,
                        usable_width,
                    )
                )

                for layout in layouts:

                    if not self._layout_inside_pallet(
                        layout,
                        usable_length,
                        usable_width
                    ):
                        continue

                    score = (
                        self._score_complete_layout(
                            layout,
                            usable_length,
                            usable_width,
                            max_height,
                        )
                    )

                    if (
                        best_score is None
                        or score < best_score
                    ):

                        best_score = score
                        best_layout = layout

        # ====================================================
        # NO VALID COMBINATION
        # ====================================================

        if best_layout is None:

            return PlannerResult(
                success=False,
                error=(
                    "No valid mixed pallet arrangement "
                    "could be generated for the current "
                    "pallet dimensions."
                )
            )

        # ----------------------------------------------------
        # MOVE OVERHANG FRAME BACK TO PALLET FRAME
        # ----------------------------------------------------

        if overhang > 0:

            for stack in best_layout:

                stack.x -= overhang
                stack.y -= overhang

        # ----------------------------------------------------
        # CLEAN STACK IDS
        # ----------------------------------------------------

        for index, stack in enumerate(
            best_layout,
            start=1
        ):

            stack.id = index

        # ----------------------------------------------------
        # CONVERT STACKS TO INDIVIDUAL ITEMS
        # ----------------------------------------------------

        slots = (
            self._stacks_to_slots(
                best_layout
            )
        )

        # ====================================================
        # EXECUTION ORDER
        #
        # Fixed product sequence required by the cell:
        # 20L -> 10L -> 1L -> 4L
        #
        # Within each SKU, place lower levels first.
        # Note: 1L is intentionally not stacked on 4L above,
        # otherwise this execution order would be physically
        # impossible (the 1L would need its 4L support first).
        # ====================================================

        sku_priority = {
            "20L": 0,
            "10L": 1,
            "1L": 2,
            "4L": 3,
        }

        slots.sort(
            key=lambda slot: (
                sku_priority.get(slot.sku, 99),
                slot.z - slot.height / 2,
                slot.level,
                slot.stack_id,
            )
        )

        for index, slot in enumerate(
            slots,
            start=1
        ):

            slot.id = index

        print()
        print("=" * 60)
        print("BEST PALLET")
        print("=" * 60)

        print(
            "Total items:",
            len(slots)
        )

        print(
            "Total weight:",
            total_weight,
            "kg"
        )

        print(
            "Floor positions:",
            len(best_layout)
        )

        print(
            "Score:",
            round(best_score, 4)
        )

        for stack in best_layout:

            print(
                f"Stack {stack.id}: "
                f"{stack.items} | "
                f"X={stack.x:.0f} "
                f"Y={stack.y:.0f} "
                f"H={stack.height():.0f}"
            )

        return PlannerResult(
            success=True,
            slots=slots
        )

    # ========================================================
    # FAMILY CANDIDATE GENERATOR
    #
    # Example:
    #
    # CARTON:
    # lower = 4L
    # upper = 1L
    #
    # BUCKET:
    # lower = 20L
    # upper = 10L
    #
    # IMPORTANT:
    # We test MANY floor-position counts.
    #
    # We do NOT automatically choose tallest towers.
    # ========================================================

    def _generate_family_candidates(
        self,
        lower_sku: str,
        upper_sku: str,
        lower_qty: int,
        upper_qty: int,
        pallet_length: float,
        pallet_width: float,
        max_height: float,
    ):

        lower_qty = int(lower_qty)
        upper_qty = int(upper_qty)

        # ----------------------------------------------------
        # EMPTY FAMILY
        # ----------------------------------------------------

        if lower_qty == 0 and upper_qty == 0:

            return [
                {
                    "stacks": [],
                    "length": 0.0,
                    "width": 0.0,
                    "score": 0.0,
                }
            ]

        lower_product = PRODUCTS[lower_sku]
        upper_product = PRODUCTS[upper_sku]

        candidates = []

        # ====================================================
        # ONLY UPPER PRODUCT EXISTS
        #
        # Example:
        # 13 x 10L
        # ====================================================

        if lower_qty == 0:

            max_vertical = min(
                upper_product.max_layers,
                max(
                    1,
                    int(
                        max_height
                        // upper_product.height
                    )
                )
            )

            min_positions = (
                upper_qty
                + max_vertical
                - 1
            ) // max_vertical

            max_positions = min(
                upper_qty,
                upper_product.units_per_layer
            )

            for positions in range(
                min_positions,
                max_positions + 1
            ):

                counts = (
                    self._balanced_distribution(
                        upper_qty,
                        positions,
                        max_vertical
                    )
                )

                if counts is None:
                    continue

                stacks = []

                for count in counts:

                    if count <= 0:
                        continue

                    stacks.append(
                        StackColumn(
                            id=0,
                            items=[upper_sku] * count,
                            base_length=upper_product.length,
                            base_width=upper_product.width,
                        )
                    )

                self._append_zone_candidates(
                    candidates=candidates,
                    stacks=stacks,
                    pallet_length=pallet_length,
                    pallet_width=pallet_width,
                    max_height=max_height,
                )

            candidates.sort(
                key=lambda item: item["score"]
            )

            return candidates

        # ====================================================
        # LOWER PRODUCT EXISTS
        # ====================================================

        max_lower_vertical = min(
            lower_product.max_layers,
            max(
                1,
                int(
                    max_height
                    // lower_product.height
                )
            )
        )

        min_support_positions = (
            lower_qty
            + max_lower_vertical
            - 1
        ) // max_lower_vertical

        max_support_positions = min(
            lower_qty,
            lower_product.units_per_layer
        )

        # ====================================================
        # TRY DIFFERENT NUMBER OF LOWER FLOOR POSITIONS
        # ====================================================

        for support_positions in range(
            min_support_positions,
            max_support_positions + 1
        ):

            lower_counts = (
                self._balanced_distribution(
                    lower_qty,
                    support_positions,
                    max_lower_vertical
                )
            )

            if lower_counts is None:
                continue

            # ------------------------------------------------
            # HOW MANY UPPER ITEMS COULD EACH SUPPORT TAKE?
            # ------------------------------------------------

            upper_capacities = []

            for lower_count in lower_counts:

                current_height = (
                    lower_count
                    * lower_product.height
                )

                available_height = (
                    max_height
                    - current_height
                )

                capacity_by_height = max(
                    0,
                    int(
                        available_height
                        // upper_product.height
                    )
                )

                capacity = min(
                    upper_product.max_layers,
                    capacity_by_height
                )

                # Must be legal stack relationship
                if not can_stack(
                    lower_sku,
                    upper_sku
                ):

                    capacity = 0

                # Must physically fit on lower product
                if capacity > 0:

                    normal_fit = (
                        upper_product.length
                        <= lower_product.length
                        and
                        upper_product.width
                        <= lower_product.width
                    )

                    rotated_fit = (
                        upper_product.allow_rotation
                        and
                        upper_product.width
                        <= lower_product.length
                        and
                        upper_product.length
                        <= lower_product.width
                    )

                    if not (
                        normal_fit
                        or rotated_fit
                    ):

                        capacity = 0

                upper_capacities.append(
                    capacity
                )

            # =================================================
            # IMPORTANT FIX
            #
            # Don't automatically put maximum number of upper
            # products on lower supports.
            #
            # Example:
            #
            # 1 x 20L
            # 13 x 10L
            #
            # Try:
            #
            # 0 on the 20L
            # 1 on the 20L
            # 2 on the 20L
            # 3 on the 20L
            #
            # Then scoring decides which is better.
            # =================================================

            max_supported = min(
                upper_qty,
                sum(upper_capacities)
            )

            for supported_upper in range(
                0,
                max_supported + 1
            ):

                upper_counts = (
                    self._distribute_upper_balanced(
                        quantity=supported_upper,
                        lower_counts=lower_counts,
                        capacities=upper_capacities,
                        lower_height=lower_product.height,
                        upper_height=upper_product.height,
                    )
                )

                actual_supported = sum(
                    upper_counts
                )

                remaining_upper = (
                    upper_qty
                    - actual_supported
                )

                # =============================================
                # BUILD MIXED SUPPORT COLUMNS
                # =============================================

                support_stacks = []

                valid = True

                for (
                    lower_count,
                    upper_count
                ) in zip(
                    lower_counts,
                    upper_counts
                ):

                    items = (
                        [lower_sku] * lower_count
                        +
                        [upper_sku] * upper_count
                    )

                    if not self._validate_stack(
                        items,
                        max_height
                    ):

                        valid = False
                        break

                    support_stacks.append(
                        StackColumn(
                            id=0,
                            items=items,
                            base_length=lower_product.length,
                            base_width=lower_product.width,
                        )
                    )

                if not valid:
                    continue

                # =============================================
                # EVERYTHING FITS ON LOWER SUPPORTS
                # =============================================

                if remaining_upper == 0:

                    self._append_zone_candidates(
                        candidates=candidates,
                        stacks=support_stacks,
                        pallet_length=pallet_length,
                        pallet_width=pallet_width,
                        max_height=max_height,
                    )

                    continue

                # =============================================
                # REMAINING UPPER PRODUCT MUST FORM ITS OWN
                # FLOOR POSITIONS
                # =============================================

                max_upper_vertical = min(
                    upper_product.max_layers,
                    max(
                        1,
                        int(
                            max_height
                            // upper_product.height
                        )
                    )
                )

                min_extra_positions = (
                    remaining_upper
                    + max_upper_vertical
                    - 1
                ) // max_upper_vertical

                max_extra_positions = min(
                    remaining_upper,
                    upper_product.units_per_layer
                )

                for extra_positions in range(
                    min_extra_positions,
                    max_extra_positions + 1
                ):

                    extra_counts = (
                        self._balanced_distribution(
                            remaining_upper,
                            extra_positions,
                            max_upper_vertical
                        )
                    )

                    if extra_counts is None:
                        continue

                    extra_stacks = []

                    for count in extra_counts:

                        if count <= 0:
                            continue

                        extra_stacks.append(
                            StackColumn(
                                id=0,
                                items=[upper_sku] * count,
                                base_length=upper_product.length,
                                base_width=upper_product.width,
                            )
                        )

                    all_stacks = (
                        self._copy_stacks(
                            support_stacks
                            + extra_stacks
                        )
                    )

                    self._append_zone_candidates(
                        candidates=candidates,
                        stacks=all_stacks,
                        pallet_length=pallet_length,
                        pallet_width=pallet_width,
                        max_height=max_height,
                    )

        # ====================================================
        # BEST CANDIDATES FIRST
        # ====================================================

        candidates.sort(
            key=lambda item: item["score"]
        )

        return candidates

    # ========================================================
    # APPEND EVERY COMPACT 2D ARRANGEMENT
    # ========================================================

    def _append_zone_candidates(
        self,
        candidates,
        stacks,
        pallet_length,
        pallet_width,
        max_height,
    ):

        arrangements = (
            self._find_best_layer_patterns(
                stacks,
                pallet_length,
                pallet_width
            )
        )

        for arrangement in arrangements:

            score = (
                self._score_zone(
                    arrangement["stacks"],
                    arrangement["length"],
                    arrangement["width"],
                    pallet_length,
                    pallet_width,
                    max_height,
                )
            )

            candidates.append(
                {
                    "stacks": arrangement["stacks"],
                    "length": arrangement["length"],
                    "width": arrangement["width"],
                    "score": score,
                }
            )

    # ========================================================
    # 2D LAYER PATTERN SEARCH
    #
    # THIS IS THE PYTHON VERSION OF THE IDEA USED BY
    # calcul_arie() IN YOUR C# PROGRAM.
    #
    # Try:
    # - different number of items per row
    # - normal orientations
    # - rotated orientations
    # - mixed orientations
    #
    # Keep dense, compact patterns.
    # ========================================================

    def _find_best_layer_patterns(
        self,
        stacks,
        pallet_length,
        pallet_width,
    ):

        if not stacks:

            return [
                {
                    "stacks": [],
                    "length": 0.0,
                    "width": 0.0,
                }
            ]

        results = []

        source = sorted(
            self._copy_stacks(stacks),
            key=lambda stack: (
                stack.base_length
                * stack.base_width
            ),
            reverse=True
        )

        total = len(source)

        # ====================================================
        # TRY DIFFERENT NUMBER OF ITEMS PER ROW
        # ====================================================

        for per_row in range(
            1,
            total + 1
        ):

            # ------------------------------------------------
            # 0 = prefer normal
            # 1 = prefer rotated
            # 2 = alternating / mixed orientation
            # ------------------------------------------------

            for orientation_mode in (
                0,
                1,
                2,
            ):

                working = (
                    self._copy_stacks(
                        source
                    )
                )

                index = 0
                y = 0.0

                zone_length = 0.0
                zone_width = 0.0

                valid = True

                row_index = 0

                while index < len(
                    working
                ):

                    row = (
                        working[
                            index:
                            index + per_row
                        ]
                    )

                    x = 0.0
                    row_height = 0.0

                    # =========================================
                    # ORIENT ITEMS IN THIS ROW
                    # =========================================

                    for local_index, stack in enumerate(
                        row
                    ):

                        product = PRODUCTS[
                            stack.items[0]
                        ]

                        rotate = False

                        if (
                            product.allow_rotation
                            and
                            stack.base_length
                            != stack.base_width
                        ):

                            if orientation_mode == 1:

                                rotate = True

                            elif orientation_mode == 2:

                                rotate = (
                                    (
                                        local_index
                                        + row_index
                                    )
                                    % 2
                                    == 1
                                )

                        if rotate:

                            (
                                stack.base_length,
                                stack.base_width
                            ) = (
                                stack.base_width,
                                stack.base_length
                            )

                            stack.rotation = 90

                        else:

                            stack.rotation = 0

                        stack.x = x
                        stack.y = y

                        x += (
                            stack.base_length
                        )

                        row_height = max(
                            row_height,
                            stack.base_width
                        )

                    row_length = x

                    # -----------------------------------------
                    # DOES ROW FIT?
                    # -----------------------------------------

                    if (
                        row_length
                        > pallet_length
                    ):

                        valid = False
                        break

                    if (
                        y
                        + row_height
                        > pallet_width
                    ):

                        valid = False
                        break

                    zone_length = max(
                        zone_length,
                        row_length
                    )

                    y += row_height

                    zone_width = y

                    row_index += 1
                    index += per_row

                if not valid:
                    continue

                # =================================================
                # CENTER SHORT ROWS
                # =================================================

                index = 0
                row_index = 0

                while index < len(
                    working
                ):

                    row = (
                        working[
                            index:
                            index + per_row
                        ]
                    )

                    row_length = sum(
                        stack.base_length
                        for stack in row
                    )

                    x_offset = (
                        zone_length
                        - row_length
                    ) / 2

                    for stack in row:

                        stack.x += (
                            x_offset
                        )

                    row_index += 1
                    index += per_row

                results.append(
                    {
                        "stacks": working,
                        "length": zone_length,
                        "width": zone_width,
                    }
                )

        # ====================================================
        # REMOVE DUPLICATE GEOMETRIES
        # ====================================================

        unique = []
        seen = set()

        for result in results:

            positions = tuple(
                sorted(
                    (
                        round(stack.x, 1),
                        round(stack.y, 1),
                        round(stack.base_length, 1),
                        round(stack.base_width, 1),
                    )
                    for stack
                    in result["stacks"]
                )
            )

            key = (
                round(
                    result["length"],
                    1
                ),
                round(
                    result["width"],
                    1
                ),
                positions,
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            unique.append(
                result
            )

        return unique

    # ========================================================
    # BALANCE QUANTITY BETWEEN FLOOR POSITIONS
    # ========================================================

    def _balanced_distribution(
        self,
        quantity,
        positions,
        max_per_position,
    ):

        if positions <= 0:
            return None

        if (
            quantity
            > positions * max_per_position
        ):

            return None

        base = (
            quantity
            // positions
        )

        remainder = (
            quantity
            % positions
        )

        result = []

        for i in range(
            positions
        ):

            value = base

            if i < remainder:

                value += 1

            if (
                value
                > max_per_position
            ):

                return None

            result.append(
                value
            )

        return result

    # ========================================================
    # BALANCE UPPER ITEMS BY CURRENT COLUMN HEIGHT
    # ========================================================

    def _distribute_upper_balanced(
        self,
        quantity,
        lower_counts,
        capacities,
        lower_height,
        upper_height,
    ):

        upper_counts = [
            0
            for _ in lower_counts
        ]

        remaining = quantity

        while remaining > 0:

            best_index = None
            best_height = None

            for i in range(
                len(lower_counts)
            ):

                if (
                    upper_counts[i]
                    >= capacities[i]
                ):

                    continue

                height = (
                    lower_counts[i]
                    * lower_height
                    +
                    upper_counts[i]
                    * upper_height
                )

                if (
                    best_height is None
                    or height < best_height
                ):

                    best_height = height
                    best_index = i

            if best_index is None:

                break

            upper_counts[
                best_index
            ] += 1

            remaining -= 1

        return upper_counts

    # ========================================================
    # VALIDATE VERTICAL COLUMN
    # ========================================================

    def _validate_stack(
        self,
        items,
        max_height,
    ):

        if not items:
            return False

        height = sum(
            PRODUCTS[sku].height
            for sku in items
        )

        if height > max_height:
            return False

        # ----------------------------------------------------
        # SAME-SKU FG LAYER LIMIT
        # ----------------------------------------------------

        for sku in PRODUCTS:

            count = (
                items.count(sku)
            )

            if (
                count
                > PRODUCTS[sku].max_layers
            ):

                return False

        # ----------------------------------------------------
        # DIRECT SUPPORT RULE
        # ----------------------------------------------------

        for i in range(
            len(items) - 1
        ):

            if not can_stack(
                items[i],
                items[i + 1]
            ):

                return False

        return True

    # ========================================================
    # ZONE SCORE
    #
    # Similar idea to old Stack Solver:
    # reward dense occupied area.
    #
    # We additionally punish excessive height.
    # ========================================================

    def _score_zone(
        self,
        stacks,
        zone_length,
        zone_width,
        pallet_length,
        pallet_width,
        max_height,
    ):

        if not stacks:

            return 0.0

        bounding_area = (
            zone_length
            * zone_width
        )

        occupied_area = sum(
            stack.base_length
            * stack.base_width
            for stack in stacks
        )

        if bounding_area > 0:

            efficiency = (
                occupied_area
                / bounding_area
            )

        else:

            efficiency = 0.0

        gap_ratio = (
            1.0
            - min(
                1.0,
                efficiency
            )
        )

        heights = [
            stack.height()
            for stack in stacks
        ]

        tallest = max(
            heights
        )

        shortest = min(
            heights
        )

        height_ratio = (
            tallest
            / max_height
        )

        height_variation = (
            tallest
            - shortest
        ) / max_height

        # ----------------------------------------------------
        # RECTANGULAR / SQUARE BLOCK PREFERENCE
        # ----------------------------------------------------

        if (
            zone_length > 0
            and zone_width > 0
        ):

            aspect = (
                max(
                    zone_length,
                    zone_width
                )
                /
                min(
                    zone_length,
                    zone_width
                )
            )

            aspect_penalty = (
                aspect
                - 1.0
            )

        else:

            aspect_penalty = 0.0

        # ----------------------------------------------------
        # SCORE
        #
        # LOWER IS BETTER
        # ----------------------------------------------------

        score = (
            gap_ratio * 6.0
            +
            height_ratio * 4.0
            +
            height_variation * 2.0
            +
            aspect_penalty * 0.7
        )

        return score

    # ========================================================
    # COMBINE CARTON AND BUCKET ZONES
    # ========================================================

    def _combine_zones(
        self,
        carton,
        bucket,
        pallet_length,
        pallet_width,
    ):

        carton_stacks = (
            carton["stacks"]
        )

        bucket_stacks = (
            bucket["stacks"]
        )

        results = []

        # ----------------------------------------------------
        # ONLY CARTONS
        # ----------------------------------------------------

        if (
            carton_stacks
            and not bucket_stacks
        ):

            layout = (
                self._copy_stacks(
                    carton_stacks
                )
            )

            self._center_layout(
                layout,
                pallet_length,
                pallet_width
            )

            return [
                layout
            ]

        # ----------------------------------------------------
        # ONLY BUCKETS
        # ----------------------------------------------------

        if (
            bucket_stacks
            and not carton_stacks
        ):

            layout = (
                self._copy_stacks(
                    bucket_stacks
                )
            )

            self._center_layout(
                layout,
                pallet_length,
                pallet_width
            )

            return [
                layout
            ]

        # ----------------------------------------------------
        # EMPTY
        # ----------------------------------------------------

        if (
            not carton_stacks
            and not bucket_stacks
        ):

            return [
                []
            ]

        # Small separation between family zones.
        gap = 10.0

        # ====================================================
        # CARTON LEFT / BUCKET RIGHT
        # ====================================================

        total_length = (
            carton["length"]
            + gap
            + bucket["length"]
        )

        total_width = max(
            carton["width"],
            bucket["width"]
        )

        if (
            total_length <= pallet_length
            and
            total_width <= pallet_width
        ):

            carton_copy = (
                self._copy_stacks(
                    carton_stacks
                )
            )

            bucket_copy = (
                self._copy_stacks(
                    bucket_stacks
                )
            )

            carton_y = (
                total_width
                - carton["width"]
            ) / 2

            bucket_y = (
                total_width
                - bucket["width"]
            ) / 2

            for stack in carton_copy:

                stack.y += (
                    carton_y
                )

            for stack in bucket_copy:

                stack.x += (
                    carton["length"]
                    + gap
                )

                stack.y += (
                    bucket_y
                )

            layout = (
                carton_copy
                + bucket_copy
            )

            self._center_layout(
                layout,
                pallet_length,
                pallet_width
            )

            results.append(
                layout
            )

        # ====================================================
        # BUCKET LEFT / CARTON RIGHT
        # ====================================================

        total_length = (
            bucket["length"]
            + gap
            + carton["length"]
        )

        total_width = max(
            bucket["width"],
            carton["width"]
        )

        if (
            total_length <= pallet_length
            and
            total_width <= pallet_width
        ):

            bucket_copy = (
                self._copy_stacks(
                    bucket_stacks
                )
            )

            carton_copy = (
                self._copy_stacks(
                    carton_stacks
                )
            )

            bucket_y = (
                total_width
                - bucket["width"]
            ) / 2

            carton_y = (
                total_width
                - carton["width"]
            ) / 2

            for stack in bucket_copy:

                stack.y += (
                    bucket_y
                )

            for stack in carton_copy:

                stack.x += (
                    bucket["length"]
                    + gap
                )

                stack.y += (
                    carton_y
                )

            layout = (
                bucket_copy
                + carton_copy
            )

            self._center_layout(
                layout,
                pallet_length,
                pallet_width
            )

            results.append(
                layout
            )

        # ====================================================
        # CARTON FRONT / BUCKET BACK
        # ====================================================

        total_length = max(
            carton["length"],
            bucket["length"]
        )

        total_width = (
            carton["width"]
            + gap
            + bucket["width"]
        )

        if (
            total_length <= pallet_length
            and
            total_width <= pallet_width
        ):

            carton_copy = (
                self._copy_stacks(
                    carton_stacks
                )
            )

            bucket_copy = (
                self._copy_stacks(
                    bucket_stacks
                )
            )

            carton_x = (
                total_length
                - carton["length"]
            ) / 2

            bucket_x = (
                total_length
                - bucket["length"]
            ) / 2

            for stack in carton_copy:

                stack.x += (
                    carton_x
                )

            for stack in bucket_copy:

                stack.x += (
                    bucket_x
                )

                stack.y += (
                    carton["width"]
                    + gap
                )

            layout = (
                carton_copy
                + bucket_copy
            )

            self._center_layout(
                layout,
                pallet_length,
                pallet_width
            )

            results.append(
                layout
            )

        # ====================================================
        # BUCKET FRONT / CARTON BACK
        # ====================================================

        total_length = max(
            bucket["length"],
            carton["length"]
        )

        total_width = (
            bucket["width"]
            + gap
            + carton["width"]
        )

        if (
            total_length <= pallet_length
            and
            total_width <= pallet_width
        ):

            bucket_copy = (
                self._copy_stacks(
                    bucket_stacks
                )
            )

            carton_copy = (
                self._copy_stacks(
                    carton_stacks
                )
            )

            bucket_x = (
                total_length
                - bucket["length"]
            ) / 2

            carton_x = (
                total_length
                - carton["length"]
            ) / 2

            for stack in bucket_copy:

                stack.x += (
                    bucket_x
                )

            for stack in carton_copy:

                stack.x += (
                    carton_x
                )

                stack.y += (
                    bucket["width"]
                    + gap
                )

            layout = (
                bucket_copy
                + carton_copy
            )

            self._center_layout(
                layout,
                pallet_length,
                pallet_width
            )

            results.append(
                layout
            )

        return results

    # ========================================================
    # CHECK LAYOUT INSIDE PALLET
    # ========================================================

    def _layout_inside_pallet(
        self,
        stacks,
        pallet_length,
        pallet_width,
    ):

        for stack in stacks:

            if stack.x < -0.001:

                return False

            if stack.y < -0.001:

                return False

            if (
                stack.x
                + stack.base_length
                > pallet_length + 0.001
            ):

                return False

            if (
                stack.y
                + stack.base_width
                > pallet_width + 0.001
            ):

                return False

        return True

    # ========================================================
    # COMPLETE PALLET SCORE
    # ========================================================

    def _score_complete_layout(
        self,
        stacks,
        pallet_length,
        pallet_width,
        max_height,
    ):

        if not stacks:

            return 0.0

        min_x = min(
            stack.x
            for stack in stacks
        )

        min_y = min(
            stack.y
            for stack in stacks
        )

        max_x = max(
            stack.x
            + stack.base_length
            for stack in stacks
        )

        max_y = max(
            stack.y
            + stack.base_width
            for stack in stacks
        )

        load_length = (
            max_x
            - min_x
        )

        load_width = (
            max_y
            - min_y
        )

        bounding_area = (
            load_length
            * load_width
        )

        occupied_area = sum(
            stack.base_length
            * stack.base_width
            for stack in stacks
        )

        if bounding_area > 0:

            floor_efficiency = min(
                1.0,
                occupied_area
                / bounding_area
            )

        else:

            floor_efficiency = 0.0

        gap_ratio = (
            1.0
            - floor_efficiency
        )

        heights = [
            stack.height()
            for stack in stacks
        ]

        tallest = max(
            heights
        )

        shortest = min(
            heights
        )

        height_ratio = (
            tallest
            / max_height
        )

        height_variation = (
            tallest
            - shortest
        ) / max_height

        # ====================================================
        # WEIGHT CENTER
        # ====================================================

        total_weight = 0.0

        weighted_x = 0.0
        weighted_y = 0.0

        for stack in stacks:

            stack_weight = sum(
                PRODUCTS[sku].weight
                for sku in stack.items
            )

            x_center = (
                stack.x
                + stack.base_length / 2
            )

            y_center = (
                stack.y
                + stack.base_width / 2
            )

            weighted_x += (
                x_center
                * stack_weight
            )

            weighted_y += (
                y_center
                * stack_weight
            )

            total_weight += (
                stack_weight
            )

        if total_weight > 0:

            cog_x = (
                weighted_x
                / total_weight
            )

            cog_y = (
                weighted_y
                / total_weight
            )

        else:

            cog_x = (
                pallet_length / 2
            )

            cog_y = (
                pallet_width / 2
            )

        center_x = (
            pallet_length / 2
        )

        center_y = (
            pallet_width / 2
        )

        x_balance = (
            abs(
                cog_x
                - center_x
            )
            / pallet_length
        )

        y_balance = (
            abs(
                cog_y
                - center_y
            )
            / pallet_width
        )

        # ====================================================
        # ASPECT RATIO
        # ====================================================

        if (
            load_length > 0
            and
            load_width > 0
        ):

            aspect_penalty = (
                max(
                    load_length,
                    load_width
                )
                /
                min(
                    load_length,
                    load_width
                )
                - 1.0
            )

        else:

            aspect_penalty = 0.0

        # ====================================================
        # FINAL SCORE
        # ====================================================

        return (
            gap_ratio * 7.0
            +
            height_ratio * 3.5
            +
            height_variation * 2.0
            +
            x_balance * 5.0
            +
            y_balance * 5.0
            +
            aspect_penalty * 0.5
        )

    # ========================================================
    # CENTER COMPLETE LOAD
    # ========================================================

    def _center_layout(
        self,
        stacks,
        pallet_length,
        pallet_width,
    ):

        if not stacks:
            return

        min_x = min(
            stack.x
            for stack in stacks
        )

        min_y = min(
            stack.y
            for stack in stacks
        )

        max_x = max(
            stack.x
            + stack.base_length
            for stack in stacks
        )

        max_y = max(
            stack.y
            + stack.base_width
            for stack in stacks
        )

        load_length = (
            max_x
            - min_x
        )

        load_width = (
            max_y
            - min_y
        )

        offset_x = (
            (
                pallet_length
                - load_length
            )
            / 2
            - min_x
        )

        offset_y = (
            (
                pallet_width
                - load_width
            )
            / 2
            - min_y
        )

        for stack in stacks:

            stack.x += (
                offset_x
            )

            stack.y += (
                offset_y
            )

    # ========================================================
    # COPY STACKS
    # ========================================================

    def _copy_stacks(
        self,
        stacks
    ):

        copied = []

        for stack in stacks:

            copied.append(
                StackColumn(
                    id=stack.id,
                    items=list(
                        stack.items
                    ),
                    x=stack.x,
                    y=stack.y,
                    base_length=stack.base_length,
                    base_width=stack.base_width,
                    rotation=stack.rotation,
                )
            )

        return copied

    # ========================================================
    # STACKS -> INDIVIDUAL PALLET ITEMS
    # ========================================================

    def _stacks_to_slots(
        self,
        stacks
    ):

        slots = []

        temp_id = 1

        for stack in stacks:

            z_bottom = 0.0

            center_x = (
                stack.x
                + stack.base_length / 2
            )

            center_y = (
                stack.y
                + stack.base_width / 2
            )

            for level, sku in enumerate(
                stack.items,
                start=1
            ):

                product = (
                    PRODUCTS[sku]
                )

                item_length = (
                    product.length
                )

                item_width = (
                    product.width
                )

                rotation = 0

                # =================================================
                # BOTTOM ITEM ORIENTATION
                # =================================================

                if level == 1:

                    rotation = int(
                        stack.rotation
                    )

                    if rotation == 90:

                        item_length = (
                            product.width
                        )

                        item_width = (
                            product.length
                        )

                # =================================================
                # UPPER ITEM
                # =================================================

                else:

                    normal_fit = (
                        item_length
                        <= stack.base_length
                        and
                        item_width
                        <= stack.base_width
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

                        rotated_fit = (
                            rotated_length
                            <= stack.base_length
                            and
                            rotated_width
                            <= stack.base_width
                        )

                        if rotated_fit:

                            item_length = (
                                rotated_length
                            )

                            item_width = (
                                rotated_width
                            )

                            rotation = 90

                # =================================================
                # Z
                # =================================================

                z_center = (
                    z_bottom
                    + product.height / 2
                )

                slots.append(
                    PalletSlot(
                        id=temp_id,
                        sku=sku,
                        x=center_x,
                        y=center_y,
                        z=z_center,
                        length=item_length,
                        width=item_width,
                        height=product.height,
                        rotation=rotation,
                        stack_id=stack.id,
                        level=level,
                        status="PENDING",
                    )
                )

                temp_id += 1

                z_bottom += (
                    product.height
                )

        return slots

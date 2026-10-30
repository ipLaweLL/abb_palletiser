from math import hypot
from typing import List, Tuple

from planner.extreme_points import PlacedStack


class LayoutScorer:
    """
    Stability-aware lexicographic scoring for pallet layouts.

    Lower tuples are better.

    Priorities:
      1. Place all requested items.
      2. Prefer stable height transitions and avoid isolated tall towers.
      3. Keep weighted mass near the pallet center.
      4. Use the pallet footprint in both X and Y.
      5. Avoid excessive overall height and height variation.
      6. Reduce wasted floor area.
      7. Prefer fewer floor positions only after layout quality.
    """

    def __init__(
        self,
        pallet_length: float,
        pallet_width: float,
        max_height: float,
    ) -> None:
        self.pallet_length = pallet_length
        self.pallet_width = pallet_width
        self.max_height = max_height

    def score(
        self,
        placed: List[PlacedStack],
        unplaced_count: int,
    ) -> Tuple:

        if not placed:
            return (
                unplaced_count,
                float("inf"),
                float("inf"),
                float("inf"),
                float("inf"),
                float("inf"),
                float("inf"),
                float("inf"),
                0,
            )

        stability_penalty = (
            self._stability_penalty(
                placed
            )
        )

        execution_penalty = (
            self._execution_sequence_penalty(
                placed
            )
        )

        fill_uniformity_penalty = (
            self._fill_uniformity_penalty(
                placed,
                rows=3,
                cols=3,
            )
        )

        cog_x, cog_y = (
            self._center_of_mass_xy(
                placed
            )
        )

        target_x = (
            self.pallet_length / 2.0
        )
        target_y = (
            self.pallet_width / 2.0
        )

        pallet_diagonal = hypot(
            self.pallet_length,
            self.pallet_width,
        )

        cog_distance = hypot(
            cog_x - target_x,
            cog_y - target_y,
        )

        cog_distance_norm = (
            cog_distance
            / pallet_diagonal
            if pallet_diagonal > 0
            else 0.0
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

        span_x = max_x - min_x
        span_y = max_y - min_y

        target_ratio = (
            self.pallet_length
            / self.pallet_width
        )

        layout_ratio = (
            span_x / span_y
            if span_y > 0
            else float("inf")
        )

        aspect_error = abs(
            layout_ratio
            - target_ratio
        )

        coverage_x = (
            span_x
            / self.pallet_length
        )
        coverage_y = (
            span_y
            / self.pallet_width
        )

        footprint_underuse = (
            (1.0 - min(coverage_x, 1.0)) ** 2
            +
            (1.0 - min(coverage_y, 1.0)) ** 2
        )

        heights = [
            stack.candidate.height
            for stack in placed
        ]

        max_stack_height = max(
            heights
        )

        height_ratio = (
            max_stack_height
            / self.max_height
            if self.max_height > 0
            else 0.0
        )

        normalized_heights = [
            (
                height
                / self.max_height
                if self.max_height > 0
                else 0.0
            )
            for height in heights
        ]

        mean_height = (
            sum(normalized_heights)
            / len(normalized_heights)
        )

        height_variance = (
            sum(
                (
                    height
                    - mean_height
                ) ** 2
                for height
                in normalized_heights
            )
            / len(normalized_heights)
        )

        used_area = sum(
            stack.length
            * stack.width
            for stack in placed
        )

        bounding_area = (
            span_x
            * span_y
        )

        wasted_area = max(
            0.0,
            bounding_area
            - used_area,
        )

        wasted_ratio = (
            wasted_area
            / bounding_area
            if bounding_area > 0
            else 0.0
        )

        return (
            unplaced_count,
            stability_penalty,
            execution_penalty,
            fill_uniformity_penalty,
            cog_distance_norm,
            footprint_underuse,
            aspect_error,
            height_ratio,
            height_variance,
            wasted_ratio,
            len(placed),
        )

    def _execution_sequence_penalty(
        self,
        placed: List[PlacedStack],
    ) -> float:
        """
        Prefer a row-major spatial sweep that follows the robot
        execution order 20L -> 10L -> 1L -> 4L.

        This is a soft preference. Mixed 20L/10L stacks naturally
        contribute to both execution stages at the same location.
        """

        priority = {
            "20L": 0,
            "10L": 1,
            "1L": 2,
            "4L": 3,
        }

        sku_positions = {
            sku: []
            for sku in priority
        }

        for stack in placed:

            center_x = (
                stack.x
                + stack.length / 2.0
            )
            center_y = (
                stack.y
                + stack.width / 2.0
            )

            x_norm = (
                center_x / self.pallet_length
                if self.pallet_length > 0
                else 0.0
            )
            y_norm = (
                center_y / self.pallet_width
                if self.pallet_width > 0
                else 0.0
            )

            # Row-major sweep: fill X first, then move upward in Y.
            sweep_position = (
                y_norm + 0.35 * x_norm
            )

            for sku in set(
                stack.candidate.items
            ):
                if sku in sku_positions:
                    sku_positions[sku].append(
                        sweep_position
                    )

        means = {}

        for sku, values in (
            sku_positions.items()
        ):
            if values:
                means[sku] = (
                    sum(values)
                    / len(values)
                )

        ordered_skus = [
            "20L",
            "10L",
            "1L",
            "4L",
        ]

        penalty = 0.0

        for left_index in range(
            len(ordered_skus)
        ):
            left_sku = (
                ordered_skus[left_index]
            )

            if left_sku not in means:
                continue

            for right_index in range(
                left_index + 1,
                len(ordered_skus),
            ):
                right_sku = (
                    ordered_skus[
                        right_index
                    ]
                )

                if right_sku not in means:
                    continue

                inversion = (
                    means[left_sku]
                    - means[right_sku]
                )

                if inversion > 0:
                    penalty += (
                        inversion ** 2
                    )

        return penalty

    def _fill_uniformity_penalty(
        self,
        placed: List[PlacedStack],
        rows: int,
        cols: int,
    ) -> float:
        """
        Measure how evenly occupied footprint area is distributed
        over a coarse pallet grid.

        Lower is better. Zero means equal occupied area in every cell.
        """

        if (
            not placed
            or rows <= 0
            or cols <= 0
            or self.pallet_length <= 0
            or self.pallet_width <= 0
        ):
            return 0.0

        cell_width = (
            self.pallet_length / cols
        )
        cell_height = (
            self.pallet_width / rows
        )

        cell_areas = []

        for row in range(rows):

            cell_y0 = (
                row * cell_height
            )
            cell_y1 = (
                cell_y0 + cell_height
            )

            for col in range(cols):

                cell_x0 = (
                    col * cell_width
                )
                cell_x1 = (
                    cell_x0 + cell_width
                )

                occupied = 0.0

                for stack in placed:

                    overlap_x = max(
                        0.0,
                        min(
                            stack.right,
                            cell_x1,
                        )
                        - max(
                            stack.x,
                            cell_x0,
                        ),
                    )

                    overlap_y = max(
                        0.0,
                        min(
                            stack.top,
                            cell_y1,
                        )
                        - max(
                            stack.y,
                            cell_y0,
                        ),
                    )

                    occupied += (
                        overlap_x
                        * overlap_y
                    )

                cell_areas.append(
                    occupied
                )

        total_occupied = sum(
            cell_areas
        )

        if total_occupied <= 0:
            return 0.0

        mean_area = (
            total_occupied
            / len(cell_areas)
        )

        if mean_area <= 0:
            return 0.0

        normalized_variance = (
            sum(
                (
                    (
                        area
                        - mean_area
                    )
                    / mean_area
                ) ** 2
                for area
                in cell_areas
            )
            / len(cell_areas)
        )

        return normalized_variance

    def _stability_penalty(
        self,
        placed: List[PlacedStack],
    ) -> float:

        if not placed:
            return 0.0

        total_weight = sum(
            stack.candidate.weight
            for stack in placed
        )

        pallet_diagonal = hypot(
            self.pallet_length,
            self.pallet_width,
        )

        target_x = (
            self.pallet_length / 2.0
        )
        target_y = (
            self.pallet_width / 2.0
        )

        neighbor_height_penalty = 0.0
        isolation_penalty = 0.0
        top_heavy_penalty = 0.0

        for index, stack in enumerate(
            placed
        ):

            height_ratio = (
                stack.candidate.height
                / self.max_height
                if self.max_height > 0
                else 0.0
            )

            center_x = (
                stack.x
                + stack.length / 2.0
            )
            center_y = (
                stack.y
                + stack.width / 2.0
            )

            center_distance_norm = (
                hypot(
                    center_x - target_x,
                    center_y - target_y,
                )
                / pallet_diagonal
                if pallet_diagonal > 0
                else 0.0
            )

            weight_share = (
                stack.candidate.weight
                / total_weight
                if total_weight > 0
                else 0.0
            )

            top_heavy_penalty += (
                (height_ratio ** 2)
                * weight_share
                * (
                    1.0
                    + center_distance_norm
                )
            )

            nearest_distance = None

            for other_index, other in enumerate(
                placed
            ):

                if other_index == index:
                    continue

                edge_distance = (
                    self._edge_distance(
                        stack,
                        other,
                    )
                )

                if (
                    nearest_distance is None
                    or
                    edge_distance
                    < nearest_distance
                ):
                    nearest_distance = (
                        edge_distance
                    )

            if nearest_distance is not None:

                nearest_norm = (
                    nearest_distance
                    / pallet_diagonal
                    if pallet_diagonal > 0
                    else 0.0
                )

                isolation_penalty += (
                    (height_ratio ** 2)
                    * nearest_norm
                )

        for left_index in range(
            len(placed)
        ):

            left = placed[left_index]

            for right_index in range(
                left_index + 1,
                len(placed),
            ):

                right = placed[
                    right_index
                ]

                distance = (
                    self._edge_distance(
                        left,
                        right,
                    )
                )

                proximity = (
                    1.0
                    / (
                        1.0
                        + distance / 300.0
                    )
                )

                height_difference = (
                    abs(
                        left.candidate.height
                        - right.candidate.height
                    )
                    / self.max_height
                    if self.max_height > 0
                    else 0.0
                )

                neighbor_height_penalty += (
                    proximity
                    * (
                        height_difference ** 2
                    )
                )

        return (
            4.0
            * neighbor_height_penalty
            +
            3.0
            * isolation_penalty
            +
            2.0
            * top_heavy_penalty
        )

    @staticmethod
    def _edge_distance(
        first: PlacedStack,
        second: PlacedStack,
    ) -> float:

        dx = max(
            0.0,
            first.x - second.right,
            second.x - first.right,
        )

        dy = max(
            0.0,
            first.y - second.top,
            second.y - first.top,
        )

        return hypot(
            dx,
            dy,
        )

    @staticmethod
    def _center_of_mass_xy(
        placed: List[PlacedStack],
    ) -> Tuple[float, float]:

        total_weight = sum(
            stack.candidate.weight
            for stack in placed
        )

        if total_weight <= 0:
            return 0.0, 0.0

        weighted_x = sum(
            (
                stack.x
                + stack.length / 2.0
            )
            * stack.candidate.weight
            for stack in placed
        )

        weighted_y = sum(
            (
                stack.y
                + stack.width / 2.0
            )
            * stack.candidate.weight
            for stack in placed
        )

        return (
            weighted_x / total_weight,
            weighted_y / total_weight,
        )

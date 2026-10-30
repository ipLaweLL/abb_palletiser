from typing import List, Tuple

from planner.extreme_points import PlacedStack


class LayoutScorer:
    """
    Lexicographic scoring for partial and complete pallet layouts.

    Lower tuples are better.

    Priorities:
      1. Place all requested items.
      2. Keep center of mass near pallet center.
      3. Use the pallet footprint in both X and Y.
      4. Avoid excessive height and height variation.
      5. Reduce wasted floor area.
      6. Prefer fewer floor positions only after quality constraints.
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
                0,
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

        cog_distance_sq = (
            (cog_x - target_x) ** 2
            +
            (cog_y - target_y) ** 2
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

        aspect_error = (
            abs(
                layout_ratio
                - target_ratio
            )
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

        mean_height = (
            sum(heights)
            / len(heights)
        )

        height_variance = (
            sum(
                (
                    height
                    - mean_height
                ) ** 2
                for height
                in heights
            )
            / len(heights)
        )

        height_ratio = (
            max_stack_height
            / self.max_height
            if self.max_height > 0
            else 0.0
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

        return (
            unplaced_count,
            cog_distance_sq,
            footprint_underuse,
            aspect_error,
            height_ratio,
            height_variance,
            wasted_area,
            len(placed),
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

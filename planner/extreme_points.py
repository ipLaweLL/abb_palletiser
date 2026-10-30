from dataclasses import dataclass
from typing import List, Tuple

from planner.models import StackCandidate


@dataclass(frozen=True)
class ExtremePoint:
    x: float
    y: float


@dataclass
class PlacedStack:
    candidate: StackCandidate
    x: float
    y: float
    length: float
    width: float
    rotation: float = 0.0

    @property
    def right(self) -> float:
        return self.x + self.length

    @property
    def top(self) -> float:
        return self.y + self.width


class ExtremePointPlacer:
    """
    Simple 2D extreme-point placement engine.

    Coordinates are pallet-local:
      x = pallet length direction
      y = pallet width direction

    This module only handles horizontal placement. Vertical legality
    is already encoded in StackCandidate by StackGenerator.
    """

    def __init__(
        self,
        pallet_length: float,
        pallet_width: float,
        gap_x: float = 20.0,
        gap_y: float = 20.0,
        edge_margin_x: float = 20.0,
        edge_margin_y: float = 20.0,
    ) -> None:
        self.pallet_length = pallet_length
        self.pallet_width = pallet_width

        self.gap_x = max(0.0, gap_x)
        self.gap_y = max(0.0, gap_y)

        self.edge_margin_x = max(
            0.0,
            edge_margin_x,
        )
        self.edge_margin_y = max(
            0.0,
            edge_margin_y,
        )

    def initial_points(self) -> List[ExtremePoint]:
        return [
            ExtremePoint(
                self.edge_margin_x,
                self.edge_margin_y,
            )
        ]

    def orientations(
        self,
        candidate: StackCandidate,
    ) -> List[Tuple[float, float, float]]:
        result = [
            (
                candidate.base_length,
                candidate.base_width,
                0.0,
            )
        ]

        if (
            candidate.base_length
            != candidate.base_width
        ):
            result.append(
                (
                    candidate.base_width,
                    candidate.base_length,
                    90.0,
                )
            )

        return result

    def can_place(
        self,
        point: ExtremePoint,
        length: float,
        width: float,
        placed: List[PlacedStack],
    ) -> bool:

        if (
            point.x < self.edge_margin_x
            or
            point.y < self.edge_margin_y
        ):
            return False

        if (
            point.x + length
            > (
                self.pallet_length
                - self.edge_margin_x
            )
        ):
            return False

        if (
            point.y + width
            > (
                self.pallet_width
                - self.edge_margin_y
            )
        ):
            return False

        for other in placed:
            if self._violates_gap(
                point.x,
                point.y,
                length,
                width,
                other,
            ):
                return False

        return True

    def place(
        self,
        candidate: StackCandidate,
        point: ExtremePoint,
        length: float,
        width: float,
        rotation: float,
    ) -> PlacedStack:

        return PlacedStack(
            candidate=candidate,
            x=point.x,
            y=point.y,
            length=length,
            width=width,
            rotation=rotation,
        )

    def next_points(
        self,
        placed: List[PlacedStack],
    ) -> List[ExtremePoint]:

        points = {
            ExtremePoint(
                self.edge_margin_x,
                self.edge_margin_y,
            )
        }

        for stack in placed:
            points.add(
                ExtremePoint(
                    stack.right
                    + self.gap_x,
                    stack.y,
                )
            )
            points.add(
                ExtremePoint(
                    stack.x,
                    stack.top
                    + self.gap_y,
                )
            )

        valid = []

        for point in points:

            if (
                point.x
                > (
                    self.pallet_length
                    - self.edge_margin_x
                )
                or
                point.y
                > (
                    self.pallet_width
                    - self.edge_margin_y
                )
            ):
                continue

            if self._point_blocked_by_any_stack(
                point,
                placed,
            ):
                continue

            valid.append(point)

        valid.sort(
            key=lambda point: (
                point.y,
                point.x,
            )
        )

        return valid

    def feasible_placements(
        self,
        candidate: StackCandidate,
        placed: List[PlacedStack],
    ) -> List[PlacedStack]:

        results = []

        for point in self.next_points(
            placed
        ):
            for (
                length,
                width,
                rotation,
            ) in self.orientations(
                candidate
            ):

                if not self.can_place(
                    point=point,
                    length=length,
                    width=width,
                    placed=placed,
                ):
                    continue

                results.append(
                    self.place(
                        candidate=candidate,
                        point=point,
                        length=length,
                        width=width,
                        rotation=rotation,
                    )
                )

        return results

    def _violates_gap(
        self,
        x: float,
        y: float,
        length: float,
        width: float,
        other: PlacedStack,
    ) -> bool:

        right = x + length
        top = y + width

        separated_with_gap = (
            right + self.gap_x
            <= other.x
            or
            x
            >= other.right + self.gap_x
            or
            top + self.gap_y
            <= other.y
            or
            y
            >= other.top + self.gap_y
        )

        return not separated_with_gap

    @staticmethod
    def _point_blocked_by_any_stack(
        point: ExtremePoint,
        placed: List[PlacedStack],
    ) -> bool:

        for stack in placed:
            on_or_inside_x = (
                stack.x <= point.x < stack.right
            )
            on_or_inside_y = (
                stack.y <= point.y < stack.top
            )

            if on_or_inside_x and on_or_inside_y:
                return True

        return False


if __name__ == "__main__":

    from planner.stack_generator import StackGenerator

    generator = StackGenerator()

    candidates = generator.generate(
        quantities={
            "1L": 3,
            "4L": 4,
            "10L": 3,
            "20L": 2,
        },
        max_height=1600,
    )

    placer = ExtremePointPlacer(
        pallet_length=1200,
        pallet_width=1000,
        gap_x=20,
        gap_y=20,
        edge_margin_x=20,
        edge_margin_y=20,
    )

    placed: List[PlacedStack] = []

    for candidate in candidates[:4]:

        options = placer.feasible_placements(
            candidate,
            placed,
        )

        if not options:
            print(
                "NO FIT:",
                candidate.items,
            )
            continue

        chosen = options[0]
        placed.append(chosen)

        print(
            f"{candidate.items} -> "
            f"X={chosen.x:.0f} "
            f"Y={chosen.y:.0f} "
            f"L={chosen.length:.0f} "
            f"W={chosen.width:.0f} "
            f"R={chosen.rotation:.0f}"
        )

        print(
            "EPs:",
            [
                (
                    point.x,
                    point.y,
                )
                for point
                in placer.next_points(
                    placed
                )
            ]
        )

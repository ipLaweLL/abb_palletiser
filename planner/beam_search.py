from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from config.products import PRODUCTS
from planner.extreme_points import ExtremePointPlacer, PlacedStack
from planner.stack_generator import StackGenerator


@dataclass
class BeamState:
    placed: List[PlacedStack] = field(default_factory=list)
    remaining: Dict[str, int] = field(default_factory=dict)

    def unplaced_count(self) -> int:
        return sum(self.remaining.values())

    def floor_positions(self) -> int:
        return len(self.placed)


class BeamSearchPlanner:
    """
    Beam-search layer over the StackGenerator + ExtremePointPlacer.

    Each state tracks:
      - stacks already positioned on the pallet
      - quantities still waiting to be placed

    The search keeps only the best N partial layouts at each depth.
    """

    def __init__(
        self,
        pallet_length: float,
        pallet_width: float,
        max_height: float,
        beam_width: int = 30,
    ) -> None:

        self.pallet_length = pallet_length
        self.pallet_width = pallet_width
        self.max_height = max_height
        self.beam_width = beam_width

        self.stack_generator = StackGenerator()
        self.placer = ExtremePointPlacer(
            pallet_length=pallet_length,
            pallet_width=pallet_width,
        )

    def search(
        self,
        quantities: Dict[str, int],
    ) -> BeamState:

        start = BeamState(
            placed=[],
            remaining={
                sku: max(
                    0,
                    int(quantities.get(sku, 0)),
                )
                for sku in PRODUCTS
            },
        )

        beam = [start]
        best = start

        while beam:

            next_states: List[BeamState] = []

            for state in beam:

                if (
                    state.unplaced_count()
                    < best.unplaced_count()
                    or
                    (
                        state.unplaced_count()
                        == best.unplaced_count()
                        and
                        self._score(state)
                        < self._score(best)
                    )
                ):
                    best = state

                if state.unplaced_count() == 0:
                    return state

                candidates = (
                    self.stack_generator.generate(
                        quantities=state.remaining,
                        max_height=self.max_height,
                    )
                )

                for candidate in candidates:

                    if not self._candidate_available(
                        candidate.items,
                        state.remaining,
                    ):
                        continue

                    options = (
                        self.placer.feasible_placements(
                            candidate=candidate,
                            placed=state.placed,
                        )
                    )

                    for placement in options:

                        next_remaining = dict(
                            state.remaining
                        )

                        for sku in candidate.items:
                            next_remaining[sku] -= 1

                        next_states.append(
                            BeamState(
                                placed=(
                                    state.placed
                                    + [placement]
                                ),
                                remaining=next_remaining,
                            )
                        )

            if not next_states:
                break

            beam = self._prune(
                next_states
            )

        return best

    def _prune(
        self,
        states: List[BeamState],
    ) -> List[BeamState]:

        unique: Dict[
            Tuple,
            BeamState,
        ] = {}

        for state in states:

            key = self._state_key(state)

            current = unique.get(key)

            if (
                current is None
                or
                self._score(state)
                < self._score(current)
            ):
                unique[key] = state

        ordered = sorted(
            unique.values(),
            key=self._score,
        )

        return ordered[
            :self.beam_width
        ]

    def _score(
        self,
        state: BeamState,
    ) -> Tuple:

        unplaced = (
            state.unplaced_count()
        )

        floor_positions = (
            state.floor_positions()
        )

        if not state.placed:

            return (
                unplaced,
                floor_positions,
                0.0,
                0.0,
                0.0,
            )

        max_x = max(
            stack.right
            for stack in state.placed
        )

        max_y = max(
            stack.top
            for stack in state.placed
        )

        bounding_area = (
            max_x * max_y
        )

        used_area = sum(
            stack.length
            * stack.width
            for stack in state.placed
        )

        wasted_area = (
            bounding_area
            - used_area
        )

        cog_x, cog_y = (
            self._center_of_mass_xy(
                state.placed
            )
        )

        target_x = (
            self.pallet_length
            / 2.0
        )

        target_y = (
            self.pallet_width
            / 2.0
        )

        cog_distance_sq = (
            (cog_x - target_x) ** 2
            +
            (cog_y - target_y) ** 2
        )

        return (
            unplaced,
            floor_positions,
            bounding_area,
            wasted_area,
            cog_distance_sq,
        )

    @staticmethod
    def _candidate_available(
        items: List[str],
        remaining: Dict[str, int],
    ) -> bool:

        needed: Dict[str, int] = {}

        for sku in items:
            needed[sku] = (
                needed.get(sku, 0)
                + 1
            )

        return all(
            needed[sku]
            <= remaining.get(sku, 0)
            for sku in needed
        )

    @staticmethod
    def _state_key(
        state: BeamState,
    ) -> Tuple:

        remaining_key = tuple(
            sorted(
                state.remaining.items()
            )
        )

        placement_key = tuple(
            sorted(
                (
                    round(stack.x, 3),
                    round(stack.y, 3),
                    round(
                        stack.length,
                        3,
                    ),
                    round(
                        stack.width,
                        3,
                    ),
                    tuple(
                        stack.candidate.items
                    ),
                )
                for stack
                in state.placed
            )
        )

        return (
            remaining_key,
            placement_key,
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


if __name__ == "__main__":

    planner = BeamSearchPlanner(
        pallet_length=1200,
        pallet_width=1000,
        max_height=1600,
        beam_width=30,
    )

    result = planner.search(
        quantities={
            "1L": 3,
            "4L": 4,
            "10L": 3,
            "20L": 2,
        }
    )

    print()
    print("=" * 60)
    print("BEAM SEARCH RESULT")
    print("=" * 60)

    print(
        "Remaining:",
        result.remaining,
    )

    print(
        "Floor positions:",
        result.floor_positions(),
    )

    for index, stack in enumerate(
        result.placed,
        start=1,
    ):

        print(
            f"Stack {index}: "
            f"{stack.candidate.items} | "
            f"X={stack.x:.0f} "
            f"Y={stack.y:.0f} "
            f"L={stack.length:.0f} "
            f"W={stack.width:.0f} "
            f"R={stack.rotation:.0f} "
            f"H={stack.candidate.height:.0f}"
        )

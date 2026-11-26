from typing import List, Optional

from planner.models import PalletSlot
from robot.abb_client import ABBClient
from robot.protocol import PLACED_RESPONSE
from robot.relative_coordinates import relative_place_xyz


class PalletExecutor:

    def __init__(
        self,
        abb: ABBClient,
    ):
        self.abb = abb

        self.slots: List[PalletSlot] = []
        self.current_index = 0

    def load_plan(
        self,
        slots: List[PalletSlot],
    ) -> None:

        self.slots = slots
        self.current_index = 0

        for slot in self.slots:
            slot.status = "PENDING"

        self._mark_next_active()

    def current_slot(
        self,
    ) -> Optional[PalletSlot]:

        if self.current_index >= len(self.slots):
            return None

        return self.slots[self.current_index]

    def place_next(
        self,
    ) -> str:

        slot = self.current_slot()

        if slot is None:
            return "COMPLETE"

        rel_x, rel_y, rel_z = relative_place_xyz(slot, self.slots[0])
        reply = self.abb.place(
            slot_id=slot.id,
            x=rel_x,
            y=rel_y,
            z=rel_z,
            rotation=slot.rotation,
        )

        if reply != PLACED_RESPONSE:
            return reply

        slot.status = "DONE"

        self.current_index += 1

        self._mark_next_active()

        return reply

    def place_next_simulated(
        self,
    ) -> str:

        slot = self.current_slot()

        if slot is None:
            return "COMPLETE"

        slot.status = "DONE"

        self.current_index += 1

        self._mark_next_active()

        return "PLACED"

    def reset(
        self,
    ) -> None:

        self.current_index = 0

        for slot in self.slots:
            slot.status = "PENDING"

        self._mark_next_active()

    def is_complete(
        self,
    ) -> bool:

        return self.current_index >= len(self.slots)

    def completed_count(
        self,
    ) -> int:

        return sum(
            1
            for slot in self.slots
            if slot.status == "DONE"
        )

    def _mark_next_active(
        self,
    ) -> None:

        for slot in self.slots:
            if slot.status == "ACTIVE":
                slot.status = "PENDING"

        slot = self.current_slot()

        if slot is not None:
            slot.status = "ACTIVE"
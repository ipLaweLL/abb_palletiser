from dataclasses import dataclass, field
from typing import List, Optional

from config.products import PRODUCTS


@dataclass
class PalletSlot:
    id: int
    sku: str

    x: float
    y: float
    z: float

    length: float
    width: float
    height: float

    rotation: float

    stack_id: int
    level: int

    status: str = "PENDING"


@dataclass
class StackCandidate:
    """
    A legal vertical stack pattern that has not yet been positioned
    on the pallet.

    items are ordered bottom -> top.
    """
    items: List[str]

    base_length: float
    base_width: float

    height: float
    weight: float

    rotation: float = 0.0


@dataclass
class StackColumn:
    id: int

    # Bottom -> top
    items: List[str] = field(
        default_factory=list
    )

    x: float = 0.0
    y: float = 0.0

    base_length: float = 0.0
    base_width: float = 0.0
    rotation: float = 0.0

    def height(self) -> float:

        return sum(
            PRODUCTS[sku].height
            for sku in self.items
        )

    @property
    def top_sku(self) -> Optional[str]:

        if not self.items:
            return None

        return self.items[-1]


@dataclass
class Rect:
    x: float
    y: float

    w: float
    h: float

    @property
    def right(self) -> float:

        return self.x + self.w

    @property
    def bottom(self) -> float:

        return self.y + self.h


@dataclass
class PlannerResult:
    success: bool

    slots: List[PalletSlot] = field(
        default_factory=list
    )

    error: str = ""

from dataclasses import dataclass
from typing import Dict


@dataclass
class Product:
    sku: str
    name: str
    length: float
    width: float
    height: float
    weight: float
    shape: str
    family: str
    allow_rotation: bool = True
    units_per_layer: int = 0
    max_layers: int = 0

    @property
    def max_units_per_pallet(self) -> int:
        return self.units_per_layer * self.max_layers


PRODUCTS: Dict[str, Product] = {
    "1L": Product(
        sku="1L",
        name="1 Ltr Carton",
        length=367,
        width=247,
        height=153,
        weight=9,
        shape="box",
        family="carton",
        allow_rotation=True,
        units_per_layer=16,
        max_layers=6,
    ),

    "4L": Product(
        sku="4L",
        name="4 Ltr Carton",
        length=380,
        width=380,
        height=220,
        weight=24,
        shape="box",
        family="carton",
        allow_rotation=True,
        units_per_layer=9,
        max_layers=4,
    ),

    "10L": Product(
        sku="10L",
        name="10 Ltr Bucket",
        length=267,
        width=267,
        height=310,
        weight=17,
        shape="circle",
        family="bucket",
        allow_rotation=False,
        units_per_layer=16,
        max_layers=3,
    ),

    "20L": Product(
        sku="20L",
        name="20 Ltr Bucket",
        length=306,
        width=306,
        height=390,
        weight=34,
        shape="circle",
        family="bucket",
        allow_rotation=False,
        units_per_layer=16,
        max_layers=2,
    ),
}
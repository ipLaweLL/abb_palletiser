"""No-robot regression test for centre-to-suction-TCP coordinate mapping.

Run: python -m robot.placement_coordinates_test
"""
from config.products import PRODUCTS
from planner.models import PalletSlot
from robot.placement_coordinates import top_contact_xyz


def main():
    for sku, product in PRODUCTS.items():
        slot = PalletSlot(
            id=1, sku=sku, x=203.5, y=143.5, z=product.height / 2,
            length=product.length, width=product.width, height=product.height,
            rotation=0, stack_id=1, level=1,
        )
        x, y, z = top_contact_xyz(slot)
        assert (x, y) == (203.5, 143.5)
        assert abs(z - product.height) < 1e-9
        # Upper layer: height of bottom item + full current product height.
        slot.z = product.height * 1.5
        assert abs(top_contact_xyz(slot)[2] - product.height * 2) < 1e-9
        print(f"{sku}: first-layer top={product.height:.1f} mm; stacked top={product.height * 2:.1f} mm")

    product = PRODUCTS["1L"]
    invalid = PalletSlot(
        id=1, sku="1L", x=0, y=0, z=76.5,
        length=product.length, width=product.width, height=150,
        rotation=0, stack_id=1, level=1,
    )
    try:
        top_contact_xyz(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched SKU geometry must fail")
    print("PASS: XYZ mapping for all SKUs; mismatched heights rejected")


if __name__ == "__main__":
    main()

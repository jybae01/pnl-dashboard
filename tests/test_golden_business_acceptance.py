from __future__ import annotations

from scripts.golden_business_acceptance import (
    _comparison,
    _same_group_composition_changed,
)


class _WorkbookValues:
    def __init__(self, values: dict[str, float]):
        self.values = values

    def value(self, address: str) -> float:
        return self.values.get(address, 0.0)


def test_acceptance_uses_existing_absolute_and_relative_tolerance_contract():
    absolute = _comparison(0.0, 1.0)
    relative = _comparison(2_000_000_000.0, 2_000_000_002.0)
    outside = _comparison(0.0, 1.000001)

    assert absolute["status"] == "PASS"
    assert relative["status"] == "PASS"
    assert outside["status"] == "FAIL"


def test_same_group_sku_composition_is_detected_without_combining_groups():
    mapping = {
        "comparison": {
            "products": {
                "SW400": {"quantity_row": 10},
                "SW440": {"quantity_row": 11},
                "BW400": {"quantity_row": 12},
                "BW440": {"quantity_row": 13},
            }
        }
    }
    base = _WorkbookValues({"K10": 60, "K11": 40, "K12": 50, "K13": 50})
    comparison = _WorkbookValues({"K10": 50, "K11": 50, "K12": 50, "K13": 50})

    assert _same_group_composition_changed(base, comparison, mapping, (7,)) is True


def test_same_group_sku_composition_ignores_pure_group_volume_change():
    mapping = {
        "comparison": {
            "products": {
                "SW400": {"quantity_row": 10},
                "SW440": {"quantity_row": 11},
                "BW400": {"quantity_row": 12},
                "BW440": {"quantity_row": 13},
            }
        }
    }
    base = _WorkbookValues({"K10": 60, "K11": 40, "K12": 50, "K13": 50})
    comparison = _WorkbookValues({"K10": 120, "K11": 80, "K12": 25, "K13": 25})

    assert _same_group_composition_changed(base, comparison, mapping, (7,)) is False

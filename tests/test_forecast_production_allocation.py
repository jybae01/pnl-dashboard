from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import forecast.bff.production_allocation as allocation_module
from forecast.bff.errors import ApiErrorCode, BffError
from forecast.bff.production_allocation import (
    BACK_PROCESS,
    CANONICAL_PRODUCTION_CODES,
    UNIT_PCS,
    BaseProductionIntegrityError,
    BusinessProductionInput,
    ForecastProductionAllocationService,
    ProductionAllocationBatch,
    ProductionAllocationValidationError,
    allocate_production,
)
from forecast.provenance import ResultProvenance


BASE_ID = "11111111-1111-4111-8111-111111111111"
MAPPING_HASH = "a" * 64
PROVENANCE = ResultProvenance("engine-1", "mapping-1", MAPPING_HASH, "1")
PRODUCTION_ROWS = {
    code: index + 1 for index, code in enumerate(CANONICAL_PRODUCTION_CODES)
}
MAPPING = {"production": PRODUCTION_ROWS}


def business(month: int, process: str, group: str, quantity, unit: str):
    return BusinessProductionInput(month, process, group, quantity, unit)


def output(result):
    return result.as_mapping()


def base(*, month7=None, month8=None):
    month7 = month7 or {"SW400": 3, "SW440": 1, "BW400": 1, "BW440": 3}
    month8 = month8 or {"SW400": 1, "SW440": 3, "BW400": 3, "BW440": 1}
    return {7: month7, 8: month8}


def test_sw_and_bw_use_selected_base_pair_ratios():
    result = allocate_production(
        [business(7, "후공정", "SW", 100, "PCS"), business(7, "후공정", "BW", 100, "PCS")],
        base(),
    )
    values = output(result)
    assert values["SW400"] == Decimal("75")
    assert values["SW440"] == Decimal("25")
    assert values["BW400"] == Decimal("25")
    assert values["BW440"] == Decimal("75")
    assert sum(values.values(), Decimal(0)) == Decimal("200")


def test_distinct_pair_ratios_are_not_reused_between_groups():
    result = allocate_production(
        [business(7, "후공정", "SW", 8, "PCS"), business(7, "후공정", "BW", 8, "PCS")],
        base(month7={"SW400": 1, "SW440": 3, "BW400": 3, "BW440": 1}),
    )
    values = output(result)
    assert (values["SW400"], values["SW440"]) == (Decimal("2"), Decimal("6"))
    assert (values["BW400"], values["BW440"]) == (Decimal("6"), Decimal("2"))


def test_same_group_uses_its_own_month_and_never_another_month():
    results = allocate_production(
        [business(7, "후공정", "SW", 10, "PCS"), business(8, "후공정", "SW", 10, "PCS")],
        base(),
    )
    assert isinstance(results, ProductionAllocationBatch)
    assert output(results[0])["SW400"] == Decimal("8")
    assert output(results[1])["SW400"] == Decimal("3")


def test_direct_base_map_is_rejected_instead_of_reused_across_months():
    rows = [
        business(7, BACK_PROCESS, "SW", 100, UNIT_PCS),
        business(8, BACK_PROCESS, "SW", 100, UNIT_PCS),
    ]

    with pytest.raises(BaseProductionIntegrityError):
        allocate_production(rows, {"SW400": 3, "SW440": 1})


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [(100, 0, (Decimal("10"), Decimal("0"))),
     (0, 100, (Decimal("0"), Decimal("10")))],
)
def test_extreme_and_zero_base_pairs(first, second, expected):
    result = allocate_production(
        business(7, "후공정", "SW", 10, "PCS"),
        {7: {"SW400": first, "SW440": second}},
    )
    assert (output(result)["SW400"], output(result)["SW440"]) == expected


def test_zero_business_total_does_not_require_a_ratio():
    result = allocate_production(business(7, "후공정", "SW", 0, "PCS"), None)
    assert (output(result)["SW400"], output(result)["SW440"]) == (Decimal("0"), Decimal("0"))


def test_positive_business_total_with_zero_base_denominator_fails_closed():
    with pytest.raises(BaseProductionIntegrityError):
        allocate_production(
            business(7, "후공정", "SW", 10, "PCS"),
            {7: {"SW400": 0, "SW440": 0}},
        )


@pytest.mark.parametrize(
    "pair",
    [({},), ({"SW400": 0, "SW440": 0},), ({"SW400": -1, "SW440": 2},),
     ({"SW400": float("nan"), "SW440": 1},), ({"SW400": 1, "SW440": float("inf")},)],
)
def test_positive_sw_total_fails_closed_for_missing_or_invalid_base(pair):
    values = pair[0]
    with pytest.raises(BaseProductionIntegrityError):
        allocate_production(business(7, "후공정", "SW", 1, "PCS"), {7: values})


@pytest.mark.parametrize(
    ("total", "expected_first"),
    [(101, Decimal("34")), (1, Decimal("0")), (999, Decimal("333")), (Decimal("101.00"), Decimal("33.67"))],
)
def test_rounding_preserves_total_and_is_deterministic(total, expected_first):
    request = [business(7, "후공정", "SW", total, "PCS")]
    first = allocate_production(request, {7: {"SW400": 1, "SW440": 2}})
    second = allocate_production(request, {7: {"SW400": 1, "SW440": 2}})
    assert first == second
    values = output(first)
    assert values["SW400"] + values["SW440"] == Decimal(str(total))
    assert values["SW400"] == expected_first


def test_positive_exponent_decimal_uses_whole_unit_quantum():
    result = allocate_production(
        business(7, "후공정", "SW", Decimal("1E+3"), "PCS"),
        {7: {"SW400": 1, "SW440": 2}},
    )
    values = output(result)
    assert (values["SW400"], values["SW440"]) == (Decimal("333"), Decimal("667"))
    assert values["SW400"] + values["SW440"] == Decimal("1E+3")


def test_large_finite_engine_quantity_is_supported_but_overflow_is_rejected():
    result = allocate_production(
        business(7, "후공정", "SW", Decimal("1E+308"), "PCS"),
        {7: {"SW400": 1, "SW440": 1}},
    )
    values = output(result)
    assert values["SW400"] + values["SW440"] == Decimal("1E+308")
    with pytest.raises(ProductionAllocationValidationError):
        allocate_production(
            business(7, "후공정", "SW", Decimal("1E+309"), "PCS"),
            {7: {"SW400": 1, "SW440": 1}},
        )


def test_quantity_precision_must_round_trip_through_existing_engine_float_contract():
    excessive_precision = Decimal("0." + "1" * 100)

    with pytest.raises(ProductionAllocationValidationError):
        allocate_production(business(7, BACK_PROCESS, "SW", excessive_precision, UNIT_PCS), base())


def test_front_process_and_lc_are_direct_and_need_no_ratio():
    result = allocate_production(
        [business(7, "전공정", "SW", Decimal("1.25"), "m"),
         business(7, "전공정", "BW", 2, "m"),
         business(7, "전공정", "TW", 3, "m"),
         business(7, "후공정", "LC", Decimal("4.5"), "PCS")],
        None,
    )
    assert output(result) == {
        "SW400": Decimal("0"), "SW440": Decimal("0"), "BW400": Decimal("0"),
        "BW440": Decimal("0"), "LC": Decimal("4.5"), "FS_SW": Decimal("1.25"),
        "FS_BW": Decimal("2"), "FS_TW": Decimal("3"),
    }


@pytest.mark.parametrize(
    "entry",
    [business(7, "전공정", "LC", 1, "m"), business(7, "후공정", "TW", 1, "PCS"),
     business(7, "전공정", "SW", 1, "PCS"), business(7, "후공정", "LC", 1, "m")],
)
def test_invalid_dimensions_and_units_fail_closed(entry):
    with pytest.raises(ProductionAllocationValidationError):
        allocate_production(entry, None)


def test_duplicate_business_dimension_is_rejected():
    with pytest.raises(ProductionAllocationValidationError):
        allocate_production(
            [business(7, "후공정", "SW", 1, "PCS"), business(7, "후공정", "SW", 2, "PCS")],
            {7: {"SW400": 1, "SW440": 1}},
        )


def test_canonical_output_is_exactly_eight_keys_in_stable_order():
    result = allocate_production(business(7, "전공정", "SW", 2, "m"), None)
    assert tuple(item.product_code for item in result.canonical_quantities) == CANONICAL_PRODUCTION_CODES
    assert set(output(result)) == set(CANONICAL_PRODUCTION_CODES)
    assert len(output(result)) == 8
    assert result.as_engine_mapping()["FS_SW"] == 2.0


class _Sessions:
    def __init__(self, role="admin"):
        self.role = role

    def require_admin(self, session_id):
        if self.role != "admin" or session_id != "admin-session":
            raise BffError(ApiErrorCode.FORBIDDEN, "Admin capability required")
        return SimpleNamespace(actor_id="actor")


@dataclass
class _Model:
    id: str = BASE_ID
    is_published: bool = True
    mapping_status: str = "published"
    mapping_version: str = "mapping-1"
    mapping_hash: str = MAPPING_HASH
    workbook_sha256: str = ""


class _Repository:
    def __init__(self, path: Path, model: _Model):
        self._path = path
        self.model = model

    def get(self, model_id):
        return self.model if model_id == BASE_ID else None

    def path(self, model_id):
        return self._path


class _Workbook:
    values = {
        "K1": 3, "K2": 1, "K3": 1, "K4": 3,
        "L1": 1, "L2": 3, "L3": 3, "L4": 1,
    }

    def __init__(self, path):
        self.path = Path(path)

    def value(self, address):
        return self.values.get(address)


def _service(tmp_path, monkeypatch, *, model=None, content=b"base-workbook"):
    path = tmp_path / "source.xlsx"
    path.write_bytes(content)
    model = model or _Model(workbook_sha256=hashlib.sha256(content).hexdigest())
    monkeypatch.setattr(allocation_module, "GoldenWorkbook", _Workbook)
    return ForecastProductionAllocationService(_Sessions(), _Repository(path, model), MAPPING, PROVENANCE)


def test_service_requires_admin_before_model_lookup(tmp_path, monkeypatch):
    path = tmp_path / "source.xlsx"
    path.write_bytes(b"source")
    sessions = _Sessions(role="viewer")
    service = ForecastProductionAllocationService(sessions, object(), MAPPING, PROVENANCE)
    with pytest.raises(BffError) as caught:
        service.allocate("viewer-session", BASE_ID, business(7, "전공정", "SW", 1, "m"))
    assert caught.value.code is ApiErrorCode.FORBIDDEN


def test_service_verifies_model_provenance_and_workbook_sha(tmp_path, monkeypatch):
    bad = _Model(workbook_sha256="b" * 64)
    service = _service(tmp_path, monkeypatch, model=bad)
    with pytest.raises(BffError) as caught:
        service.allocate("admin-session", BASE_ID, business(7, "전공정", "SW", 1, "m"))
    assert caught.value.code is ApiErrorCode.INPUT_INTEGRITY_MISMATCH


def test_service_reads_same_month_pairs_and_returns_verified_provenance(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    result = service.allocate("admin-session", BASE_ID, business(8, "후공정", "SW", 10, "PCS"))
    assert result.base_model_id == BASE_ID
    assert result.base_workbook_sha256 == service._repository.model.workbook_sha256
    assert result.source_sw_pair == (Decimal("1"), Decimal("3"))
    assert (output(result)["SW400"], output(result)["SW440"]) == (Decimal("3"), Decimal("7"))


def test_service_maps_invalid_business_input_to_validation_error(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    with pytest.raises(BffError) as caught:
        service.allocate("admin-session", BASE_ID, business(7, "후공정", "SW", -1, "PCS"))
    assert caught.value.code is ApiErrorCode.VALIDATION_ERROR


def test_service_rejects_model_identity_mismatch_before_source_read(tmp_path, monkeypatch):
    wrong = _Model(
        id="22222222-2222-4222-8222-222222222222",
        workbook_sha256=hashlib.sha256(b"base-workbook").hexdigest(),
    )
    service = _service(tmp_path, monkeypatch, model=wrong)
    service._repository.path = lambda _model_id: pytest.fail("source must not be read")
    with pytest.raises(BffError) as caught:
        service.allocate(
            "admin-session", BASE_ID, business(7, "후공정", "SW", 1, "PCS")
        )
    assert caught.value.code is ApiErrorCode.MODEL_NOT_FOUND


def test_service_maps_missing_ratio_source_to_integrity_error(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    _Workbook.values = {"K1": 0, "K2": 0}
    try:
        with pytest.raises(BffError) as caught:
            service.allocate("admin-session", BASE_ID, business(7, "후공정", "SW", 1, "PCS"))
        assert caught.value.code is ApiErrorCode.INPUT_INTEGRITY_MISMATCH
    finally:
        _Workbook.values = {
            "K1": 3, "K2": 1, "K3": 1, "K4": 3,
            "L1": 1, "L2": 3, "L3": 3, "L4": 1,
        }

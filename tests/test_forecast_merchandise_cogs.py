from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import forecast.engine as engine_module
from forecast.engine import (
    CostAdjustment,
    ForecastEngine,
    ForecastInput,
    SalesInput,
    calculate_lc_merchandise_forecast,
    calculate_merchandise_cogs_total,
)
from forecast.merchandise_cogs import (
    GoldenForecastMerchandiseAdapter,
    MerchandiseSourceValidationError,
    NewBusinessGoodsCogsMode,
    NewBusinessGoodsCogsValidationError,
    calculate_forecast_merchandise_cogs,
    normalize_new_business_goods_cogs,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MAPPING = json.loads(
    (ROOT / "config" / "forecast_merchandise_sources.json").read_text(encoding="utf-8")
)
MONTH_COLUMNS = {month: chr(ord("E") + month - 1) for month in range(1, 13)}


class FakeWorkbook:
    def __init__(self, cutoff: int, *, lc_rate: float = 0.8, new_rate: float = 0.7):
        self.values: dict[str, object] = {}
        self.formulas: dict[str, str] = {}
        for month, column in MONTH_COLUMNS.items():
            self.values[f"{column}3"] = "실적" if month <= cutoff else "추정"
        for product_code, rate in (("LC", lc_rate), ("NEW_BUSINESS", new_rate)):
            spec = SOURCE_MAPPING["products"][product_code]
            self.values[f"C{spec['section_row']}"] = spec["expected_section_label"]
            self.values[f"D{spec['actual_revenue_row']}"] = spec["expected_revenue_label"]
            self.values[f"D{spec['actual_cogs_row']}"] = spec["expected_cogs_label"]
            self.values[f"D{spec['actual_monthly_rate_row']}"] = spec["expected_monthly_rate_label"]
            for month in range(1, cutoff + 1):
                column = MONTH_COLUMNS[month]
                revenue = float(100 * month)
                cogs = revenue * rate
                revenue_address = f"{column}{spec['actual_revenue_row']}"
                cogs_address = f"{column}{spec['actual_cogs_row']}"
                rate_address = f"{column}{spec['actual_monthly_rate_row']}"
                rate_revenue_row = int(
                    spec.get(
                        "monthly_rate_revenue_reference_row",
                        spec["actual_revenue_row"],
                    )
                )
                rate_revenue_address = f"{column}{rate_revenue_row}"
                self.values[revenue_address] = revenue
                self.values[cogs_address] = cogs
                self.values[rate_address] = rate
                if rate_revenue_row != spec["actual_revenue_row"]:
                    self.values[rate_revenue_address] = revenue
                    self.formulas[rate_revenue_address] = f"={revenue_address}"
                if spec["actual_revenue_row"] != spec["forecast_revenue_row"]:
                    self.formulas[revenue_address] = f"={column}{spec['forecast_revenue_row']}"
                self.formulas[rate_address] = f"=IFERROR({cogs_address}/{rate_revenue_address},0)"

    def raw_value(self, address: str):
        return self.values.get(address)

    def value(self, address: str):
        return self.values.get(address)


def _sources(workbook: FakeWorkbook, forecast_month: int):
    return GoldenForecastMerchandiseAdapter(SOURCE_MAPPING).build(workbook, forecast_month)


def test_lc_actual_january_to_june_forecast_july():
    source = _sources(FakeWorkbook(6, lc_rate=0.81), 7)["LC"]
    result = calculate_forecast_merchandise_cogs(
        source, forecast_month=7, forecast_merchandise_revenue=1_000
    )
    assert result.latest_actual_month == 6
    assert result.actual_ytd_cogs_rate == pytest.approx(0.81)
    assert result.applied_forecast_cogs == pytest.approx(810)
    assert result.revenue_source_reference == "Data!E105:J105"
    assert result.monthly_rate_source_reference == "Data!E1661:J1661"
    assert result.calculation_source == "ACTUAL_YTD"


def test_explicit_lc_merchandise_revenue_drives_cogs_without_lc_product_revenue():
    source = _sources(FakeWorkbook(6, lc_rate=0.60), 7)["LC"]
    first = calculate_lc_merchandise_forecast(
        {
            "LC": SalesInput(quantity=100, amount=100_000_000),
            "LC_MERCHANDISE": SalesInput(quantity=20, amount=20_000_000),
        },
        source,
        forecast_month=7,
    )
    changed_product = calculate_lc_merchandise_forecast(
        {
            "LC": SalesInput(quantity=0, amount=0),
            "LC_MERCHANDISE": SalesInput(quantity=20, amount=20_000_000),
        },
        source,
        forecast_month=7,
    )
    assert first.forecast_merchandise_revenue == 20_000_000
    assert first.actual_ytd_cogs_rate == pytest.approx(0.60)
    assert first.applied_forecast_cogs == pytest.approx(12_000_000)
    assert changed_product.applied_forecast_cogs == pytest.approx(12_000_000)


def test_lc_merchandise_quantity_does_not_replace_explicit_zero_revenue():
    result = calculate_lc_merchandise_forecast(
        {
            "LC": SalesInput(quantity=100, amount=100_000_000),
            "LC_MERCHANDISE": SalesInput(quantity=50, amount=0),
        },
        _sources(FakeWorkbook(6, lc_rate=0.60), 7)["LC"],
        forecast_month=7,
    )
    assert result.forecast_merchandise_revenue == 0
    assert result.applied_forecast_cogs == 0


@pytest.mark.parametrize(
    ("lc_revenue", "new_business_revenue", "expected_total"),
    [
        (20_000_000, 20_000_000, 20_000_000),
        (0, 20_000_000, 8_000_000),
        (20_000_000, 0, 12_000_000),
        (0, 0, 0),
    ],
)
def test_merchandise_cogs_total_contains_only_lc_merchandise_and_new_business(
    lc_revenue, new_business_revenue, expected_total,
):
    sources = _sources(FakeWorkbook(6, lc_rate=0.60, new_rate=0.40), 7)
    lc = calculate_lc_merchandise_forecast(
        {
            "LC": SalesInput(quantity=1_000, amount=900_000_000),
            "LC_MERCHANDISE": SalesInput(quantity=20, amount=lc_revenue),
        },
        sources["LC"],
        forecast_month=7,
    )
    new_business = calculate_forecast_merchandise_cogs(
        sources["NEW_BUSINESS"],
        forecast_month=7,
        forecast_merchandise_revenue=new_business_revenue,
        selection=normalize_new_business_goods_cogs(
            "ACTUAL_YTD_DEFAULT", None, ""
        ),
    )
    assert calculate_merchandise_cogs_total(lc, new_business) == pytest.approx(
        expected_total
    )


def test_engine_writes_explicit_lc_merchandise_revenue_and_excludes_manufactured_lc(
    monkeypatch, tmp_path,
):
    sources = _sources(FakeWorkbook(6, lc_rate=0.60, new_rate=0.40), 7)

    class Adapter:
        def __init__(self, _mapping):
            pass

        def build(self, _workbook, _forecast_month):
            return sources

    class EngineWorkbook:
        instances = []

        def __init__(self, _path):
            self.values = {}
            self.inputs = {}
            self.formulas = {"K101": "=K56", "K102": "=K57"}
            self.__class__.instances.append(self)

        def raw_value(self, address):
            return "계획" if address == "K3" else self.values.get(address)

        def value(self, address):
            return self.inputs.get(address, self.values.get(address, 0))

        def set_text(self, address, value, *_args):
            self.values[address] = value

        def set_input(self, address, value, *_args, **_kwargs):
            self.inputs[address] = value

        def recalculate(self):
            if "K56" in self.inputs:
                self.values["K101"] = self.inputs["K56"]
                self.values["K1645"] = self.inputs["K56"]
            if "K57" in self.inputs:
                self.values["K102"] = self.inputs["K57"]
                self.values["K1646"] = self.inputs["K57"]
            return {}

        def add_merchandise_cogs_evidence(self, _records):
            pass

        def formula_changes(self):
            return []

        def save(self, destination):
            Path(destination).write_bytes(b"forecast")
            return Path(destination)

        def log_dicts(self):
            return []

    mapping = {
        "formula_input_exceptions": [],
        "sales": {"LC": {"quantity_row": 56, "amount_row": 57}},
        "production": {"LC": 200},
        "mcm": {},
        "lc_goods": {"quantity_row": 104, "amount_row": 105},
        "new_business_revenue_row": 114,
        "other_revenue_row": 119,
        "special_rows": {
            "selling_transport": 1168,
            "packaging": 1194,
            "disposal": 1273,
            "obsolescence": 1295,
            "lc_unit_cost": 1300,
            "raw_material_process_rows": {
                "front_process": 211,
                "back_process": 699,
            },
            "goods_cogs": 1289,
            "customs_refund": 1294,
        },
        "allocation_validation": [],
        "comparison": {
            "pnl_rows": {
                "revenue": 2001,
                "cogs": 2002,
                "gross_profit": 2003,
                "selling_expense": 2004,
                "general_admin": 2005,
                "operating_profit": 2006,
            }
        },
    }
    mapping_path = tmp_path / "model_mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    merchandise_mapping_path = tmp_path / "forecast_merchandise_sources.json"
    merchandise_mapping_path.write_text(json.dumps(SOURCE_MAPPING), encoding="utf-8")
    model_path = tmp_path / "model.xlsx"
    model_path.write_bytes(b"model")

    monkeypatch.setattr(engine_module, "GoldenWorkbook", EngineWorkbook)
    monkeypatch.setattr(engine_module, "GoldenForecastMerchandiseAdapter", Adapter)

    def run(product_amount, production_quantity, suffix, transport_adjustment=0):
        request = ForecastInput(
            month=7,
            sales={
                "LC": SalesInput(quantity=100, amount=product_amount),
                "LC_MERCHANDISE": SalesInput(quantity=20, amount=20_000_000),
                "UF_MBR": SalesInput(quantity=0, amount=20_000_000),
            },
            production={"LC": production_quantity},
            new_business_goods_cogs_mode="ACTUAL_YTD_DEFAULT",
            lc_sales_mode="EXPLICIT_LC_PRODUCT_MERCHANDISE",
            plan_na_sa_sales=1_000_000,
            na_sa_sales=2_000_000,
            uf_mbr_transport_rate=0.99,
            ix_transport_rate=0.99,
            tariff_applicable_rate=0.01,
            tariff_rate=0.99,
            sga_adjustments=(
                [CostAdjustment(1168, transport_adjustment, "명시적 운반비 조정")]
                if transport_adjustment else []
            ),
        )
        result = ForecastEngine(
            model_path,
            mapping_path,
            merchandise_mapping_path,
        ).run(request, tmp_path / f"forecast-{suffix}.xlsx")
        return result, EngineWorkbook.instances[-1]

    first, first_workbook = run(100_000_000, 100, "first")
    changed, changed_workbook = run(900_000_000, 999_999, "changed")

    assert first_workbook.inputs["K56"] == 100
    assert changed_workbook.inputs["K56"] == 100
    assert first_workbook.inputs["K57"] == 100_000_000
    assert changed_workbook.inputs["K57"] == 900_000_000
    assert first_workbook.inputs["K101"] == 100
    assert changed_workbook.inputs["K101"] == 100
    assert first_workbook.inputs["K102"] == 100_000_000
    assert changed_workbook.inputs["K102"] == 900_000_000
    assert first_workbook.values["K1645"] == 100
    assert changed_workbook.values["K1645"] == 100
    assert first_workbook.values["K1646"] == 100_000_000
    assert changed_workbook.values["K1646"] == 900_000_000
    assert first_workbook.inputs["K104"] == 20
    assert changed_workbook.inputs["K104"] == 20
    assert first_workbook.inputs["K105"] == 20_000_000
    assert changed_workbook.inputs["K105"] == 20_000_000
    assert first_workbook.inputs["K1660"] == pytest.approx(12_000_000)
    assert changed_workbook.inputs["K1660"] == pytest.approx(12_000_000)
    assert first_workbook.inputs["K1734"] == pytest.approx(8_000_000)
    assert changed_workbook.inputs["K1734"] == pytest.approx(8_000_000)
    assert first_workbook.inputs["K1289"] == pytest.approx(20_000_000)
    assert changed_workbook.inputs["K1289"] == pytest.approx(20_000_000)
    assert first.detail["goods_cogs_total"] == pytest.approx(20_000_000)
    assert changed.detail["goods_cogs_total"] == pytest.approx(20_000_000)
    assert first.detail["merchandise_cogs_total"] == pytest.approx(20_000_000)
    assert changed.detail["merchandise_cogs_total"] == pytest.approx(20_000_000)
    assert first.detail["forecast_sales_contract_version"] == "forecast-sales-v2.0.0"
    assert first.detail["lc_sales_mode"] == "EXPLICIT_LC_PRODUCT_MERCHANDISE"
    assert first_workbook.inputs["K1168"] == pytest.approx(5_170_000)
    assert changed_workbook.inputs["K1168"] == pytest.approx(29_170_000)
    assert first.detail["plan_na_sa_tariff"] == pytest.approx(85_000)
    assert first.detail["forecast_na_sa_tariff"] == pytest.approx(170_000)
    assert first.detail["authoritative_uf_mbr_freight_rate"] == pytest.approx(0.10)
    assert first.detail["authoritative_tariff_eligible_ratio"] == pytest.approx(0.85)

    adjusted, adjusted_workbook = run(100_000_000, 100, "adjusted", 1_234)
    assert adjusted.detail["selling_transport_before_adjustment"] == pytest.approx(
        5_170_000
    )
    assert adjusted.detail["selling_transport_after_adjustment"] == pytest.approx(
        5_171_234
    )
    assert adjusted_workbook.inputs["K1168"] == pytest.approx(5_171_234)

    legacy = ForecastEngine(
        model_path,
        mapping_path,
        merchandise_mapping_path,
    ).run(
        ForecastInput(
            month=7,
            sales={
                "LC": SalesInput(quantity=100, amount=100_000_000),
                "UF_MBR": SalesInput(quantity=0, amount=20_000_000),
            },
            production={"LC": 80},
            new_business_goods_cogs_mode="ACTUAL_YTD_DEFAULT",
        ),
        tmp_path / "forecast-legacy.xlsx",
    )
    legacy_workbook = EngineWorkbook.instances[-1]
    assert legacy_workbook.inputs["K105"] == 0
    assert legacy_workbook.inputs["K1660"] == 0
    assert legacy_workbook.inputs["K1734"] == pytest.approx(8_000_000)
    assert legacy_workbook.inputs["K1289"] == pytest.approx(8_000_000)
    assert legacy.detail["lc_sales_mode"] == "LEGACY_LC_PRODUCT_ONLY"

    with pytest.raises(ValueError, match="sales contract identity"):
        ForecastEngine(
            model_path,
            mapping_path,
            merchandise_mapping_path,
        ).run(
            ForecastInput(
                month=7,
                sales={
                    "LC": SalesInput(quantity=100, amount=100_000_000),
                    "LC_MERCHANDISE": SalesInput(quantity=20, amount=20_000_000),
                },
            ),
            tmp_path / "forecast-invalid-legacy.xlsx",
        )


def test_lc_actual_to_june_forecast_july_to_september_is_actual_only():
    workbook = FakeWorkbook(6)
    results = [
        calculate_forecast_merchandise_cogs(
            _sources(workbook, month)["LC"],
            forecast_month=month,
            forecast_merchandise_revenue=1_000,
        )
        for month in (7, 8, 9)
    ]
    assert {item.latest_actual_month for item in results} == {6}
    assert {item.revenue_source_reference for item in results} == {"Data!E105:J105"}
    assert {item.applied_forecast_cogs for item in results} == {800.0}


def test_lc_cutoff_moves_to_july_for_august_and_september():
    workbook = FakeWorkbook(7, lc_rate=0.84)
    for month in (8, 9):
        result = calculate_forecast_merchandise_cogs(
            _sources(workbook, month)["LC"],
            forecast_month=month,
            forecast_merchandise_revenue=2_000,
        )
        assert result.revenue_source_reference == "Data!E105:K105"
        assert result.applied_forecast_cogs == pytest.approx(1_680)


def test_cutoff_change_updates_weighted_ytd_rate():
    before = FakeWorkbook(6, lc_rate=0.8)
    after = FakeWorkbook(7, lc_rate=0.8)
    spec = SOURCE_MAPPING["products"]["LC"]
    after.values[f"K{spec['actual_cogs_row']}"] = 700.0
    after.values[f"K{spec['actual_monthly_rate_row']}"] = 1.0
    before_result = calculate_forecast_merchandise_cogs(
        _sources(before, 8)["LC"], forecast_month=8, forecast_merchandise_revenue=1_000
    )
    after_result = calculate_forecast_merchandise_cogs(
        _sources(after, 8)["LC"], forecast_month=8, forecast_merchandise_revenue=1_000
    )
    assert after_result.actual_ytd_cogs_rate > before_result.actual_ytd_cogs_rate


def test_zero_denominator_and_missing_sources_fail_closed():
    zero = FakeWorkbook(6)
    lc = SOURCE_MAPPING["products"]["LC"]
    for month in range(1, 7):
        column = MONTH_COLUMNS[month]
        zero.values[f"{column}{lc['actual_revenue_row']}"] = 0.0
        zero.values[f"{column}{lc['actual_cogs_row']}"] = 0.0
    with pytest.raises(MerchandiseSourceValidationError, match="revenue is zero") as captured:
        _sources(zero, 7)
    assert captured.value.code == "actual_ytd_revenue_zero"

    missing_revenue = FakeWorkbook(6)
    missing_revenue.values[f"J{lc['actual_revenue_row']}"] = None
    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(missing_revenue, 7)
    assert captured.value.code == "actual_ytd_revenue_missing"

    missing_cogs = FakeWorkbook(6)
    new = SOURCE_MAPPING["products"]["NEW_BUSINESS"]
    missing_cogs.values[f"J{new['actual_cogs_row']}"] = None
    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(missing_cogs, 7)
    assert captured.value.code == "actual_ytd_cogs_missing"


def test_paired_blank_actual_month_is_omitted_from_weighted_ytd_sum_without_zero_fallback():
    workbook = FakeWorkbook(6, lc_rate=0.60, new_rate=0.40)
    for product_code, month in (("LC", 3), ("NEW_BUSINESS", 4)):
        spec = SOURCE_MAPPING["products"][product_code]
        column = MONTH_COLUMNS[month]
        workbook.values[f"{column}{spec['actual_revenue_row']}"] = None
        workbook.values[f"{column}{spec['actual_cogs_row']}"] = None
        workbook.values[f"{column}{spec['actual_monthly_rate_row']}"] = None
        workbook.formulas.pop(f"{column}{spec['actual_monthly_rate_row']}", None)

    sources = _sources(workbook, 7)

    assert sources["LC"].actual_ytd_cogs_rate == pytest.approx(0.60)
    assert sources["NEW_BUSINESS"].actual_ytd_cogs_rate == pytest.approx(0.40)
    assert sources["LC"].revenue_source_reference == "Data!E105:J105"


def test_blank_revenue_with_numeric_zero_cogs_is_not_treated_as_a_paired_blank():
    workbook = FakeWorkbook(6, lc_rate=0.60)
    lc = SOURCE_MAPPING["products"]["LC"]
    workbook.values[f"G{lc['actual_revenue_row']}"] = None
    workbook.values[f"G{lc['actual_cogs_row']}"] = 0.0

    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(workbook, 7)

    assert captured.value.code == "actual_ytd_revenue_missing"


def test_formula_linked_blank_new_business_revenue_with_zero_cogs_is_no_activity():
    workbook = FakeWorkbook(6, new_rate=0.40)
    spec = SOURCE_MAPPING["products"]["NEW_BUSINESS"]
    workbook.values["H114"] = None
    workbook.values[f"H{spec['actual_revenue_row']}"] = None
    workbook.values[f"H{spec['actual_cogs_row']}"] = 0
    workbook.values[f"H{spec['actual_monthly_rate_row']}"] = None
    workbook.formulas.pop(f"H{spec['actual_monthly_rate_row']}", None)

    source = _sources(workbook, 7)["NEW_BUSINESS"]

    assert source.actual_ytd_cogs_rate == pytest.approx(0.40)


def test_formula_linked_blank_new_business_cannot_hide_cogs_self_reference():
    workbook = FakeWorkbook(6, new_rate=0.40)
    spec = SOURCE_MAPPING["products"]["NEW_BUSINESS"]
    workbook.values["H114"] = None
    workbook.values[f"H{spec['actual_revenue_row']}"] = None
    workbook.values[f"H{spec['actual_cogs_row']}"] = 0
    workbook.formulas[f"H{spec['actual_cogs_row']}"] = "=K1289"

    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(workbook, 7)

    assert captured.value.code == "actual_ytd_revenue_missing"


def test_no_cutoff_noncontiguous_and_forecast_self_reference_are_blocked():
    no_actual = FakeWorkbook(6)
    for column in MONTH_COLUMNS.values():
        no_actual.values[f"{column}3"] = "추정"
    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(no_actual, 7)
    assert captured.value.code == "actual_cutoff_missing"

    gap = FakeWorkbook(7)
    gap.values["G3"] = "추정"
    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(gap, 8)
    assert captured.value.code == "actual_period_non_contiguous"

    self_reference = FakeWorkbook(6)
    lc = SOURCE_MAPPING["products"]["LC"]
    self_reference.formulas[f"J{lc['actual_cogs_row']}"] = "=K1289"
    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(self_reference, 7)
    assert captured.value.code == "actual_cogs_forecast_self_reference"


def test_monthly_rate_rows_validate_but_are_not_used_as_ytd_rate():
    workbook = FakeWorkbook(6, lc_rate=0.8)
    lc = SOURCE_MAPPING["products"]["LC"]
    workbook.values[f"J{lc['actual_revenue_row']}"] = 600.0
    workbook.values[f"J{lc['actual_cogs_row']}"] = 600.0
    workbook.values[f"J{lc['actual_monthly_rate_row']}"] = 1.0
    source = _sources(workbook, 7)["LC"]
    assert source.actual_ytd_cogs_rate != 1.0
    assert source.actual_ytd_cogs_rate == pytest.approx(source.actual_ytd_cogs / source.actual_ytd_revenue)


def test_new_business_actual_ytd_default_and_rate_separation():
    sources = _sources(FakeWorkbook(6, lc_rate=0.82, new_rate=0.67), 7)
    automatic = normalize_new_business_goods_cogs("ACTUAL_YTD_DEFAULT", None, "")
    lc = calculate_forecast_merchandise_cogs(
        sources["LC"], forecast_month=7, forecast_merchandise_revenue=1_000
    )
    new = calculate_forecast_merchandise_cogs(
        sources["NEW_BUSINESS"], forecast_month=7,
        forecast_merchandise_revenue=2_000, selection=automatic,
    )
    assert lc.applied_forecast_cogs == pytest.approx(820)
    assert new.applied_forecast_cogs == pytest.approx(1_340)
    assert new.mode == "ACTUAL_YTD_DEFAULT"
    assert new.calculation_source == "ACTUAL_YTD"
    assert new.revenue_source_reference == "Data!E1733:J1733"


def test_new_business_cutoff_change_updates_actual_ytd_rate():
    before = FakeWorkbook(6, new_rate=0.7)
    after = FakeWorkbook(7, new_rate=0.7)
    spec = SOURCE_MAPPING["products"]["NEW_BUSINESS"]
    after.values[f"K{spec['actual_cogs_row']}"] = 700.0
    after.values[f"K{spec['actual_monthly_rate_row']}"] = 1.0
    selection = normalize_new_business_goods_cogs("ACTUAL_YTD_DEFAULT", None, "")

    before_result = calculate_forecast_merchandise_cogs(
        _sources(before, 8)["NEW_BUSINESS"],
        forecast_month=8,
        forecast_merchandise_revenue=1_000,
        selection=selection,
    )
    after_result = calculate_forecast_merchandise_cogs(
        _sources(after, 8)["NEW_BUSINESS"],
        forecast_month=8,
        forecast_merchandise_revenue=1_000,
        selection=selection,
    )

    assert before_result.latest_actual_month == 6
    assert after_result.latest_actual_month == 7
    assert after_result.actual_ytd_cogs_rate > before_result.actual_ytd_cogs_rate


def test_new_business_actual_source_cannot_reference_forecast_output():
    workbook = FakeWorkbook(6)
    spec = SOURCE_MAPPING["products"]["NEW_BUSINESS"]
    workbook.formulas[f"J{spec['actual_cogs_row']}"] = "=K1289"

    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(workbook, 7)

    assert captured.value.code == "actual_cogs_forecast_self_reference"
    assert captured.value.product_code == "NEW_BUSINESS"


@pytest.mark.parametrize("amount", [0, 123])
def test_actual_ytd_default_rejects_any_manual_amount(amount):
    with pytest.raises(NewBusinessGoodsCogsValidationError) as captured:
        normalize_new_business_goods_cogs("ACTUAL_YTD_DEFAULT", amount, "")
    assert captured.value.code == "actual_ytd_manual_amount_conflict"


def test_manual_override_positive_zero_and_reason_are_authoritative():
    source = _sources(FakeWorkbook(6), 7)["NEW_BUSINESS"]
    for amount in (123.0, 0.0):
        selection = normalize_new_business_goods_cogs(
            NewBusinessGoodsCogsMode.MANUAL_OVERRIDE, amount, "사용자 사유"
        )
        result = calculate_forecast_merchandise_cogs(
            source, forecast_month=7, forecast_merchandise_revenue=2_000,
            selection=selection,
        )
        assert result.applied_forecast_cogs == amount
        assert result.manual_reason == "사용자 사유"
        assert result.calculation_source == "MANUAL_OVERRIDE"


def test_explicit_manual_requires_amount_and_reason():
    with pytest.raises(NewBusinessGoodsCogsValidationError) as captured:
        normalize_new_business_goods_cogs("MANUAL_OVERRIDE", None, "사유")
    assert captured.value.code == "manual_amount_required"
    with pytest.raises(NewBusinessGoodsCogsValidationError) as captured:
        normalize_new_business_goods_cogs("MANUAL_OVERRIDE", 0, "")
    assert captured.value.code == "manual_reason_required"


def test_legacy_no_mode_preserves_omitted_and_explicit_zero_semantics():
    omitted = normalize_new_business_goods_cogs(None, None, "")
    explicit_zero = normalize_new_business_goods_cogs(None, 0, "")
    assert omitted.mode is NewBusinessGoodsCogsMode.MANUAL_OVERRIDE
    assert omitted.manual_amount == explicit_zero.manual_amount == 0.0
    assert omitted.legacy_normalized and explicit_zero.legacy_normalized


def test_scope_and_source_formula_mismatch_fail_closed():
    invalid_scope = copy.deepcopy(SOURCE_MAPPING)
    invalid_scope["products"]["LC"]["specification"] = "manufactured"
    with pytest.raises(MerchandiseSourceValidationError) as captured:
        GoldenForecastMerchandiseAdapter(invalid_scope).build(FakeWorkbook(6), 7)
    assert captured.value.code == "product_scope_mismatch"

    invalid_new_scope = copy.deepcopy(SOURCE_MAPPING)
    invalid_new_scope["products"]["NEW_BUSINESS"]["specification"] = "서비스"
    with pytest.raises(MerchandiseSourceValidationError) as captured:
        GoldenForecastMerchandiseAdapter(invalid_new_scope).build(FakeWorkbook(6), 7)
    assert captured.value.code == "product_scope_mismatch"

    wrong_formula = FakeWorkbook(6)
    lc = SOURCE_MAPPING["products"]["LC"]
    wrong_formula.formulas[f"J{lc['actual_revenue_row']}"] = "=J57"
    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(wrong_formula, 7)
    assert captured.value.code == "actual_revenue_formula_mismatch"

    wrong_rate_lineage = FakeWorkbook(6)
    wrong_rate_lineage.formulas[
        f"J{lc['monthly_rate_revenue_reference_row']}"
    ] = "=J102"
    with pytest.raises(MerchandiseSourceValidationError) as captured:
        _sources(wrong_rate_lineage, 7)
    assert captured.value.code == "actual_rate_revenue_lineage_mismatch"


def test_forecast_source_mapping_is_additive_and_global_mapping_has_no_slice2_rows():
    global_mapping = json.loads((ROOT / "config" / "model_mapping.json").read_text(encoding="utf-8"))
    assert "forecast_merchandise_cogs" not in global_mapping
    assert SOURCE_MAPPING["mapping_version"] == "forecast-merchandise-v1.1.0"
    assert SOURCE_MAPPING["sales_rows"] == {
        "LC_PRODUCT": {"quantity_row": 101, "revenue_row": 102},
        "LC_MERCHANDISE": {"quantity_row": 104, "revenue_row": 105},
    }
    assert SOURCE_MAPPING["products"]["LC"]["actual_revenue_row"] == 105
    assert SOURCE_MAPPING["products"]["LC"]["actual_cogs_row"] == 1660
    assert SOURCE_MAPPING["products"]["LC"]["actual_monthly_rate_row"] == 1661
    assert SOURCE_MAPPING["products"]["LC"]["monthly_rate_revenue_reference_row"] == 1659
    assert SOURCE_MAPPING["products"]["NEW_BUSINESS"]["actual_revenue_row"] == 1733
    assert SOURCE_MAPPING["products"]["NEW_BUSINESS"]["actual_cogs_row"] == 1734
    assert SOURCE_MAPPING["products"]["NEW_BUSINESS"]["actual_monthly_rate_row"] == 1736
    assert SOURCE_MAPPING["total_forecast_cogs_row"] == 1289

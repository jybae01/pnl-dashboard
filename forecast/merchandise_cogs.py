from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from enum import Enum
from numbers import Real
from typing import Any, Mapping, Protocol

from .provenance import mapping_hash
from .workbook import _normalize_period_type


MONTH_COLUMNS = {month: chr(ord("E") + month - 1) for month in range(1, 13)}


class NewBusinessGoodsCogsMode(str, Enum):
    ACTUAL_YTD_DEFAULT = "ACTUAL_YTD_DEFAULT"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class NewBusinessGoodsCogsValidationError(ValueError):
    def __init__(self, code: str, message: str, *, field: str):
        self.code = code
        self.field = field
        super().__init__(message)


@dataclass(frozen=True)
class NewBusinessGoodsCogsSelection:
    mode: NewBusinessGoodsCogsMode
    manual_amount: float | None
    reason: str
    legacy_normalized: bool


def normalize_new_business_goods_cogs(
    mode: str | NewBusinessGoodsCogsMode | None,
    amount: Any,
    reason: Any,
    *,
    legacy_normalized: bool = False,
) -> NewBusinessGoodsCogsSelection:
    """Return one unambiguous canonical mode while preserving legacy zero semantics."""

    is_legacy = mode is None or legacy_normalized
    if mode is None:
        normalized_mode = NewBusinessGoodsCogsMode.MANUAL_OVERRIDE
    else:
        try:
            normalized_mode = (
                mode
                if isinstance(mode, NewBusinessGoodsCogsMode)
                else NewBusinessGoodsCogsMode(str(mode))
            )
        except ValueError as exc:
            raise NewBusinessGoodsCogsValidationError(
                "mode_invalid",
                "new_business_goods_cogs_mode is invalid",
                field="new_business_goods_cogs_mode",
            ) from exc

    normalized_reason = "" if reason is None else str(reason)
    if len(normalized_reason) > 500 or any(
        ord(character) < 32 and character != "\t" for character in normalized_reason
    ):
        raise NewBusinessGoodsCogsValidationError(
            "reason_invalid",
            "new_business_goods_cogs_reason must be safe text up to 500 characters",
            field="new_business_goods_cogs_reason",
        )

    if normalized_mode is NewBusinessGoodsCogsMode.ACTUAL_YTD_DEFAULT:
        if amount is not None:
            raise NewBusinessGoodsCogsValidationError(
                "actual_ytd_manual_amount_conflict",
                "ACTUAL_YTD_DEFAULT must not include a manual amount",
                field="new_business_goods_cogs",
            )
        if normalized_reason.strip():
            raise NewBusinessGoodsCogsValidationError(
                "actual_ytd_manual_reason_conflict",
                "ACTUAL_YTD_DEFAULT must not include a manual reason",
                field="new_business_goods_cogs_reason",
            )
        return NewBusinessGoodsCogsSelection(
            normalized_mode, None, "", False
        )

    if amount is None:
        if is_legacy:
            normalized_amount = 0.0
        else:
            raise NewBusinessGoodsCogsValidationError(
                "manual_amount_required",
                "MANUAL_OVERRIDE requires new_business_goods_cogs",
                field="new_business_goods_cogs",
            )
    elif isinstance(amount, bool) or not isinstance(amount, Real):
        raise NewBusinessGoodsCogsValidationError(
            "manual_amount_invalid",
            "new_business_goods_cogs must be a finite nonnegative number",
            field="new_business_goods_cogs",
        )
    else:
        normalized_amount = float(amount)
        if not math.isfinite(normalized_amount) or normalized_amount < 0:
            raise NewBusinessGoodsCogsValidationError(
                "manual_amount_invalid",
                "new_business_goods_cogs must be a finite nonnegative number",
                field="new_business_goods_cogs",
            )
    if not is_legacy and not normalized_reason.strip():
        raise NewBusinessGoodsCogsValidationError(
            "manual_reason_required",
            "MANUAL_OVERRIDE requires new_business_goods_cogs_reason",
            field="new_business_goods_cogs_reason",
        )
    return NewBusinessGoodsCogsSelection(
        normalized_mode,
        normalized_amount,
        normalized_reason,
        is_legacy,
    )


class MerchandiseSourceValidationError(ValueError):
    """Fail-closed error for authoritative Actual merchandise sources."""

    def __init__(self, code: str, message: str, *, product_code: str | None = None):
        self.code = code
        self.product_code = product_code
        prefix = f"{product_code}: " if product_code else ""
        super().__init__(prefix + message)


class MerchandiseWorkbook(Protocol):
    formulas: Mapping[str, str]

    def raw_value(self, address: str) -> Any: ...
    def value(self, address: str) -> Any: ...


@dataclass(frozen=True)
class ActualYtdMerchandiseSource:
    product_code: str
    business_source: str
    specification: str
    currency: str
    latest_actual_month: int
    actual_months: tuple[int, ...]
    actual_ytd_revenue: float
    actual_ytd_cogs: float
    actual_ytd_cogs_rate: float
    revenue_row: int
    cogs_row: int
    monthly_rate_row: int
    forecast_revenue_row: int
    total_forecast_cogs_row: int
    source_mapping_version: str
    source_mapping_hash: str

    @property
    def first_actual_column(self) -> str:
        return MONTH_COLUMNS[self.actual_months[0]]

    @property
    def last_actual_column(self) -> str:
        return MONTH_COLUMNS[self.actual_months[-1]]

    @property
    def revenue_source_reference(self) -> str:
        return f"Data!{self.first_actual_column}{self.revenue_row}:{self.last_actual_column}{self.revenue_row}"

    @property
    def cogs_source_reference(self) -> str:
        return f"Data!{self.first_actual_column}{self.cogs_row}:{self.last_actual_column}{self.cogs_row}"

    @property
    def monthly_rate_source_reference(self) -> str:
        return f"Data!{self.first_actual_column}{self.monthly_rate_row}:{self.last_actual_column}{self.monthly_rate_row}"


@dataclass(frozen=True)
class ForecastMerchandiseCogsCalculation:
    product_code: str
    business_source: str
    specification: str
    currency: str
    mode: str
    calculation_source: str
    forecast_month: int
    latest_actual_month: int
    actual_ytd_revenue: float
    actual_ytd_cogs: float
    actual_ytd_cogs_rate: float
    forecast_merchandise_revenue: float
    actual_ytd_derived_cogs: float
    manual_cogs: float | None
    manual_reason: str
    applied_forecast_cogs: float
    legacy_normalized: bool
    revenue_source_reference: str
    cogs_source_reference: str
    monthly_rate_source_reference: str
    forecast_revenue_source_reference: str
    total_forecast_cogs_source_reference: str
    canonical_revenue_field: str
    canonical_cogs_field: str
    canonical_rate_field: str
    canonical_forecast_revenue_field: str
    canonical_forecast_cogs_field: str
    source_mapping_version: str
    source_mapping_hash: str
    validation_status: str = "PASS"
    actual_cutoff_valid: bool = True
    actual_only_numerator: bool = True
    actual_only_denominator: bool = True
    zero_denominator_check: bool = True
    missing_source_check: bool = True
    no_forecast_self_reference: bool = True
    product_scope_valid: bool = True
    mode_valid: bool = True
    manual_amount_conflict_free: bool = True
    manual_reason_valid: bool = True
    no_hardcoded_forecast_cogs: bool = True
    golden_source_valid: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _row_text(workbook: MerchandiseWorkbook, row: int) -> str:
    return " | ".join(
        str(value).strip()
        for column in ("A", "B", "C", "D")
        if (value := workbook.raw_value(f"{column}{row}")) not in (None, "")
    )


def _finite_number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


class GoldenForecastMerchandiseAdapter:
    """Map Golden Actual-only rows to canonical YTD merchandise rates."""

    def __init__(self, source_mapping: Mapping[str, Any]):
        if not isinstance(source_mapping, Mapping):
            raise MerchandiseSourceValidationError("mapping_missing", "forecast merchandise source mapping is required")
        self.mapping = source_mapping
        self.mapping_version = str(source_mapping.get("mapping_version") or "").strip()
        self.mapping_hash = mapping_hash(source_mapping)
        if str(source_mapping.get("schema_version") or "") != "1" or not self.mapping_version:
            raise MerchandiseSourceValidationError("mapping_invalid", "forecast merchandise mapping identity is invalid")

    def latest_confirmed_actual_month(
        self, workbook: MerchandiseWorkbook, forecast_month: int
    ) -> tuple[int, tuple[int, ...]]:
        try:
            period_type_row = int(self.mapping["period_type_row"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MerchandiseSourceValidationError("period_type_mapping_missing", "period_type_row is required") from exc
        actual_months = tuple(
            month
            for month, column in MONTH_COLUMNS.items()
            if _normalize_period_type(workbook.raw_value(f"{column}{period_type_row}")) == "실적"
        )
        if not actual_months:
            raise MerchandiseSourceValidationError("actual_cutoff_missing", "latest confirmed Actual month is unavailable")
        cutoff = max(actual_months)
        if actual_months != tuple(range(1, cutoff + 1)):
            raise MerchandiseSourceValidationError("actual_period_non_contiguous", "confirmed Actual months must be contiguous from January")
        if forecast_month <= cutoff:
            raise MerchandiseSourceValidationError(
                "forecast_month_not_after_actual",
                f"forecast month {forecast_month} must be after Actual cutoff {cutoff}",
            )
        return cutoff, actual_months

    def build(
        self, workbook: MerchandiseWorkbook, forecast_month: int
    ) -> dict[str, ActualYtdMerchandiseSource]:
        cutoff, actual_months = self.latest_confirmed_actual_month(workbook, forecast_month)
        products = self.mapping.get("products")
        if not isinstance(products, Mapping) or set(products) != {"LC", "NEW_BUSINESS"}:
            raise MerchandiseSourceValidationError("product_mapping_invalid", "LC and NEW_BUSINESS mappings are required")
        try:
            total_row = int(self.mapping["total_forecast_cogs_row"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MerchandiseSourceValidationError("output_mapping_missing", "total Forecast COGS row is required") from exc
        return {
            str(product_code): self._build_product(
                workbook, str(product_code), spec, cutoff, actual_months, total_row
            )
            for product_code, spec in products.items()
        }

    def _build_product(
        self,
        workbook: MerchandiseWorkbook,
        product_code: str,
        spec: Any,
        cutoff: int,
        actual_months: tuple[int, ...],
        total_row: int,
    ) -> ActualYtdMerchandiseSource:
        if not isinstance(spec, Mapping):
            raise MerchandiseSourceValidationError("product_mapping_invalid", "product mapping must be an object", product_code=product_code)
        required_rows = ("section_row", "actual_revenue_row", "actual_cogs_row", "actual_monthly_rate_row", "forecast_revenue_row")
        try:
            rows = {key: int(spec[key]) for key in required_rows}
            monthly_rate_revenue_reference_row = int(
                spec.get(
                    "monthly_rate_revenue_reference_row",
                    rows["actual_revenue_row"],
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MerchandiseSourceValidationError("source_mapping_invalid", "all canonical source rows are required", product_code=product_code) from exc

        if product_code == "LC" and str(spec.get("specification")) != "4-inch":
            raise MerchandiseSourceValidationError("product_scope_mismatch", "LC merchandise scope must be 4-inch", product_code=product_code)
        if product_code == "NEW_BUSINESS" and str(spec.get("specification")) != "상품":
            raise MerchandiseSourceValidationError("product_scope_mismatch", "new-business scope must be merchandise only", product_code=product_code)
        label_checks = (
            (rows["section_row"], str(spec.get("expected_section_label") or "")),
            (rows["actual_revenue_row"], str(spec.get("expected_revenue_label") or "")),
            (rows["actual_cogs_row"], str(spec.get("expected_cogs_label") or "")),
            (rows["actual_monthly_rate_row"], str(spec.get("expected_monthly_rate_label") or "")),
        )
        for row, expected in label_checks:
            observed = _row_text(workbook, row)
            if not expected or expected not in observed:
                raise MerchandiseSourceValidationError(
                    "source_label_mismatch",
                    f"Data row {row} expected '{expected}', observed '{observed}'",
                    product_code=product_code,
                )

        ytd_revenue = 0.0
        ytd_cogs = 0.0
        for month in actual_months:
            column = MONTH_COLUMNS[month]
            revenue_address = f"{column}{rows['actual_revenue_row']}"
            cogs_address = f"{column}{rows['actual_cogs_row']}"
            rate_address = f"{column}{rows['actual_monthly_rate_row']}"
            rate_revenue_address = f"{column}{monthly_rate_revenue_reference_row}"
            expected_revenue_formula = f"={column}{rows['forecast_revenue_row']}"
            revenue_formula = str(workbook.formulas.get(revenue_address) or "").replace("$", "").upper()
            direct_revenue_source = rows["actual_revenue_row"] == rows["forecast_revenue_row"]
            if direct_revenue_source and revenue_formula:
                raise MerchandiseSourceValidationError(
                    "actual_revenue_formula_mismatch",
                    f"{revenue_address} must be a direct scoped revenue source",
                    product_code=product_code,
                )
            if not direct_revenue_source and revenue_formula != expected_revenue_formula.upper():
                raise MerchandiseSourceValidationError(
                    "actual_revenue_formula_mismatch",
                    f"{revenue_address} must reference scoped revenue {expected_revenue_formula}",
                    product_code=product_code,
                )
            if monthly_rate_revenue_reference_row != rows["actual_revenue_row"]:
                rate_revenue_formula = str(
                    workbook.formulas.get(rate_revenue_address) or ""
                ).replace("$", "").upper()
                if rate_revenue_formula != f"={revenue_address}".upper():
                    raise MerchandiseSourceValidationError(
                        "actual_rate_revenue_lineage_mismatch",
                        f"{rate_revenue_address} must reference authoritative revenue {revenue_address}",
                        product_code=product_code,
                    )
            revenue = _finite_number(workbook.value(revenue_address))
            cogs = _finite_number(workbook.value(cogs_address))
            # Excel SUM semantics omit a genuinely inactive month only when
            # both authoritative cells are physically blank.  No blank value
            # is coerced to zero; every one-sided source remains a hard error.
            if revenue is None and cogs is None:
                continue
            # The approved New Business source is a formula-linked alias of
            # its sales input row.  In an inactive month the input is blank,
            # the alias evaluates blank, and the workbook stores explicit
            # zero COGS.  Recognize only this traced no-activity shape; LC and
            # every other one-sided blank remain fail-closed.
            forecast_revenue_address = f"{column}{rows['forecast_revenue_row']}"
            formula_linked_new_business_no_activity = (
                product_code == "NEW_BUSINESS"
                and revenue is None
                and cogs is not None
                and abs(cogs) <= 1e-12
                and revenue_formula == expected_revenue_formula.upper()
                and workbook.raw_value(forecast_revenue_address) in (None, "")
                and workbook.raw_value(cogs_address) == 0
                and not str(workbook.formulas.get(cogs_address) or "").strip()
            )
            if formula_linked_new_business_no_activity:
                continue
            if revenue is None:
                raise MerchandiseSourceValidationError("actual_ytd_revenue_missing", f"{revenue_address} is missing", product_code=product_code)
            if cogs is None:
                raise MerchandiseSourceValidationError("actual_ytd_cogs_missing", f"{cogs_address} is missing", product_code=product_code)
            if revenue < 0:
                raise MerchandiseSourceValidationError("actual_revenue_negative", f"{revenue_address} must be nonnegative", product_code=product_code)
            if abs(revenue) <= 1e-12 and abs(cogs) > 1e-12:
                raise MerchandiseSourceValidationError("actual_cogs_without_revenue", f"{cogs_address} has COGS without Actual revenue", product_code=product_code)

            # Actual numerator cells must not reach into the Forecast output or
            # any month after the authoritative cutoff.
            cogs_formula = str(workbook.formulas.get(cogs_address) or "")
            for reference_column, reference_row in re.findall(
                r"\$?([A-Z]{1,3})\$?(\d+)", cogs_formula.upper()
            ):
                referenced_month = next(
                    (
                        month for month, candidate in MONTH_COLUMNS.items()
                        if candidate == reference_column
                    ),
                    None,
                )
                if int(reference_row) == total_row or (
                    referenced_month is not None and referenced_month > cutoff
                ):
                    raise MerchandiseSourceValidationError(
                        "actual_cogs_forecast_self_reference",
                        f"{cogs_address} depends on Forecast output or period",
                        product_code=product_code,
                    )

            if abs(revenue) <= 1e-12:
                ytd_revenue += revenue
                ytd_cogs += cogs
                continue

            rate_formula = str(workbook.formulas.get(rate_address) or "").replace("$", "").upper()
            if not rate_formula:
                raise MerchandiseSourceValidationError("actual_rate_formula_missing", f"{rate_address} has no Golden monthly rate formula", product_code=product_code)
            if cogs_address.upper() not in rate_formula or rate_revenue_address.upper() not in rate_formula:
                raise MerchandiseSourceValidationError("actual_rate_formula_scope_mismatch", f"{rate_address} must reference {cogs_address} and {rate_revenue_address}", product_code=product_code)
            if abs(revenue) > 1e-12:
                observed_rate = _finite_number(workbook.value(rate_address))
                monthly_rate = cogs / revenue
                if observed_rate is None or abs(observed_rate - monthly_rate) > max(1e-12, abs(monthly_rate) * 1e-9):
                    raise MerchandiseSourceValidationError("actual_rate_value_mismatch", f"{rate_address} does not reconcile to COGS / revenue", product_code=product_code)
            ytd_revenue += revenue
            ytd_cogs += cogs

        if abs(ytd_revenue) <= 1e-12:
            raise MerchandiseSourceValidationError("actual_ytd_revenue_zero", "Actual YTD merchandise revenue is zero", product_code=product_code)
        return ActualYtdMerchandiseSource(
            product_code=product_code,
            business_source=str(spec.get("business_source") or product_code),
            specification=str(spec.get("specification") or ""),
            currency=str(spec.get("currency") or "KRW"),
            latest_actual_month=cutoff,
            actual_months=actual_months,
            actual_ytd_revenue=ytd_revenue,
            actual_ytd_cogs=ytd_cogs,
            actual_ytd_cogs_rate=ytd_cogs / ytd_revenue,
            revenue_row=rows["actual_revenue_row"],
            cogs_row=rows["actual_cogs_row"],
            monthly_rate_row=rows["actual_monthly_rate_row"],
            forecast_revenue_row=rows["forecast_revenue_row"],
            total_forecast_cogs_row=total_row,
            source_mapping_version=self.mapping_version,
            source_mapping_hash=self.mapping_hash,
        )


def calculate_forecast_merchandise_cogs(
    source: ActualYtdMerchandiseSource,
    *,
    forecast_month: int,
    forecast_merchandise_revenue: float,
    selection: NewBusinessGoodsCogsSelection | None = None,
) -> ForecastMerchandiseCogsCalculation:
    if forecast_month <= source.latest_actual_month:
        raise MerchandiseSourceValidationError("forecast_month_not_after_actual", "forecast month must be after the latest Actual cutoff", product_code=source.product_code)
    revenue = _finite_number(forecast_merchandise_revenue)
    if revenue is None or revenue < 0:
        raise MerchandiseSourceValidationError("forecast_revenue_invalid", "forecast merchandise revenue must be a finite nonnegative amount", product_code=source.product_code)
    if source.product_code == "LC":
        if selection is not None:
            raise MerchandiseSourceValidationError("product_scope_mismatch", "LC does not accept a new-business selection", product_code=source.product_code)
        mode = NewBusinessGoodsCogsMode.ACTUAL_YTD_DEFAULT.value
        calculation_source = "ACTUAL_YTD"
        manual_amount = None
        manual_reason = ""
        legacy = False
    else:
        if selection is None:
            raise MerchandiseSourceValidationError("mode_missing", "new-business mode is required", product_code=source.product_code)
        mode = selection.mode.value
        calculation_source = "ACTUAL_YTD" if selection.mode is NewBusinessGoodsCogsMode.ACTUAL_YTD_DEFAULT else "MANUAL_OVERRIDE"
        manual_amount = selection.manual_amount
        manual_reason = selection.reason
        legacy = selection.legacy_normalized
    derived = revenue * source.actual_ytd_cogs_rate
    applied = derived if calculation_source == "ACTUAL_YTD" else float(manual_amount)
    column = MONTH_COLUMNS[forecast_month]
    prefix = "lc" if source.product_code == "LC" else "new_business"
    return ForecastMerchandiseCogsCalculation(
        product_code=source.product_code,
        business_source=source.business_source,
        specification=source.specification,
        currency=source.currency,
        mode=mode,
        calculation_source=calculation_source,
        forecast_month=forecast_month,
        latest_actual_month=source.latest_actual_month,
        actual_ytd_revenue=source.actual_ytd_revenue,
        actual_ytd_cogs=source.actual_ytd_cogs,
        actual_ytd_cogs_rate=source.actual_ytd_cogs_rate,
        forecast_merchandise_revenue=revenue,
        actual_ytd_derived_cogs=derived,
        manual_cogs=manual_amount,
        manual_reason=manual_reason,
        applied_forecast_cogs=applied,
        legacy_normalized=legacy,
        revenue_source_reference=source.revenue_source_reference,
        cogs_source_reference=source.cogs_source_reference,
        monthly_rate_source_reference=source.monthly_rate_source_reference,
        forecast_revenue_source_reference=f"Data!{column}{source.forecast_revenue_row}",
        total_forecast_cogs_source_reference=f"Data!{column}{source.total_forecast_cogs_row}",
        canonical_revenue_field=f"{prefix}_actual_ytd_merchandise_revenue",
        canonical_cogs_field=f"{prefix}_actual_ytd_merchandise_cogs",
        canonical_rate_field=f"{prefix}_actual_ytd_merchandise_cogs_rate",
        canonical_forecast_revenue_field=f"{prefix}_forecast_merchandise_revenue",
        canonical_forecast_cogs_field=f"{prefix}_forecast_merchandise_cogs",
        source_mapping_version=source.source_mapping_version,
        source_mapping_hash=source.source_mapping_hash,
        product_scope_valid=(source.product_code != "LC" or source.specification == "4-inch"),
        manual_reason_valid=(calculation_source != "MANUAL_OVERRIDE" or legacy or bool(manual_reason.strip())),
    )

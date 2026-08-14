from __future__ import annotations

import math
import uuid
from typing import Any, Mapping, Sequence

from .auth import AccessCodeSessionService
from .dto import PnlDashboardResponse
from .errors import ApiErrorCode, BffError
from .gateway import BffApplicationGateway, GatewayTransientError


PNL_REQUIRED_CODES = {"revenue", "cogs", "gross_profit", "operating_profit"}
PRODUCT_CODES = {"SW", "BW", "LC", "FS", "신사업"}
EFFECT_CODES = {
    "sales_quantity", "sales_mix", "sales_price", "sales_fx", "tariff",
    "material_total", "manufacturing_realized", "inventory_timing", "sga_variable", "sga_fixed",
}


class PnlDashboardService:
    """Read the strict published default Result/default Comparison snapshot."""

    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: BffApplicationGateway,
        *,
        supported_result_schema_versions: Sequence[str],
    ) -> None:
        versions = tuple(str(value).strip() for value in supported_result_schema_versions)
        if not versions or any(not value for value in versions):
            raise ValueError("at least one supported result schema version is required")
        self._sessions = sessions
        self._gateway = gateway
        self._supported_versions = versions

    def viewer_read(self, session_id: str) -> PnlDashboardResponse:
        self._sessions.require_viewer(session_id)
        try:
            row = self._gateway.get_viewer_pnl_dashboard(
                supported_result_schema_versions=self._supported_versions,
            )
        except GatewayTransientError as exc:
            raise BffError(
                ApiErrorCode.TRANSIENT_SYSTEM_ERROR,
                "P&L dashboard is temporarily unavailable",
            ) from exc
        if row is None:
            raise BffError(ApiErrorCode.RESULT_NOT_AVAILABLE, "P&L dashboard not available")
        return build_pnl_dashboard_response(row, self._supported_versions)


def build_pnl_dashboard_response(
    row: Mapping[str, Any], supported_versions: Sequence[str]
) -> PnlDashboardResponse:
    result_id = _uuid(row.get("result_id"))
    job_id = _uuid(row.get("job_id"))
    baseline_id = _uuid(row.get("baseline_model_id"))
    comparison_id = _uuid(row.get("comparison_model_id"))
    if baseline_id == comparison_id:
        raise _integrity()
    schema = _text(row.get("result_schema_version"))
    if schema not in supported_versions:
        raise _integrity()
    dashboard = _mapping(row.get("dashboard"))
    if dashboard.get("snapshot_version") != "1":
        raise _integrity()
    identity = dict(_mapping(dashboard.get("identity")))
    if _uuid(identity.get("baseline_model_id")) != baseline_id or _uuid(
        identity.get("comparison_model_id")
    ) != comparison_id:
        raise _integrity()
    _text(identity.get("baseline_model_name")); _text(identity.get("comparison_model_name"))
    _integer(identity.get("model_year"))
    months = _integer_list(identity.get("available_months"))
    if not months or months != list(range(months[0], months[-1] + 1)):
        raise _integrity()
    if (
        _integer(identity.get("start_month")) != months[0]
        or _integer(identity.get("end_month")) != months[-1]
        or any(month < 1 or month > 12 for month in months)
    ):
        raise _integrity()
    actual_months = _integer_list(identity.get("actual_months"))
    if actual_months != months[:len(actual_months)]:
        raise _integrity()
    actual_through = identity.get("actual_through_month")
    if (actual_through is None) != (not actual_months):
        raise _integrity()
    if actual_through is not None and _integer(actual_through) != actual_months[-1]:
        raise _integrity()

    kpis = dict(_mapping(dashboard.get("kpis")))
    if _integer(kpis.get("latest_month")) != months[-1]:
        raise _integrity()
    for code in ("revenue", "gross_profit", "operating_profit"):
        metric = _mapping(kpis.get(code))
        _financial(_mapping(metric.get("latest")), expected_code=code)
        _financial(_mapping(metric.get("period")), expected_code=code)
    for key in ("latest_operating_margin", "period_operating_margin"):
        margin = _mapping(kpis.get(key))
        baseline = _nullable_number(margin.get("baseline"))
        comparison = _nullable_number(margin.get("comparison"))
        delta = _nullable_number(margin.get("delta_percentage_points"))
        if baseline is None or comparison is None:
            if delta is not None:
                raise _integrity()
        elif delta is None or not _close(comparison - baseline, delta):
            raise _integrity()
    _validate_margin(
        _mapping(kpis.get("latest_operating_margin")),
        _mapping(_mapping(kpis.get("operating_profit")).get("latest")),
        _mapping(_mapping(kpis.get("revenue")).get("latest")),
    )
    _validate_margin(
        _mapping(kpis.get("period_operating_margin")),
        _mapping(_mapping(kpis.get("operating_profit")).get("period")),
        _mapping(_mapping(kpis.get("revenue")).get("period")),
    )

    monthly = tuple(dict(value) for value in _mapping_rows(dashboard.get("monthly_series")))
    if [_integer(value.get("month")) for value in monthly] != months:
        raise _integrity()
    for value in monthly:
        period_type = value.get("comparison_period_type")
        if period_type not in {"실적", "추정", "계획", None}:
            raise _integrity()
        for code in ("revenue", "cogs", "gross_profit", "operating_profit"):
            _financial(_mapping(value.get(code)), expected_code=code)
        _nullable_number(value.get("baseline_operating_margin"))
        _nullable_number(value.get("comparison_operating_margin"))
        _validate_ratio(value.get("baseline_operating_margin"),
                        _number(_mapping(value.get("operating_profit")).get("baseline")),
                        _number(_mapping(value.get("revenue")).get("baseline")))
        _validate_ratio(value.get("comparison_operating_margin"),
                        _number(_mapping(value.get("operating_profit")).get("comparison")),
                        _number(_mapping(value.get("revenue")).get("comparison")))
        for side in ("baseline", "comparison"):
            if not _close(
                _number(_mapping(value.get("revenue")).get(side))
                - _number(_mapping(value.get("cogs")).get(side)),
                _number(_mapping(value.get("gross_profit")).get(side)),
            ):
                raise _integrity()

    statement = tuple(dict(value) for value in _mapping_rows(dashboard.get("pnl_statement")))
    codes = {_text(value.get("code")) for value in statement}
    if not PNL_REQUIRED_CODES.issubset(codes):
        raise _integrity()
    for value in statement:
        _financial(value)
    statement_by_code = {_text(value.get("code")): value for value in statement}
    if len(statement_by_code) != len(statement):
        raise _integrity()
    _pnl_identity(statement_by_code)
    comparison_revenue = _number(statement_by_code["revenue"].get("comparison"))
    for value in statement:
        _validate_ratio(value.get("comparison_ratio_to_revenue"),
                        _number(value.get("comparison")), comparison_revenue)

    manufacturing = dict(_mapping(dashboard.get("manufacturing")))
    for value in _mapping_rows(manufacturing.get("cost_lines")):
        _financial(value)
        _validate_ratio(value.get("comparison_ratio_to_revenue"),
                        _number(value.get("comparison")), comparison_revenue)
    material = _mapping(manufacturing.get("material_components"))
    if material.get("jpy_fx_unit") != "KRW/JPY" or material.get("mcm_is_separate_effect") is not False:
        raise _integrity()
    for key in ("nonwoven_price_ex_fx", "nonwoven_jpy", "materials_ex_nonwoven", "total"):
        _nullable_number(material.get(key))
    components = tuple(material.get(key) for key in (
        "nonwoven_price_ex_fx", "nonwoven_jpy", "materials_ex_nonwoven"
    ))
    if material.get("total") is not None and all(value is not None for value in components):
        if not _close(sum(_number(value) for value in components), _number(material.get("total"))):
            raise _integrity()
    policy = _mapping(manufacturing.get("fixed_cost_policy"))
    if (
        policy.get("manufacturing_effect_includes_variable_and_fixed") is not True
        or policy.get("fixed_manufacturing_is_not_a_separate_top_level_effect") is not True
    ):
        raise _integrity()
    for value in _mapping_rows(manufacturing.get("accounts")):
        _account(value, manufacturing=True)

    sga = dict(_mapping(dashboard.get("sga")))
    if _text(sga.get("fixed_scope")) != "fixed SG&A accounts excluding customer freight and tariff":
        raise _integrity()
    for value in _mapping_rows(sga.get("accounts")):
        _account(value, manufacturing=False)

    groups = tuple(dict(value) for value in _mapping_rows(dashboard.get("product_groups")))
    seen: set[str] = set()
    for value in groups:
        code = _text(value.get("code"))
        if code not in PRODUCT_CODES or code in seen:
            raise _integrity()
        seen.add(code)
        if code == "LC" and value.get("display_name") != "4인치 LC":
            raise _integrity()
        if value.get("quantity_unit") != ("m" if code == "FS" else "PCS"):
            raise _integrity()
        for key in (
            "baseline_quantity", "comparison_quantity", "baseline_revenue",
            "comparison_revenue", "revenue_delta", "baseline_cogs",
            "comparison_cogs", "baseline_gross_profit", "comparison_gross_profit",
        ):
            _number(value.get(key))
        if not _close(
            _number(value.get("comparison_revenue")) - _number(value.get("baseline_revenue")),
            _number(value.get("revenue_delta")),
        ):
            raise _integrity()
        if not _close(
            _number(value.get("baseline_revenue")) - _number(value.get("baseline_cogs")),
            _number(value.get("baseline_gross_profit")),
        ) or not _close(
            _number(value.get("comparison_revenue")) - _number(value.get("comparison_cogs")),
            _number(value.get("comparison_gross_profit")),
        ):
            raise _integrity()

    facts = dict(_mapping(dashboard.get("key_facts")))
    effects = _mapping_rows(facts.get("effects"))
    effect_codes = {_text(value.get("code")) for value in effects}
    if effect_codes != EFFECT_CODES or len(effect_codes) != len(effects):
        raise _integrity()
    if tuple(effects) != tuple(sorted(effects, key=lambda row: (-abs(_number(row.get("profit_effect"))), _text(row.get("code"))))):
        raise _integrity()
    for value in effects:
        _text(value.get("code")); _text(value.get("label")); _number(value.get("profit_effect"))
    effects_total = _number(facts.get("effects_total"))
    residual = _number(facts.get("residual"))
    op_delta = _number(facts.get("operating_profit_delta"))
    if (not _close(sum(_number(value.get("profit_effect")) for value in effects), effects_total)
            or not _close(effects_total + residual, op_delta)
            or not isinstance(facts.get("reconciled"), bool)):
        raise _integrity()

    return PnlDashboardResponse(
        result_id=result_id,
        job_id=job_id,
        identity=identity,
        kpis=kpis,
        monthly_series=monthly,
        pnl_statement=statement,
        manufacturing=manufacturing,
        sga=sga,
        product_groups=groups,
        key_facts=facts,
        result_schema_version=schema,
        completed_at=_text(row.get("completed_at")),
        published_at=_text(row.get("published_at")),
    )


def _financial(value: Mapping[str, Any], expected_code: str | None = None) -> None:
    code = _text(value.get("code"))
    if expected_code is not None and code != expected_code:
        raise _integrity()
    _text(value.get("label"))
    baseline = _number(value.get("baseline"))
    comparison = _number(value.get("comparison"))
    delta = _number(value.get("delta"))
    if not _close(comparison - baseline, delta):
        raise _integrity()
    _nullable_number(value.get("comparison_ratio_to_revenue"))


def _account(value: Mapping[str, Any], *, manufacturing: bool) -> None:
    _text(value.get("account")); classification = _text(value.get("classification"))
    baseline = _number(value.get("baseline")); comparison = _number(value.get("comparison"))
    if not _close(comparison - baseline, _number(value.get("delta"))):
        raise _integrity()
    effect = _nullable_number(value.get("profit_effect"))
    if not manufacturing and classification in {"transport"} and effect not in (0.0, None):
        raise _integrity()
    for key in ("inventory_realization_rate", "activity_effect", "unit_effect", "fixed_effect"):
        _nullable_number(value.get(key))


def _pnl_identity(rows: Mapping[str, Mapping[str, Any]]) -> None:
    for side in ("baseline", "comparison"):
        if not _close(
            _number(rows["revenue"].get(side)) - _number(rows["cogs"].get(side)),
            _number(rows["gross_profit"].get(side)),
        ):
            raise _integrity()
        if "selling_expense" in rows and "general_admin" in rows:
            if not _close(
                _number(rows["gross_profit"].get(side))
                - _number(rows["selling_expense"].get(side))
                - _number(rows["general_admin"].get(side)),
                _number(rows["operating_profit"].get(side)),
            ):
                raise _integrity()


def _validate_margin(
    margin: Mapping[str, Any], profit: Mapping[str, Any], revenue: Mapping[str, Any]
) -> None:
    _validate_ratio(margin.get("baseline"), _number(profit.get("baseline")),
                    _number(revenue.get("baseline")))
    _validate_ratio(margin.get("comparison"), _number(profit.get("comparison")),
                    _number(revenue.get("comparison")))


def _validate_ratio(value: Any, numerator: float, denominator: float) -> None:
    if denominator == 0:
        if value is not None:
            raise _integrity()
        return
    if value is None or not _close(_number(value), numerator / denominator * 100.0):
        raise _integrity()


def _mapping_rows(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(row, Mapping) for row in value):
        raise _integrity()
    return tuple(value)  # type: ignore[return-value]


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _integrity()
    return value


def _integer_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        raise _integrity()
    return [_integer(item) for item in value]


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _integrity()
    return value


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _integrity()
    number = float(value)
    if not math.isfinite(number):
        raise _integrity()
    return number


def _nullable_number(value: Any) -> float | None:
    return None if value is None else _number(value)


def _text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise _integrity()
    return text


def _uuid(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise _integrity() from exc


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= max(1.0, abs(left), abs(right)) * 1e-9


def _integrity() -> BffError:
    return BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "P&L dashboard payload is invalid")

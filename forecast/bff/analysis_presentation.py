from __future__ import annotations

import math
import uuid
from typing import Any, Mapping, Sequence

from ..provenance import ResultProvenance, SHA256_PATTERN
from .auth import AccessCodeSessionService
from .dto import (
    AnalysisActivityResponse,
    AnalysisDrilldownResponse,
    AnalysisDrilldownRowResponse,
    AnalysisExecutiveSummaryResponse,
    AnalysisPresentationEffectResponse,
    AnalysisPresentationIdentityResponse,
    AnalysisPresentationKpiResponse,
    AnalysisPresentationResponse,
    AnalysisProductGroupResponse,
    AnalysisResidualResponse,
)
from .errors import ApiErrorCode, BffError
from .gateway import BffApplicationGateway, GatewayTransientError


EFFECT_ORDER = (
    "sales_quantity",
    "sales_mix",
    "sales_price",
    "sales_fx",
    "material_total",
    "manufacturing_realized",
    "inventory_timing",
    "sga_variable",
    "sga_fixed",
    "tariff",
)

MANUFACTURING_VARIABLE_ACCOUNTS = (
    "수도광열비",
    "소모품비",
    "원자재운반비",
    "외주가공비",
)

EFFECT_METADATA = {
    "sales_quantity": ("판매수량", "INTERNAL", "Base 판매단가·매출총이익률 기준의 판매수량 효과"),
    "sales_mix": ("제품 Mix", "INTERNAL", "제품군 기준의 판매 Mix 효과"),
    "sales_price": ("판매단가", "INTERNAL", "표시 판매단가와 고객배송 운반비 효과를 정확히 한 번 포함"),
    "sales_fx": ("매출환율", "EXTERNAL", "KRW/USD 매출환율 효과"),
    "material_total": ("원재료", "COST", "부직포 가격·JPY 환율·기타 원부재료의 결정론적 합계"),
    "manufacturing_realized": ("제조경비", "COST", "전공정/후공정 제조경비 발생효과; 재고실현율 multiplier 미적용"),
    "inventory_timing": ("재고·원가 반영시차", "COST", "Gross Inventory Timing - Core Manufactured COGS overlap"),
    "sga_variable": ("변동 판관비", "COST", "고객배송 운반비와 관세를 제외한 변동 판관비"),
    "sga_fixed": ("고정 판관비", "COST", "고객배송 운반비와 관세를 제외한 고정 판관비"),
    "tariff": ("관세", "EXTERNAL", "별도 관세 효과"),
}

PRODUCT_ORDER = ("SW", "BW", "LC", "FS", "신사업")
PRODUCT_LABELS = {
    "SW": "SW",
    "BW": "BW",
    "LC": "4인치 LC",
    "FS": "FS",
    "신사업": "신사업",
}
RESIDUAL_CLASSIFICATIONS = {
    "VALIDATION_ARTIFACT",
    "FORMULA_EVALUATOR_GAP",
    "MAPPING_GAP",
    "ENGINE_BUG",
    "INTENTIONAL_SCOPE_GAP",
    "INVENTORY_TIMING",
    "BUSINESS_POLICY_GAP",
    "UNEXPLAINED",
}
RESIDUAL_LABELS = {
    "VALIDATION_ARTIFACT": "검증 절차 영향",
    "FORMULA_EVALUATOR_GAP": "수식 평가기 범위 차이",
    "MAPPING_GAP": "Mapping 미해결",
    "ENGINE_BUG": "Engine 오류 조사 필요",
    "INTENTIONAL_SCOPE_GAP": "V1 의도적 범위 제외",
    "INVENTORY_TIMING": "재고·원가 반영시차",
    "BUSINESS_POLICY_GAP": "업무정책 미확정",
    "UNEXPLAINED": "미설명 잔여차이",
}


class AnalysisPresentationService:
    """Map one stored deterministic Result into a narrow display contract."""

    def __init__(
        self,
        sessions: AccessCodeSessionService,
        gateway: BffApplicationGateway,
        provenance: ResultProvenance,
        *,
        supported_result_schema_versions: Sequence[str],
    ) -> None:
        versions = tuple(str(value).strip() for value in supported_result_schema_versions)
        if not versions or any(not value for value in versions):
            raise ValueError("at least one supported result schema version is required")
        self._sessions = sessions
        self._gateway = gateway
        self._provenance = provenance
        self._supported_versions = versions

    def admin_read(self, session_id: str, result_id: str) -> AnalysisPresentationResponse:
        self._sessions.require_admin(session_id)
        normalized = _uuid(result_id)
        try:
            row = self._gateway.get_admin_analysis_presentation(
                normalized,
                supported_result_schema_versions=self._supported_versions,
            )
        except GatewayTransientError as exc:
            raise _transient() from exc
        if row is None:
            raise BffError(ApiErrorCode.RESULT_NOT_FOUND, "Result not found")
        return build_analysis_presentation(
            normalized,
            row,
            self._provenance,
            self._supported_versions,
        )

    def viewer_read(self, session_id: str, result_id: str) -> AnalysisPresentationResponse:
        self._sessions.require_viewer(session_id)
        normalized = _uuid(result_id)
        try:
            row = self._gateway.get_viewer_analysis_presentation(
                normalized,
                supported_result_schema_versions=self._supported_versions,
            )
        except GatewayTransientError as exc:
            raise _transient() from exc
        if row is None:
            raise BffError(ApiErrorCode.RESULT_NOT_AVAILABLE, "Result not available")
        response = build_analysis_presentation(
            normalized,
            row,
            self._provenance,
            self._supported_versions,
        )
        try:
            available = self._gateway.validate_result_availability(
                normalized,
                supported_result_schema_versions=self._supported_versions,
            )
        except GatewayTransientError as exc:
            raise _transient() from exc
        if not available:
            raise BffError(ApiErrorCode.RESULT_NOT_AVAILABLE, "Result not available")
        return response


def build_analysis_presentation(
    result_id: str,
    row: Mapping[str, Any],
    provenance: ResultProvenance,
    supported_versions: Sequence[str],
) -> AnalysisPresentationResponse:
    values = _validated_row(result_id, row, provenance, supported_versions)
    payload = _mapping(values["result_payload"])
    if str(payload.get("payload_schema_version") or "") != values["result_schema_version"]:
        raise _integrity()
    result = _mapping(payload.get("comparison_result"))
    analysis_view = _mapping(payload.get("analysis_view"))
    _mapping(payload.get("fact_pack"))
    request = _mapping(values["analysis_request"])

    baseline_id = values["baseline_model_id"]
    comparison_id = values["comparison_model_id"]
    if _model_id(result.get("baseline")) != baseline_id or _model_id(result.get("comparison")) != comparison_id:
        raise _integrity()

    start_month = _integer(request.get("start_month"))
    end_month = _integer(request.get("end_month"))
    if not 1 <= start_month <= end_month <= 12:
        raise _integrity()
    baseline_fx = _positive(request.get("baseline_sales_fx"))
    comparison_fx = _positive(request.get("comparison_sales_fx"))
    period = _mapping(result.get("period"))
    months = period.get("months")
    if not isinstance(months, (list, tuple)) or tuple(_integer(value) for value in months) != tuple(
        range(start_month, end_month + 1)
    ):
        raise _integrity()

    pnl = _indexed_rows(result.get("pnl"), "code")
    revenue = _financial_row(pnl.get("revenue"))
    operating_profit = _financial_row(pnl.get("operating_profit"))
    op_delta = _number(result.get("operating_profit_delta"))
    if not _close(operating_profit[2], op_delta):
        raise _integrity()

    source_effects = _indexed_rows(result.get("effects"), "code")
    if set(source_effects) != set(EFFECT_ORDER):
        raise _integrity()
    amounts = {code: _number(source_effects[code].get("profit_effect")) for code in EFFECT_ORDER}
    effects_total = _number(result.get("effects_total"))
    residual_amount = _number(result.get("residual"))
    if not _close(sum(amounts.values()), effects_total) or not _close(
        effects_total + residual_amount,
        op_delta,
    ):
        raise _integrity()

    sales = _mapping(result.get("sales_analysis"))
    sales_totals = _mapping(sales.get("totals"))
    sales_rows = _sequence_of_mappings(sales.get("rows"))
    if not _close(_positive(sales.get("baseline_fx_krw_per_usd")), baseline_fx) or not _close(
        _positive(sales.get("comparison_fx_krw_per_usd")), comparison_fx
    ):
        raise _integrity()
    _validate_sales_effects(amounts, sales_totals)
    material = _mapping(result.get("material_analysis"))
    inventory = _mapping(result.get("inventory_analysis"))
    if (
        inventory.get("source_validation_status") != "PASS"
        or inventory.get("scope_validation_status") != "PASS"
    ):
        raise _integrity()
    manufacturing_accounts = _sequence_of_mappings(result.get("manufacturing_accounts"))
    sga_accounts = _sequence_of_mappings(result.get("sga_accounts"))
    _validate_cost_effects(
        amounts, material, inventory, manufacturing_accounts, sga_accounts
    )

    effects = tuple(
        _effect_response(
            code,
            amounts[code],
            sales_rows=sales_rows,
            sales_totals=sales_totals,
            material=material,
            inventory=inventory,
            manufacturing_accounts=manufacturing_accounts,
            sga_accounts=sga_accounts,
        )
        for code in EFFECT_ORDER
    )

    residual_classification = str(result.get("residual_classification") or "UNEXPLAINED")
    if residual_classification not in RESIDUAL_CLASSIFICATIONS:
        raise _integrity()
    residual = AnalysisResidualResponse(
        amount=residual_amount,
        classification=residual_classification,
        display_label=RESIDUAL_LABELS[residual_classification],
    )
    product_groups = _product_groups(sales_rows)
    activities = _activities(analysis_view)
    positives = tuple(sorted(
        (effect for effect in effects if effect.profit_effect > 0),
        key=lambda effect: (-effect.profit_effect, EFFECT_ORDER.index(effect.code)),
    )[:3])
    negatives = tuple(sorted(
        (effect for effect in effects if effect.profit_effect < 0),
        key=lambda effect: (effect.profit_effect, EFFECT_ORDER.index(effect.code)),
    )[:3])

    identity = AnalysisPresentationIdentityResponse(
        result_id=result_id,
        job_id=values["job_id"],
        baseline_model_id=baseline_id,
        comparison_model_id=comparison_id,
        baseline_model_name=values["baseline_model_name"],
        comparison_model_name=values["comparison_model_name"],
        start_month=start_month,
        end_month=end_month,
        baseline_sales_fx=baseline_fx,
        comparison_sales_fx=comparison_fx,
        result_schema_version=values["result_schema_version"],
        completed_at=values["completed_at"],
        is_published=values["is_published"],
        is_default=values["is_default"],
        published_at=values["published_at"],
    )
    kpis = AnalysisPresentationKpiResponse(
        baseline_revenue=revenue[0],
        comparison_revenue=revenue[1],
        revenue_delta=revenue[2],
        baseline_operating_profit=operating_profit[0],
        comparison_operating_profit=operating_profit[1],
        operating_profit_delta=op_delta,
        effects_total=effects_total,
        residual=residual_amount,
    )
    return AnalysisPresentationResponse(
        identity=identity,
        kpis=kpis,
        effects=effects,
        residual=residual,
        product_groups=product_groups,
        manufacturing_activities=activities,
        executive_summary=AnalysisExecutiveSummaryResponse(
            operating_profit_delta=op_delta,
            top_positive_effects=positives,
            top_negative_effects=negatives,
            residual=residual,
        ),
    )


def _validated_row(
    result_id: str,
    row: Mapping[str, Any],
    provenance: ResultProvenance,
    supported_versions: Sequence[str],
) -> dict[str, Any]:
    required = (
        "result_id", "job_id", "result_payload", "analysis_request",
        "baseline_model_id", "comparison_model_id", "baseline_model_name",
        "comparison_model_name", "baseline_workbook_sha256",
        "comparison_workbook_sha256", "engine_version", "mapping_version",
        "mapping_hash", "result_schema_version", "completed_at", "created_at",
        "is_published", "is_default",
    )
    if any(row.get(key) is None for key in required):
        raise _integrity()
    values = dict(row)
    for key in ("result_id", "job_id", "baseline_model_id", "comparison_model_id"):
        values[key] = _integrity_uuid(values[key])
    if values["result_id"] != result_id or values["baseline_model_id"] == values["comparison_model_id"]:
        raise _integrity()
    for key in ("baseline_workbook_sha256", "comparison_workbook_sha256", "mapping_hash"):
        if not SHA256_PATTERN.fullmatch(str(values[key])):
            raise _integrity()
    if (
        str(values["engine_version"]) != provenance.engine_version
        or str(values["mapping_version"]) != provenance.mapping_version
        or str(values["mapping_hash"]) != provenance.mapping_hash
        or str(values["result_schema_version"]) not in supported_versions
    ):
        raise _integrity()
    for key in ("baseline_model_name", "comparison_model_name", "completed_at", "created_at"):
        values[key] = str(values[key]).strip()
        if not values[key]:
            raise _integrity()
    values["result_schema_version"] = str(values["result_schema_version"])
    if not isinstance(values["is_published"], bool) or not isinstance(values["is_default"], bool):
        raise _integrity()
    values["published_at"] = str(values["published_at"]) if values.get("published_at") else None
    return values


def _effect_response(
    code: str,
    amount: float,
    *,
    sales_rows: tuple[Mapping[str, Any], ...],
    sales_totals: Mapping[str, Any],
    material: Mapping[str, Any],
    inventory: Mapping[str, Any],
    manufacturing_accounts: tuple[Mapping[str, Any], ...],
    sga_accounts: tuple[Mapping[str, Any], ...],
) -> AnalysisPresentationEffectResponse:
    label, category, description = EFFECT_METADATA[code]
    drilldown = _drilldown(
        code,
        sales_rows=sales_rows,
        sales_totals=sales_totals,
        material=material,
        inventory=inventory,
        manufacturing_accounts=manufacturing_accounts,
        sga_accounts=sga_accounts,
    )
    return AnalysisPresentationEffectResponse(code, label, category, amount, description, drilldown)


def _drilldown(
    code: str,
    *,
    sales_rows: tuple[Mapping[str, Any], ...],
    sales_totals: Mapping[str, Any],
    material: Mapping[str, Any],
    inventory: Mapping[str, Any],
    manufacturing_accounts: tuple[Mapping[str, Any], ...],
    sga_accounts: tuple[Mapping[str, Any], ...],
) -> AnalysisDrilldownResponse:
    if code == "sales_mix":
        return AnalysisDrilldownResponse(
            "unavailable", False, (), "제품군 Mix 총액의 persisted 세부행은 V1 Result에 없습니다."
        )
    if code in {"sales_quantity", "sales_price", "sales_fx"}:
        field = {
            "sales_quantity": "quantity_effect",
            "sales_price": "pure_price_effect",
            "sales_fx": "sales_fx_effect",
        }[code]
        rows = [
            AnalysisDrilldownRowResponse(
                row_id=f"{code}:{group}",
                label=PRODUCT_LABELS[group],
                unit="m" if group == "FS" else "PCS",
                baseline=_number(source.get("baseline_quantity")),
                comparison=_number(source.get("comparison_quantity")),
                delta=_number(source.get("quantity_delta")),
                profit_effect=_number(source.get(field)),
                note="persisted sales_analysis 제품군 행",
            )
            for source in sales_rows
            for group in [str(source.get("product_group"))]
            if group in PRODUCT_LABELS
        ]
        if code == "sales_price":
            rows.append(AnalysisDrilldownRowResponse(
                row_id="sales_price:customer_delivery_transport",
                label="고객배송 운반비",
                unit="KRW",
                baseline=_number(sales_totals.get("baseline_transport_ex_tariff")),
                comparison=_number(sales_totals.get("comparison_transport_ex_tariff")),
                delta=(
                    _number(sales_totals.get("comparison_transport_ex_tariff"))
                    - _number(sales_totals.get("baseline_transport_ex_tariff"))
                ),
                profit_effect=_number(sales_totals.get("transport_effect")),
                note="수량/원단위 분해 없이 판매단가 Effect에 한 번 반영",
            ))
        return AnalysisDrilldownResponse("sales", bool(rows), tuple(rows), None if rows else "세부행 없음")
    if code == "material_total":
        component_specs = (
            ("nonwoven_price_ex_fx", "부직포 가격효과(환율 제외)"),
            ("nonwoven_jpy", "부직포 JPY 환율효과"),
            ("materials_ex_nonwoven", "기타 원부재료"),
        )
        rows = tuple(
            AnalysisDrilldownRowResponse(
                row_id=f"material:{key}",
                label=label,
                unit="KRW",
                baseline=None,
                comparison=None,
                delta=None,
                profit_effect=_number(material.get(key)),
                note="MCM 독립효과와 수율/사용량 효과를 생성하지 않음",
            )
            for key, label in component_specs
            if material.get(key) is not None
        )
        return AnalysisDrilldownResponse("material", bool(rows), rows, None if rows else "원재료 세부 payload 없음")
    if code == "manufacturing_realized":
        rows = tuple(_account_row("manufacturing", source, "final_profit_effect") for source in manufacturing_accounts)
        return AnalysisDrilldownResponse("manufacturing", bool(rows), rows, None if rows else "제조경비 계정 세부 payload 없음")
    if code == "inventory_timing":
        rows = (
            AnalysisDrilldownRowResponse(
                "inventory:manufactured_cogs",
                "제조품 매출원가 Effect",
                "KRW",
                _number(inventory.get("base_manufactured_cogs")),
                _number(inventory.get("comparison_manufactured_cogs")),
                (
                    _number(inventory.get("comparison_manufactured_cogs"))
                    - _number(inventory.get("base_manufactured_cogs"))
                ),
                _number(inventory.get("manufactured_cogs_effect")),
                "Base Manufactured COGS - Comparison Manufactured COGS",
            ),
            AnalysisDrilldownRowResponse(
                "inventory:current_manufacturing_cost",
                "당기투입제조원가 Effect",
                "KRW",
                _number(inventory.get("base_current_manufacturing_cost")),
                _number(inventory.get("comparison_current_manufacturing_cost")),
                (
                    _number(inventory.get("comparison_current_manufacturing_cost"))
                    - _number(inventory.get("base_current_manufacturing_cost"))
                ),
                _number(inventory.get("current_manufacturing_cost_effect")),
                "Base Current Manufacturing Cost - Comparison Current Manufacturing Cost",
            ),
        )
        return AnalysisDrilldownResponse("inventory", True, rows)
    if code in {"sga_variable", "sga_fixed"}:
        classification = "variable" if code == "sga_variable" else "fixed"
        rows = tuple(
            _account_row("sga", source, "profit_effect")
            for source in sga_accounts
            if source.get("classification") == classification
        )
        return AnalysisDrilldownResponse("sga", bool(rows), rows, None if rows else "판관비 계정 세부 payload 없음")
    if code == "tariff":
        rows = tuple(
            _account_row("tariff", source, "profit_effect")
            for source in sga_accounts
            if source.get("classification") == "tariff" and _number(source.get("profit_effect")) != 0
        )
        if not rows:
            rows = (AnalysisDrilldownRowResponse(
                "tariff:direct", "관세", "KRW", None, None, None,
                _number(sales_totals.get("tariff_effect")), "persisted sales_analysis 관세 총액",
                "selling",
            ),)
        return AnalysisDrilldownResponse("tariff", True, rows)
    raise _integrity()


def _account_row(prefix: str, source: Mapping[str, Any], effect_key: str) -> AnalysisDrilldownRowResponse:
    account = str(source.get("account") or "").strip()
    if not account:
        raise _integrity()
    baseline = _number(source.get("baseline_amount"))
    comparison = _number(source.get("comparison_amount"))
    section = (
        "manufacturing"
        if prefix == "manufacturing"
        else "selling"
        if prefix == "tariff" or source.get("section") == "판매비"
        else "general_admin"
        if source.get("section") == "일반관리비"
        else None
    )
    return AnalysisDrilldownRowResponse(
        row_id=f"{prefix}:{source.get('row')}:{account}",
        label=account,
        unit="KRW",
        baseline=baseline,
        comparison=comparison,
        delta=_number(source.get("delta")),
        profit_effect=_optional_number(source.get(effect_key)),
        note=str(source.get("calculation_status") or source.get("classification") or ""),
        section=section,
    )


def _product_groups(rows: tuple[Mapping[str, Any], ...]) -> tuple[AnalysisProductGroupResponse, ...]:
    by_group: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        group = str(row.get("product_group"))
        if group not in PRODUCT_LABELS or group in by_group:
            raise _integrity()
        by_group[group] = row
    return tuple(
        AnalysisProductGroupResponse(
            code=group,
            display_name=PRODUCT_LABELS[group],
            quantity_unit="m" if group == "FS" else "PCS",
            baseline_quantity=_number(by_group[group].get("baseline_quantity")),
            comparison_quantity=_number(by_group[group].get("comparison_quantity")),
            baseline_revenue=_number(by_group[group].get("baseline_amount")),
            comparison_revenue=_number(by_group[group].get("comparison_amount")),
        )
        for group in PRODUCT_ORDER
        if group in by_group
    )


def _activities(analysis_view: Mapping[str, Any]) -> tuple[AnalysisActivityResponse, ...]:
    manufacturing = _mapping(analysis_view.get("manufacturing"))
    rows = _sequence_of_mappings(manufacturing.get("activities"))
    output = []
    for row in rows:
        basis = str(row.get("production_basis") or "")
        unit = str(row.get("unit") or "")
        if (basis == "FS" and unit != "m") or (basis != "FS" and unit != "PCS"):
            raise _integrity()
        baseline = _number(row.get("baseline"))
        comparison = _number(row.get("comparison"))
        delta = _number(row.get("delta"))
        if not _close(comparison - baseline, delta):
            raise _integrity()
        output.append(AnalysisActivityResponse(
            process=str(row.get("process") or ""),
            production_basis=basis,
            unit=unit,
            baseline=baseline,
            comparison=comparison,
            delta=delta,
        ))
    return tuple(output)


def _validate_sales_effects(amounts: Mapping[str, float], totals: Mapping[str, Any]) -> None:
    for code, key in (
        ("sales_quantity", "quantity_effect"),
        ("sales_mix", "mix_effect"),
        ("sales_price", "sales_price_effect"),
        ("sales_fx", "sales_fx_effect"),
        ("tariff", "tariff_effect"),
    ):
        if not _close(amounts[code], _number(totals.get(key))):
            raise _integrity()
    if not _close(_number(totals.get("transport_quantity_effect")), 0.0):
        raise _integrity()
    transport = _number(totals.get("transport_effect"))
    if totals.get("transport_unit_effect") is not None and not _close(
        _number(totals.get("transport_unit_effect")), transport
    ):
        raise _integrity()
    displayed = totals.get("displayed_sales_price_effect")
    if displayed is not None and not _close(_number(displayed) + transport, amounts["sales_price"]):
        raise _integrity()


def _validate_cost_effects(
    amounts: Mapping[str, float],
    material: Mapping[str, Any],
    inventory: Mapping[str, Any],
    manufacturing_accounts: tuple[Mapping[str, Any], ...],
    sga_accounts: tuple[Mapping[str, Any], ...],
) -> None:
    if material.get("total") is not None and not _close(_number(material.get("total")), amounts["material_total"]):
        raise _integrity()
    parts = [material.get(key) for key in (
        "nonwoven_price_ex_fx", "nonwoven_jpy", "materials_ex_nonwoven"
    )]
    if all(value is not None for value in parts) and not _close(
        sum(_number(value) for value in parts), amounts["material_total"]
    ):
        raise _integrity()
    variable_matches = {
        account: [row for row in manufacturing_accounts if row.get("account") == account]
        for account in MANUFACTURING_VARIABLE_ACCOUNTS
    }
    if (
        not manufacturing_accounts
        or any(len(rows) != 1 for rows in variable_matches.values())
        or any(row.get("final_profit_effect") is None for row in manufacturing_accounts)
    ):
        raise _integrity()
    if not _close(
        sum(_number(row.get("final_profit_effect")) for row in manufacturing_accounts),
        amounts["manufacturing_realized"],
    ):
        raise _integrity()
    if not _close(
        _number(inventory.get("inventory_timing_effect")),
        amounts["inventory_timing"],
    ):
        raise _integrity()
    slice5d_numeric_fields = (
        "gross_inventory_timing_effect",
        "core_cogs_quantity_overlap_effect",
        "core_cogs_mix_overlap_effect",
        "core_manufactured_cogs_overlap_effect",
    )
    slice5d_present = any(
        inventory.get(field) is not None for field in slice5d_numeric_fields
    )
    if slice5d_present:
        if any(inventory.get(field) is None for field in slice5d_numeric_fields):
            raise _integrity()
        if (
            inventory.get("core_overlap_policy_status") != "APPLIED_CORE_ONLY"
            or inventory.get("core_overlap_source_validation_status") != "PASS"
            or inventory.get("core_overlap_pool_validation_status") != "PASS"
        ):
            raise _integrity()
        gross_inventory_timing = _number(
            inventory.get("gross_inventory_timing_effect")
        )
    else:
        gross_inventory_timing = (
            _number(inventory.get("manufactured_cogs_effect"))
            - _number(inventory.get("current_manufacturing_cost_effect"))
        )
    raw_core_overlap = inventory.get("core_manufactured_cogs_overlap_effect")
    core_overlap = _number(raw_core_overlap) if raw_core_overlap is not None else 0.0
    if not _close(gross_inventory_timing - core_overlap, amounts["inventory_timing"]):
        raise _integrity()
    if slice5d_present and not _close(
        _number(inventory.get("core_cogs_quantity_overlap_effect"))
        + _number(inventory.get("core_cogs_mix_overlap_effect")),
        core_overlap,
    ):
        raise _integrity()
    for classification, code in (("variable", "sga_variable"), ("fixed", "sga_fixed")):
        if not _close(
            sum(
                _number(row.get("profit_effect"))
                for row in sga_accounts
                if row.get("classification") == classification
            ),
            amounts[code],
        ):
            raise _integrity()
    if any(
        not _close(_number(row.get("profit_effect")), 0.0)
        for row in sga_accounts
        if row.get("classification") == "transport"
    ):
        raise _integrity()


def _financial_row(value: Any) -> tuple[float, float, float]:
    row = _mapping(value)
    baseline = _number(row.get("baseline"))
    comparison = _number(row.get("comparison"))
    delta = _number(row.get("delta"))
    if not _close(comparison - baseline, delta):
        raise _integrity()
    return baseline, comparison, delta


def _indexed_rows(value: Any, key: str) -> dict[str, Mapping[str, Any]]:
    rows = _sequence_of_mappings(value)
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        code = str(row.get(key) or "")
        if not code or code in output:
            raise _integrity()
        output[code] = row
    return output


def _sequence_of_mappings(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise _integrity()
    rows = tuple(value)
    if any(not isinstance(row, Mapping) for row in rows):
        raise _integrity()
    return rows  # type: ignore[return-value]


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _integrity()
    return value


def _model_id(value: Any) -> str:
    return _integrity_uuid(_mapping(value).get("id"))


def _integrity_uuid(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise _integrity() from exc


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _integrity()
    return value


def _positive(value: Any) -> float:
    number = _number(value)
    if number <= 0:
        raise _integrity()
    return number


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _integrity()
    number = float(value)
    if not math.isfinite(number):
        raise _integrity()
    return number


def _optional_number(value: Any) -> float | None:
    return None if value is None else _number(value)


def _close(left: float, right: float) -> bool:
    tolerance = max(1.0, abs(left), abs(right)) * 1e-9
    return abs(left - right) <= tolerance


def _uuid(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BffError(
            ApiErrorCode.VALIDATION_ERROR,
            "Request identifier is invalid",
            field_errors={"result_id": "must be a UUID"},
        ) from exc


def _integrity() -> BffError:
    return BffError(ApiErrorCode.INPUT_INTEGRITY_MISMATCH, "Analysis presentation payload is invalid")


def _transient() -> BffError:
    return BffError(ApiErrorCode.TRANSIENT_SYSTEM_ERROR, "Analysis presentation is temporarily unavailable")

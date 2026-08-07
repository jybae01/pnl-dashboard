from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable


MONEY_SCALE = 1_000_000


def _record_dict(item: Any) -> dict[str, Any]:
    if is_dataclass(item):
        return asdict(item)
    if isinstance(item, dict):
        return dict(item)
    return {"value": item}


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _money_million(value: Any) -> float:
    return round(_number(value) / MONEY_SCALE, 3)


def _compact_effects(rows: Iterable[Any]) -> list[dict[str, Any]]:
    output = []
    for source in rows:
        item = _record_dict(source)
        output.append({
            "code": item.get("code", ""),
            "label": item.get("factor") or item.get("label") or item.get("item") or item.get("code", ""),
            "baseline_million_krw": _money_million(item.get("baseline")),
            "comparison_million_krw": _money_million(item.get("comparison")),
            "delta_million_krw": _money_million(item.get("delta")),
            "profit_effect_million_krw": _money_million(item.get("profit_effect")),
        })
    return output


def _compact_sales_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    output = []
    for source in rows:
        item = _record_dict(source)
        output.append({
            "product_group": item.get("product_group", ""),
            "baseline_quantity": _number(item.get("baseline_quantity")),
            "comparison_quantity": _number(item.get("comparison_quantity")),
            "quantity_delta": _number(item.get("comparison_quantity")) - _number(item.get("baseline_quantity")),
            "baseline_amount_million_krw": _money_million(item.get("baseline_amount")),
            "comparison_amount_million_krw": _money_million(item.get("comparison_amount")),
            "baseline_gross_margin_rate": _number(item.get("baseline_gross_margin_rate")),
            "quantity_effect_million_krw": _money_million(item.get("quantity_effect")),
            "pure_price_effect_million_krw": _money_million(item.get("pure_price_effect")),
            "sales_fx_effect_million_krw": _money_million(item.get("sales_fx_effect")),
            "total_sales_effect_million_krw": _money_million(item.get("total_sales_effect")),
        })
    return output


def _compact_production(rows: Iterable[Any]) -> list[dict[str, Any]]:
    output = []
    for source in rows:
        item = _record_dict(source)
        output.append({
            "code": item.get("code", ""),
            "label": item.get("label") or item.get("item") or item.get("code", ""),
            "baseline": _number(item.get("baseline")),
            "comparison": _number(item.get("comparison")),
            "delta": _number(item.get("delta")),
        })
    return output


def _top_effects(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: abs(_number(row.get("profit_effect_million_krw"))),
        reverse=True,
    )[:limit]


def analysis_signature(result: dict[str, Any]) -> str:
    return "__".join([
        str(result.get("baseline", {}).get("id", "base")),
        str(result.get("comparison", {}).get("id", "comparison")),
        str(result.get("period", {}).get("key", "period")),
    ])


def build_fact_pack(
    result: dict[str, Any],
    *,
    sales_rows: Iterable[Any] = (),
    sales_totals: dict[str, Any] | None = None,
    baseline_sales_fx: float | None = None,
    comparison_sales_fx: float | None = None,
    business_notes: str = "",
) -> dict[str, Any]:
    """Build the only data handed to ChatGPT for interpretation.

    MCM data is deliberately omitted. It is neither a standalone bridge effect nor
    a management cause in V1. Every amount remains a deterministic engine result.
    """
    sales_totals = sales_totals or {}
    effects = _compact_effects(result.get("effects", []))
    cost_rows = _compact_effects(result.get("cost_summary", []))

    material_codes = {"raw_material", "customs_refund"}
    manufacturing_codes = {"labor", "outsourcing", "other_processing", "processing_total", "manufacturing_expense"}
    sga_codes = {"selling_expense", "general_admin", "sga_total", "tariff"}

    return {
        "comparison": {
            "baseline": result.get("baseline", {}),
            "comparison": result.get("comparison", {}),
            "period": result.get("period", {}),
            "delta_definition": "comparison - baseline",
            "profit_effect_sign": "+ means operating-profit improvement; - means deterioration",
        },
        "pnl": {
            "operating_profit_delta_million_krw": _money_million(result.get("operating_profit_delta")),
            "effects_total_million_krw": _money_million(result.get("effects_total")),
            "residual_million_krw": _money_million(result.get("residual")),
        },
        "sales": {
            "baseline_sales_fx_krw_per_usd": baseline_sales_fx,
            "comparison_sales_fx_krw_per_usd": comparison_sales_fx,
            "quantity_effect_million_krw": _money_million(sales_totals.get("quantity_effect")),
            "pure_price_effect_million_krw": _money_million(sales_totals.get("pure_price_effect")),
            "sales_fx_effect_million_krw": _money_million(sales_totals.get("sales_fx_effect")),
            "total_sales_effect_million_krw": _money_million(sales_totals.get("total_sales_effect")),
            "products": _compact_sales_rows(sales_rows),
        },
        "materials": {
            "policy": [
                "Do not identify yield/usage effect separately in V1.",
                "Do not identify MCM as a separate effect in V1.",
                "Use only deterministic nonwoven price, JPY, and materials-excluding-nonwoven values when supplied.",
            ],
            "engine_rows": [row for row in cost_rows if row.get("code") in material_codes],
            "detailed_analysis": result.get("material_analysis") or {},
        },
        "manufacturing": {
            "activity_policy": {
                "front_process": "FS SAP production receipt length",
                "back_process": "SW + BW + LC SAP production receipt PCS total",
            },
            "production": _compact_production(result.get("production", [])),
            "engine_rows": [row for row in cost_rows if row.get("code") in manufacturing_codes],
            "detailed_analysis": result.get("manufacturing_analysis") or {},
        },
        "sga": {
            "policy": [
                "Show all accounts in practitioner detail; do not collapse them into 기타.",
                "Customer delivery freight must not be double-counted with sales effects.",
                "Tariff is a separate external effect when supplied by the deterministic engine.",
            ],
            "engine_rows": [row for row in cost_rows if row.get("code") in sga_codes],
            "detailed_analysis": result.get("sga_analysis") or {},
        },
        "all_cost_rows": cost_rows,
        "effect_bridge": effects,
        "top_effects": _top_effects(effects),
        "business_notes": [line.strip() for line in business_notes.splitlines() if line.strip()],
        "reconciliation": {
            "status": "PASS" if result.get("reconciled") else "CHECK",
            "reconciled": bool(result.get("reconciled")),
            "residual_million_krw": _money_million(result.get("residual")),
        },
    }


_ANALYST_RULES = """당신은 관리손익 분석 담당자다.
- 아래 FACT PACK에 제공된 숫자를 변경하거나 새로 계산하지 않는다.
- FACT PACK에 없는 경영적 원인을 사실처럼 추정하지 않는다.
- business_notes에 있는 원인은 해당 숫자와 연결이 합리적인 범위에서만 설명한다.
- 손익효과 부호는 + 개선 / - 악화 기준을 그대로 따른다.
- 중요도는 top_effects와 제공된 효과금액을 따른다.
- 정합성 상태가 CHECK이면 확정적인 경영진 결론을 작성하지 말고 검증 필요를 먼저 표시한다.
- MCM은 현재 V1에서 별도 효과로 식별되지 않았으므로 독립 효과처럼 설명하지 않는다.
- 원재료 수율/사용량 효과를 임의로 만들지 않는다.
- 근거가 부족한 항목은 '제공된 데이터만으로 원인 특정 불가'라고 표시한다.
"""


def _fact_json(fact_pack: dict[str, Any]) -> str:
    return json.dumps(fact_pack, ensure_ascii=False, indent=2)


def build_executive_prompt(fact_pack: dict[str, Any]) -> str:
    return f"""{_ANALYST_RULES}

아래 FACT PACK만 사용해 한국어 경영진 분석을 작성한다.
출력: 경영진 요약, 주요 손익 변동요인 상위 5개, 판매/원부재료/제조경비/판관비, 확인 필요사항.
금액 단위는 백만원이며 원인과 상쇄관계를 우선 설명한다.

FACT PACK:
{_fact_json(fact_pack)}
"""


def build_question_prompt(fact_pack: dict[str, Any], question: str) -> str:
    return f"""{_ANALYST_RULES}

아래 FACT PACK만 근거로 질문에 답한다. 필요한 확정 계산값이 없으면 임의 계산하지 말고 무엇이 필요한지 말한다.
사용자 질문:
{question.strip()}

FACT PACK:
{_fact_json(fact_pack)}
"""


def build_synthesis_prompt(fact_pack: dict[str, Any]) -> str:
    return f"""{_ANALYST_RULES}

아래 FACT PACK으로 영업이익 증감 구조와 중요한 상쇄관계를 설명하는 최종 종합 손익분석을 작성한다.
FACT PACK에 없는 내부/외부 분류나 금액을 새로 만들지 않는다.

FACT PACK:
{_fact_json(fact_pack)}
"""

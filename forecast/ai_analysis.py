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
    output: list[dict[str, Any]] = []
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
    output: list[dict[str, Any]] = []
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
    output: list[dict[str, Any]] = []
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


def _top_effects(effect_rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    ranked = sorted(
        effect_rows,
        key=lambda row: abs(_number(row.get("profit_effect_million_krw"))),
        reverse=True,
    )
    return ranked[:limit]


def analysis_signature(result: dict[str, Any]) -> str:
    baseline = result.get("baseline", {})
    comparison = result.get("comparison", {})
    period = result.get("period", {})
    return "__".join([
        str(baseline.get("id", "base")),
        str(comparison.get("id", "comparison")),
        str(period.get("key", "period")),
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
    """Build the only dataset that may be handed to an external AI for interpretation.

    The fact pack intentionally omits separate MCM attribution. Current V1 does not
    identify a comparable MCM effect from the planning model, so AI must not present
    MCM as an independently calculated business effect.
    """
    sales_totals = sales_totals or {}
    effects = _compact_effects(result.get("effects", []))
    cost_rows = _compact_effects(result.get("cost_summary", []))

    material_rows = [
        row for row in cost_rows
        if row.get("code") in {"raw_material", "customs_refund"}
    ]
    manufacturing_rows = [
        row for row in cost_rows
        if row.get("code") in {
            "labor", "outsourcing", "other_processing", "processing_total", "manufacturing_expense"
        }
    ]
    sga_rows = [
        row for row in cost_rows
        if row.get("code") in {"selling_expense", "general_admin", "sga_total", "tariff"}
    ]

    pack = {
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
                "Use the business labels: nonwoven price effect excluding FX, nonwoven JPY effect, materials excluding nonwoven effect when those values are supplied by the deterministic engine.",
            ],
            "engine_rows": material_rows,
            "detailed_analysis": result.get("material_analysis") or {},
        },
        "manufacturing": {
            "activity_policy": {
                "front_process": "FS SAP production receipt length",
                "back_process": "SW + BW + LC SAP production receipt PCS total",
            },
            "production": _compact_production(result.get("production", [])),
            "engine_rows": manufacturing_rows,
            "detailed_analysis": result.get("manufacturing_analysis") or {},
        },
        "sga": {
            "policy": [
                "Show all accounts in the practitioner detail view; do not collapse detail accounts into 기타.",
                "Customer delivery freight may be displayed in SG&A detail but must not be double-counted when it is analyzed in sales effects.",
                "Tariff is a separately identified external effect when supplied by the deterministic engine.",
            ],
            "engine_rows": sga_rows,
            "detailed_analysis": result.get("sga_analysis") or {},
        },
        "effect_bridge": effects,
        "top_effects": _top_effects(effects),
        "business_notes": [
            line.strip() for line in business_notes.splitlines() if line.strip()
        ],
        "reconciliation": {
            "status": "PASS" if result.get("reconciled") else "CHECK",
            "reconciled": bool(result.get("reconciled")),
            "residual_million_krw": _money_million(result.get("residual")),
        },
    }
    return pack


_ANALYST_RULES = """당신은 관리손익 분석 담당자다.
- 아래 FACT PACK에 제공된 숫자를 변경하거나 새로 계산하지 않는다.
- FACT PACK에 없는 경영적 원인을 사실처럼 추정하지 않는다.
- business_notes에 있는 원인은 해당 숫자와 연결이 합리적인 범위에서만 설명한다.
- 손익효과 부호는 + 개선 / - 악화 기준을 그대로 따른다.
- 중요도는 top_effects와 제공된 효과금액을 따른다.
- 정합성 상태가 CHECK이면 확정적인 경영진 결론을 작성하지 말고 검증 필요를 먼저 표시한다.
- 재고·원가 반영시차는 FACT PACK에 값이나 메모가 있을 때만 언급한다.
- MCM은 현재 V1에서 별도 효과로 식별되지 않았으므로 독립 효과처럼 설명하지 않는다.
- 원재료 수율/사용량 효과를 임의로 만들지 않는다.
- 근거가 부족한 항목은 '제공된 데이터만으로 원인 특정 불가'라고 표시한다.
"""


def _fact_json(fact_pack: dict[str, Any]) -> str:
    return json.dumps(fact_pack, ensure_ascii=False, indent=2)


def build_executive_prompt(fact_pack: dict[str, Any]) -> str:
    return f"""{_ANALYST_RULES}

목표: 아래 FACT PACK만 사용해서 계획 대비 실적/추정 손익을 경영진에게 보고할 수 있는 한국어 분석을 작성한다.

출력 형식:
1. 경영진 요약: 4~6문장
2. 주요 손익 변동요인: 영향금액 절대값 기준 상위 5개를 중요한 순서대로 설명
3. 판매효과: 수량 / 순수단가 / 매출환율 중심
4. 원부재료: 제공된 확정 항목만 설명
5. 제조경비: 조업도 / 원단위 / 고정비 / 재고실현 관련 값이 있을 때만 설명
6. 판관비: 주요 계정 증감과 별도효과를 구분
7. 확인 필요사항: 데이터로 원인 특정이 안 되는 항목만 간단히 제시

문체:
- 기획팀의 경영회의 보고 문체
- 금액 단위는 백만원
- 불필요한 수식 설명은 생략
- 숫자보다 원인과 상쇄관계를 우선 설명하되, 모든 수치는 FACT PACK 값과 일치해야 한다.

FACT PACK:
{_fact_json(fact_pack)}
"""


def build_question_prompt(fact_pack: dict[str, Any], question: str) -> str:
    question = question.strip()
    return f"""{_ANALYST_RULES}

아래 FACT PACK만 근거로 사용자의 질문에 답한다.
새로운 계산이 필요한데 FACT PACK에 그 결과가 없다면 임의 계산하지 말고, 어떤 확정 계산값이 추가로 필요한지 말한다.
답변은 먼저 결론을 제시하고 그 다음 근거 숫자를 간단히 제시한다.

사용자 질문:
{question}

FACT PACK:
{_fact_json(fact_pack)}
"""


def build_synthesis_prompt(fact_pack: dict[str, Any]) -> str:
    return f"""{_ANALYST_RULES}

목표: 아래 FACT PACK을 바탕으로 최종 종합 손익분석 보고문을 작성한다.
이 보고문은 여러 상세 탭을 다시 나열하는 것이 아니라 영업이익 증감의 구조와 경영적으로 중요한 상쇄관계를 한 번에 이해시키는 것이 목적이다.

출력 형식:
- 제목 1줄
- 종합 결론 3문장
- 영업이익 증감 Bridge 설명 5~8문장
- 내부요인 / 외부요인 / 비용요인 관점의 핵심 포인트
- 제품군 또는 계정 수준에서 반드시 봐야 할 항목 최대 5개
- 다음 확인사항 또는 경영진 질문 예상 3개 이내

제약:
- FACT PACK에 없는 내부/외부 분류를 새로 만들어 금액을 합산하지 않는다.
- 숫자 재계산 금지. 제공된 합계와 효과만 인용한다.
- 원인이 business_notes에 없으면 단정하지 않는다.

FACT PACK:
{_fact_json(fact_pack)}
"""

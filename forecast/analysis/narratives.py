from __future__ import annotations


def _amount(value: float, unit: str) -> str:
    return f"{abs(value):,.0f}{unit}"


def build_narrative(
    operating_profit_delta: float,
    effects: list[dict[str, float | str]],
    residual: float,
    *,
    unit: str = "원",
    limit: int = 3,
) -> str:
    direction = "증가" if operating_profit_delta >= 0 else "감소"
    sentences = [f"비교 모형의 영업이익은 기준 모형 대비 {_amount(operating_profit_delta, unit)} {direction}했습니다."]
    positives = sorted((item for item in effects if float(item["profit_effect"]) > 0), key=lambda x: float(x["profit_effect"]), reverse=True)
    negatives = sorted((item for item in effects if float(item["profit_effect"]) < 0), key=lambda x: float(x["profit_effect"]))
    if positives:
        text = ", ".join(f"{item['label']} {_amount(float(item['profit_effect']), unit)}" for item in positives[:limit])
        sentences.append(f"주요 개선요인은 {text}입니다.")
    if negatives:
        text = ", ".join(f"{item['label']} {_amount(float(item['profit_effect']), unit)}" for item in negatives[:limit])
        sentences.append(f"주요 부담요인은 {text}입니다.")
    if abs(residual) >= 1:
        sentences.append(f"세부 효과로 귀속되지 않은 잔여차이는 {_amount(residual, unit)}입니다.")
    return " ".join(sentences)


def build_mcm_narrative(mcm_effect: float, outsourcing_decrease_effect: float, *, unit: str = "원") -> str:
    """Explain MCM reclassification economics without adding another bridge item."""
    if not mcm_effect and not outsourcing_decrease_effect:
        return ""
    parts = []
    if mcm_effect:
        direction = "개선" if mcm_effect > 0 else "부담"
        parts.append(f"원부재료 내 MCM(유상사급) 영향은 {_amount(mcm_effect, unit)} {direction}")
    if outsourcing_decrease_effect:
        parts.append(f"외주가공비 감소 영향은 {_amount(outsourcing_decrease_effect, unit)} 개선")
    net = mcm_effect + outsourcing_decrease_effect
    net_direction = "개선" if net >= 0 else "부담"
    return (
        "MCM(유상사급) 물량 전환으로 " + ", ".join(parts)
        + f"으로 나타났으며 설명용 순효과는 {_amount(net, unit)} {net_direction}입니다. "
        "이 순효과는 원부재료 및 제조경비 효과에 이미 포함되어 영업이익 브리지에 다시 더하지 않습니다."
    )

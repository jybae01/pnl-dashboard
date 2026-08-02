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

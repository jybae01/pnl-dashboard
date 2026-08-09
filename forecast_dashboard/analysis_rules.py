"""Pure business rules shared by future profit-analysis services."""

from __future__ import annotations

import numpy as np
import pandas as pd


VARIABLE_MANUFACTURING_ACCOUNTS = frozenset({"수도광열비", "소모품비", "외주가공비", "원자재운반비"})
VARIABLE_SGA_ACCOUNTS = frozenset({"브랜드사용료", "포장비"})


def classify_manufacturing_cost(account_name: str) -> str:
    return "variable" if str(account_name).strip() in VARIABLE_MANUFACTURING_ACCOUNTS else "fixed"


def classify_sga_cost(account_name: str) -> str:
    return "variable" if str(account_name).strip() in VARIABLE_SGA_ACCOUNTS else "fixed"


def inventory_realization_rate(cost_of_sales: float, manufacturing_input: float) -> float:
    """Return COGS/current manufacturing input without a 100% cap."""
    if manufacturing_input == 0:
        raise ZeroDivisionError("당기투입제조원가가 0이면 재고실현율을 계산할 수 없습니다.")
    return float(cost_of_sales) / float(manufacturing_input)


def convert_jpy_to_krw(jpy_amount: float, krw_per_jpy: float) -> float:
    """KRW/JPY is applied directly; no divide-by-100 adjustment is allowed."""
    return float(jpy_amount) * float(krw_per_jpy)


def outsourcing_analysis_quantity(production: pd.DataFrame) -> float:
    """Exclude MCM and explicitly ineligible quantities from outsourcing analysis."""
    if production.empty:
        return 0.0
    eligible = production.get("outsourcing_eligible_flag", pd.Series(True, index=production.index)).fillna(True).astype(bool)
    mcm = production.get("mcm_flag", pd.Series(False, index=production.index)).fillna(False).astype(bool)
    quantities = pd.to_numeric(production.get("sap_production_qty", 0.0), errors="coerce").fillna(0.0)
    return float(quantities[eligible & ~mcm].sum())


def manufacturing_activity_bases(production: pd.DataFrame) -> tuple[float, float]:
    """Return front-stage FS length and back-stage SW+BW PCS from SAP receipts."""
    if production.empty:
        return 0.0, 0.0
    groups = production.get("product_group", pd.Series("", index=production.index)).astype(str).str.upper()
    stages = production.get("process_stage", pd.Series("", index=production.index)).astype(str).str.lower()
    front = pd.to_numeric(production.get("sap_production_length", 0.0), errors="coerce").fillna(0.0)
    back = pd.to_numeric(production.get("sap_production_qty", 0.0), errors="coerce").fillna(0.0)
    front_mask = groups.eq("FS") | stages.isin({"front", "전공정"})
    back_mask = groups.isin({"SW", "BW"}) & ~groups.eq("LC")
    return float(front[front_mask].sum()), float(back[back_mask].sum())


def freight_price_effect_source(freight_amount: float, tariff_amount: float) -> float:
    return float(freight_amount) - float(tariff_amount)


def mcm_material_amount(issue_amount: float, mcm_issue_amount: float) -> float:
    """MCM paid-supply amount remains entirely in materials, never outsourcing."""
    return float(issue_amount) + float(mcm_issue_amount)


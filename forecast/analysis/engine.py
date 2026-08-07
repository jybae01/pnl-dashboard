from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from .configuration import AnalysisConfig
from .manufacturing_effects import ManufacturingEffects, calculate_manufacturing_effects
from .material_effects import MaterialEffects, calculate_material_effects
from .narratives import build_narrative
from .reconciliation import ReconciliationResult, reconcile
from .sales_effects import SalesEffects, calculate_sales_effects
from .schema import AnalysisScenario
from .sga_effects import SgaEffects, calculate_sga_effects
from .validation import validate_scenario


@dataclass
class AnalysisResult:
    base: dict[str, str]
    comparison: dict[str, str]
    months: tuple[str, ...]
    effects: list[dict[str, float | str]]
    sales: SalesEffects
    material: MaterialEffects
    manufacturing: ManufacturingEffects
    sga: SgaEffects
    reconciliation: ReconciliationResult
    narrative: str
    issues: list[str] = field(default_factory=list)


class AnalysisEngine:
    """Deterministic Base-vs-Comparison analysis engine.

    Delta metadata is Comparison - Base. Every effect is signed as operating-profit
    improvement (+) or deterioration (-).
    """

    def __init__(self, config_path: str | Path):
        self.config = AnalysisConfig.load(config_path)

    def compare(
        self,
        base: AnalysisScenario,
        comparison: AnalysisScenario,
        months: tuple[str, ...] | None = None,
    ) -> AnalysisResult:
        common = tuple(sorted(set(base.months) & set(comparison.months)))
        selected = months or common
        if not selected or not set(selected).issubset(set(common)):
            raise ValueError("두 모형에 공통으로 존재하는 기간만 비교할 수 있습니다.")
        left, right = base.select(selected), comparison.select(selected)

        sales = calculate_sales_effects(left, right, self.config)
        material = calculate_material_effects(left, right)
        manufacturing = calculate_manufacturing_effects(left, right, self.config)
        sga = calculate_sga_effects(left, right, self.config)
        direct = self._direct_effects(left, right)

        effects: list[dict[str, float | str]] = [
            {"code": "sales_quantity", "label": "판매수량 효과", "profit_effect": sales.quantity},
            {"code": "sales_mix", "label": "제품 Mix 효과", "profit_effect": sales.mix},
            {"code": "sales_price", "label": "판매단가 효과(관세 제외 운반비 원단위 포함)", "profit_effect": sales.price},
            {"code": "sales_fx", "label": "매출환율 효과", "profit_effect": sales.sales_fx},
            {"code": "tariff", "label": "관세 효과", "profit_effect": sales.tariff},
            {"code": "nonwoven_price_ex_fx", "label": "부직포 단가효과(환율 제외)", "profit_effect": material.nonwoven_price_ex_fx},
            {"code": "nonwoven_jpy", "label": "부직포 엔화 효과", "profit_effect": material.nonwoven_jpy},
            {"code": "materials_ex_nonwoven", "label": "부직포 제외 원재료 효과", "profit_effect": material.materials_ex_nonwoven},
            {"code": "manufacturing_realized", "label": "노무비·제조경비 손익실현 효과", "profit_effect": manufacturing.realized_total},
            {"code": "sga_variable", "label": "변동 판관비 효과", "profit_effect": sga.variable},
            {"code": "sga_fixed", "label": "고정 판관비 효과", "profit_effect": sga.fixed},
            *direct,
        ]
        op_delta = sum(row.operating_profit for row in right.pnl) - sum(row.operating_profit for row in left.pnl)
        check = reconcile(
            op_delta,
            effects,
            absolute_tolerance=self.config.absolute_tolerance,
            relative_tolerance=self.config.relative_tolerance,
        )
        issues = [
            *(f"기준 모형: {item}" for item in validate_scenario(left, self.config)),
            *(f"비교 모형: {item}" for item in validate_scenario(right, self.config)),
            *sales.issues,
            *material.issues,
            *manufacturing.issues,
        ]
        narrative = build_narrative(op_delta, effects, check.residual)
        return AnalysisResult(
            base=asdict(base.meta),
            comparison=asdict(comparison.meta),
            months=tuple(selected),
            effects=effects,
            sales=sales,
            material=material,
            manufacturing=manufacturing,
            sga=sga,
            reconciliation=check,
            narrative=narrative,
            issues=issues,
        )

    @staticmethod
    def _direct_effects(base: AnalysisScenario, comparison: AnalysisScenario) -> list[dict[str, float | str]]:
        left: dict[str, tuple[str, float]] = {}
        right: dict[str, tuple[str, float]] = {}
        for row in base.direct_effects:
            label, amount = left.get(row.code, (row.label, 0.0))
            left[row.code] = (label, amount + row.amount)
        for row in comparison.direct_effects:
            label, amount = right.get(row.code, (row.label, 0.0))
            right[row.code] = (label, amount + row.amount)
        output = []
        for code in sorted(set(left) | set(right)):
            label = right.get(code, left.get(code))[0]
            base_amount = left.get(code, (label, 0.0))[1]
            comparison_amount = right.get(code, (label, 0.0))[1]
            output.append({
                "code": code,
                "label": label,
                "profit_effect": base_amount - comparison_amount,
            })
        return output

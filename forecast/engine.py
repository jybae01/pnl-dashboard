from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .workbook import GoldenWorkbook


@dataclass
class SalesInput:
    quantity: float = 0
    amount: float = 0


@dataclass
class CostAdjustment:
    row: int
    amount: float = 0
    reason: str = ""


@dataclass
class ForecastInput:
    month: int = 7
    sales: dict[str, SalesInput] = field(default_factory=dict)
    production: dict[str, float] = field(default_factory=dict)
    mcm: dict[str, float] = field(default_factory=dict)
    manufacturing_adjustments: list[CostAdjustment] = field(default_factory=list)
    sga_adjustments: list[CostAdjustment] = field(default_factory=list)
    disposal_adjustment: float = 0
    disposal_reason: str = ""
    obsolescence_adjustment: float = 0
    obsolescence_reason: str = ""
    new_business_goods_cogs: float = 0
    new_business_goods_cogs_reason: str = ""
    uf_mbr_cogs_rate: float = 0.85
    ix_cogs_rate: float = 0.85
    uf_mbr_transport_rate: float = 0.05
    ix_transport_rate: float = 0.05
    ix_pack_liters: float = 25
    ix_pack_cost: float = 380
    plan_na_sa_sales: float = 0
    na_sa_sales: float = 0
    tariff_applicable_rate: float = 0.10
    tariff_rate: float = 0.13
    raw_material_basis: str = "model"
    raw_material_direct: float | None = None
    raw_material_adjustment: float = 0
    raw_material_reason: str = ""
    refund_rate: float = 0.013


@dataclass
class ForecastResult:
    month: int
    revenue: float
    cogs: float
    gross_profit: float
    sga: float
    operating_profit: float
    operating_margin: float
    detail: dict[str, float]
    validations: list[dict[str, Any]]
    input_log: list[dict[str, Any]]
    workbook_path: str
    start_month: int = 0
    end_month: int = 0


class ForecastEngine:
    def __init__(self, model_path: str | Path, mapping_path: str | Path):
        self.model_path = Path(model_path)
        raw_mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
        self.mapping = {
            key: value for key, value in raw_mapping.items()
            if key != "schema_overrides"
        }
        self.schema_name = "legacy"
        workbook = GoldenWorkbook(self.model_path)
        for schema in raw_mapping.get("schema_overrides", []):
            detected = all(
                self._mapping_token(workbook.raw_value(address))
                == self._mapping_token(expected)
                for address, expected in schema.get("detect_cells", {}).items()
            )
            if detected:
                self.mapping = self._deep_merge(self.mapping, schema.get("mapping", {}))
                self.schema_name = str(schema.get("name") or "custom")
                break

    @staticmethod
    def _mapping_token(value: Any) -> str:
        return re.sub(r"[\s_]+", "", str(value or "")).casefold()

    @classmethod
    def _deep_merge(cls, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = cls._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def column(month: int) -> str:
        if month < 1 or month > 12: raise ValueError("month must be 1..12")
        return chr(ord("E") + month - 1)

    def run(self, request: ForecastInput, destination: str | Path) -> ForecastResult:
        col = self.column(request.month)
        wb = GoldenWorkbook(self.model_path)
        explicit = set(self.mapping["formula_input_exceptions"])

        if str(wb.raw_value(f"{col}3") or "").strip() == "실적":
            raise ValueError(f"{request.month}월은 기준 모형에서 실적으로 확정되어 추정할 수 없습니다.")

        # Mark only the generated month as forecast in the downloaded workbook.
        # Other months keep the Golden Model's existing plan/actual labels.
        wb.set_text(f"{col}3", "추정", "forecast.period_type", "추정 산출 월")

        def put(row: int, value: float, source: str, reason: str = "") -> None:
            addr = f"{col}{row}"
            wb.set_input(addr, value, source, reason, allow_formula=(addr in explicit or f"*{row}" in explicit))

        # Existing products. LC is split into manufactured and purchased excess after production is known.
        for key, spec in self.mapping["sales"].items():
            if key in ("LC", "UF_MBR", "IX", "OTHER"): continue
            item = request.sales.get(key, SalesInput())
            put(spec["quantity_row"], item.quantity, f"sales.{key}.quantity")
            put(spec["amount_row"], item.amount, f"sales.{key}.amount")

        for key, row in self.mapping["production"].items():
            put(row, request.production.get(key, 0), f"production.{key}")
        for key, row in self.mapping["mcm"].items():
            put(row, request.mcm.get(key, 0), f"mcm.{key}", "MCM(유상사급): 기존 모형 로직 사용")

        lc = request.sales.get("LC", SalesInput())
        lc_production = request.production.get("LC", 0)
        manufactured_qty = min(max(lc.quantity, 0), max(lc_production, 0))
        goods_qty = max(lc.quantity - manufactured_qty, 0)
        lc_price = lc.amount / lc.quantity if lc.quantity else 0
        put(self.mapping["sales"]["LC"]["quantity_row"], manufactured_qty, "sales.LC.manufactured_quantity")
        put(self.mapping["sales"]["LC"]["amount_row"], manufactured_qty * lc_price, "sales.LC.manufactured_amount")
        put(self.mapping["lc_goods"]["quantity_row"], goods_qty, "sales.LC.goods_quantity")
        put(self.mapping["lc_goods"]["amount_row"], goods_qty * lc_price, "sales.LC.goods_amount")

        uf = request.sales.get("UF_MBR", SalesInput())
        ix = request.sales.get("IX", SalesInput())
        other = request.sales.get("OTHER", SalesInput())
        put(self.mapping["new_business_revenue_row"], uf.amount + ix.amount, "sales.new_business.amount")
        put(self.mapping["other_revenue_row"], other.amount, "sales.other.amount")

        for adjustment in request.manufacturing_adjustments:
            base = float(wb.value(f"{col}{adjustment.row}") or 0)
            put(adjustment.row, base + adjustment.amount, "manufacturing_adjustment", adjustment.reason)
        for adjustment in request.sga_adjustments:
            base = float(wb.value(f"{col}{adjustment.row}") or 0)
            put(adjustment.row, base + adjustment.amount, "sga_adjustment", adjustment.reason)

        selling_transport_row = self.mapping["special_rows"]["selling_transport"]
        packaging_row = self.mapping["special_rows"]["packaging"]
        transport = uf.amount * request.uf_mbr_transport_rate + ix.amount * request.ix_transport_rate
        packaging = (ix.quantity / request.ix_pack_liters * request.ix_pack_cost) if request.ix_pack_liters else 0
        plan_tariff = request.plan_na_sa_sales * request.tariff_applicable_rate * request.tariff_rate
        forecast_tariff = request.na_sa_sales * request.tariff_applicable_rate * request.tariff_rate
        tariff_adjustment = forecast_tariff - plan_tariff
        # These amounts are reference calculations only. The administrator
        # decides which amounts to reflect in the SG&A forecast inputs.
        selling_transport_value = float(wb.value(f"{col}{selling_transport_row}") or 0)
        packaging_value = float(wb.value(f"{col}{packaging_row}") or 0)

        disposal_row = self.mapping["special_rows"]["disposal"]
        obsolescence_row = self.mapping["special_rows"]["obsolescence"]
        put(disposal_row, float(wb.value(f"{col}{disposal_row}") or 0) + request.disposal_adjustment, "cogs.disposal", request.disposal_reason)
        put(obsolescence_row, float(wb.value(f"{col}{obsolescence_row}") or 0) + request.obsolescence_adjustment, "cogs.obsolescence", request.obsolescence_reason)

        # First pass obtains the model LC unit manufacturing cost and raw-material input.
        wb.recalculate()
        lc_unit_cost = float(wb.value(f"{col}{self.mapping['special_rows']['lc_unit_cost']}") or 0)
        raw_material_rows = self.mapping["special_rows"]["raw_material_process_rows"]
        front_material_row = int(raw_material_rows["front_process"])
        back_material_row = int(raw_material_rows["back_process"])
        model_front_rm = float(wb.value(f"{col}{front_material_row}") or 0)
        model_back_rm = float(wb.value(f"{col}{back_material_row}") or 0)
        model_rm = model_front_rm + model_back_rm
        front_rm_ratio = model_front_rm / model_rm if model_rm else 0
        back_rm_ratio = model_back_rm / model_rm if model_rm else 0
        applied_front_rm = model_front_rm
        applied_back_rm = model_back_rm
        refund_reason = request.raw_material_reason
        if request.raw_material_basis == "direct" and request.raw_material_direct is not None:
            applied_rm = float(request.raw_material_direct)
            if applied_rm < 0:
                raise ValueError("구매팀 추정 투입비는 0원 이상이어야 합니다.")
            if not model_rm and applied_rm:
                raise ValueError(
                    "추정 생산 기준 전공정·후공정 원재료비가 모두 0원이어서 "
                    "구매팀 추정 투입비를 배부할 수 없습니다."
                )
            applied_front_rm = applied_rm * front_rm_ratio
            # Make the two applied values reconcile exactly to the purchase-team total.
            applied_back_rm = applied_rm - applied_front_rm
            front_reason = (
                f"구매팀 예상 총 투입비 {applied_rm:,.0f}원 × "
                f"추정 전공정 원재료비 비율 {front_rm_ratio:.1%}"
            )
            back_reason = (
                f"구매팀 예상 총 투입비 {applied_rm:,.0f}원 × "
                f"추정 후공정 원재료비 비율 {back_rm_ratio:.1%}"
            )
            put(
                front_material_row,
                applied_front_rm,
                "raw_material.purchase_estimate.front_process",
                front_reason,
            )
            put(
                back_material_row,
                applied_back_rm,
                "raw_material.purchase_estimate.back_process",
                back_reason,
            )
            refund_reason = (
                f"구매팀 예상 투입비 {applied_rm:,.0f}원 × "
                f"원재료 관세 환급률 {request.refund_rate:.1%}"
            )
        else:
            applied_rm = model_rm + request.raw_material_adjustment
        refund = applied_rm * request.refund_rate
        reference_new_business_goods_cogs = (
            uf.amount * request.uf_mbr_cogs_rate
            + ix.amount * request.ix_cogs_rate
        )
        goods_cogs = goods_qty * lc_unit_cost + request.new_business_goods_cogs
        put(
            self.mapping["special_rows"]["goods_cogs"],
            goods_cogs,
            "cogs.goods",
            request.new_business_goods_cogs_reason,
        )
        put(self.mapping["special_rows"]["customs_refund"], -refund, "cogs.customs_refund", refund_reason)

        errors = wb.recalculate()
        validation = self._validate(wb, col, request, errors)
        if request.raw_material_basis == "direct" and request.raw_material_direct is not None:
            allocation_delta = applied_front_rm + applied_back_rm - applied_rm
            validation.append({
                "name": "구매팀 원재료 투입비 배부 정합성",
                "ok": abs(allocation_delta) < 1,
                "value": allocation_delta,
                "message": "전공정+후공정=구매팀 예상 총액",
            })
        output = wb.save(destination)
        pnl_rows = self.mapping["comparison"]["pnl_rows"]
        revenue = float(wb.value(f"{col}{pnl_rows['revenue']}") or 0)
        cogs = float(wb.value(f"{col}{pnl_rows['cogs']}") or 0)
        gp = float(wb.value(f"{col}{pnl_rows['gross_profit']}") or 0)
        selling_expense = float(wb.value(f"{col}{pnl_rows['selling_expense']}") or 0)
        general_admin = float(wb.value(f"{col}{pnl_rows['general_admin']}") or 0)
        model_sga = selling_expense + general_admin
        model_op = float(wb.value(f"{col}{pnl_rows['operating_profit']}") or 0)
        sga = model_sga
        op = model_op
        web_bridge_delta = revenue - cogs - sga - op
        validation.append({"name": "손익 산식 정합성", "ok": abs(web_bridge_delta) < 1,
                           "value": web_bridge_delta, "message": "매출-매출원가-판관비=영업이익"})
        return ForecastResult(
            month=request.month, revenue=revenue, cogs=cogs, gross_profit=gp, sga=sga,
            operating_profit=op, operating_margin=(op/revenue if revenue else 0),
            detail={
                "lc_manufactured_qty": manufactured_qty, "lc_goods_qty": goods_qty,
                "lc_unit_cost": lc_unit_cost, "uf_mbr_goods_cogs": uf.amount * request.uf_mbr_cogs_rate,
                "ix_goods_cogs": ix.amount * request.ix_cogs_rate,
                "new_business_goods_cogs_reference": reference_new_business_goods_cogs,
                "new_business_goods_cogs_applied": request.new_business_goods_cogs,
                "new_business_transport": transport,
                "ix_packaging": packaging,
                "plan_na_sa_sales": request.plan_na_sa_sales,
                "forecast_na_sa_sales": request.na_sa_sales,
                "plan_na_sa_tariff": plan_tariff,
                "forecast_na_sa_tariff": forecast_tariff,
                "na_sa_tariff_adjustment": tariff_adjustment,
                "selling_transport_before_adjustment": selling_transport_value,
                "selling_transport_after_adjustment": selling_transport_value,
                "packaging_model_value": packaging_value,
                "disposal_adjustment": request.disposal_adjustment,
                "obsolescence_adjustment": request.obsolescence_adjustment,
                "model_sga_including_tariff_adjustment": model_sga,
                "model_operating_profit_including_tariff_adjustment": model_op,
                "model_raw_material_input": model_rm,
                "model_front_raw_material_input": model_front_rm,
                "model_back_raw_material_input": model_back_rm,
                "front_raw_material_ratio": front_rm_ratio,
                "back_raw_material_ratio": back_rm_ratio,
                "applied_raw_material_input": applied_rm,
                "applied_front_raw_material_input": applied_front_rm,
                "applied_back_raw_material_input": applied_back_rm,
                "raw_material_customs_refund": refund, "goods_cogs_total": goods_cogs,
            }, validations=validation, input_log=wb.log_dicts(), workbook_path=str(output),
            start_month=request.month, end_month=request.month,
        )

    def _validate(self, wb: GoldenWorkbook, col: str, request: ForecastInput, errors: dict[str, str]) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for group in self.mapping["allocation_validation"]:
            values = [wb.value(f"{col}{row}") for row in group["rows"]]
            missing = any(value in (None, "") for value in values)
            total = sum(float(value or 0) for value in values)
            target = group.get("target", 1.0)
            ok = (not missing) and abs(total-target) <= group.get("tolerance", 1e-6)
            checks.append({"name": group["name"], "ok": ok, "value": total, "message": "정상" if ok else "누락 또는 합계 불일치"})
        pnl_rows = self.mapping["comparison"]["pnl_rows"]
        op_bridge = (
            float(wb.value(f"{col}{pnl_rows['revenue']}") or 0)
            - float(wb.value(f"{col}{pnl_rows['cogs']}") or 0)
            - float(wb.value(f"{col}{pnl_rows['selling_expense']}") or 0)
            - float(wb.value(f"{col}{pnl_rows['general_admin']}") or 0)
        )
        op = float(wb.value(f"{col}{pnl_rows['operating_profit']}") or 0)
        checks.append({"name":"영업이익 정합성", "ok":abs(op_bridge-op)<1, "value":op_bridge-op, "message":"허용오차 1원"})
        overwritten = wb.formula_changes()
        allowed = set(self.mapping["formula_input_exceptions"])
        unexpected = [addr for addr in overwritten if addr not in allowed and f"*{re.search(r'\d+',addr).group(0)}" not in allowed]
        checks.append({"name":"수식 보호", "ok":not unexpected, "value":unexpected, "message":"지정 예외 외 수식 덮어쓰기 없음"})
        checks.append({"name":"수식 재계산", "ok":not errors, "value":len(errors), "message":"서버 계산 오류 수"})
        return checks

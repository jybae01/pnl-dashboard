from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from .merchandise_cogs import (
    ActualYtdMerchandiseSource,
    ForecastMerchandiseCogsCalculation,
    GoldenForecastMerchandiseAdapter,
    MerchandiseSourceValidationError,
    NewBusinessGoodsCogsMode,
    calculate_forecast_merchandise_cogs,
    normalize_new_business_goods_cogs,
)
from .sales_contract import (
    FORECAST_SALES_CONTRACT_VERSION,
    LC_MERCHANDISE_CODE,
    LC_PRODUCT_CODE,
    LC_SALES_MODE_EXPLICIT,
    LC_SALES_MODE_LEGACY_PRODUCT_ONLY,
)
from .workbook import GoldenWorkbook


V11_EXISTING_PRODUCT_FREIGHT_RATE = 0.015
V11_UF_MBR_FREIGHT_RATE = 0.10
V11_IX_FREIGHT_RATE = 0.05
V11_TARIFF_ELIGIBLE_RATIO = 0.85
V11_TARIFF_RATE = 0.10


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
    new_business_goods_cogs_mode: str | None = None
    new_business_goods_cogs: float | None = None
    new_business_goods_cogs_reason: str = ""
    new_business_goods_cogs_legacy_normalized: bool = False
    uf_mbr_cogs_rate: float = 0.85
    ix_cogs_rate: float = 0.85
    # Legacy DTO fields retained for compatibility. The v1.1 engine uses the
    # authoritative constants above regardless of request values.
    uf_mbr_transport_rate: float = V11_UF_MBR_FREIGHT_RATE
    ix_transport_rate: float = V11_IX_FREIGHT_RATE
    ix_pack_liters: float = 25
    ix_pack_cost: float = 380
    plan_na_sa_sales: float = 0
    na_sa_sales: float = 0
    tariff_applicable_rate: float = V11_TARIFF_ELIGIBLE_RATIO
    tariff_rate: float = V11_TARIFF_RATE
    raw_material_basis: str = "model"
    raw_material_direct: float | None = None
    raw_material_adjustment: float = 0
    raw_material_reason: str = ""
    refund_rate: float = 0.013
    sales_contract_version: str = FORECAST_SALES_CONTRACT_VERSION
    lc_sales_mode: str = LC_SALES_MODE_LEGACY_PRODUCT_ONLY


@dataclass
class ForecastResult:
    month: int
    revenue: float
    cogs: float
    gross_profit: float
    sga: float
    operating_profit: float
    operating_margin: float
    detail: dict[str, Any]
    validations: list[dict[str, Any]]
    input_log: list[dict[str, Any]]
    workbook_path: str
    start_month: int = 0
    end_month: int = 0


def calculate_v11_forecast_transport_policy(
    sales: Mapping[str, SalesInput],
    *,
    plan_na_sa_sales: float,
    na_sa_sales: float,
) -> dict[str, float]:
    """Return the backend-authoritative monthly freight and tariff policy."""

    def revenue(code: str) -> float:
        value = float(sales.get(code, SalesInput()).amount)
        if not isfinite(value) or value < 0:
            raise ValueError(f"{code} Forecast 매출액은 유한한 0 이상 값이어야 합니다.")
        return value

    plan_regional = float(plan_na_sa_sales)
    forecast_regional = float(na_sa_sales)
    if (
        not isfinite(plan_regional)
        or not isfinite(forecast_regional)
        or plan_regional < 0
        or forecast_regional < 0
    ):
        raise ValueError("북미·남미 매출액은 유한한 0 이상 값이어야 합니다.")

    sw_revenue = revenue("SW400") + revenue("SW440")
    bw_revenue = revenue("BW400") + revenue("BW440")
    lc_revenue = revenue(LC_PRODUCT_CODE)
    fs_revenue = revenue("FS_SW") + revenue("FS_BW") + revenue("FS_TW")
    uf_mbr_revenue = revenue("UF_MBR")
    ix_revenue = revenue("IX")

    sw_freight = sw_revenue * V11_EXISTING_PRODUCT_FREIGHT_RATE
    bw_freight = bw_revenue * V11_EXISTING_PRODUCT_FREIGHT_RATE
    lc_freight = lc_revenue * V11_EXISTING_PRODUCT_FREIGHT_RATE
    fs_freight = fs_revenue * V11_EXISTING_PRODUCT_FREIGHT_RATE
    uf_mbr_freight = uf_mbr_revenue * V11_UF_MBR_FREIGHT_RATE
    ix_freight = ix_revenue * V11_IX_FREIGHT_RATE
    existing_freight = sw_freight + bw_freight + lc_freight + fs_freight
    default_customer_freight = existing_freight + uf_mbr_freight + ix_freight
    plan_tariff = plan_regional * V11_TARIFF_ELIGIBLE_RATIO * V11_TARIFF_RATE
    forecast_tariff = (
        forecast_regional * V11_TARIFF_ELIGIBLE_RATIO * V11_TARIFF_RATE
    )

    return {
        "sw_revenue": sw_revenue,
        "bw_revenue": bw_revenue,
        "lc_revenue": lc_revenue,
        "fs_revenue": fs_revenue,
        "uf_mbr_revenue": uf_mbr_revenue,
        "ix_revenue": ix_revenue,
        "sw_freight": sw_freight,
        "bw_freight": bw_freight,
        "lc_freight": lc_freight,
        "fs_freight": fs_freight,
        "existing_product_freight": existing_freight,
        "uf_mbr_freight": uf_mbr_freight,
        "ix_freight": ix_freight,
        "new_business_freight": uf_mbr_freight + ix_freight,
        "default_customer_freight": default_customer_freight,
        "plan_tariff": plan_tariff,
        "forecast_tariff": forecast_tariff,
        "tariff_adjustment": forecast_tariff - plan_tariff,
        "target_selling_transport": default_customer_freight + forecast_tariff,
    }


def calculate_lc_merchandise_forecast(
    sales: Mapping[str, SalesInput],
    source: ActualYtdMerchandiseSource,
    *,
    forecast_month: int,
) -> ForecastMerchandiseCogsCalculation:
    """Apply the authoritative LC merchandise rate to explicit merchandise revenue.

    LC manufactured-product sales and production are deliberately absent from
    this boundary.  They cannot influence merchandise COGS.
    """

    merchandise = sales.get(LC_MERCHANDISE_CODE, SalesInput())
    return calculate_forecast_merchandise_cogs(
        source,
        forecast_month=forecast_month,
        forecast_merchandise_revenue=merchandise.amount,
    )


def calculate_merchandise_cogs_total(
    lc_merchandise: ForecastMerchandiseCogsCalculation,
    new_business_merchandise: ForecastMerchandiseCogsCalculation,
) -> float:
    """Canonical merchandise-only COGS aggregation.

    Manufactured LC and every other manufactured-product cost are excluded by
    construction because this boundary accepts only merchandise calculations.
    """

    return (
        lc_merchandise.applied_forecast_cogs
        + new_business_merchandise.applied_forecast_cogs
    )


class ForecastEngine:
    def __init__(
        self,
        model_path: str | Path,
        mapping_path: str | Path,
        merchandise_mapping_path: str | Path | None = None,
    ):
        self.model_path = Path(model_path)
        self.mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
        if merchandise_mapping_path:
            source_path = Path(merchandise_mapping_path)
        else:
            frozen_candidate = Path(mapping_path).parent / "forecast_merchandise_sources.json"
            source_path = frozen_candidate if frozen_candidate.is_file() else (
                Path(__file__).resolve().parents[1] / "config" / "forecast_merchandise_sources.json"
            )
        self.merchandise_mapping = json.loads(source_path.read_text(encoding="utf-8"))

    @staticmethod
    def column(month: int) -> str:
        if month < 1 or month > 12: raise ValueError("month must be 1..12")
        return chr(ord("E") + month - 1)

    def run(self, request: ForecastInput, destination: str | Path) -> ForecastResult:
        merchandise_input = request.sales.get(LC_MERCHANDISE_CODE)
        explicit_mode_valid = (
            request.lc_sales_mode == LC_SALES_MODE_EXPLICIT
            and merchandise_input is not None
        )
        legacy_mode_valid = (
            request.lc_sales_mode == LC_SALES_MODE_LEGACY_PRODUCT_ONLY
            and (
                merchandise_input is None
                or (
                    merchandise_input.quantity == 0
                    and merchandise_input.amount == 0
                )
            )
        )
        if (
            request.sales_contract_version != FORECAST_SALES_CONTRACT_VERSION
            or not (explicit_mode_valid or legacy_mode_valid)
        ):
            raise ValueError("Forecast sales contract identity is invalid")
        col = self.column(request.month)
        wb = GoldenWorkbook(self.model_path)
        try:
            sales_rows = self.merchandise_mapping["sales_rows"]
            lc_product_rows = sales_rows["LC_PRODUCT"]
            lc_merchandise_rows = sales_rows["LC_MERCHANDISE"]
            lc_product_input_rows = self.mapping["sales"][LC_PRODUCT_CODE]
            authoritative_rows = {
                int(lc_product_input_rows["quantity_row"]),
                int(lc_product_input_rows["amount_row"]),
                int(lc_product_rows["quantity_row"]),
                int(lc_product_rows["revenue_row"]),
                int(lc_merchandise_rows["quantity_row"]),
                int(lc_merchandise_rows["revenue_row"]),
                int(self.merchandise_mapping["products"]["LC"]["actual_cogs_row"]),
                int(self.merchandise_mapping["products"]["NEW_BUSINESS"]["actual_cogs_row"]),
                int(self.merchandise_mapping["total_forecast_cogs_row"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise MerchandiseSourceValidationError(
                "source_mapping_invalid",
                "Forecast LC sales and merchandise output rows are required",
            ) from exc
        explicit = set(self.mapping["formula_input_exceptions"]) | {
            f"*{row}" for row in authoritative_rows
        }
        new_business_selection = normalize_new_business_goods_cogs(
            request.new_business_goods_cogs_mode,
            request.new_business_goods_cogs,
            request.new_business_goods_cogs_reason,
            legacy_normalized=request.new_business_goods_cogs_legacy_normalized,
        )

        period_type_row = int(self.merchandise_mapping["period_type_row"])
        if str(wb.raw_value(f"{col}{period_type_row}") or "").strip() == "실적":
            raise ValueError(f"{request.month}월은 기준 모형에서 실적으로 확정되어 추정할 수 없습니다.")
        merchandise_sources = GoldenForecastMerchandiseAdapter(
            self.merchandise_mapping
        ).build(wb, request.month)
        configured_output_row = {
            source.total_forecast_cogs_row for source in merchandise_sources.values()
        }
        if configured_output_row != {int(self.mapping["special_rows"]["goods_cogs"])}:
            raise MerchandiseSourceValidationError(
                "output_mapping_mismatch",
                "Forecast merchandise output mapping does not match the canonical P&L row",
            )
        expected_revenue_rows = {
            "LC": int(lc_merchandise_rows["revenue_row"]),
            "NEW_BUSINESS": int(self.mapping["new_business_revenue_row"]),
        }
        if any(
            merchandise_sources[code].forecast_revenue_row != row
            for code, row in expected_revenue_rows.items()
        ):
            raise MerchandiseSourceValidationError(
                "forecast_revenue_mapping_mismatch",
                "Forecast merchandise revenue mapping does not match canonical revenue rows",
            )

        # Mark only the generated month as forecast in the downloaded workbook.
        # Other months keep the Golden Model's existing plan/actual labels.
        wb.set_text(
            f"{col}{period_type_row}",
            "추정",
            "forecast.period_type",
            "추정 산출 월",
        )

        def put(row: int, value: float, source: str, reason: str = "") -> None:
            addr = f"{col}{row}"
            wb.set_input(addr, value, source, reason, allow_formula=(addr in explicit or f"*{row}" in explicit))

        # Existing manufactured products. LC merchandise has its own canonical
        # sales item and is never inferred from production or a shared LC price.
        for key, spec in self.mapping["sales"].items():
            if key in (LC_PRODUCT_CODE, "UF_MBR", "IX", "OTHER"): continue
            item = request.sales.get(key, SalesInput())
            put(spec["quantity_row"], item.quantity, f"sales.{key}.quantity")
            put(spec["amount_row"], item.amount, f"sales.{key}.amount")

        for key, row in self.mapping["production"].items():
            put(row, request.production.get(key, 0), f"production.{key}")
        for key, row in self.mapping["mcm"].items():
            put(row, request.mcm.get(key, 0), f"mcm.{key}", "MCM(유상사급): 기존 모형 로직 사용")

        lc_product = request.sales.get(LC_PRODUCT_CODE, SalesInput())
        lc_merchandise_sales = request.sales.get(LC_MERCHANDISE_CODE, SalesInput())
        manufactured_qty = lc_product.quantity
        goods_qty = lc_merchandise_sales.quantity
        lc_goods_revenue = lc_merchandise_sales.amount
        put(int(lc_product_input_rows["quantity_row"]), lc_product.quantity, "sales.LC.product_quantity")
        put(int(lc_product_input_rows["amount_row"]), lc_product.amount, "sales.LC.product_amount")
        for output_key, input_key in (
            ("quantity_row", "quantity_row"),
            ("revenue_row", "amount_row"),
        ):
            output_address = f"{col}{int(lc_product_rows[output_key])}"
            input_address = f"{col}{int(lc_product_input_rows[input_key])}"
            observed_formula = str(wb.formulas.get(output_address) or "").replace("$", "").upper()
            if observed_formula != f"={input_address}".upper():
                raise MerchandiseSourceValidationError(
                    "lc_product_sales_formula_mismatch",
                    f"{output_address} must reference canonical LC Product input {input_address}",
                    product_code="LC",
                )
        # Persist the two authoritative Forecast sales rows as explicit values
        # as well as their underlying input cells.  Generated workbooks then
        # carry correct row-level evidence even before desktop Excel refreshes
        # formula caches on open.
        put(int(lc_product_rows["quantity_row"]), lc_product.quantity, "sales.LC.product_quantity_output")
        put(int(lc_product_rows["revenue_row"]), lc_product.amount, "sales.LC.product_amount_output")
        put(int(lc_merchandise_rows["quantity_row"]), goods_qty, "sales.LC_MERCHANDISE.goods_quantity")
        put(int(lc_merchandise_rows["revenue_row"]), lc_goods_revenue, "sales.LC_MERCHANDISE.goods_amount")

        uf = request.sales.get("UF_MBR", SalesInput())
        ix = request.sales.get("IX", SalesInput())
        other = request.sales.get("OTHER", SalesInput())
        new_business_revenue = uf.amount + ix.amount
        put(self.mapping["new_business_revenue_row"], new_business_revenue, "sales.new_business.amount")
        put(self.mapping["other_revenue_row"], other.amount, "sales.other.amount")

        for adjustment in request.manufacturing_adjustments:
            base = float(wb.value(f"{col}{adjustment.row}") or 0)
            put(adjustment.row, base + adjustment.amount, "manufacturing_adjustment", adjustment.reason)

        selling_transport_row = self.mapping["special_rows"]["selling_transport"]
        packaging_row = self.mapping["special_rows"]["packaging"]
        transport_policy = calculate_v11_forecast_transport_policy(
            request.sales,
            plan_na_sa_sales=request.plan_na_sa_sales,
            na_sa_sales=request.na_sa_sales,
        )
        transport = transport_policy["new_business_freight"]
        packaging = (ix.quantity / request.ix_pack_liters * request.ix_pack_cost) if request.ix_pack_liters else 0
        plan_tariff = transport_policy["plan_tariff"]
        forecast_tariff = transport_policy["forecast_tariff"]
        tariff_adjustment = transport_policy["tariff_adjustment"]
        plan_selling_transport = float(
            wb.value(f"{col}{selling_transport_row}") or 0
        )
        authoritative_selling_transport = transport_policy["target_selling_transport"]
        selling_transport_automatic_adjustment = (
            authoritative_selling_transport - plan_selling_transport
        )
        put(
            selling_transport_row,
            authoritative_selling_transport,
            "sga_authoritative_default",
            (
                "v1.1 Backend authoritative: 기존제품 운반비 1.5%, UF/MBR 10%, "
                "IX 5%, Forecast 미주매출 관세 8.5%"
            ),
        )
        selling_transport_before_user_adjustment = float(
            wb.value(f"{col}{selling_transport_row}") or 0
        )
        for adjustment in request.sga_adjustments:
            base = float(wb.value(f"{col}{adjustment.row}") or 0)
            put(
                adjustment.row,
                base + adjustment.amount,
                "sga_adjustment",
                adjustment.reason,
            )
        selling_transport_after_user_adjustment = float(
            wb.value(f"{col}{selling_transport_row}") or 0
        )
        packaging_value = float(wb.value(f"{col}{packaging_row}") or 0)

        disposal_row = self.mapping["special_rows"]["disposal"]
        obsolescence_row = self.mapping["special_rows"]["obsolescence"]
        put(disposal_row, float(wb.value(f"{col}{disposal_row}") or 0) + request.disposal_adjustment, "cogs.disposal", request.disposal_reason)
        put(obsolescence_row, float(wb.value(f"{col}{obsolescence_row}") or 0) + request.obsolescence_adjustment, "cogs.obsolescence", request.obsolescence_reason)

        # First pass obtains the model LC unit manufacturing cost and raw-material input.
        wb.recalculate()
        for row_key, expected_value in (
            ("quantity_row", lc_product.quantity),
            ("revenue_row", lc_product.amount),
        ):
            output_address = f"{col}{int(lc_product_rows[row_key])}"
            output_value = float(wb.value(output_address) or 0)
            tolerance = max(1e-6, abs(float(expected_value)) * 1e-9)
            if abs(output_value - float(expected_value)) > tolerance:
                raise MerchandiseSourceValidationError(
                    "lc_product_sales_mapping_mismatch",
                    f"{output_address} does not reconcile to canonical LC Product input",
                    product_code="LC",
                )
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
        lc_merchandise = calculate_lc_merchandise_forecast(
            request.sales,
            merchandise_sources["LC"],
            forecast_month=request.month,
        )
        new_business_merchandise = calculate_forecast_merchandise_cogs(
            merchandise_sources["NEW_BUSINESS"],
            forecast_month=request.month,
            forecast_merchandise_revenue=new_business_revenue,
            selection=new_business_selection,
        )
        goods_cogs = calculate_merchandise_cogs_total(
            lc_merchandise, new_business_merchandise
        )
        put(
            merchandise_sources["LC"].cogs_row,
            lc_merchandise.applied_forecast_cogs,
            "cogs.lc_merchandise",
        )
        put(
            merchandise_sources["NEW_BUSINESS"].cogs_row,
            new_business_merchandise.applied_forecast_cogs,
            "cogs.new_business_merchandise",
            new_business_selection.reason
            if new_business_selection.mode is NewBusinessGoodsCogsMode.MANUAL_OVERRIDE
            else "",
        )
        put(
            self.mapping["special_rows"]["goods_cogs"],
            goods_cogs,
            "cogs.goods",
            new_business_selection.reason
            if new_business_selection.mode is NewBusinessGoodsCogsMode.MANUAL_OVERRIDE
            else "",
        )
        put(self.mapping["special_rows"]["customs_refund"], -refund, "cogs.customs_refund", refund_reason)
        wb.add_merchandise_cogs_evidence(
            [lc_merchandise.as_dict(), new_business_merchandise.as_dict()]
        )

        errors = wb.recalculate()
        validation = self._validate(
            wb,
            col,
            request,
            errors,
            formula_input_exceptions=explicit,
        )
        validation.extend([
            {
                "name": f"{item.product_code} 상품원가 Source 및 Mode",
                "ok": item.validation_status == "PASS",
                "value": item.calculation_source,
                "message": "Actual-only source와 명시적 mode 검증",
            }
            for item in (lc_merchandise, new_business_merchandise)
        ])
        explicit_transport_adjustment = sum(
            float(item.amount)
            for item in request.sga_adjustments
            if int(item.row) == int(selling_transport_row)
        )
        expected_selling_transport = (
            authoritative_selling_transport + explicit_transport_adjustment
        )
        validation.append({
            "name": "판매비 운반비 Backend authoritative 및 1회 반영",
            "ok": abs(
                selling_transport_after_user_adjustment
                - expected_selling_transport
            ) < 1,
            "value": (
                selling_transport_after_user_adjustment
                - expected_selling_transport
            ),
            "message": "Backend Target Selling Transport + 명시적 사용자 조정",
        })
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
                "lc_product_sales_quantity": lc_product.quantity,
                "lc_product_sales_revenue": lc_product.amount,
                "lc_merchandise_sales_quantity": lc_merchandise_sales.quantity,
                "lc_merchandise_sales_revenue": lc_goods_revenue,
                "forecast_sales_contract_version": request.sales_contract_version,
                "lc_sales_mode": request.lc_sales_mode,
                "lc_unit_cost": lc_unit_cost, "uf_mbr_goods_cogs": uf.amount * request.uf_mbr_cogs_rate,
                "ix_goods_cogs": ix.amount * request.ix_cogs_rate,
                "new_business_goods_cogs_reference": reference_new_business_goods_cogs,
                "lc_merchandise_cogs_calculation_source": lc_merchandise.calculation_source,
                "lc_merchandise_cogs_applied": lc_merchandise.applied_forecast_cogs,
                "lc_actual_ytd_merchandise_revenue": lc_merchandise.actual_ytd_revenue,
                "lc_actual_ytd_merchandise_cogs": lc_merchandise.actual_ytd_cogs,
                "lc_actual_ytd_merchandise_cogs_rate": lc_merchandise.actual_ytd_cogs_rate,
                "new_business_goods_cogs_mode": new_business_merchandise.mode,
                "new_business_goods_cogs_calculation_source": new_business_merchandise.calculation_source,
                "new_business_goods_cogs_applied": new_business_merchandise.applied_forecast_cogs,
                "new_business_actual_ytd_merchandise_revenue": new_business_merchandise.actual_ytd_revenue,
                "new_business_actual_ytd_merchandise_cogs": new_business_merchandise.actual_ytd_cogs,
                "new_business_actual_ytd_merchandise_cogs_rate": new_business_merchandise.actual_ytd_cogs_rate,
                "new_business_goods_cogs_reason": new_business_merchandise.manual_reason,
                "new_business_goods_cogs_legacy_normalized": new_business_merchandise.legacy_normalized,
                "forecast_merchandise_source_mapping_version": new_business_merchandise.source_mapping_version,
                "forecast_merchandise_source_mapping_hash": new_business_merchandise.source_mapping_hash,
                "new_business_transport": transport,
                "sw_default_freight": transport_policy["sw_freight"],
                "bw_default_freight": transport_policy["bw_freight"],
                "lc_default_freight": transport_policy["lc_freight"],
                "fs_default_freight": transport_policy["fs_freight"],
                "existing_product_freight": transport_policy["existing_product_freight"],
                "uf_mbr_default_freight": transport_policy["uf_mbr_freight"],
                "ix_default_freight": transport_policy["ix_freight"],
                "default_customer_freight": transport_policy["default_customer_freight"],
                "ix_packaging": packaging,
                "plan_na_sa_sales": request.plan_na_sa_sales,
                "forecast_na_sa_sales": request.na_sa_sales,
                "plan_na_sa_tariff": plan_tariff,
                "forecast_na_sa_tariff": forecast_tariff,
                "na_sa_tariff_adjustment": tariff_adjustment,
                "plan_selling_transport": plan_selling_transport,
                "selling_transport_automatic_adjustment": selling_transport_automatic_adjustment,
                "selling_transport_authoritative_target": authoritative_selling_transport,
                "selling_transport_before_adjustment": selling_transport_before_user_adjustment,
                "selling_transport_after_adjustment": selling_transport_after_user_adjustment,
                "authoritative_existing_freight_rate": V11_EXISTING_PRODUCT_FREIGHT_RATE,
                "authoritative_uf_mbr_freight_rate": V11_UF_MBR_FREIGHT_RATE,
                "authoritative_ix_freight_rate": V11_IX_FREIGHT_RATE,
                "authoritative_tariff_eligible_ratio": V11_TARIFF_ELIGIBLE_RATIO,
                "authoritative_tariff_rate": V11_TARIFF_RATE,
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
                "raw_material_customs_refund": refund,
                "goods_cogs_total": goods_cogs,
                "merchandise_cogs_total": goods_cogs,
            }, validations=validation, input_log=wb.log_dicts(), workbook_path=str(output),
            start_month=request.month, end_month=request.month,
        )

    def _validate(
        self,
        wb: GoldenWorkbook,
        col: str,
        request: ForecastInput,
        errors: dict[str, str],
        *,
        formula_input_exceptions: set[str] | None = None,
    ) -> list[dict[str, Any]]:
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
        allowed = formula_input_exceptions or set(self.mapping["formula_input_exceptions"])
        unexpected = [addr for addr in overwritten if addr not in allowed and f"*{re.search(r'\d+',addr).group(0)}" not in allowed]
        checks.append({"name":"수식 보호", "ok":not unexpected, "value":unexpected, "message":"지정 예외 외 수식 덮어쓰기 없음"})
        checks.append({"name":"수식 재계산", "ok":not errors, "value":len(errors), "message":"서버 계산 오류 수"})
        return checks

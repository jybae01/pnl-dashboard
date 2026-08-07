from __future__ import annotations

import html
import json
import os
import tempfile
import zipfile
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from forecast.comparison import GenericComparisonEngine, PeriodOption
from forecast.analysis_export_hook import render_analysis_export
from forecast.baseline import inspect_baseline_workbook
from forecast.engine import CostAdjustment, ForecastEngine, ForecastInput, ForecastResult, SalesInput
from forecast.presentation.analysis_tabs import render_comparison_analysis
from forecast.presentation.formatting import format_million
from forecast.storage import BaselineStore, ModelRegistry, ResultStore
from forecast.workbook import GoldenWorkbook, extract_period_types, infer_workbook_year

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "models" / "golden_model.xlsx"
MAPPING = ROOT / "config" / "model_mapping.json"
STORE = ResultStore(ROOT / "data")
REGISTRY = ModelRegistry(ROOT / "data" / "registry")
BASELINE = BaselineStore(ROOT / "data" / "baseline")
RELEASE_FILE = ROOT / "config" / "release.json"


def load_release_info() -> dict:
    default = {
        "release_name": "Forecast V1 Beta",
        "version": "1.0.0-beta.1",
    }
    try:
        loaded = json.loads(RELEASE_FILE.read_text(encoding="utf-8"))
        return {**default, **loaded}
    except (OSError, ValueError, TypeError):
        return default


RELEASE = load_release_info()

st.set_page_config(
    page_title=f"손익 추정 시스템 · {RELEASE['release_name']}",
    layout="wide",
)


def secret(name: str) -> str | None:
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name)


def authenticate() -> str:
    if "role" in st.session_state:
        return st.session_state.role
    viewer, admin = secret("VIEWER_CODE"), secret("ADMIN_CODE")
    if not viewer or not admin:
        st.error("인증코드 없이 앱이 실행되었습니다.")
        st.info("현재 실행 창을 종료한 뒤 프로젝트 폴더의 `start_forecast.cmd`를 실행해 주세요. 일반 사용자 코드와 관리자 코드를 차례로 입력하면 앱이 다시 열립니다.")
        st.code(".\\run.ps1", language="powershell")
        st.stop()
    code = st.text_input(
        "접속 코드",
        type="password",
        key="forecast_access_code",
        autocomplete="one-time-code",
        placeholder="접속 코드를 입력하세요",
    )
    if st.button("로그인", type="primary"):
        if code == admin:
            st.session_state.role = "admin"
            st.rerun()
        if code == viewer:
            st.session_state.role = "viewer"
            st.rerun()
        st.error("접속 코드가 올바르지 않습니다.")
    st.stop()


def money(value: float) -> str:
    return format_million(value)


def center_table_text(frame: pd.DataFrame):
    """Center headers and non-numeric text while preserving numeric alignment."""
    text_columns = [column for column in frame.columns if not pd.api.types.is_numeric_dtype(frame[column])]
    styler = frame.style.set_table_styles([
        {"selector": "th", "props": [("text-align", "center")]},
    ])
    if text_columns:
        styler = styler.set_properties(subset=text_columns, **{"text-align": "center"})
    return styler


def forecast_workbook_bytes(
    path: str | Path,
    months: list[int],
    input_log: list[dict] | None = None,
) -> bytes:
    """Return a download copy with every selected month marked as forecast."""
    workbook = GoldenWorkbook(path)
    if workbook.audit_entry_count() == 0:
        workbook.restore_audit_logs(input_log)
    for month in months:
        column = ForecastEngine.column(month)
        current_status = str(workbook.raw_value(f"{column}3") or "").strip()
        if current_status == "실적":
            raise ValueError(f"{month}월은 기준 모형에서 실적으로 고정되어 있습니다.")
        if current_status != "추정":
            workbook.set_text(f"{column}3", "추정", "download.period_type", "추정 산출 월")
    with tempfile.TemporaryDirectory(dir=ROOT / "data") as directory:
        output = Path(directory) / "forecast_download.xlsx"
        workbook.save(output)
        return output.read_bytes()


def reset_session_after_baseline_change(message: str) -> None:
    role = st.session_state.get("role")
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if role:
        st.session_state.role = role
    st.session_state.baseline_notice = message


def show_result(result: dict) -> None:
    start_month = int(result.get("start_month") or result.get("month") or 0)
    end_month = int(result.get("end_month") or result.get("month") or 0)
    if start_month:
        period_label = f"{start_month}월" if start_month == end_month else f"{start_month}~{end_month}월"
        st.caption(f"추정 기간: {period_label}")
    cols = st.columns(5)
    cards = [("매출액", "revenue"), ("매출원가", "cogs"), ("매출총이익", "gross_profit"),
             ("판관비", "sga"), ("영업이익", "operating_profit")]
    revenue = float(result["revenue"])
    for col, (label, key) in zip(cols, cards):
        value = float(result[key])
        ratio = value / revenue * 100 if revenue else 0
        display_value = money(value) if key == "revenue" else f"{money(value)} ({ratio:,.1f}%)"
        col.metric(label, display_value)
    with st.expander("검증 결과", expanded=False):
        st.dataframe(
            center_table_text(pd.DataFrame(result["validations"])),
            use_container_width=True,
            hide_index=True,
        )


def _forecast_page_single_month_legacy(role: str) -> None:
    st.title("추정 산출")
    if role == "viewer":
        latest = STORE.load()
        if latest:
            show_result(latest)
        else:
            st.info("관리자가 확정한 추정 결과가 없습니다.")
        return

    year = st.number_input("추정 연도", min_value=2020, max_value=2100, value=2026, step=1)
    month = st.selectbox("추정 대상월", list(range(1, 13)), index=6, format_func=lambda value: f"{value}월")
    workbook = GoldenWorkbook(MODEL)
    column = ForecastEngine.column(month)
    engine = ForecastEngine(MODEL, MAPPING)

    st.subheader("판매 입력")
    sales_keys = ["SW400", "SW440", "BW400", "BW440", "LC", "FS_SW", "FS_BW", "FS_TW", "UF_MBR", "IX", "OTHER"]
    labels = {"UF_MBR": "UF/MBR", "IX": "IX (수량 L)", "OTHER": "기타매출"}
    sales_df = st.data_editor(pd.DataFrame([
        {"코드": key, "구분": labels.get(key, key), "수량": 0.0, "매출액(원)": 0.0} for key in sales_keys
    ]), disabled=["코드", "구분"], hide_index=True, use_container_width=True)

    st.subheader("생산 입력")
    production_keys = ["SW400", "SW440", "BW400", "BW440", "LC", "FS_SW", "FS_BW", "FS_TW"]
    production_df = st.data_editor(pd.DataFrame([{"코드": key, "생산수량": 0.0} for key in production_keys]),
                                   disabled=["코드"], hide_index=True, use_container_width=True)
    mcm_keys = ["SW400", "SW440", "BW400", "BW440"]
    mcm_df = st.data_editor(pd.DataFrame([{"코드": key, "MCM(유상사급) 수량": 0.0} for key in mcm_keys]),
                            disabled=["코드"], hide_index=True, use_container_width=True)

    def cost_table(rows: list[int]) -> pd.DataFrame:
        records = []
        for row in rows:
            label = workbook.raw_value(f"D{row}") or workbook.raw_value(f"C{row}") or f"행 {row}"
            plan_amount = float(workbook.value(f"{column}{row}") or 0)
            records.append({
                "행": row, "항목": label, "계획금액": plan_amount,
                "추정금액": plan_amount, "사유": "",
            })
        return pd.DataFrame(records)

    st.subheader("제조경비 조정")
    manufacturing_df = st.data_editor(cost_table(engine.mapping["manufacturing_input_rows"]),
        disabled=["행", "항목", "계획금액"], hide_index=True, use_container_width=True)
    st.subheader("판관비 조정")
    sga_df = st.data_editor(cost_table(engine.mapping["sga_input_rows"]),
        disabled=["행", "항목", "계획금액"], hide_index=True, use_container_width=True)

    st.subheader("신사업")
    c1, c2, c3, c4 = st.columns(4)
    uf_cogs = c1.number_input("UF/MBR 상품원가율", 0.0, 1.0, 0.85, 0.01)
    ix_cogs = c2.number_input("IX 상품원가율", 0.0, 1.0, 0.85, 0.01)
    uf_transport = c3.number_input("UF/MBR 운반비율", 0.0, 1.0, 0.05, 0.01)
    ix_transport = c4.number_input("IX 운반비율", 0.0, 1.0, 0.05, 0.01)
    c1, c2 = st.columns(2)
    pack_liters = c1.number_input("IX 포장단위(L)", 0.01, value=25.0)
    pack_cost = c2.number_input("IX 포장비(원/ea)", 0.0, value=380.0)

    st.subheader("북미/남미 관세")
    c1, c2 = st.columns(2)
    plan_regional_sales = c1.number_input("북미/남미 계획 매출액(원)", 0.0, value=0.0)
    regional_sales = c2.number_input("북미/남미 추정 매출액(원)", 0.0, value=0.0)
    c1, c2 = st.columns(2)
    tariff_applicable = c1.number_input("관세 적용 대상 매출 비중", 0.0, 1.0, 0.10, 0.01)
    tariff_rate = c2.number_input("북미/남미 관세율", 0.0, 1.0, 0.13, 0.01)
    plan_tariff = plan_regional_sales * tariff_applicable * tariff_rate
    forecast_tariff = regional_sales * tariff_applicable * tariff_rate
    tariff_delta = forecast_tariff - plan_tariff
    c1, c2, c3 = st.columns(3)
    c1.metric("계획 관세", money(plan_tariff))
    c2.metric("추정 관세", money(forecast_tariff))
    c3.metric("관세 증감", money(tariff_delta), delta=money(tariff_delta), delta_color="inverse")
    st.caption("관세 증감액만 계획 판관비에 가감하며, 다운로드 엑셀의 기존 수식이나 세금과공과 셀은 변경하지 않습니다.")

    st.subheader("매출원가 조정")
    c1, c2 = st.columns(2)
    disposal = c1.number_input("제품 폐기손실(원)", value=0.0)
    disposal_reason = c1.text_input("제품 폐기손실 사유")
    obsolescence = c2.number_input("제품 진부화 평가손실(원)", value=0.0)
    obsolescence_reason = c2.text_input("제품 진부화 평가손실 사유")

    st.subheader("원재료 관세 환급")
    basis = st.radio("적용 예상 원재료 투입비 기준", ["model", "direct"], horizontal=True,
        format_func=lambda value: "모형 산출값 + 조정" if value == "model" else "구매팀 직접 입력")
    raw_direct = st.number_input("구매팀 예상 원재료 투입비(원)", 0.0, value=0.0, disabled=basis != "direct")
    raw_adjustment = st.number_input("모형 산출값 조정액(원)", value=0.0, disabled=basis != "model")
    raw_reason = st.text_input("원재료 투입비 적용 사유")
    refund_rate = st.number_input("관세 환급률", 0.0, 1.0, 0.013, 0.001, format="%.3f")

    if st.button("추정 계산 실행", type="primary"):
        sales = {row["코드"]: SalesInput(float(row["수량"]), float(row["매출액(원)"])) for _, row in sales_df.iterrows()}
        production = {row["코드"]: float(row["생산수량"]) for _, row in production_df.iterrows()}
        mcm = {row["코드"]: float(row["MCM(유상사급) 수량"]) for _, row in mcm_df.iterrows()}
        mfg = [
            CostAdjustment(
                int(row["행"]), float(row["추정금액"]) - float(row["계획금액"]), str(row["사유"]),
            )
            for _, row in manufacturing_df.iterrows()
            if abs(float(row["추정금액"]) - float(row["계획금액"])) > 0.5
        ]
        sga = [
            CostAdjustment(
                int(row["행"]), float(row["추정금액"]) - float(row["계획금액"]), str(row["사유"]),
            )
            for _, row in sga_df.iterrows()
            if abs(float(row["추정금액"]) - float(row["계획금액"])) > 0.5
        ]
        request = ForecastInput(month=month, sales=sales, production=production, mcm=mcm,
            manufacturing_adjustments=mfg, sga_adjustments=sga, disposal_adjustment=disposal,
            disposal_reason=disposal_reason, obsolescence_adjustment=obsolescence,
            obsolescence_reason=obsolescence_reason, uf_mbr_cogs_rate=uf_cogs, ix_cogs_rate=ix_cogs,
            uf_mbr_transport_rate=uf_transport, ix_transport_rate=ix_transport, ix_pack_liters=pack_liters,
            ix_pack_cost=pack_cost, plan_na_sa_sales=plan_regional_sales, na_sa_sales=regional_sales,
            tariff_applicable_rate=tariff_applicable,
            tariff_rate=tariff_rate, raw_material_basis=basis,
            raw_material_direct=raw_direct if basis == "direct" else None,
            raw_material_adjustment=raw_adjustment, raw_material_reason=raw_reason, refund_rate=refund_rate)
        output = ROOT / "data" / f"forecast_{year}_{month:02d}.xlsx"
        result = engine.run(request, output)
        st.session_state.forecast_result = asdict(result)
        st.session_state.forecast_year = int(year)

    if "forecast_result" in st.session_state:
        result = st.session_state.forecast_result
        show_result(result)
        download_data = forecast_workbook_bytes(
            result["workbook_path"], [int(result["month"])], result.get("input_log", []),
        )
        download_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            "추정 모형 엑셀 다운로드",
            download_data,
            file_name=(
                f"Forecast_{st.session_state.forecast_year}_{result['month']:02d}_"
                f"{download_timestamp}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            on_click="ignore",
        )
        st.caption("북미/남미 관세 증감은 웹 결과에만 별도 가감되며 다운로드 모형의 세금과공과 셀에는 기록하지 않습니다.")
        if all(item["ok"] for item in result["validations"]):
            version = st.text_input("확정 버전", value="V1")
            if st.button("이 결과를 일반 모드에 확정 공개"):
                STORE.confirm(ForecastResult(**result))
                path = Path(result["workbook_path"])
                REGISTRY.add(path.read_bytes(), name=f"{st.session_state.forecast_year}년 {result['month']}월 추정",
                    model_type="추정", year=st.session_state.forecast_year,
                    created_date=date.today().isoformat(), version=version, confirmed=True, file_name=path.name,
                    tariff_adjustment_monthly={str(result["month"]): tariff_delta})
                st.success("확정 결과를 공개하고 모형 목록에 등록했습니다.")
        else:
            st.error("검증 미통과 항목이 있어 결과를 확정할 수 없습니다.")


def forecast_page(role: str) -> None:
    st.title("추정 산출")
    if role == "viewer":
        latest = STORE.load()
        if latest:
            show_result(latest)
        else:
            st.info("관리자가 확정한 추정 결과가 없습니다.")
        return

    current_year = date.today().year
    active_baseline = BASELINE.load()
    baseline_path = BASELINE.workbook_file if active_baseline else None
    actual_through = active_baseline.actual_through_month if active_baseline else 0
    baseline_year = active_baseline.year if active_baseline else current_year
    baseline_token = active_baseline.uploaded_at if active_baseline else "not-uploaded"

    if st.session_state.get("baseline_notice"):
        st.success(st.session_state.pop("baseline_notice"))

    with st.expander("추정 기준 모형", expanded=active_baseline is None):
        if active_baseline:
            st.info(
                f"현재 기준: {active_baseline.name} · "
                f"{active_baseline.actual_through_month}월까지 실적 고정"
            )
            st.caption(
                f"원본 파일: {active_baseline.file_name} · 적용일시: {active_baseline.uploaded_at}"
            )
        else:
            if baseline_path is not None:
                st.info(f"현재 기준: 내장 Golden Model · {actual_through}월까지 실적 고정")
            else:
                st.info("최신 실적이 반영된 기준 엑셀을 업로드해 주세요.")

        uploaded_baseline = st.file_uploader(
            "최신 실적 반영 기준 엑셀 업로드",
            type=["xlsx"],
            key="forecast_baseline_upload",
        )
        if st.button(
            "업로드 파일을 추정 기준으로 적용",
            type="primary",
            disabled=uploaded_baseline is None,
        ):
            content = uploaded_baseline.getvalue()
            try:
                with tempfile.TemporaryDirectory(dir=ROOT / "data") as directory:
                    probe_path = Path(directory) / "baseline.xlsx"
                    probe_path.write_bytes(content)
                    uploaded_actual_through, _ = inspect_baseline_workbook(probe_path)
                meta = BASELINE.activate(
                    content,
                    name=Path(uploaded_baseline.name).stem,
                    file_name=uploaded_baseline.name,
                    year=current_year,
                    actual_through_month=uploaded_actual_through,
                    version=datetime.now().strftime("%Y%m%d_%H%M%S"),
                )
            except Exception as exc:
                st.error(f"기준 모형을 적용할 수 없습니다: {exc}")
            else:
                reset_session_after_baseline_change(
                    f"{meta.name}을(를) 추정 기준으로 적용했습니다. "
                    f"{meta.actual_through_month}월까지 실적으로 고정됩니다."
                )
                st.rerun()

    if baseline_path is None:
        return

    st.markdown("**추정 기간**")
    c1, c2, separator, c3, _ = st.columns([0.7, 0.7, 0.08, 0.7, 2.82])
    year_options = list(range(current_year - 3, current_year + 4))
    year = c1.selectbox(
        "추정연도",
        year_options,
        index=year_options.index(baseline_…7093 tokens truncated…   tariff_control = tariff_controls[month]
            plan_sales = float(tariff_control["plan_sales"])
            forecast_sales = float(tariff_control["forecast_sales"])
            applicable_rate = float(tariff_control["applicable_rate"])
            tariff_rate = float(tariff_control["tariff_rate"])
            disposal_row = cogs_adjustment_df.loc[cogs_adjustment_df["항목"] == "제품 폐기손실"].iloc[0]
            obsolescence_row = cogs_adjustment_df.loc[cogs_adjustment_df["항목"] == "제품 진부화 평가손실"].iloc[0]
            raw_control = refund_controls[month]
            raw_basis_label = str(raw_control["basis"])
            requests[month] = ForecastInput(
                month=month, sales=sales, production=production, mcm=mcm,
                manufacturing_adjustments=mfg, sga_adjustments=sga,
                disposal_adjustment=float(disposal_row[f"{month}월 금액"]),
                disposal_reason=reason_for(month, "매출원가 조정", "disposal"),
                obsolescence_adjustment=float(obsolescence_row[f"{month}월 금액"]),
                obsolescence_reason=reason_for(month, "매출원가 조정", "obsolescence"),
                uf_mbr_cogs_rate=float(
                    month_value(new_business_cogs_rates, "UF/MBR 상품원가율", month)
                ) / 100,
                ix_cogs_rate=float(
                    month_value(new_business_cogs_rates, "IX 상품원가율", month)
                ) / 100,
                uf_mbr_transport_rate=float(
                    month_value(new_business_transport_rates, "UF/MBR 운반비율", month)
                ) / 100,
                ix_transport_rate=float(
                    month_value(new_business_transport_rates, "IX 운반비율", month)
                ) / 100,
                ix_pack_liters=float(month_value(packaging_df, "IX 포장단위(L)", month)),
                ix_pack_cost=float(month_value(packaging_df, "IX 포장비(원/ea)", month)),
                plan_na_sa_sales=plan_sales, na_sa_sales=forecast_sales,
                tariff_applicable_rate=applicable_rate, tariff_rate=tariff_rate,
                raw_material_basis="direct" if raw_basis_label == "구매팀 예상 금액" else "model",
                raw_material_direct=float(raw_control["purchase_amount"])
                    if raw_basis_label == "구매팀 예상 금액" else None,
                raw_material_adjustment=0,
                raw_material_reason="",
                refund_rate=float(raw_control["refund_rate"]),
            )

        final_output = ROOT / "data" / f"forecast_{year}_{start_month:02d}_{end_month:02d}.xlsx"
        month_results = []
        with tempfile.TemporaryDirectory(dir=ROOT / "data") as directory:
            source = baseline_path
            for index, month in enumerate(months):
                destination = final_output if index == len(months) - 1 else Path(directory) / f"month_{month:02d}.xlsx"
                result = ForecastEngine(source, MAPPING).run(requests[month], destination)
                month_results.append(result)
                source = destination

        period_revenue = sum(item.revenue for item in month_results)
        period_op = sum(item.operating_profit for item in month_results)
        detail_keys = [
            "plan_na_sa_sales", "forecast_na_sa_sales", "plan_na_sa_tariff",
            "forecast_na_sa_tariff", "na_sa_tariff_adjustment", "disposal_adjustment",
            "obsolescence_adjustment", "raw_material_customs_refund",
        ]
        period_result = ForecastResult(
            month=end_month,
            start_month=start_month,
            end_month=end_month,
            revenue=period_revenue,
            cogs=sum(item.cogs for item in month_results),
            gross_profit=sum(item.gross_profit for item in month_results),
            sga=sum(item.sga for item in month_results),
            operating_profit=period_op,
            operating_margin=period_op / period_revenue if period_revenue else 0,
            detail={key: sum(float(item.detail.get(key, 0)) for item in month_results) for key in detail_keys},
            validations=[
                {**validation, "name": f"{item.month}월 - {validation['name']}"}
                for item in month_results for validation in item.validations
            ],
            input_log=[
                {"month": item.month, **log} for item in month_results for log in item.input_log
            ],
            workbook_path=str(final_output),
        )
        st.session_state.forecast_result = asdict(period_result)
        st.session_state.forecast_month_results = [asdict(item) for item in month_results]
        st.session_state.forecast_year = int(year)
        st.session_state.forecast_selection = (
            int(year), start_month, end_month, baseline_token
        )
        st.rerun()

    current_selection = (int(year), start_month, end_month, baseline_token)
    if "forecast_result" not in st.session_state:
        return
    if tuple(st.session_state.get("forecast_selection", ())) != current_selection:
        st.info("추정 기간이 변경되었습니다. 입력 후 추정 계산을 다시 실행해 주세요.")
        return

    result = st.session_state.forecast_result
    show_result(result)
    monthly_frame = pd.DataFrame([
        {
            "월": f"{item['month']}월", "매출액": round(item["revenue"]), "매출원가": round(item["cogs"]),
            "매출총이익": round(item["gross_profit"]), "판관비": round(item["sga"]),
            "영업이익": round(item["operating_profit"]),
            "영업이익률": item["operating_margin"] * 100,
        }
        for item in st.session_state.forecast_month_results
    ])
    st.subheader("월별 추정 결과")
    st.dataframe(
        center_table_text(monthly_frame), hide_index=True, use_container_width=True,
        column_config={
            **{key: number_column(won=True) for key in ["매출액", "매출원가", "매출총이익", "판관비", "영업이익"]},
            "영업이익률": number_column(percent=True),
        },
    )
    download_data = forecast_workbook_bytes(
        result["workbook_path"], months, result.get("input_log", []),
    )
    download_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        "추정 모형 엑셀 다운로드",
        download_data,
        file_name=(
            f"Forecast_{st.session_state.forecast_year}_{start_month:02d}_{end_month:02d}_"
            f"{download_timestamp}.xlsx"
        ),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        on_click="ignore",
    )
    st.caption(
        "다운로드 모형의 Data 옆 `입력반영내역` 시트에서 기준값과 달라진 직접 입력을 확인할 수 있습니다. "
        "`이동`을 누르면 실제 반영된 Data 셀로 이동하며, 입력에 따라 변동된 수식 셀은 목록에서 제외됩니다."
    )
    st.caption(
        "판관비에는 관리자가 추정금액에서 직접 입력한 조정만 반영됩니다."
    )
    if all(item["ok"] for item in result["validations"]):
        version = st.text_input("확정 버전", value="V1", key="period_forecast_version")
        if st.button("이 결과를 일반 모드에 확정 공개", key="confirm_period_forecast"):
            STORE.confirm(ForecastResult(**result))
            path = Path(result["workbook_path"])
            label = f"{start_month}월" if start_month == end_month else f"{start_month}~{end_month}월"
            REGISTRY.add(
                path.read_bytes(), name=f"{st.session_state.forecast_year}년 {label} 추정",
                model_type="추정", year=st.session_state.forecast_year,
                created_date=date.today().isoformat(), version=version, confirmed=True,
                file_name=path.name,
            )
            st.success("확정 결과를 공개하고 모형 목록에 등록했습니다.")
    else:
        st.error("검증 미통과 항목이 있어 결과를 확정할 수 없습니다.")


def model_table(models) -> pd.DataFrame:
    return pd.DataFrame([{
        "모형명": item.name, "구분": item.model_type, "월별구성": item.period_composition,
        "작성일": item.created_date, "버전": item.version, "확정 여부": "확정" if item.confirmed else "미확정",
        "업로드 시각": item.uploaded_at,
    } for item in models])


def data_management_page(role: str) -> None:
    st.title("데이터 관리")
    if role != "admin":
        st.warning("관리자 전용 메뉴입니다.")
        return
    with st.expander("모형 업로드", expanded=True):
        uploaded = st.file_uploader("계획·실적·추정 모형", type=["xlsx"])
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("모형명")
        model_type = c2.selectbox("모형 구분", ["계획", "실적", "추정"])
        version = c3.text_input("버전", value="V1")
        c1, c2 = st.columns(2)
        created = c1.date_input("작성일", value=date.today())
        confirmed = c2.checkbox("확정 모형")
        st.caption(
            "기준연도는 업로드 워크북의 월 헤더·날짜·연도 셀에서 자동 판별합니다. "
            "판별할 수 없으면 현재 연도를 사용하며, 비교용 기간은 항상 1~12월로 저장합니다."
        )
        if st.button("모형 등록", type="primary", disabled=uploaded is None or not name.strip()):
            content = uploaded.getvalue()
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as temp:
                temp.write(content)
                temp_path = Path(temp.name)
            try:
                if not zipfile.is_zipfile(temp_path):
                    raise ValueError("유효한 xlsx 파일이 아닙니다.")
                probe = GoldenWorkbook(temp_path)
                if probe.raw_value("B1197") is None or probe.value("K1201") is None or probe.value("K1260") is None:
                    raise ValueError("Forecast V1 비교 매핑과 호환되는 손익 모형이 아닙니다.")
                detected_year = infer_workbook_year(temp_path, fallback_year=date.today().year)
                period_types = extract_period_types(temp_path)
                REGISTRY.add(
                    content,
                    name=name,
                    model_type=model_type,
                    year=detected_year,
                    created_date=created.isoformat(),
                    version=version,
                    confirmed=confirmed,
                    file_name=uploaded.name,
                    period_types=period_types,
                )
                st.success("모형을 등록했습니다.")
                st.rerun()
            finally:
                temp_path.unlink(missing_ok=True)

    models = REGISTRY.list()
    st.subheader("업로드 모형 목록")
    if models:
        st.dataframe(center_table_text(model_table(models)), use_container_width=True, hide_index=True)
        st.caption("모형 구분은 목록 정보이며 비교 조합을 제한하지 않습니다.")
    else:
        st.info("등록된 모형이 없습니다.")


def comparison_page(role: str) -> None:
    st.title("손익 분석 — 범용 모형 비교")
    if role != "admin":
        st.warning("관리자 전용 메뉴입니다.")
        return
    models = REGISTRY.list()
    if len(models) < 2:
        st.info("데이터 관리에서 비교할 모형을 2개 이상 등록해 주세요.")
        return

    selected = [item.id for item in models if st.session_state.get(f"select_model_{item.id}", False)]
    if len(selected) > 2:
        for model_id in selected[2:]:
            st.session_state[f"select_model_{model_id}"] = False
        selected = selected[:2]
    st.caption("정확히 2개를 선택합니다. 두 개가 선택되면 나머지 체크박스는 잠깁니다.")
    header = st.columns([0.5, 2.6, 1, 1.6, 1.1, 0.9, 1])
    for col, label in zip(header, ["선택", "모형명", "구분", "기준기간", "작성일", "버전", "확정 여부"]):
        col.markdown(f"**{label}**")
    for item in models:
        columns = st.columns([0.5, 2.6, 1, 1.6, 1.1, 0.9, 1])
        checked = item.id in selected
        columns[0].checkbox("선택", key=f"select_model_{item.id}", label_visibility="collapsed",
                            disabled=len(selected) >= 2 and not checked)
        values = [item.name, item.model_type, item.basis_period, item.created_date, item.version,
                  "확정" if item.confirmed else "미확정"]
        for col, value in zip(columns[1:], values):
            col.write(value)

    selected = [item.id for item in models if st.session_state.get(f"select_model_{item.id}", False)]
    if set(st.session_state.get("comparison_order", [])) != set(selected):
        st.session_state.comparison_order = selected[:2]
    if len(selected) != 2:
        st.info(f"현재 {len(selected)}개 선택됨 — 비교 분석은 2개 선택 후 활성화됩니다.")
        st.button("비교 분석", disabled=True)
        return

    order = st.session_state.comparison_order
    baseline_meta, comparison_meta = REGISTRY.get(order[0]), REGISTRY.get(order[1])
    c1, c2, c3 = st.columns([2, 0.8, 2])
    c1.success(f"기준 모형: {baseline_meta.name} ({baseline_meta.model_type})")
    if c2.button("기준 ↔ 비교 전환", use_container_width=True):
        st.session_state.comparison_order = [order[1], order[0]]
        st.session_state.pop("comparison_result", None)
        st.rerun()
    c3.info(f"비교 모형: {comparison_meta.name} ({comparison_meta.model_type})")
    st.caption("모든 증감액은 ‘비교 모형 - 기준 모형’으로 계산됩니다.")

    engine = GenericComparisonEngine(MAPPING)
    common_months = engine.common_months(baseline_meta, comparison_meta)
    if not common_months:
        st.error("두 모형에 공통으로 존재하는 분석기간이 없습니다.")
        st.button("비교 분석", disabled=True)
        return

    st.markdown("**분석 기간**")
    c1, c2, separator, c3, _ = st.columns([0.7, 0.7, 0.08, 0.7, 2.82])
    if st.session_state.get("comparison_analysis_year") != baseline_meta.year:
        st.session_state["comparison_analysis_year"] = baseline_meta.year
    analysis_year = c1.selectbox(
        "분석 연도",
        [baseline_meta.year],
        key="comparison_analysis_year",
    )
    if st.session_state.get("comparison_start_month") not in common_months:
        st.session_state["comparison_start_month"] = common_months[0]
    start_month = c2.selectbox(
        "시작 월",
        list(common_months),
        index=0,
        format_func=lambda value: f"{value}월",
        key="comparison_start_month",
    )
    separator.markdown("<div style='text-align:center;padding-top:2rem;'>~</div>", unsafe_allow_html=True)
    end_options = [month for month in common_months if month >= start_month]
    if st.session_state.get("comparison_end_month") not in end_options:
        st.session_state["comparison_end_month"] = start_month
    end_month = c3.selectbox(
        "종료 월",
        end_options,
        format_func=lambda value: f"{value}월",
        key="comparison_end_month",
    )
    selected_months = tuple(range(start_month, end_month + 1))
    selected_period = PeriodOption(
        key=f"R{analysis_year}_{start_month:02d}_{end_month:02d}",
        label=(f"{start_month}월" if start_month == end_month else f"{start_month}~{end_month}월"),
        months=selected_months,
        period_type="월" if start_month == end_month else "선택기간",
    )
    fx_key = f"{baseline_meta.id}_{comparison_meta.id}_{selected_period.key}"
    st.markdown("**판매효과 분해용 매출환율**")
    fx1, fx2, fx_note = st.columns([1, 1, 3])
    baseline_sales_fx = fx1.number_input(
        "기준 매출환율(KRW/USD)",
        min_value=0.0001,
        value=1480.0,
        step=0.1,
        format="%.2f",
        key=f"baseline_sales_fx_{fx_key}",
    )
    comparison_sales_fx = fx2.number_input(
        "비교 매출환율(KRW/USD)",
        min_value=0.0001,
        value=1480.0,
        step=0.1,
        format="%.2f",
        key=f"comparison_sales_fx_{fx_key}",
    )
    fx_note.caption("입력 환율은 비교 분석 실행 시 deterministic 판매효과 Result에 저장됩니다.")
    if st.button("비교 분석", type="primary", disabled=len(selected) != 2):
        result = engine.compare(baseline_meta, REGISTRY.path(baseline_meta.id), comparison_meta,
                                REGISTRY.path(comparison_meta.id), selected_period,
                                baseline_sales_fx=float(baseline_sales_fx),
                                comparison_sales_fx=float(comparison_sales_fx))
        st.session_state.comparison_result = asdict(result)

    if "comparison_result" not in st.session_state:
        return
    result = st.session_state.comparison_result
    if result["baseline"]["id"] != baseline_meta.id or result["comparison"]["id"] != comparison_meta.id:
        return
    if result["period"]["key"] != selected_period.key:
        st.info("분석기간이 변경되었습니다. 비교 분석 버튼을 다시 눌러 주세요.")
        return
    stored_sales = result.get("sales_analysis") or {}
    if stored_sales and (
        float(stored_sales.get("baseline_fx_krw_per_usd", 0.0)) != float(baseline_sales_fx)
        or float(stored_sales.get("comparison_fx_krw_per_usd", 0.0)) != float(comparison_sales_fx)
    ):
        st.info("매출환율이 변경되었습니다. 비교 분석 버튼을 다시 눌러 주세요.")
        return
    render_comparison_analysis(result)
    try:
        render_analysis_export(result)
    except Exception as exc:
        st.warning(f"검증 엑셀을 생성할 수 없습니다: {exc}")


role = authenticate()
menu = st.segmented_control("업무 메뉴", ["손익 현황", "추정 산출", "손익 분석", "데이터 관리"],
                            default="추정 산출", selection_mode="single")
st.caption(f"{RELEASE['release_name']} · v{RELEASE['version']}")
if menu == "손익 현황":
    st.info("현재 작성된 손익 대시보드를 연결할 메뉴입니다.")
elif menu == "추정 산출":
    forecast_page(role)
elif menu == "손익 분석":
    comparison_page(role)
else:
    data_management_page(role)

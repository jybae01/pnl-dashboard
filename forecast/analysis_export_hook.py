from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from .analysis_export import MIME_XLSX, build_comparison_audit_workbook
from .sales_comparison import calculate_sales_effect_rows, sales_effect_totals
from .storage import ModelRegistry


_INSTALLED_ATTR = "_pnl_analysis_export_hook_installed"


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(value))
    return cleaned.strip("_") or "model"


def _export_cache_key(result: dict[str, Any], baseline_fx: float, comparison_fx: float) -> str:
    payload = {
        "baseline": result.get("baseline"),
        "comparison": result.get("comparison"),
        "period": result.get("period"),
        "result": result,
        "baseline_fx": baseline_fx,
        "comparison_fx": comparison_fx,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def render_analysis_export(result: dict[str, Any]) -> None:
    baseline = result.get("baseline") or {}
    comparison = result.get("comparison") or {}
    period = result.get("period") or {}
    if not baseline.get("id") or not comparison.get("id") or not period.get("key"):
        return

    sales_analysis = result.get("sales_analysis") or {}
    if sales_analysis.get("rows"):
        baseline_fx = float(sales_analysis["baseline_fx_krw_per_usd"])
        comparison_fx = float(sales_analysis["comparison_fx_krw_per_usd"])
        sales_rows = list(sales_analysis["rows"])
        totals = dict(sales_analysis["totals"])
    else:
        fx_key = f"{baseline['id']}_{comparison['id']}_{period['key']}"
        baseline_fx = float(st.session_state.get(f"baseline_sales_fx_{fx_key}", 1480.0))
        comparison_fx = float(st.session_state.get(f"comparison_sales_fx_{fx_key}", 1480.0))
        sales_rows = calculate_sales_effect_rows(
            result.get("sales_groups", []), baseline_fx, comparison_fx
        )
        totals = sales_effect_totals(sales_rows)

    root = Path(__file__).resolve().parents[1]
    registry = ModelRegistry(root / "data" / "registry")
    cache_key = _export_cache_key(result, baseline_fx, comparison_fx)
    state_key = "comparison_audit_export_cache"
    cached = st.session_state.get(state_key) or {}
    if cached.get("key") != cache_key:
        payload = build_comparison_audit_workbook(
            result=result,
            sales_rows=sales_rows,
            sales_totals=totals,
            baseline_fx=baseline_fx,
            comparison_fx=comparison_fx,
            baseline_path=registry.path(str(baseline["id"])),
            comparison_path=registry.path(str(comparison["id"])),
            mapping_path=root / "config" / "model_mapping.json",
        )
        cached = {"key": cache_key, "payload": payload}
        st.session_state[state_key] = cached

    st.divider()
    st.subheader("분석 계산근거 다운로드")
    st.caption(
        "기준·비교 원천값, 실제 참조 셀, 원본 수식, 분석 수식, 엔진 계산값과 "
        "정합성 확인 결과를 하나의 엑셀에서 확인할 수 있습니다."
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        "손익분석 검증 엑셀 다운로드",
        cached["payload"],
        file_name=(
            f"손익분석_검증_{_safe_name(baseline.get('name', '기준'))}_"
            f"{_safe_name(comparison.get('name', '비교'))}_{period['key']}_{timestamp}.xlsx"
        ),
        mime=MIME_XLSX,
        on_click="ignore",
        key=f"comparison_audit_download_{cache_key}",
    )


def install_analysis_export_hook() -> None:
    """Append the audit download immediately after the comparison narrative.

    The existing Streamlit page is intentionally left unchanged. The hook only
    reacts when the exact narrative stored in ``comparison_result`` is written.
    """
    if getattr(st, _INSTALLED_ATTR, False):
        return
    original_write = st.write

    def write_with_analysis_export(*args, **kwargs):
        rendered = original_write(*args, **kwargs)
        try:
            result = st.session_state.get("comparison_result")
            narrative = (result or {}).get("narrative")
            if narrative and len(args) == 1 and args[0] == narrative:
                render_analysis_export(result)
        except Exception as exc:
            st.warning(f"검증 엑셀을 생성할 수 없습니다: {exc}")
        return rendered

    st.write = write_with_analysis_export
    setattr(st, _INSTALLED_ATTR, True)

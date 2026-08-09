from __future__ import annotations

from typing import Any

import streamlit as st

from ..persistence.contracts import ResultRepository
from .analysis_tabs import render_persisted_analysis_view


class InvalidCompletedResult(ValueError):
    pass


def persisted_analysis_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Return only a view already materialized inside completed JSONB."""

    if payload.get("payload_type") != "comparison_analysis":
        raise InvalidCompletedResult("completed result is not a comparison analysis payload")
    view = payload.get("analysis_view")
    if not isinstance(view, dict):
        raise InvalidCompletedResult("completed result has no persisted analysis_view")
    required = {"metadata", "summary", "sales", "material", "manufacturing", "sga"}
    missing = sorted(required - set(view))
    if missing:
        raise InvalidCompletedResult(f"persisted analysis_view is missing: {', '.join(missing)}")
    return view


def render_viewer_dashboard(results: ResultRepository) -> None:
    """Read and render completed JSONB; never open Excel or invoke an engine."""

    st.title("손익 현황")
    payload = results.load_completed()
    if payload is None:
        st.info("공개 완료된 손익분석 결과가 없습니다.")
        return
    try:
        view = persisted_analysis_view(payload)
    except InvalidCompletedResult as exc:
        st.error(f"완료 결과 형식을 확인해 주세요: {exc}")
        return
    provenance = " · ".join(
        str(payload.get(key) or "-")
        for key in ("engine_version", "mapping_version", "result_schema_version")
    )
    st.caption(f"엔진 · 매핑 · 결과 스키마: {provenance}")
    render_persisted_analysis_view(view)

"""UI-independent state transitions for period comparison controls.

The Streamlit widgets keep a user's in-progress (draft) dates under their
existing widget keys.  Separate applied keys record the dates used to render
the comparison, so a widget rerun cannot silently change the displayed data.
"""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PeriodApplyResult:
    """Result of trying to apply the current draft period."""

    applied: bool
    start_month: str
    end_month: str
    error_message: str | None = None


def _applied_keys(start_key: str, end_key: str) -> tuple[str, str]:
    return f"{start_key}_applied", f"{end_key}_applied"


def initialize_period_state(
    session_state: MutableMapping[str, object],
    months: Sequence[str],
    start_key: str,
    end_key: str,
) -> None:
    """Set the initial draft and applied periods to the first available month."""
    if not months:
        raise ValueError("months must contain at least one month")

    default_month = months[0]
    applied_start_key, applied_end_key = _applied_keys(start_key, end_key)
    for key in (start_key, end_key, applied_start_key, applied_end_key):
        if key not in session_state:
            session_state[key] = default_month


def get_applied_period(
    session_state: MutableMapping[str, object],
    months: Sequence[str],
    start_key: str,
    end_key: str,
) -> tuple[str, str]:
    """Return the last successfully applied period, initializing it if needed."""
    initialize_period_state(session_state, months, start_key, end_key)
    applied_start_key, applied_end_key = _applied_keys(start_key, end_key)
    return session_state[applied_start_key], session_state[applied_end_key]  # type: ignore[return-value]


def apply_draft_period(
    session_state: MutableMapping[str, object],
    months: Sequence[str],
    start_key: str,
    end_key: str,
) -> PeriodApplyResult:
    """Apply a valid draft period; preserve the prior applied period otherwise."""
    initialize_period_state(session_state, months, start_key, end_key)

    draft_start = session_state[start_key]
    draft_end = session_state[end_key]
    applied_start, applied_end = get_applied_period(
        session_state, months, start_key, end_key
    )

    if draft_start not in months or draft_end not in months:
        return PeriodApplyResult(
            applied=False,
            start_month=applied_start,
            end_month=applied_end,
            error_message="선택한 월을 확인한 뒤 다시 조회해 주세요.",
        )

    if months.index(draft_start) > months.index(draft_end):
        return PeriodApplyResult(
            applied=False,
            start_month=applied_start,
            end_month=applied_end,
            error_message="시작월은 종료월보다 늦을 수 없습니다. 기간을 다시 선택해 주세요.",
        )

    applied_start_key, applied_end_key = _applied_keys(start_key, end_key)
    session_state[applied_start_key] = draft_start
    session_state[applied_end_key] = draft_end
    return PeriodApplyResult(
        applied=True,
        start_month=draft_start,
        end_month=draft_end,
    )


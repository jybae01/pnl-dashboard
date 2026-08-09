from pathlib import Path

from forecast_dashboard.period_state import (
    apply_draft_period,
    get_applied_period,
    initialize_period_state,
)


MONTHS = [f"{month}월" for month in range(1, 13)]
START_KEY = "st_pnl"
END_KEY = "ed_pnl"


def new_session() -> dict[str, object]:
    session: dict[str, object] = {}
    initialize_period_state(session, MONTHS, START_KEY, END_KEY)
    return session


def test_initial_entry_uses_the_default_period_for_a_normal_render():
    session = new_session()

    assert get_applied_period(session, MONTHS, START_KEY, END_KEY) == ("1월", "1월")


def test_changing_only_the_start_month_keeps_the_applied_period():
    session = new_session()
    session[START_KEY] = "2월"

    assert get_applied_period(session, MONTHS, START_KEY, END_KEY) == ("1월", "1월")


def test_changing_only_the_end_month_keeps_the_applied_period():
    session = new_session()
    session[END_KEY] = "2월"

    assert get_applied_period(session, MONTHS, START_KEY, END_KEY) == ("1월", "1월")


def test_query_applies_the_draft_period_only_after_a_click():
    session = new_session()
    session[START_KEY] = "2월"
    session[END_KEY] = "4월"

    result = apply_draft_period(session, MONTHS, START_KEY, END_KEY)

    assert result.applied is True
    assert result.error_message is None
    assert get_applied_period(session, MONTHS, START_KEY, END_KEY) == ("2월", "4월")


def test_invalid_period_is_not_applied():
    session = new_session()
    session[START_KEY] = "2월"
    session[END_KEY] = "4월"
    apply_draft_period(session, MONTHS, START_KEY, END_KEY)
    session[START_KEY] = "5월"
    session[END_KEY] = "4월"

    result = apply_draft_period(session, MONTHS, START_KEY, END_KEY)

    assert result.applied is False
    assert "시작월" in result.error_message
    assert get_applied_period(session, MONTHS, START_KEY, END_KEY) == ("2월", "4월")


def test_period_selectors_wait_for_form_submission():
    app_source = Path("app.py").read_text(encoding="utf-8")
    function_source = app_source.split(
        "def render_centered_period_selectors", maxsplit=1
    )[1].split("\nmonths = ", maxsplit=1)[0]

    assert "with st.form(" in function_source
    assert 'st.form_submit_button("조회하기"' in function_source
    assert "st.button(" not in function_source

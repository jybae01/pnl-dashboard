from __future__ import annotations

from typing import Any


MILLION_KRW = 1_000_000.0


def million_value(value: Any) -> float | None:
    """Convert a raw KRW result to KRW millions for presentation only."""
    if value is None:
        return None
    return float(value) / MILLION_KRW


def format_million(value: Any, *, suffix: bool = True, signed: bool = False) -> str:
    """Format raw KRW consistently without changing the calculation value.

    Management screens favor integer KRW millions. A non-zero amount below
    KRW 1 million keeps one decimal so that a meaningful amount is not hidden.
    """
    converted = million_value(value)
    if converted is None:
        return "미산출"
    if 0 < abs(converted) < 1:
        rendered = f"{converted:+,.1f}" if signed else f"{converted:,.1f}"
    else:
        rendered = f"{converted:+,.0f}" if signed else f"{converted:,.0f}"
    return f"{rendered}백만원" if suffix else rendered


def format_number(value: Any, *, decimals: int = 0) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.{decimals}f}"


def format_signed_number(value: Any, *, decimals: int = 0) -> str:
    if value is None:
        return "-"
    return f"{float(value):+,.{decimals}f}"

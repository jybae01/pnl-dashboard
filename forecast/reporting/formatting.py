from __future__ import annotations

from .formulas import NullableNumber


NULL_TEXT = "—"


def format_number(
    value: NullableNumber,
    *,
    decimals: int = 0,
    signed: bool = False,
    null_text: str = NULL_TEXT,
) -> str:
    if value is None:
        return null_text
    normalized = 0 if value == 0 else value
    prefix = "+" if signed and normalized > 0 else ""
    return f"{prefix}{normalized:,.{decimals}f}"


def format_rate(
    value: NullableNumber,
    *,
    decimals: int = 2,
    signed: bool = False,
    null_text: str = NULL_TEXT,
) -> str:
    if value is None:
        return null_text
    return f"{format_number(value, decimals=decimals, signed=signed)}%"


def format_percentage_point(
    value: NullableNumber,
    *,
    decimals: int = 2,
    signed: bool = True,
    null_text: str = NULL_TEXT,
) -> str:
    if value is None:
        return null_text
    return f"{format_number(value, decimals=decimals, signed=signed)}%p"


def optional_number_text(value: NullableNumber, *, decimals: int = 0) -> str | None:
    if value is None:
        return None
    return format_number(value, decimals=decimals)


def optional_rate_text(value: NullableNumber, *, decimals: int = 1) -> str | None:
    if value is None:
        return None
    return format_rate(value, decimals=decimals)

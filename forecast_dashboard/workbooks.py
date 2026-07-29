"""Cached workbook generation and parsing."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import streamlit as st

from .storage import validate_xlsx


@st.cache_data(show_spinner=False, max_entries=4)
def read_workbook(payload: bytes) -> pd.DataFrame:
    validate_xlsx(payload)
    return pd.read_excel(io.BytesIO(payload), header=None, engine="openpyxl")


def extract_series(keyword: str, frame: pd.DataFrame) -> np.ndarray | None:
    if frame.shape[1] < 4:
        return None
    value_start = 4 if frame.shape[1] >= 16 else 3
    if frame.shape[1] < value_start + 12:
        return None

    lookup = frame.iloc[:, 2:4].fillna("").astype(str)
    exact = lookup.eq(keyword).any(axis=1)
    matches = exact if exact.any() else lookup.apply(lambda col: col.str.contains(keyword, regex=False)).any(axis=1)
    if not matches.any():
        return None
    row_index = matches[matches].index[0]
    values = pd.to_numeric(
        frame.loc[row_index].iloc[value_start : value_start + 12], errors="coerce"
    ).fillna(0.0)
    return values.to_numpy(dtype=float)


def safe_extract(
    keyword: str,
    frame: pd.DataFrame,
    unit: str = "money",
    default_val: np.ndarray | None = None,
) -> np.ndarray:
    values = extract_series(keyword, frame)
    if values is None:
        return default_val.copy() if default_val is not None else np.zeros(12, dtype=float)
    return values / 1_000_000.0 if unit == "money" else values

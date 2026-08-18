"""Canonical Forecast sales input identities.

The transport DTO intentionally remains the small
``{product_code, quantity, amount}`` shape.  Distinct product codes preserve
LC manufactured-product and merchandise inputs through preview, orchestration,
and the Forecast engine without introducing a second discriminator.
"""

from __future__ import annotations

from dataclasses import dataclass


LC_PRODUCT_CODE = "LC"
LC_MERCHANDISE_CODE = "LC_MERCHANDISE"
FORECAST_SALES_CONTRACT_VERSION = "forecast-sales-v2.0.0"
LC_SALES_MODE_EXPLICIT = "EXPLICIT_LC_PRODUCT_MERCHANDISE"
LC_SALES_MODE_LEGACY_PRODUCT_ONLY = "LEGACY_LC_PRODUCT_ONLY"


@dataclass(frozen=True)
class ForecastSalesItem:
    code: str
    category: str
    detail: str
    unit: str


CANONICAL_FORECAST_SALES_ITEMS: tuple[ForecastSalesItem, ...] = (
    ForecastSalesItem("SW400", "SW", "SW400", "PCS"),
    ForecastSalesItem("SW440", "SW", "SW440", "PCS"),
    ForecastSalesItem("BW400", "BW", "BW400", "PCS"),
    ForecastSalesItem("BW440", "BW", "BW440", "PCS"),
    ForecastSalesItem(LC_PRODUCT_CODE, "LC", "LC(제품)", "PCS"),
    ForecastSalesItem(LC_MERCHANDISE_CODE, "LC", "LC(상품)", "PCS"),
    ForecastSalesItem("FS_SW", "FS", "FS SW", "m"),
    ForecastSalesItem("FS_BW", "FS", "FS BW", "m"),
    ForecastSalesItem("FS_TW", "FS", "FS TW", "m"),
    ForecastSalesItem("UF_MBR", "신사업", "UF/MBR", "—"),
    ForecastSalesItem("IX", "신사업", "IX", "L"),
    ForecastSalesItem("OTHER", "OTHER", "기타매출", "—"),
)

CANONICAL_FORECAST_SALES_BY_CODE = {
    item.code: item for item in CANONICAL_FORECAST_SALES_ITEMS
}
CANONICAL_FORECAST_SALES_BY_DETAIL = {
    item.detail: item for item in CANONICAL_FORECAST_SALES_ITEMS
}
CANONICAL_FORECAST_SALES_CODES = frozenset(CANONICAL_FORECAST_SALES_BY_CODE)
LEGACY_FORECAST_SALES_CODES = CANONICAL_FORECAST_SALES_CODES - {
    LC_MERCHANDISE_CODE
}


__all__ = [
    "ForecastSalesItem",
    "LC_PRODUCT_CODE",
    "LC_MERCHANDISE_CODE",
    "FORECAST_SALES_CONTRACT_VERSION",
    "LC_SALES_MODE_EXPLICIT",
    "LC_SALES_MODE_LEGACY_PRODUCT_ONLY",
    "CANONICAL_FORECAST_SALES_ITEMS",
    "CANONICAL_FORECAST_SALES_BY_CODE",
    "CANONICAL_FORECAST_SALES_BY_DETAIL",
    "CANONICAL_FORECAST_SALES_CODES",
    "LEGACY_FORECAST_SALES_CODES",
]

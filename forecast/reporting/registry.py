from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


TEMPLATE_VERSION = "PNL_REPORTING_V1"
MONTH_KEYS = tuple(f"{month:02d}" for month in range(1, 13))
MONTH_HEADERS = tuple(f"{month}월" for month in range(1, 13))

SHEET_MONTHLY_PNL = "01_월별손익"
SHEET_MANUFACTURING_COGS = "02_매출원가상세"
SHEET_SGA = "03_판관비상세"
SHEET_PRODUCT_PNL = "04_제품군손익"
REQUIRED_SHEETS = (
    SHEET_MONTHLY_PNL,
    SHEET_MANUFACTURING_COGS,
    SHEET_SGA,
    SHEET_PRODUCT_PNL,
)

MONTHLY_PNL_HEADERS = ("항목명", "단위", *MONTH_HEADERS, "row_key", "template_version")
MANUFACTURING_COGS_HEADERS = ("매출원가 요소", "단위", *MONTH_HEADERS, "row_key")
SGA_HEADERS = ("판관비 항목", "구분", "단위", *MONTH_HEADERS, "row_key")
PRODUCT_PNL_HEADERS = (
    "제품군",
    "규격",
    "손익 항목",
    "단위",
    *MONTH_HEADERS,
    "product_group_key",
    "row_key",
)


@dataclass(frozen=True)
class RowDefinition:
    key: str
    label: str
    unit: str
    is_input: bool
    order: int
    level: int = 0
    kind: str = "default"
    parent_key: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class ProductGroupDefinition:
    key: str
    display: str
    dimension: str
    quantity_unit: str | None
    order: int


@dataclass(frozen=True)
class ProductRowDefinition:
    product_group_key: str
    key: str
    label: str
    unit: str
    is_input: bool
    order: int
    level: int = 0
    kind: str = "default"


MONTHLY_PNL_ROWS = (
    RowDefinition("revenue", "Ⅰ. 매출액", "백만원", False, 1, kind="header"),
    RowDefinition("rev_product", "1. 제품 매출", "백만원", True, 2, 1, parent_key="revenue"),
    RowDefinition("rev_semi", "2. 반제품 매출", "백만원", True, 3, 1, parent_key="revenue"),
    RowDefinition("rev_merch", "3. 상품 매출", "백만원", True, 4, 1, parent_key="revenue"),
    RowDefinition("rev_other", "4. 기타 매출", "백만원", True, 5, 1, parent_key="revenue"),
    RowDefinition("rev_rebate", "5. 판매장려금", "백만원", True, 6, 1, parent_key="revenue"),
    RowDefinition("sales_volume", "Ⅱ. 매출수량", "-", False, 7, kind="header"),
    RowDefinition("volume_sw", "8인치 SW", "PCS", False, 8, 1, parent_key="sales_volume"),
    RowDefinition("volume_bw", "8인치 BW", "PCS", False, 9, 1, parent_key="sales_volume"),
    RowDefinition("volume_lc", "4인치 LC", "PCS", False, 10, 1, parent_key="sales_volume"),
    RowDefinition("volume_fs", "반제품 (FS)", "m", False, 11, 1, parent_key="sales_volume"),
    RowDefinition("cogs", "Ⅲ. 매출원가", "백만원", False, 12, kind="header"),
    RowDefinition("cogs_product", "1. 제품 매출원가", "백만원", True, 13, 1, parent_key="cogs"),
    RowDefinition("cogs_semi", "2. 반제품 매출원가", "백만원", True, 14, 1, parent_key="cogs"),
    RowDefinition("cogs_merch", "3. 상품 매출원가", "백만원", True, 15, 1, parent_key="cogs"),
    RowDefinition("cogs_other", "4. 기타 매출원가", "백만원", True, 16, 1, parent_key="cogs"),
    RowDefinition("cogs_inventory_loss", "5. 재고자산 평가손실", "백만원", True, 17, 1, parent_key="cogs"),
    RowDefinition("cogs_ratio", "매출원가율", "%", False, 18),
    RowDefinition("gross_profit", "Ⅳ. 매출총이익", "백만원", False, 19, kind="total"),
    RowDefinition("gross_margin", "매출총이익률", "%", False, 20),
    RowDefinition("sga", "Ⅴ. 판매비와 관리비", "백만원", False, 21, kind="header"),
    RowDefinition("operating_profit", "Ⅵ. 영업이익", "백만원", False, 22, kind="total"),
    RowDefinition("operating_margin", "영업이익률", "%", False, 23),
    RowDefinition("adjusted_operating_profit", "Ⅶ. 조정 영업이익", "백만원", True, 24, kind="total"),
    RowDefinition("adjusted_operating_margin", "조정 영업이익률", "%", False, 25),
)

MANUFACTURING_COGS_ROWS = (
    RowDefinition("mfg_material", "원부재료비", "백만원", True, 1),
    RowDefinition("mfg_labor", "노무비", "백만원", True, 2),
    RowDefinition("mfg_outsourcing", "외주가공비", "백만원", True, 3),
    RowDefinition("mfg_other", "기타 제조경비", "백만원", True, 4),
    RowDefinition("mfg_total", "합계", "백만원", False, 5, kind="total"),
)

SGA_ROWS = (
    RowDefinition("admin", "일반관리비 소계", "백만원", False, 1, kind="header", category="일반관리비"),
    RowDefinition("admin_labor", "1. 인건비", "백만원", True, 2, 1, parent_key="admin", category="일반관리비"),
    RowDefinition("admin_depr", "2. 감가상각비", "백만원", True, 3, 1, parent_key="admin", category="일반관리비"),
    RowDefinition("admin_rnd", "3. 경상개발비", "백만원", True, 4, 1, parent_key="admin", category="일반관리비"),
    RowDefinition("admin_fee", "4. 수수료", "백만원", True, 5, 1, parent_key="admin", category="일반관리비"),
    RowDefinition("admin_other", "5. 기타", "백만원", False, 6, 1, parent_key="admin", category="일반관리비"),
    RowDefinition("admin_other_1", "• 통신비", "백만원", True, 7, 2, parent_key="admin_other", category="세부항목"),
    RowDefinition("admin_other_2", "• 소모품비", "백만원", True, 8, 2, parent_key="admin_other", category="세부항목"),
    RowDefinition("admin_other_3", "• 도서인쇄비", "백만원", True, 9, 2, parent_key="admin_other", category="세부항목"),
    RowDefinition("admin_other_4", "• 기타 잡비", "백만원", True, 10, 2, parent_key="admin_other", category="세부항목"),
    RowDefinition("sales", "판매비 소계", "백만원", False, 11, kind="header", category="판매비"),
    RowDefinition("sales_freight", "1. 운반비", "백만원", True, 12, 1, parent_key="sales", category="판매비"),
    RowDefinition("sales_commission", "2. 수수료", "백만원", True, 13, 1, parent_key="sales", category="판매비"),
    RowDefinition("sales_brand", "3. 브랜드사용료", "백만원", True, 14, 1, parent_key="sales", category="판매비"),
    RowDefinition("sales_labor", "4. 인건비", "백만원", True, 15, 1, parent_key="sales", category="판매비"),
    RowDefinition("sales_sample", "5. 견본비", "백만원", True, 16, 1, parent_key="sales", category="판매비"),
    RowDefinition("sales_bad_debt", "6. 대손상각", "백만원", True, 17, 1, parent_key="sales", category="판매비"),
    RowDefinition("sales_sundry", "7. 잡비", "백만원", True, 18, 1, parent_key="sales", category="판매비"),
    RowDefinition("sales_other", "8. 기타", "백만원", False, 19, 1, parent_key="sales", category="판매비"),
    RowDefinition("sales_other_1", "• 포장재료비", "백만원", True, 20, 2, parent_key="sales_other", category="세부항목"),
    RowDefinition("sales_other_2", "• 보관료/창고료", "백만원", True, 21, 2, parent_key="sales_other", category="세부항목"),
    RowDefinition("sales_other_3", "• 기타 판매부대비", "백만원", True, 22, 2, parent_key="sales_other", category="세부항목"),
    RowDefinition("sga_total", "판관비 총계", "백만원", False, 23, 2, kind="total", category="총계"),
)

PRODUCT_GROUPS = (
    ProductGroupDefinition("SW", "8인치 SW", "8-inch", "PCS", 1),
    ProductGroupDefinition("BW", "8인치 BW", "8-inch", "PCS", 2),
    ProductGroupDefinition("LC", "4인치 LC", "4-inch", "PCS", 3),
    ProductGroupDefinition("FS", "FS", "LENGTH", "m", 4),
    ProductGroupDefinition("NEW_BUSINESS", "신사업", "해당없음", None, 5),
)

_REGULAR_PRODUCT_METRICS = (
    ("revenue", "1. 매출액", "백만원", True, 0, "header"),
    ("volume", "2. 매출수량", None, True, 0, "default"),
    ("asp", "3. 평균 판매 단가(ASP)", "원", False, 0, "default"),
    ("cogs", "4. 매출원가", "백만원", True, 0, "default"),
    ("cogs_ratio", "• 매출원가율", "%", False, 1, "default"),
    ("gross_profit", "5. 매출총이익", "백만원", False, 0, "total"),
    ("gross_margin", "• 매출총이익률", "%", False, 1, "default"),
    ("sga", "6. 판매관리비", "백만원", True, 0, "default"),
    ("operating_profit", "7. 영업이익", "백만원", False, 0, "total"),
    ("operating_margin", "• 영업이익률", "%", False, 1, "default"),
)

_NEW_BUSINESS_METRICS = (
    ("revenue", "1. 매출액", "백만원", True, 0, "header"),
    ("cogs", "2. 매출원가", "백만원", True, 0, "default"),
    ("cogs_ratio", "• 매출원가율", "%", False, 1, "default"),
    ("gross_profit", "3. 매출총이익", "백만원", False, 0, "total"),
    ("gross_margin", "• 매출총이익률", "%", False, 1, "default"),
    ("sga", "4. 판매관리비", "백만원", True, 0, "default"),
    ("operating_profit", "5. 영업이익", "백만원", False, 0, "total"),
    ("operating_margin", "• 영업이익률", "%", False, 1, "default"),
)


def _product_rows() -> tuple[ProductRowDefinition, ...]:
    rows: list[ProductRowDefinition] = []
    order = 1
    for group in PRODUCT_GROUPS:
        metrics = _NEW_BUSINESS_METRICS if group.key == "NEW_BUSINESS" else _REGULAR_PRODUCT_METRICS
        for key, label, unit, is_input, level, kind in metrics:
            rows.append(
                ProductRowDefinition(
                    product_group_key=group.key,
                    key=key,
                    label=label,
                    unit=group.quantity_unit if key == "volume" else str(unit),
                    is_input=is_input,
                    order=order,
                    level=int(level),
                    kind=str(kind),
                )
            )
            order += 1
    return tuple(rows)


PRODUCT_PNL_ROWS = _product_rows()

ROW_REGISTRIES = MappingProxyType({
    SHEET_MONTHLY_PNL: MONTHLY_PNL_ROWS,
    SHEET_MANUFACTURING_COGS: MANUFACTURING_COGS_ROWS,
    SHEET_SGA: SGA_ROWS,
})

SHEET_HEADERS = MappingProxyType({
    SHEET_MONTHLY_PNL: MONTHLY_PNL_HEADERS,
    SHEET_MANUFACTURING_COGS: MANUFACTURING_COGS_HEADERS,
    SHEET_SGA: SGA_HEADERS,
    SHEET_PRODUCT_PNL: PRODUCT_PNL_HEADERS,
})

SHEET_DATA_RANGES = MappingProxyType({
    SHEET_MONTHLY_PNL: (2, 26, 16),
    SHEET_MANUFACTURING_COGS: (2, 6, 15),
    SHEET_SGA: (2, 24, 16),
    SHEET_PRODUCT_PNL: (2, 49, 18),
})


def authoritative_input_count() -> int:
    return (
        sum(row.is_input for rows in ROW_REGISTRIES.values() for row in rows)
        + sum(row.is_input for row in PRODUCT_PNL_ROWS)
    )

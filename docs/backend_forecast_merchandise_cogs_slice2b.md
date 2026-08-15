# Slice 2B — Forecast Merchandise COGS

## Git and scope

- Base / Start HEAD: `7cc9c7f878a442ec57470162f90aa16258e681c8`
- Branch: `agent/backend-forecast-merchandise-cogs-slice2b-v1`
- Preserved dirty reference worktree: `work/pnl-dashboard`
- Preserved dirty reference HEAD: `756bd2b76af00bd6250935b3988adeb60a30ba35`
- Preserved tracked diff hash: `1e8454201d46b201371afcb5179d881e48bcfc2f`
- Production allocation, Inventory Timing, Quantity/Mix, Raw Material, and Manufacturing formulas were not changed.

## Contract

`new_business_goods_cogs_mode` is explicit on the new HTTP/React path:

- `ACTUAL_YTD_DEFAULT`: manual amount and reason must be absent.
- `MANUAL_OVERRIDE`: amount is required, numeric zero is valid, and a nonblank reason is required.
- A mode-less legacy payload is normalized to `MANUAL_OVERRIDE`; omitted amount becomes the historical authoritative `0`, and a legacy blank reason remains valid.

The React default is `ACTUAL_YTD_DEFAULT`. The browser does not calculate a rate or COGS amount. Switching back to automatic mode clears the manual amount and reason so an unused value cannot be silently submitted.

## Golden source and formulas

The additive source identity is `forecast-merchandise-v1.0.0` with canonical hash
`3e92c689e78b97bbddd51dd391f980d7463cc583a030922448677960ef493600`.

It is separate from Base Model provenance and maps:

| Scope | Revenue source | COGS source | Monthly validation rate | Forecast revenue |
|---|---:|---:|---:|---:|
| LC merchandise, 4-inch | 1659 `매출액` | 1660 `매출원가` | 1661 `매출원가율` | 105 |
| New-business merchandise | 1733 `신사업 / 매출액` | 1734 `매출원가` | 1736 `매출원가율` | 114 |

Rows 1661 and 1736 validate each Actual month's `COGS / Revenue`; neither is used as a YTD rate. The canonical rate is:

```text
SUM(Actual-only merchandise COGS through cutoff)
/
SUM(Actual-only merchandise revenue through cutoff)
```

The latest contiguous `실적` month in `Data!E3:P3` is the backend-authoritative cutoff. A missing or non-contiguous cutoff, missing revenue/COGS source, zero YTD denominator, source label/formula mismatch, future-period dependency, output self-reference, or merchandise scope mismatch fails closed.

The applied formulas are:

```text
LC Forecast Merchandise COGS
= LC Forecast Merchandise Revenue × LC Actual YTD Merchandise COGS Rate

New Business ACTUAL_YTD_DEFAULT
= New Business Forecast Merchandise Revenue × New Business Actual YTD Merchandise COGS Rate

New Business MANUAL_OVERRIDE
= new_business_goods_cogs
```

LC and new-business applied COGS are summed once into the existing canonical `special_rows.goods_cogs` output. `uf_mbr_cogs_rate` and `ix_cogs_rate` remain reference calculations only.

## Provenance and execution

The global `model_mapping.json` and `mapping_registry.json` remain unchanged at `analysis-v1.2.0` / `38af7474...`. The Forecast service validates the separate source file, includes its version/hash in the idempotency fingerprint, freezes it beside the already-frozen global mapping for the whole chained run, and writes the identity to Evidence. `ForecastProductionAllocationService._require_model` retains exact Base Model version/hash checks.

## Evidence workbook

The existing `GoldenWorkbook.save` path now appends `상품원가검증` after `입력반영내역`. It does not create another writer or save path. For each product/month it records:

- mode and calculation source;
- Actual cutoff and formula-linked Actual-only YTD revenue/COGS/rate;
- formula-linked Forecast merchandise revenue;
- manual amount/reason where applicable;
- formula-selected applied COGS and Engine result reconciliation;
- cutoff, source, denominator, self-reference, scope, mode, conflict, reason, hardcoding, and Golden validations;
- canonical fields, source references, target output, and source mapping version/hash.

The total row reconciles the two applied product rows to `Data!<month>1289`. A manual zero reason is retained in both Evidence and the existing `입력반영내역` I-column/J-hyperlink path even when the target cell was already zero. Existing recalculation flags and `calcChain` removal remain unchanged.

## Verification

- Focused backend: `47 passed, 15 skipped`
- Full backend excluding one confirmed pre-existing unrelated assertion: `525 passed, 18 skipped, 1 deselected`
- Full backend without deselection: the same 525 tests pass; `test_reachable_management_route_uses_trusted_ingestion_not_legacy_mock` fails because the baseline `ModelManagementView.tsx` already contains `window.setTimeout`. The test fails identically at clean checkpoint `7cc9c7f`.
- Frontend tests: `79 passed`
- Frontend production build: PASS
- Frontend lint: PASS with pre-existing unused-symbol warnings outside Slice 2B
- Python compile: PASS
- `git diff --check`: PASS

The private Golden workbook is not checked into this worktree, so Golden-dependent Engine tests remain skipped. Slice 2A pinned the unchanged source SHA-256 values as Base `01480ddf...` and Comparison `9f02bb4f...`; this Slice does not write any source workbook.

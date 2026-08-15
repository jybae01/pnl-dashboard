# Slice 5A — OP Bridge Residual Root Cause Analysis

## Scope and decision

Slice 5A adds Source-based RCA metadata and a formula-bearing `Residual_RCA`
Evidence sheet. It does not change any Business Formula, Effect amount, residual
formula, mapping dependency, or forecast policy. No new Effect or residual plug
is created.

The existing identity remains authoritative:

```text
effects_total + residual = operating_profit_delta
```

RCA independently reconstructs Base and Comparison operating profit from
Revenue, COGS, Selling Expense, and General Administration, then compares each
direct P&L bucket with the canonical Effects assigned to that bucket.

## Private Golden acceptance

Read-only acceptance was executed for July–September 2026 (`R07_09`) with the
current Golden Base and Comparison workbooks. Source SHA-256 values were
identical before and after analysis.

| Source | SHA-256 |
|---|---|
| Base | `01480DDFA16382F93E227C60A4D0E73BF6A7AEF3B30B59C681992EB4E5A0F4D4` |
| Comparison | `9F02BB4F1375737085255ED9AA61478480206749F7EFF76811AA437C70B2B00E` |

Direct P&L reconstruction:

| P&L line | Base | Comparison | OP effect |
|---|---:|---:|---:|
| Revenue | 79,817,089,872.083 | 60,001,179,771.000 | -19,815,910,101.083 |
| COGS | 55,610,025,463.427 | 46,853,639,890.813 | +8,756,385,572.614 |
| Selling Expense | 10,414,186,124.188 | 6,978,480,604.000 | +3,435,705,520.188 |
| General Administration | 6,823,368,466.044 | 6,407,982,488.000 | +415,385,978.044 |
| Operating Profit | 6,969,509,818.424 | -238,923,211.813 | **-7,208,433,030.237** |

`Σ Direct P&L effects = Operating Profit Delta` is PASS.

Existing bridge:

```text
Effects total       +9,313,086,812.924
Existing residual  -16,521,519,843.161
OP delta             -7,208,433,030.237
```

## Bucket RCA

| Bucket | Direct effect | Canonical explained | Residual contribution |
|---|---:|---:|---:|
| Sales / Revenue | -19,815,910,101.083 | -5,028,551,921.247 | -14,787,358,179.836 |
| Manufactured COGS | +7,447,538,173.269 | +10,490,547,235.939 | -3,043,009,062.670 |
| Merchandise COGS | +203,513,784.345 | 0.000 | +203,513,784.345 |
| Other COGS | +1,105,333,615.000 | 0.000 | +1,105,333,615.000 |
| SG&A | +3,851,091,498.232 | +3,851,091,498.232 | 0.000 within tolerance |
| Other operating scope | 0.000 | 0.000 | 0.000 |

Classified total equals the existing residual within the configured numerical
tolerance. The Source-covered `UNEXPLAINED` amount is zero within tolerance.

### Sales basis

Quantity and Mix use Base GP/unit. V1 Mix excludes composition changes inside
the same product group. Customer freight is a non-additive child of Price and
is allocated to the SG&A direct-source boundary only for RCA. It remains in
Price exactly once in the official bridge.

### Current manufacturing cost basis

The Manufactured COGS gap is exactly the Slice 1B Current Manufacturing Cost
Basis Gap:

| Source | Classification | Amount |
|---|---|---:|
| row 321 production issue vs canonical RM driver | `FORMULA_BASIS_DIFFERENCE` | +185,474,477.330 |
| row 322 tariff-refund adjustment | `SCOPE_EXCLUDED` | +147,643,370.000 |
| row 323 paid supply | `MAPPING_GAP` | -3,376,126,910.000 |
| Manufacturing direct vs Activity/Unit/Fixed | `PRESENTATION_ONLY` | 0.000 within tolerance |
| **Basis Gap** | disclosure only | **-3,043,009,062.670** |

This gap is not additive and is not promoted to an Effect.

### Non-manufactured COGS

Actual comparison V1 has no canonical additive Effect for Merchandise COGS or
the other P&L COGS scope. They remain `SCOPE_EXCLUDED`. Forecast Merchandise
COGS is not mixed into the Actual comparison bridge.

Current-cost row 323 and P&L row 1293 are distinct sources. Current-cost row
322 and P&L row 1294 are also distinct sources; the RCA does not combine them.

## Effect map and double-count controls

The persisted RCA map records both official additive Effects and non-additive
children/source disclosures. It separately records `rca_allocation` so the
Price parent can be split into displayed Price and freight for P&L bucket
comparison without double counting the official bridge.

Workbook formulas validate:

- Quantity and Mix each occur once.
- Freight remains a non-additive Price child.
- Tariff remains separate.
- nonwoven price, JPY, and other materials remain children of Raw Material.
- Activity, Unit, and Fixed remain children of Manufacturing.
- Inventory Timing is allocated once.
- Merchandise and Manufactured COGS scopes remain separate.
- Current Cost Basis Gap remains non-additive.
- MCM remains a `PRESENTATION_ONLY`, non-additive policy/source disclosure and
  is not combined with the row-323 paid-supply mapping gap.
- classified residual components equal the existing residual.

## Evidence and source boundary

`Residual_RCA` contains actual Excel formulas for:

- Base and Comparison OP reconstruction;
- Direct OP Delta;
- direct bucket effects;
- canonical allocation by `SUMIFS` over the Effect map;
- bucket gaps;
- classified component total;
- comparison with the existing `최종Bridge_검증` residual;
- double-count validations.

Golden locations are Evidence metadata only. The Engine continues to use the
validated Source Map/Adapter and has no Golden row dependency added by this
Slice.

## Business decision candidates (not implemented)

The RCA identifies three possible future policy discussions only:

1. whether the Sales GP-driver basis should remain intentionally distinct from
   direct Revenue;
2. whether Actual non-manufactured COGS needs a future canonical taxonomy;
3. whether row-323 paid supply requires an approved canonical mapping.

No decision or formula change is made in Slice 5A.

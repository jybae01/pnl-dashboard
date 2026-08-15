# Slice 5B — Sales GP Driver / COGS Basis Overlap Analysis

## Status

Repository/Golden analysis: `PASS`

Double-count verdict: `PARTIAL_OVERLAP`

This slice adds analysis metadata and Evidence Workbook formulas only. It does
not change the production Quantity, Mix, Inventory Timing, OP Delta, effects
total, or Residual formulas.

## Scope and sign convention

- Matched manufactured sales scope: SW, BW, and LC in the PCS pool; FS in the
  LENGTH(m) pool.
- LC merchandise and New Business merchandise are excluded.
- `embedded_cogs_expense_delta` uses expense-source sign:
  `Comparison COGS - Base COGS`.
- `overlap_profit_candidate` uses OP Bridge sign:
  `- embedded_cogs_expense_delta`.

The analysis is performed per month and pool before monetary results are
summed. PCS and LENGTH quantities are never combined.

## Counterfactual formulas

These formulas are analysis-only and are not new canonical effects.

```text
Revenue-basis Quantity
= (Comparison pool quantity - Base pool quantity)
  × Base product mix
  × Base Revenue/unit

Revenue-basis Mix
= Comparison pool quantity
  × (Comparison product mix - Base product mix)
  × Base Revenue/unit

Embedded COGS Quantity
= Revenue-basis Quantity - GP-basis Quantity

Embedded COGS Mix
= Revenue-basis Mix - GP-basis Mix

Embedded Sales COGS
= Embedded COGS Quantity + Embedded COGS Mix
```

## Golden result (2026-07 through 2026-09)

| Measure | KRW |
|---|---:|
| Official GP-basis Quantity | -3,045,998,282.262 |
| Official GP-basis Mix | -3,242,936,639.675 |
| Matched manufactured Revenue-basis Quantity | -20,069,451,466.360 |
| Matched manufactured Revenue-basis Mix | -395,644,775.797 |
| Matched manufactured GP-basis Quantity | -6,130,663,053.418 |
| Matched manufactured GP-basis Mix | -158,271,868.519 |
| Embedded COGS Quantity, expense sign | -13,938,788,412.942 |
| Embedded COGS Mix, expense sign | -237,372,907.277 |
| Embedded Sales COGS, expense sign | -14,176,161,320.219 |
| Overlap candidate, OP Bridge sign | +14,176,161,320.219 |
| Sales product COGS direct effect | +16,597,207,954.228 |
| P&L Manufactured COGS direct effect | +7,447,538,173.269 |
| Sales-to-P&L COGS scope difference | -9,149,669,780.959 |
| Current Inventory Timing | +9,676,004,217.008 |
| Candidate adjusted Inventory Timing | -4,500,157,103.211 |
| Slice 5A Sales formula-basis gap | -14,787,358,179.836 |
| Embedded candidate / Slice 5A gap | 95.87% |
| Basis gap after embedded candidate | -611,196,859.617 |

Monthly overlap candidates in OP Bridge sign are:

- July: `+6,042,985,423.520` KRW
- August: `+9,422,703.774` KRW
- September: `+8,123,753,192.924` KRW
- July–September: `+14,176,161,320.219` KRW

## Verdict rationale

The GP-based sales driver mathematically embeds a Base COGS quantity/mix
component. The same Golden formula graph also feeds product COGS and the P&L
manufactured COGS lines used by Inventory Timing. This establishes a real
overlap candidate.

However, sales product COGS does not reconcile exactly to the direct P&L
manufactured COGS lines by month or cumulatively. The P&L lines contain a
different source scope and adjustments. Therefore the analysis cannot
authoritatively label the entire 14.176bn KRW as an exact duplicate inside
Inventory Timing. The supported verdict is `PARTIAL_OVERLAP`, confidence
`MEDIUM`.

The 95.87% relationship is a source-derived sensitivity statistic, not a
Residual plug. The remaining 0.611bn KRW is displayed explicitly, and the LC
mapping gap prevents promotion of either amount to an authoritative adjustment.

The intra-group SW400/SW440 and BW400/BW440 reference analysis is classified
`INTRA_GROUP_SKU_BASIS_DIFFERENCE`. Revenue and quantity sources exist by SKU,
but SKU-level COGS is not mapped, so its exact embedded COGS amount remains
`INSUFFICIENT_SOURCE`. The official V1 Mix policy is unchanged.

## Option comparison

- Current / Option C: keep all production formulas and the current Residual.
- Option A: retain GP-based Quantity/Mix and subtract the matched overlap
  candidate from Inventory Timing.
- Option B: use Revenue-basis Quantity/Mix for analysis while retaining the
  current direct COGS/Inventory Timing structure.

Options A and B produce the same matched-scope counterfactual effects total
within tolerance, but neither is implemented. Their July–September
counterfactual effects total is approximately `-4,863,074,507.295` KRW and
Residual is approximately `-2,345,358,522.942` KRW. In every option the Excel
identity `effects_total + residual = OP_delta` is validated by formula.

## Source trace

- Product sales quantity and revenue: mapped `Data` rows for SW/BW/LC/FS.
- Product COGS: mapped `Data` rows SW 1595, BW 1634, LC 1670, FS 1722.
- P&L manufactured COGS: Finished Goods row 1269 and Semi-finished Goods row
  1280.
- Current manufacturing cost: row 325.
- Source references are emitted from validated Source Map/Adapter metadata;
  row references are Evidence metadata and are not Engine dependencies.

## Business decision gate

The current recommendation is `OPTION_C_PENDING_SCOPE_RECONCILIATION`.
Option A remains the first structural candidate after source reconciliation
because it preserves the established management meaning of GP-based
Quantity/Mix. It must not be implemented yet: LC currently combines the
manufactured sales quantity source (mapped row 56) with LC total Revenue/COGS
sources (mapped rows 1669/1670, including merchandise). The Workbook exposes
this as `MAPPING_GAP_LC_MANUFACTURED_QUANTITY_TOTAL_COGS` and also discloses the
New Business zero-Base-quantity/non-unitized Revenue boundary. A separate Slice
5C would need an approved, authoritative manufactured/merchandise source
contract before any production formula could change.

# Golden Model structural E2E validation

Validation date: 2026-08-09

Branch: `agent/phase2-worker-viewer`

Decision: **SYNTHETIC BRIDGE INVALID FOR FINAL RECONCILIATION**

This report does not change a deterministic formula or plug residual. The fixed
contracts are product-group-only Mix, uncapped
`COGS / current-period manufacturing input`, and
`effects_total + residual = operating_profit_delta`.

## 1. Structural preflight

The available 1,810-row, `Data`-sheet workbook passes the existing structural
preflight and Anchor checks. It is a structure-compatible validation source, not
the unavailable private `models/golden_model.xlsx` and not evidence that a
company comparison workbook was recalculated and saved by Excel.

Structural compatibility proves sheet/row/column/anchor expectations only. It
does not prove current cached formula values, custom-evaluator equivalence, or OP
Bridge completeness.

## 2. Formula evaluation coverage

| Workbook | Formula cells | Evaluator success | Cached fallback | Numeric evaluator-vs-cache mismatch | Blank/zero representation difference |
|---|---:|---:|---:|---:|---:|
| Base | 14,569 | 14,569 | 0 | 0 | 38 |
| ForecastEngine synthetic comparison | 14,562 | 14,562 | 0 | 292 in the P&L closure | reported separately |

The comparison's numeric differences are expected evidence that its Excel
cached values are stale after Python-side source changes; the file was not
opened, recalculated, and saved by Excel. Runtime comparisons use the custom
evaluator, so evaluator coverage—not the stale cache—controls synthetic validity.
The 38/39 nonnumeric differences are empty-string/blank/zero representation
differences and are reported separately.

## 3. Formula fallback list

The Base and current synthetic comparison have no formula fallback. Minimal
`AVERAGE` support covers exactly the Golden Model shapes formerly listed here:

- `K1734`, `L1734:P1734`: new-business COGS using historical average rate.
- `K345:K347`: manufacturing allocation ratios.
- `K956:K960`: material adjustment assumptions.
- `S927`, `S970`, `T927:X927`, `Y928:Y930`: downstream summary averages.

All 24 formulas now evaluate exactly to their cached values. Zero is included;
referenced blank/text/logical values are ignored; errors propagate; no numeric
value raises the normal fallback signal. Existing cached-fallback runtime
semantics remain unchanged for unsupported or error formulas.

The former synthetic `K106 = K105/K104` zero denominator came from omitting LC
purchased goods when seeding ForecastEngine. The harness now preserves both LC
components; K104 is positive and K106 evaluates. This was a
`VALIDATION_ARTIFACT`, not a production-formula defect.

## 4. P&L dependency coverage

The mapped K-month outputs are revenue `K1248`, COGS `K1268`, gross profit
`K1298`, selling expense `K1302`, G&A `K1303`, and OP `K1306`.

| Workbook | Relevant P&L formulas | Evaluated | Fallbacks | Status |
|---|---:|---:|---:|---|
| Base | 2,120 | 2,120 | 0 | FORMULA_COMPLETE |
| Synthetic comparison | 2,113 | 2,113 | 0 | FORMULA_COMPLETE, caches stale |

Base P&L closure has zero numeric evaluator/cache mismatch (two blank/zero
representation differences only). Synthetic P&L closure has 292 numeric cache
mismatches because Excel has not recalculated it. Its composite residual is not
final business evidence even though custom formula propagation is complete.

## 5. Single-driver validation

Each scenario starts from a fresh Base copy. Amounts are KRW.

| Driver | Source(s) | Propagation | OP delta | Deterministic effect | Residual | Assessment |
|---|---|---|---:|---:|---:|---|
| Sales quantity | FS inputs; freight zeroed on both controlled sides | Complete | 31,944,443.192 | 31,944,443.192 | -0.000004 | PASS; no non-target effect |
| Product-group Mix | SW400↔BW400, total PCS fixed | Complete | 32,534,928.969 | 26,831,230.049 | 5,703,698.920 | `INTENTIONAL_SCOPE_GAP`; no SKU-Mix effect added |
| Sales price | `K33` | Complete | 181,634,784.757 | 181,634,784.757 | ~0 | PASS |
| Sales FX | all positive-quantity revenue sources + LC goods, external FX | Complete | 848,087,451.343 | 848,087,451.343 | ~0 | PASS |
| JPY | `K9` | Complete | -5,237,216.399 | -30,053,381.053 | 24,816,164.654 | `INVENTORY_TIMING` candidate |
| Nonwoven price | controlled `K11` assumption | Complete | -5,237,216.399 | -30,053,381.053 | 24,816,164.654 | synthetic source; `INVENTORY_TIMING` candidate |
| Materials excluding nonwoven | component `K209` | Complete | -2,086,460.508 | -11,973,000.144 | 9,886,539.636 | `INVENTORY_TIMING` candidate |
| One variable manufacturing account | `K297` +10m | Complete | -2,722,346.898 | -10,630,750.874 | 7,908,403.977 | `INVENTORY_TIMING` candidate |
| Manufacturing salary | `K290` +50m | Complete | -10,884,930.139 | -53,152,175.077 | 42,267,244.938 | `INVENTORY_TIMING` candidate |
| Production quantity | `K556` +5% | Formula complete | 7,701,681.388 | 2,640,897.207 | 5,060,784.181 | `INVENTORY_TIMING` candidate |
| Variable SGA | `K1194` +10m | Complete | -10,000,000 | -10,000,000 | 0 | PASS |
| Fixed SGA | `K1200` +10m | Complete | -10,000,000 | -10,000,000 | 0 | PASS |
| Customer freight | `K1168` +10m | Complete | -10,000,000 | -10,000,000 | ~0 | PASS |
| Tariff | external metadata +13m | External driver | -13,000,000 | -13,000,000 | 0 | PASS |

The previously reported “salary +50m” changed `K301`, which is depreciation.
The corrected salary source is `K290`; the earlier -11.443m/-53.154m/41.711m
figures are therefore not a salary isolation result.

## 6. Sales

Level 1 sales identities match their independent source calculations. V1 Mix is
only SW/BW/LC/FS/new-business product-group Mix. SKU-internal composition is not
promoted to an effect. The quantity harness now uses a controlled pair with
customer freight set to zero on both sides. It produces no non-target price
component and records the control as `CONTROLLED_TEST_ASSUMPTION`.

The former KRW 306,863 price component was a validation artifact that exposed a
real adapter limitation: `transport_activity` combines PCS-based SW/BW/LC with
FS LENGTH, while LC totals can be paired with manufactured-only quantity. This
is `ENGINE_BUG` plus `BUSINESS_POLICY_GAP`; no allocation policy is invented.

## 7. Materials

`K205:K211` and `K684:K699` formulas are supported except where they consume
explicit cached assumptions. Component `K209` has a supported route through
material allocation to `K1268` and `K1306`. In contrast:

```text
K211 -> K321
K699 -> K321
K321 -> K324 / K327
```

No `K321 -> K1268/K1306` formula path exists. Rows 211/699 are therefore
`INTENTIONAL_ANALYSIS_BASIS` pools in the adapter, not direct P&L drivers.
Treating a direct-total overwrite as proof of a workbook mapping defect is a
`VALIDATION_ARTIFACT`; the totals are not connected to P&L and are not wired in
this change.

## 8. Manufacturing

The corrected salary chain is complete with zero source-path fallback:

```text
K290 -> K294 -> K289 -> K339 -> ... -> K1154 -> K1269 -> K1268 -> K1298 -> K1306
```

The workbook marginal OP response to +50m salary is -10.885m while the fixed
uncapped policy produces -53.152m. This is classified as an actual inventory/
cost-recognition timing candidate, not an evaluator-path gap, mapping rewrite,
or engine bug. It may be reported as a candidate “inventory/cost timing estimated
effect” only; no deterministic effect is added in this phase.

## 9. SGA

Variable SGA, fixed SGA, customer delivery freight, and external tariff isolate
to zero residual (within floating tolerance). Customer freight remains in the
sales transport decomposition and is not double-counted as SGA.

## 10. FX

Sales FX and JPY are kept separate, then regrouped for presentation without
changing `effects_total`. JPY remains direct KRW/JPY with no `/100`. The pure
sales-FX construction reconciles; the JPY OP gap is an inventory-timing candidate.

## 11. MCM

MCM remains an independent worker/adapter record used to exclude outsourced
quantity from the outsourcing denominator. It is not a standalone deterministic
effect and does not expand V1 Mix.

## 12. Residual three-level assessment

- Level 1 — Calculation identity: PASS for independently rederived sales,
  material three-component, manufacturing activity/unit/fixed, SGA, FX
  regrouping, and the plus-only residual identity.
- Level 2 — Workbook propagation: Base PASS; synthetic evaluator propagation
  PASS but Excel-cache freshness CHECK (292 P&L numeric mismatches).
- Level 3 — OP Bridge completeness: CHECK for the composite synthetic
  comparison. Its residual is not final business evidence.

Residual cause codes used are `VALIDATION_ARTIFACT`,
`FORMULA_EVALUATOR_GAP`, `MAPPING_GAP`, `ENGINE_BUG`,
`INTENTIONAL_SCOPE_GAP`, `INVENTORY_TIMING`, `BUSINESS_POLICY_GAP`, and
`UNEXPLAINED`. No residual is automatically converted into a new effect.

## 13. Validation artifact / real mapping gap distinction

Confirmed validation artifacts are stale comparison caches, the former K106
zero denominator, the old K301-as-salary scenario, direct-total 211/699 OP
assumptions, and the former freight-adjusted quantity construction. The
mixed-unit transport denominator is a confirmed engine limitation, but no
allocation policy is invented. No real P&L mapping gap is proven. The 211/699 source semantics need
business confirmation only if they are intended to be P&L drivers rather than
analysis pools.

## 14. Remaining validation on the actual Golden Model

Final approval requires two structurally identical workbooks that Excel has
actually recalculated and saved: Base Golden Model and Comparison Golden Model.
They must have current cached formulas. Until supplied, real OP propagation,
comparison cached-value freshness, actual 211/699 intent, and full Bridge
completeness are **BLOCKED**. The private `models/golden_model.xlsx` is absent;
the known `sales_fx` monkeypatch signature issue is tracked separately.

## 15. Supabase Live E2E readiness

**OFFLINE READY; LIVE BLOCKED.** Worker/publication separation, formula
diagnostics, and pair freshness gating are implemented offline. Structural preflight and Level 1 calculation identities
can be tested offline, but the synthetic Bridge is invalid for final
reconciliation and the Excel-calculated Base/Comparison pair is unavailable.
No credentials are connected and no live deployment is performed. Supabase live
E2E approval must wait for both an Excel-calculated pair and an authorized live
environment.

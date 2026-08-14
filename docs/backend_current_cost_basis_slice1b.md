# Backend Current Manufacturing Cost Basis Gap — Slice 1B

## Dependency map

| Boundary | Symbols | Upstream callers | Canonical/source boundary | Downstream impact | Existing tests |
|---|---|---|---|---|---|
| Golden adapter | `GoldenAnalysisAdapter.build`, `_material_products`, `_inventory_source_validation` | `GenericComparisonEngine._extract`, validation scripts, adapter tests | All Golden row numbers remain in `config/model_mapping.json`; the adapter emits normalized current-cost components and audit references | `AnalysisScenario`, comparison result, evidence source trace | `test_golden_analysis_adapter.py`, `test_phase2_preflight.py` |
| Canonical schema | `ProductRecord`, `ExpenseRecord`, `CurrentCostComponentRecord`, `AnalysisScenario` | Golden adapter, direct engine tests | Material source components and row-325 components carry business meaning, values, formulas, and references without row-number use in the engine | material/manufacturing/basis analysis | `test_analysis_v1.py`, `test_inventory_timing.py` |
| Raw-material engine | `calculate_material_effects` | `AnalysisEngine.compare`, `GenericComparisonEngine.compare`, Golden adapter presentation assembly | Existing total formula remains `(Base unit cost - Comparison unit cost) × Comparison sales basis`; source components use the same denominators and sum back to the unchanged total | material detail and current-cost basis evidence only | `test_material_effects.py`, Golden regression |
| Manufacturing engine | `calculate_manufacturing_effects` | canonical and generic comparison engines | Existing activity/unit/fixed formulas remain unchanged; component metadata only separates labor from manufacturing expense | current-cost basis evidence; no new bridge effect | manufacturing effect tests |
| Basis analysis | `calculate_current_cost_basis_analysis` | canonical and generic comparison engines | Direct row-325 components are compared with existing driver components; no residual or plug is created | nested `current_cost_basis_analysis`, evidence workbook | new `test_current_cost_basis.py` |
| Inventory engine | `calculate_inventory_timing_effects` | canonical and generic comparison engines | Official Inventory Timing formula is unchanged | existing `inventory_timing` top-level effect | `test_inventory_timing.py` |
| Evidence workbook | `_write_current_cost_basis`, `_analysis_source_specs` | comparison audit workbook/evidence history | Formula-bearing reconciliation links direct components, existing driver components, basis gap, and validation | separate audit sheet; no Golden overwrite | `test_analysis_export.py` |

## Verified Golden formula boundary

- `Current Manufacturing Cost (row 325) = Raw-material total (row 324) + Manufacturing processing total (row 319)`.
- `Raw-material total (row 324) = Production issue raw materials (row 321) + Raw-material tariff refund adjustment (row 322) + Paid supply (row 323)`.
- `Manufacturing processing total (row 319) = Labor (row 289) + Manufacturing expense (row 296)`.
- `row 289 = rows 294 + 295`; `row 296 = SUM(rows 297:318)`.

The current-cost basis analysis is explanatory evidence only. It does not change Quantity/Mix/Price/FX, raw-material, manufacturing activity/unit/fixed, Inventory Timing, residual, or OP-bridge formulas.

## Golden A/B result (2026-07 through 2026-09)

| Component | Base | Comparison | Direct difference | Existing effect | Gap | Reason |
|---|---:|---:|---:|---:|---:|---|
| Production-issue raw material (row 321) | 16,388,119,726.118 | 16,400,463,461.000 | -12,343,734.882 | -197,818,212.212 | +185,474,477.330 | Direct amount and canonical unit-cost × Comparison-basis driver use different formula bases. |
| Tariff refund adjustment (row 322) | 0.000 | -147,643,370.000 | +147,643,370.000 | 0.000 | +147,643,370.000 | Direct current-cost adjustment is outside the canonical Raw Material driver. |
| Paid supply (row 323) | 0.000 | 3,376,126,910.000 | -3,376,126,910.000 | 0.000 | -3,376,126,910.000 | No direct dependency maps this current-cost source to the canonical Raw Material/MCM driver. |
| Labor (row 289) | 8,398,408,590.336 | 6,870,067,369.000 | +1,528,341,221.336 | +1,528,341,221.336 | 0.000 | Existing fixed component ties to the direct amount. |
| Manufacturing expense (row 296) | 20,815,025,625.807 | 21,331,005,616.000 | -515,979,990.193 | -515,979,990.193 | 0.000 | Existing activity + unit + fixed components tie to the direct amount. |

The direct current manufacturing cost effect is `-2,228,466,043.739`. The
existing Raw Material plus Manufacturing driver subtotal is
`+814,543,018.931`, so the Basis Gap is `-3,043,009,062.670`.

The manufacturing subtotal is fully reconciled. The raw-material-side gap is:

- formula-scope difference (row 321 vs canonical Raw Material): `+185,474,477.330`
- excluded current-cost adjustment (row 322): `+147,643,370.000`
- source-scope difference (row 323): `-3,376,126,910.000`
- unexplained: `0.000` within the existing KRW 1 tolerance

## Architecture decision

- **Option A** means existing drivers fully decompose direct current manufacturing cost.
- **Option B** means both Raw Material and Manufacturing drivers intentionally use bases different from the direct source.
- **Option C** means part is directly decomposable while part has a structural business-policy basis difference.

Golden A/B is **Option C**: Manufacturing direct cost is exactly decomposed by
Activity + Unit Cost + Fixed, while the canonical Raw Material driver uses a
production/output unit-cost and Comparison sales/applicable basis that does not
directly decompose rows 321–323.

The approved formulas remain unchanged. Until a separate business-policy
decision is made, `inventory_timing` stays the single additive timing effect and
the Basis Gap is disclosed only as evidence. A future bridge redesign may make
direct Current Manufacturing Cost/Manufactured COGS the additive level and move
driver analysis below it as non-additive explanation, but this Slice does not
make that change.

## Residual and evidence

- OP delta: `-7,208,433,030.237`
- effects total: `+9,313,086,812.924`
- residual (unchanged): `-16,521,519,843.161`
- Basis Gap mathematically linked to residual attribution: `-3,043,009,062.670`
- residual remainder: `-13,478,510,780.491`
- plug created: `false`

The `당기제조원가_기준차이` evidence sheet connects direct source cells,
existing driver totals, component gaps, classifications, and residual disclosure
using Excel formulas. Source trace includes rows 289, 296, 319, 321–325. The
Golden workbooks are read-only inputs and are never overwritten.

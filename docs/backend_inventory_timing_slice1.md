# Backend Inventory Timing Slice 1

## Dependency map

| Boundary | Modified symbol | Upstream callers | Schema / source boundary | Downstream impact | Existing regression |
|---|---|---|---|---|---|
| Golden adapter | `GoldenAnalysisAdapter.build`, `manufacturing_accounts` | `GenericComparisonEngine._extract`, Golden validation scripts, adapter tests | `analysis_adapter.inventory_timing` resolves all row numbers; the engine receives canonical values only | comparison result, evidence source trace | `test_golden_analysis_adapter.py`, `test_comparison_analysis_bridge.py` |
| Canonical schema | `InventoryCostRecord`, `OpeningInventoryUnitRecord`, `AnalysisScenario` | Golden adapter, direct analysis tests | `current_manufacturing_cost`, finished/semi-finished COGS, opening quantities/amounts and audit references | engine and export payload | `test_inventory_timing.py`, `test_analysis_v1.py` |
| Manufacturing engine | `calculate_manufacturing_effects` | `AnalysisEngine.compare`, `GenericComparisonEngine.compare`, adapter account assembly | existing activity/unit/fixed formulas unchanged; realization rate retained as reference only | `manufacturing_realized` compatibility code now carries occurrence effect | analysis, bridge, presentation and Golden tests |
| Inventory engine | `calculate_inventory_timing_effects`, `classify_persistence` | canonical engine and generic comparison | no row numbers; independent canonical sources | one `inventory_timing` bridge effect plus explanation metadata | `test_inventory_timing.py` |
| Result assembly | `GenericComparisonEngine.compare`, `AnalysisEngine.compare` | worker/result persistence | canonical ten-effect contract | OP bridge, residual identity, BFF | bridge and presentation tests |
| Presentation | backend/frontend effect orders and drill-down contracts | BFF response and dashboard builders | exact effect set contains `inventory_timing` once | dashboard/presentation clients | presentation and dashboard suites |
| Evidence workbook | `_write_inventory_timing`, source-trace specs | comparison audit export and evidence history | canonical result plus audited Golden references | formula-bearing XLSX | `test_analysis_export.py` |

No Slice 2 forecast product-cost boundary was changed.

The Slice 1A mapping identity was published as `analysis-v1.1.0`; Slice 1B
supersedes it with `analysis-v1.2.0`. Existing stored
Results retain their pinned mapping version/hash and are not silently treated
as current under the new ten-effect contract; the result schema remains the
existing JSON envelope because the additive inventory payload is carried
inside the stored canonical Result.

## Golden source validation

Pinned read-only pair:

- Base SHA-256: `01480ddfa16382f93e227c60a4d0e73bf6a7aef3b30b59c681992eb4e5a0f4d4`
- Comparison SHA-256: `9f02bb4f1375737085255ed9aa61478480206749f7eff76811aa437c70b2b00e`
- Both workbooks have 1,838 `Data` rows and use the checked-in P&L anchors.

Validated sources:

| Candidate | Actual source | Representative formula | Canonical field | Scope decision |
|---|---|---|---|---|
| row 325 | `제조원가` | `K325=K324+K319` | `current_manufacturing_cost` | PASS: raw-material total plus manufacturing-processing total for current manufacturing input |
| row 1269 | `1. 제품 매출원가(천원)` | Base `IF(K3="실적",K1154+K1274+K1270+K1271+K1272+K1273,K1154+K1274+K1273)`; comparison non-actual branch omits disposal | `finished_goods_cogs` | PASS with explicit embedded product adjustment rows 1270:1274 |
| row 1380 | `외주가공비` | `K1380=K408` | none | REJECTED: not semi-finished COGS |
| row 1280 | `2. 반제품 매출원가(천원)` | `IF(K$3="실적",K536+K1282+K1283+K1281,K536+K1281)` | `semi_finished_goods_cogs` | PASS with explicit semi-finished adjustment rows 1281:1283 |

`Data!1268` proves the P&L COGS partition:

`total COGS = product COGS + semi-finished COGS + goods COGS + other COGS + inventory valuation loss`.

Therefore manufactured COGS is explicitly rows 1269 + 1280. Goods COGS (including LC/new-business goods), other COGS and inventory valuation loss are excluded. Freight remains SG&A and tariff remains its existing separate direct effect. No residual or plug participates in the inventory formula.

The 7–9 month representative pair is Base `계획` versus Comparison `추정`, as read from `Data!K3:M3`. The implementation is scenario-neutral and will retain `실적` comparison values when an actual comparison model is supplied; this particular Golden pair does not contain a Base-plan/Comparison-actual overlap for those months.

## Formula and double-counting evidence

Official sign convention is Base minus Comparison:

- Manufactured COGS Effect = `7,447,538,173.269`
- Current Manufacturing Cost Effect = `-2,228,466,043.739`
- Inventory Timing Effect = `9,676,004,217.008`

The existing raw-material plus manufacturing-driver subtotal is `814,543,018.931`; its difference from Current Manufacturing Cost Effect is `-3,043,009,062.670`. This is not plugged. The business cause is a basis mismatch: existing material effects apply unit-cost differences to comparison sales/input quantities, while manufacturing effects decompose account occurrence into activity/unit/fixed drivers; row 325 is the total current-period manufacturing-input amount. Inventory Timing is still independently sourced and included once, while the disclosed current-cost driver gap remains in normal reconciliation residual.

The legacy realization-applied manufacturing effect for 7–9 months was `1,044,592,554.992`. With the multiplier removed, the unchanged occurrence formulas produce `1,012,361,231.143`, a `-32,231,323.849` change.

The resulting bridge is:

- OP delta: `-7,208,433,030.237`
- effects total: `9,313,086,812.924`
- residual: `-16,521,519,843.161`
- effects total + residual: `-7,208,433,030.237` (PASS)

Residual remains the reconciliation difference; no residual classification amount is used to derive Inventory Timing.

## Explanation policy evidence

- Rolling 3M inventory effects: July `3,728,859,291.416`, August `906,072,914.338`, September `5,041,072,011.255`.
- Persistence: `CONSISTENT`.
- Opening-unit evidence uses FS `LENGTH (m)` and SW/BW/LC `PCS`; LC is `4-inch`. There is no PCS + LENGTH aggregation.
- Latest-month opening-unit deltas are FS `-921.325/m`, SW `-12,380.393/PCS`, BW `-28,817.161/PCS`, LC `-3,109.723/PCS`, all directionally supporting improvement.
- Product-unit coverage is `LIMITED` because rolling/WIP and other inventory layers are not quantified.
- No authoritative business materiality threshold exists. Status is `UNCONFIGURED` and the deterministic decision is `NO_PRIMARY`, confidence `LOW`, with supporting/reference evidence preserved.

## Golden A/B interpretation

Quantity/Mix/Price/FX, raw-material and manufacturing occurrence formulas were not changed. The bridge changes for two explicit business reasons only:

1. the final manufacturing realization multiplier was removed; and
2. the independently sourced Inventory Timing effect was added once.

The residual is recomputed by the existing identity and was not edited or reclassified as a plug.

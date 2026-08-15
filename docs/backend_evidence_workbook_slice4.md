# Slice 4 — Evidence Workbook Full Traceability

## Scope

Slice 4 changes Evidence generation only. It does not change the canonical
Quantity, Mix, Price, Sales FX, Raw Material, Manufacturing, Inventory Timing,
Forecast Merchandise, tariff, residual, or persistence policies.

The persisted comparison Result now includes additive audit metadata:

- sales product-group rows, PCS/LENGTH pool totals, and freight/tariff rows;
- raw-material driver rows and nonwoven KRW/JPY decomposition rows;
- manufacturing account allocation, activity denominator, unit-cost, and
  occurrence rows;
- validated Golden Source References for those canonical inputs.

Golden row addresses remain evidence metadata. Engine formulas continue to
consume canonical records rather than Golden row numbers.

## Workbook sheets

| Sheet | Purpose |
|---|---|
| `판매효과_근거` | Product-group inputs; PCS/LENGTH pool Quantity and Mix; symmetric Price/FX; freight in Price once; tariff separate |
| `원부재료_근거` | Canonical material unit-cost driver; nonwoven total; KRW/JPY; other-material decomposition |
| `제조경비_근거` | Front LENGTH(m)/back PCS production denominators; baseline allocation ratio; Volume/Unit/Fixed formulas |
| `재고원가반영시차_근거` | Manufactured COGS, current manufacturing cost, Inventory Timing, rolling 3M, opening inventory, explanation metadata |
| `상품원가검증` | Explicit link to the authoritative Slice 2B Forecast workbook sheet; no duplicate calculation |
| `당기제조원가_기준차이` | Slice 1B direct-current-cost versus canonical-driver Basis Gap disclosure; no new Effect or plug |
| `판관비_검증` | Account-level Base minus Comparison formulas and Bridge position |
| `최종Bridge_검증` | Direct references to detail formula cells, Engine comparison, double-count gates, and OP identity |
| `수식_정의` | Formula and policy catalog |
| `원천셀_추적` | Source mapping/cell/formula/value trace when pinned sources are available; stored SHA/provenance otherwise |

## Formula identities

- Quantity by pool: `(Comparison total quantity - Base total quantity) × Σ(Base mix × Base GP/unit)`
- Mix by pool: `Comparison total quantity × Σ((Comparison mix - Base mix) × Base GP/unit)`
- Price: symmetric foreign-price effect plus customer-delivery freight once
- Sales FX: symmetric FX component, separate from Price
- Raw Material: `(Base unit cost - Comparison unit cost) × Comparison applicable sales basis`
- Nonwoven JPY: `Comparison input length × Base JPY unit × (Base JPY FX - Comparison JPY FX)`
- Manufacturing: `Volume + Unit + Fixed`; inventory realization is reference-only
- Inventory Timing: `Manufactured COGS Effect - Current Manufacturing Cost Effect`
- Bridge: `effects_total + residual = OP_delta`

Every identity above is emitted as an Excel formula. Engine output is stored in
an adjacent cell only for reconciliation.

## Validation

Generation rejects explicit `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, broken
sheet references, and broken defined-name destinations. The final Bridge also
checks that Freight, tariff, Raw Material FX, manufacturing children,
Inventory Timing, Forecast Merchandise scope, and Current Cost Basis Gap are
not double-counted.

Repository acceptance uses deterministic Golden fixtures and Microsoft Excel
full recalculation/rendering. Private Golden acceptance remains an external
environment gate when private source workbooks are unavailable.

# Slice 5D — Core Manufactured COGS Overlap Production Policy

## Decision

The V1 Sales Quantity and Mix formulas remain unchanged. They continue to use
Base GP/unit and therefore already contain the Base COGS consequence of the
matched sales quantity and between-product-group mix movement.

Production Inventory Timing now uses:

```text
Gross Inventory Timing
  = Manufactured COGS Effect - Current Manufacturing Cost Effect

Core Manufactured COGS Overlap
  = Core Quantity COGS Overlap + Core Mix COGS Overlap

Net Inventory Timing
  = Gross Inventory Timing - Core Manufactured COGS Overlap
```

Only Net Inventory Timing is additive in the OP Bridge. Gross Inventory Timing
and all overlap amounts are non-additive evidence children. No new top-level
Effect was introduced.

## Authoritative core source contract

The Golden adapter resolves source locations from `config/model_mapping.json`
and emits canonical `CoreManufacturedCogsRecord` rows. The calculator does not
depend on Golden row numbers.

| Group | Pool/unit | Core COGS source | Quantity source | Excluded source |
|---|---|---|---|---|
| SW | PCS | SW400 + SW440 core product COGS (rows 1031, 1056) | manufactured sales quantity (row 1593) | SW adjustment (rows 1572, 1585) |
| BW | PCS | BW400 + BW440 core product COGS (rows 1081, 1106) | manufactured sales quantity (row 1632) | BW adjustment (rows 1611, 1624) |
| LC | PCS, 4-inch | manufactured LC core COGS (row 1131) | manufactured LC quantity (row 1645) | LC adjustment (row 1650), merchandise (row 1660) |
| FS | LENGTH(m) | FS_SW + FS_BW + FS_TW semi-finished COGS (rows 473, 494, 515) | manufactured FS length (row 1720) | FS adjustments (rows 1686, 1699, 1712) |

The contract fails closed for an absent mapped source, non-positive Base
denominator, duplicate month/group record, or pool/unit mismatch. PCS and
LENGTH quantities are never aggregated together; only KRW effects are summed.

Explicit exclusions are product-group adjustments, P&L finished/semi-finished
adjustments, LC merchandise, New Business merchandise, Other COGS, inventory or
period adjustments, and current-cost row 323 paid supply.

Row 323 remains a Current Manufacturing Cost source and Current Cost Basis Gap
disclosure. It is not a Raw Material, MCM, separate paid-supply, overlap, or
Residual-plug Effect.

## Formula and sign

For each month, pool, and product group `i`:

```text
Base Core COGS/unit_i = Base Core Manufactured COGS_i / Base Quantity_i

Embedded Core COGS Quantity expense_i
  = (Comparison Pool Quantity - Base Pool Quantity)
    × Base Mix_i × Base Core COGS/unit_i

Core COGS Quantity Overlap Effect_i
  = - Embedded Core COGS Quantity expense_i

Embedded Core COGS Mix expense_i
  = Comparison Pool Quantity
    × (Comparison Mix_i - Base Mix_i)
    × Base Core COGS/unit_i

Core COGS Mix Overlap Effect_i
  = - Embedded Core COGS Mix expense_i
```

The overlap uses the OP-effect sign convention: positive is OP improvement and
negative is OP deterioration.

## Actual Golden acceptance — 2026 Jul–Sep

Golden input hashes before and after generation:

- Base: `01480ddfa16382f93e227c60a4d0e73bf6a7aef3b30b59c681992eb4e5a0f4d4`
- Comparison: `9f02bb4f1375737085255ed9aa61478480206749f7eff76811aa437c70b2b00e`

| Period | Gross Inventory Timing | Quantity overlap | Mix overlap | Total overlap | Net Inventory Timing |
|---|---:|---:|---:|---:|---:|
| 2026-07 | 3,728,859,291.416 | 5,803,247,549.828 | 224,498,826.705 | 6,027,746,376.533 | -2,298,887,085.118 |
| 2026-08 | 906,072,914.338 | -7,993,815.811 | 132,683,485.580 | 124,689,669.769 | 781,383,244.569 |
| 2026-09 | 5,041,072,011.255 | 7,904,739,839.156 | 178,705,699.333 | 8,083,445,538.489 | -3,042,373,527.234 |
| Jul–Sep | 9,676,004,217.008 | 13,699,993,573.173 | 535,888,011.618 | 14,235,881,584.791 | -4,559,877,367.783 |

Quantity remains `-3,045,998,282.262`, Mix remains
`-3,242,936,639.675`, and OP Delta remains `-7,208,433,030.237`.
Effects Total changes from `9,313,086,812.924` to `-4,922,794,771.868`.
Residual is authoritatively recalculated from `-16,521,519,843.161` to
`-2,285,638,258.369`; it is not manually targeted or plugged.

The updated Residual RCA classified total equals the new Residual within
floating-point tolerance. `UNEXPLAINED` is approximately `-0.000006 KRW`, which
is numeric round-off and not a Source component. The OP identity remains:

```text
-4,922,794,771.868 + -2,285,638,258.369 = -7,208,433,030.237
```

Rolling 3M now uses the monthly Net Inventory Timing values and is `MIXED` for
Jul–Sep, rather than explaining the production Effect with Gross values.

## Evidence and compatibility

`재고원가반영시차_근거` exposes Gross, pool/group Core Quantity and Mix
overlap formulas, exclusions, Net, monthly trend, Source References, and
Engine/Evidence checks. `최종Bridge_검증` references the Net cell once; Gross
and overlap are reference-only. `Residual_RCA` contains the non-additive overlap
deduction component so its waterfall reconciles to the new Residual.

Historic stored presentation payloads without Slice 5D fields retain their
legacy Gross identity. New payloads validate both `Gross - Overlap = Net` and
`Quantity overlap + Mix overlap = Total overlap` and fail closed on mismatch.

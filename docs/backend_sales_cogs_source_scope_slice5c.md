# Slice 5C — Sales/Product COGS ↔ P&L Manufactured COGS Source Scope

## Status

- Repository / actual Golden Source RCA: **PASS**
- Source-scope verdict: **OVERLAP_CONFIRMED**
- Decision gate: **OPTION_A_NOT_READY**
- Production Quantity, Mix, Inventory Timing, Residual, and OP Delta formulas: unchanged
- Golden SHA-256 before/after: unchanged

## Sign convention

All COGS effects below use the OP bridge sign: `Base cost - Comparison cost`.
Positive values improve OP.  The Slice 5B embedded COGS expense sign is the
opposite (`Comparison cost - Base cost`).

## Authoritative source contracts

### Sales Product COGS

| Group | Sales total | P&L-core matched source | Sales-only adjustment | Classification |
|---|---|---|---|---|
| SW | `Data!1595` | `Data!1031 + Data!1056` | `Data!1572 + Data!1585` | MANUFACTURED_ONLY |
| BW | `Data!1634` | `Data!1081 + Data!1106` | `Data!1611 + Data!1624` | MANUFACTURED_ONLY |
| LC | `Data!1670` | `Data!1131` | `Data!1650`; merchandise `Data!1660` | MANUFACTURED_AND_MERCHANDISE_SEPARABLE |
| FS | `Data!1722` | `Data!473 + Data!494 + Data!515` (`Data!536`) | `Data!1686 + Data!1699 + Data!1712` | SEMI_FINISHED_SCOPE |

### P&L Manufactured COGS

```text
P&L Manufactured COGS
= Finished Goods COGS Data!1269
+ Semi-finished Goods COGS Data!1280

P&L core source
= Data!1154 (Data!1031 + 1056 + 1081 + 1106 + 1131)
+ Data!536  (Data!473 + 494 + 515)
```

`Data!1269` and `Data!1280` apply their own plan/actual branch adjustments.
The RCA uses the actual evaluated total less the core source, rather than
assuming every visible adjustment row is additive in every month.

## Scope difference decomposition (2026-07~09)

```text
Sales Product COGS effect                           +16,597,207,954.228
P&L Manufactured COGS effect                        +7,447,538,173.269
Scope Difference (Sales - P&L)                      +9,149,669,780.959

  SW Sales COGS adjustment                          +1,329,812,954.415
  BW Sales COGS adjustment                          +2,283,550,846.509
  LC Sales COGS adjustment                             +73,584,956.173
  FS Sales COGS adjustment                          +5,232,026,471.230
  LC merchandise COGS included in Sales               +638,096,827.946
  P&L finished-goods adjustment contribution          -566,543,982.314
  P&L semi-finished adjustment contribution           +159,141,707.000
  UNEXPLAINED                                                +0.000002
Classified total                                    +9,149,669,780.959
```

The floating-point remainder is below the OP-relative tolerance and is
displayed as zero in the Evidence Workbook.  No plug or estimated allocation
is used.

Monthly scope differences are:

| Month | Sales Product COGS | P&L Manufactured COGS | Scope Difference | Validation |
|---|---:|---:|---:|---|
| 2026-07 | 6,276,611,284.093 | 2,768,699,297.256 | 3,507,911,986.838 | PASS |
| 2026-08 | 1,513,524,150.421 | -1,534,575,168.427 | 3,048,099,318.849 | PASS |
| 2026-09 | 8,807,072,519.714 | 6,213,414,044.441 | 2,593,658,475.273 | PASS |

## LC source contract

For July, August, and September, all three identities close from Golden formulas:

```text
LC total quantity  Data!1668 = manufactured Data!1645 + merchandise Data!1658
LC total revenue   Data!1669 = manufactured Data!1646 + merchandise Data!1659
LC total COGS      Data!1670 = manufactured Data!1647 + merchandise Data!1660
LC manufactured COGS Data!1647 = P&L core Data!1131 + Sales adjustment Data!1650
```

Verdict: `LC_MANUFACTURED_MERCHANDISE_SEPARABLE`.  No proportional
allocation is used.

## New Business denominator

Base New Business has revenue and COGS but no Base quantity for all selected
months.  Comparison quantity appears only in August and September.  The
approved Forecast Merchandise contract also classifies this source as
merchandise (`Data!1733` revenue, `Data!1734` COGS).

Verdict: `MERCHANDISE_NON_UNITIZED_BASE`.  This is not a hidden mapping skip;
it remains excluded from the manufactured GP Quantity/Mix scope pending a
separate merchandise taxonomy decision.

## SKU/source coverage

| Group | Source detail | Coverage |
|---|---|---|
| SW | SW400 `32/33/(1031+1572)`; SW440 `38/39/(1056+1585)` | FULL |
| BW | BW400 `44/45/(1081+1611)`; BW440 `50/51/(1106+1624)` | FULL |
| LC | 4-inch `1645/1646/1647` | FULL |
| FS | FS_SW `1681/1682/(473+1686)`; FS_BW `1694/1695/(494+1699)`; FS_TW `1707/1708/(515+1712)` | FULL |

Coverage indicates source availability only.  It does not promote intra-group
SKU movement to a new production Mix effect.

## Matched embedded manufactured COGS

Using the same month, pool, product group, quantity, and P&L-core COGS source:

```text
Matched embedded Quantity expense component    -13,699,993,573.173
Matched embedded Mix expense component             -535,888,011.618
Matched embedded total expense component         -14,235,881,584.791
OP bridge overlap candidate                       +14,235,881,584.791
```

The matched core direct COGS effect is `+7,040,135,897.955`.  The remaining
`-7,195,745,686.837` is the matched unit-cost/other-source remainder, and the
identity closes.  Therefore the same manufactured Base COGS volume/mix
component is present in the GP-based Sales driver and inside the P&L
manufactured COGS side used by Inventory Timing.

## Counterfactuals (not production)

| Option | Inventory Timing | Effects Total | Residual | OP Delta |
|---|---:|---:|---:|---:|
| Current / Option C | 9,676,004,217.008 | 9,313,086,812.924 | -16,521,519,843.161 | -7,208,433,030.237 |
| Option A matched scope | -4,559,877,367.783 | -4,922,794,771.868 | -2,285,638,258.369 | -7,208,433,030.237 |
| Option B revenue basis | 9,676,004,217.008 | -4,863,074,507.295 | -2,345,358,522.942 | -7,208,433,030.237 |

Every option satisfies `effects_total + residual = OP_delta`.  Option A and B
differ by `59,720,264.573`, the now-explicit Sales-only COGS source-scope
component.  Neither option is persisted by Slice 5C.

## Decision

The core-source overlap is confirmed, but Option A remains
`OPTION_A_NOT_READY`.  Excluding the separately identified LC merchandise
component leaves `+8,511,572,953.013` of Sales/P&L adjustment-basis difference.
Those rows are fully source-traced and make `UNEXPLAINED = 0`, but there is no
approved Business Formula that allocates that formula-basis difference between
Sales and Inventory Timing.  Production therefore remains Option C/current.

The next approved design Slice must define that contract before Option A can be
implemented; Slice 5C does not change Inventory Timing or any Business Formula.

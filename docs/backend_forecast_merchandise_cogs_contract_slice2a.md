# Slice 2A — Forecast Merchandise COGS Contract Alignment

## Verdict

`CONTRACT_CONFLICT`

LC와 신사업에 각각 최신 확정 Actual 누계 상품원가율을 적용하는 목표 공식은 명확하다.

```text
Forecast Merchandise COGS
= Forecast Merchandise Revenue
× Latest Confirmed Actual YTD Merchandise COGS Rate
```

LC에는 현재 별도 상품원가 직접입력 계약이 없어 `DEFAULT_DERIVATION`으로 도입할 수 있다. 그러나 신사업은 최신 React/BFF/Engine 계약에서 `new_business_goods_cogs`가 실제 P&L에 직접 반영되는 authoritative 금액이다. 이 필드는 optional/null이 아니라 기본값 `0`인 숫자이므로, 현재 요청만으로는 “직접입력 없음”과 “0원으로 명시적 override”를 구분할 수 없다. 따라서 신사업 YTD 기본 산식과 기존 직접입력 계약의 precedence를 코드가 임의로 정할 수 없다.

Slice 2B 구현은 이 계약 결정 전까지 중단한다. Slice 1/1B와 생산배부 계약은 변경하지 않는다.

## Worktree and baseline

- Preserved reference worktree: `work/pnl-dashboard`
- Preserved branch: `agent/backend-forecast-merchandise-cogs-v1`
- Preserved HEAD: `756bd2b76af00bd6250935b3988adeb60a30ba35`
- Clean Slice 2A worktree: `work/pnl-dashboard-slice2a`
- Clean Slice 2A branch: `agent/backend-forecast-merchandise-cogs-contract-v1`
- Start HEAD: `756bd2b76af00bd6250935b3988adeb60a30ba35`
- `a18783b058e6cd169559f79a52df18cdc8cad23e` is an ancestor of the start HEAD; the start HEAD is two commits ahead.
- The preserved worktree was not reset, cleaned, stashed, rebased, or checked out. Its tracked diff hash remained unchanged while the clean worktree was created.

## Authoritative contract matrix

| Item | UI source and meaning | DTO / orchestration | Engine meaning | Workbook | Classification | Authoritative evidence |
|---|---|---|---|---|---|---|
| `new_business_goods_cogs` | Advanced input, “신사업 매출원가 직접 반영액”; default `0` | Numeric field, default `0`, validated nonnegative and forwarded unchanged | Added directly to LC goods COGS and written once to `special_rows.goods_cogs` | Direct override at `Data!<month>1289`; audit source `cogs.goods` | `AUTHORITATIVE_OVERRIDE_PRESERVED`; conflicts with an implicit YTD default because absence is not representable | React label/help, adapter round-trip tests, `ForecastInput`, Engine write, `test_forecast_keeps_reference_costs_manual_and_applies_cogs_adjustments` |
| `new_business_goods_cogs_reason` | Optional reason paired with direct amount | Safe text up to 500 characters, forwarded unchanged | Passed to the `cogs.goods` workbook write | Appears in `입력반영내역` reason column for the direct write | Preserve with the authoritative override | UI adapter tests, orchestration mapper, Engine `put(..., reason)` |
| `uf_mbr_cogs_rate` | Editable default 0.85; UI says reference only | Numeric 0..1, forwarded unchanged | Computes `UF_MBR amount × rate` only in result detail | No P&L cell write; no direct audit row | Reference input, not an applied override | React help text, README, Engine detail, baseline forecast test |
| `ix_cogs_rate` | Editable default 0.85; UI says reference only | Numeric 0..1, forwarded unchanged | Computes `IX amount × rate` only in result detail | No P&L cell write; no direct audit row | Reference input, not an applied override | React help text, README, Engine detail, baseline forecast test |
| LC merchandise revenue | User supplies one LC sales quantity and amount; Engine splits manufactured vs merchandise quantity using same-month LC production and applies the common LC sales unit price | Sales DTO is forwarded; production reaches Engine only after authoritative allocation on the React/BFF path | Merchandise revenue is `goods_qty × LC sales unit price`; written to mapped LC merchandise amount row | `Data!<month>105` through `lc_goods.amount_row` | Eligible for `DEFAULT_DERIVATION` of LC merchandise COGS | Engine LC split and workbook mapping |
| New-business merchandise revenue | User supplies UF/MBR and IX sales amounts | Sales DTO is forwarded unchanged | Revenue is `UF_MBR amount + IX amount` | `Data!<month>114` | Eligible as YTD-formula forecast revenue, but COGS precedence conflicts with the authoritative direct amount | Engine new-business revenue write and sales DTO tests |

Authority order used in this audit:

1. Active React labels/help and HTTP payload tests.
2. HTTP DTO, orchestration validation/mapping, and Engine write behavior.
3. Engine/Workbook regression tests.
4. README/CHANGELOG explanatory text.
5. `app.py` only as a legacy compatibility caller, not as the production contract.

## Exact conflict requiring a business decision

The current UI initializes `newBusinessGoodsCogs` to string `"0"`. The adapter converts blank or `"0"` to numeric `0`, and the HTTP/Engine dataclasses also default the field to `0`. The Engine treats that number as the applied new-business merchandise COGS. A baseline regression explicitly proves that the calculated UF/MBR+IX reference can be 2,550,000 while `Data!K1289` remains 0.

Consequently, this payload has no “not supplied” state:

```text
new_business_goods_cogs = 0
```

It can mean either:

- no manual override, so Actual YTD derivation should run; or
- an authoritative explicit zero override.

No existing authoritative source selects one meaning. Slice 2B therefore needs one approved contract, for example:

1. Add an explicit mode such as `ACTUAL_YTD_DEFAULT` / `MANUAL_OVERRIDE`, retaining zero as a valid manual value; or
2. Make the direct amount nullable and define `null = derive`, numeric including zero = override; or
3. Declare the direct amount always authoritative, in which case automatic new-business YTD COGS cannot replace it.

Options 1 and 2 change the UI/DTO contract and require separate approval. The current Slice 2 instructions do not authorize choosing one.

## Golden source conclusion from the preserved reference work

The candidate rate rows are not themselves YTD cells:

| Product | Candidate | Actual meaning | Numerator / denominator for authoritative YTD derivation | Forecast inclusion |
|---|---:|---|---|---|
| LC merchandise, 4-inch | 1661 | Monthly `매출원가율`, formula equivalent to row 1660 / row 1659 | Actual-month row 1660 COGS / Actual-month row 1659 revenue, aggregated only through the latest confirmed Actual month | Forecast months must be excluded |
| New business merchandise | 1736 | Monthly `매출원가율`, formula equivalent to row 1734 / row 1733 | Actual-month row 1734 COGS / Actual-month row 1733 revenue, aggregated only through the latest confirmed Actual month | Forecast months must be excluded |

Thus rows 1661/1736 are validation/reference rows. The reproducible YTD source is the actual-period numerator and denominator range. The preserved Golden pair identifies June as the latest confirmed Actual month in both workbooks; Comparison July–September are forecast/estimate, not confirmed Actual.

## Production allocation boundary

The latest production contract remains intact and outside Slice 2:

```text
React six business rows
→ HTTP BusinessProductionInput
→ ForecastProductionAllocationService
→ selected Base Model same-month SW/BW 400/440 ratios
→ canonical eight rows
→ ForecastEngine
```

The allocation module explicitly forbids sales mix, another-month inference, and fixed 50:50. Positive SW/BW input with a missing or zero same-month base denominator fails closed. The dirty Slice 2 reference does not need or justify changes to this boundary.

`app.py` directly constructs canonical production inputs and invokes `ForecastEngine`; it is a legacy compatibility caller. It must not cause allocation or fallback logic to be added to the shared Engine.

## Mapping provenance gate

Baseline active mapping provenance is `analysis-v1.2.0` with hash `38af747400d688ac2a15fa043d2219b36749471399755490ee73e6e70f70fd0f`. `ForecastProductionAllocationService._require_model` requires exact equality of both mapping version and hash with the selected registered Base Model.

The preserved dirty diff changes `model_mapping.json` and globally publishes `analysis-v1.3.0`. Porting that change would cause previously valid 1.2 Base Models to fail `_require_model` unless a separate migration/re-registration policy were approved. The exact guard must not be weakened.

Verdict: `NO_GLOBAL_BUMP_REQUIRED` is the recommended architecture for Slice 2B. Put the merchandise-only Golden source map in a separate forecast-specific mapping/config identity, validate and freeze it alongside the forecast run, and record its own version/hash in evidence. Do not change the registered Base Model’s `model_mapping` provenance. If implementation proves that separate configuration is impossible, stop with `GLOBAL_BUMP_REQUIRES_MIGRATION_POLICY` rather than updating the global mapping.

## Workbook contract

Slice 2B must extend the existing `GoldenWorkbook` writer only. That path:

1. writes input overrides;
2. appends `입력반영내역` next to `Data`;
3. preserves reason in column I and the target-cell hyperlink in column J;
4. sets workbook recalculation flags; and
5. removes stale `xl/calcChain.xml` before ZIP save.

A merchandise evidence sheet may be appended through this writer, but it must not create a parallel save path. If a manual new-business override is selected under the future approved contract, evidence must show the override source, amount, reason, and the YTD-derived reference separately.

## Dirty Slice 2 salvage matrix

| Preserved item | Decision | Reason |
|---|---|---|
| Golden row/label/formula investigation | `SAFE_TO_PORT` | Confirms monthly rate rows and actual numerator/denominator sources; corrects stale “Comparison actual through September” claim |
| Actual cutoff, Actual-only YTD aggregation, zero/missing validation, self-reference prevention in `forecast/merchandise_cogs.py` | `SAFE_TO_PORT` as logic, not wholesale file copy | The math and fail-closed concepts match the target rule; constructor/config integration must be reworked |
| `forecast/merchandise_cogs.py` as a whole | `REWORK_REQUIRED` | It reads the globally bumped mapping and has no approved new-business override state |
| Engine diff | `DO_NOT_PORT` wholesale | It labels four live inputs as ignored and silently drops the authoritative direct amount/reason |
| Orchestration validation-error mapping | `SAFE_TO_PORT` only if the corresponding source adapter is adopted | Error taxonomy improvement is independent, but imports currently depend on the unapproved module integration |
| Global `model_mapping.json` additions and mapping registry 1.3 bump | `DO_NOT_PORT` | Breaks exact registered-model provenance without migration policy |
| Forecast-specific source map concept | `SAFE_TO_PORT` after separation | Required to keep row numbers outside Engine without changing global Base Model provenance |
| Preflight additions | `REWORK_REQUIRED` | Must validate the separate forecast-specific source map, not the global model mapping |
| `상품원가검증` workbook sheet | `REWORK_REQUIRED` | Must include approved override/default mode, override source/reason, and YTD reference while reusing the existing save path |
| Evidence tests | `REWORK_REQUIRED` | Formula trace tests are useful; expectations must cover override semantics and unchanged provenance/calcChain behavior |
| Golden source tests | `SAFE_TO_PORT` after config separation | Label, formula, cutoff, denominator, and scope checks remain valid |
| Dirty Slice 2 documentation | `REWORK_REQUIRED` | It contains stale cutoff/provenance assumptions and does not preserve the current direct-input contract |
| `.pytest-temp-review/` | `DO_NOT_PORT` | Temporary test artifact only |

## Slice 2A stop decision

- LC dynamic YTD formula: contract-aligned in principle.
- New-business dynamic YTD formula: business target confirmed, but precedence against the existing authoritative direct amount is unresolved.
- Production allocation: unchanged and protected.
- Global mapping bump: rejected; separate forecast mapping recommended.
- Workbook provenance/calcChain path: must be reused unchanged.
- Slice 2B: **do not start until the new-business explicit-input mode is approved.**

## Verification and review

- Focused baseline regression: `46 passed, 15 skipped` across production allocation, business-production HTTP, and Forecast Engine tests.
- `git diff --check`: PASS.
- Reviewer: registered `luna-worker`, runtime `gpt-5.6-luna`, reasoning `max` (Luna Max).
- Reviewer blocker: the same `CONTRACT_CONFLICT` described above; no independent formula or cutoff blocker.
- Reviewer edits: none (read-only review).
- Code changes in Slice 2A: none. This document is the only clean-branch artifact.

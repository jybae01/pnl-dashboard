# Golden Business Acceptance

## Provenance

- Branch: `agent/golden-business-acceptance`
- Frozen base: `e3a3ec1aad50bb7abe940de715f1d0db0001eb43`
- Deployed runtime source before this acceptance: content-equivalent to the frozen base
- Base scenario: 2026 January-June actual, July-December plan
- Comparison scenario: 2026 January-June actual, July-September forecast, October-December plan
- Primary period: 2026-07 through 2026-09
- Secondary period: 2026-01 through 2026-12
- Existing tolerance: absolute `1.0`, relative `1e-9`, applied as the larger of the two

The Golden run pins both workbook identities, the mapping file, the period, the
scenario roles, and the backend source. It never performs an implicit
latest/default lookup.

## Workbook identity and calculation freshness

| Input | Original SHA-256 | Excel-recalculated SHA-256 |
|---|---|---|
| Base | `01480ddfa16382f93e227c60a4d0e73bf6a7aef3b30b59c681992eb4e5a0f4d4` | `f1bf4ee5ed319002ad0db1b1f6f61a2414f743fe2cbe50dfc5a6aa0ef574918d` |
| Comparison | `9f02bb4f1375737085255ed9aa61478480206749f7eff76811aa437c70b2b00e` | `f08581a8b76d2ff5ca6afef426d359152bd76954a9d289ca3edef2fd901f20ed` |

Microsoft Excel 15.0 opened only temporary copies with link updates, alerts,
events, and macros disabled. `CalculateFullRebuild` returned synchronously,
Excel reported ready before save, the copies were saved with the current Excel
calculation version, and no orphan Excel process remained. Excel 2013 retained
the application-wide `xlPending` state even after the synchronous rebuild;
freshness was therefore independently closed by zero Golden-relevant P&L cache
changes, zero numeric mismatches between the formula evaluator and cached
values, complete evaluation of the Golden-relevant model formulas, and a clean
save/reopen cycle. A ZIP-level original-versus-recalculated comparison found one
Base validation-only cached precision change at `Data!E983` (about `1e-11`) and
201 formula-representation normalizations; neither changes a Golden P&L output.
The Comparison had no original-versus-recalculated cached-value delta. The
original files were never opened for write.

Neither workbook contains an external link or workbook connection. The Base
has validation-only saved `#REF!` cells on `정합성확인`. The Comparison has the
same validation artifacts plus one isolated `Data` `#DIV/0!` cell. Reverse
dependency inspection found no path from that cell to the canonical monthly
Revenue, COGS, Gross Profit, or Operating Profit outputs.

## Acceptance result

- All 12 monthly P&L reconciliations passed without aggregate cancellation.
- Primary and secondary Base, Comparison, and Delta P&L reconciliations passed.
- Primary and secondary product-group reconciliations passed for every mapped
  canonical group, including SW, BW, LC, FS, and New Business.
- All nine current canonical Effect totals passed against the audit-only
  independent reference.
- The independent reference reads the configured raw source rows and applies
  the confirmed V1 formulas locally. It does not import a production Effect
  function or use an Engine amount as its expected value.
- `effects_total + residual = operating_profit_delta` passed for every month
  and both aggregate periods.
- Residual was not used as a plug. Its evidenced components are
  `INTENTIONAL_SCOPE_GAP` for same-group SKU composition excluded from V1 Mix,
  and `INVENTORY_TIMING` for the difference between realized workbook COGS and
  production-issue/current-input effect timing.
- Excel provides canonical P&L reference values but no Effect bridge oracle.
  Therefore `EXCEL EFFECT ORACLE = NOT_PRESENT` remains unchanged.

## Defect found and corrected

The Golden pair exposed an Engine defect: identical SG&A account labels can
occur in both selling-expense and general-administration sections. A dictionary
comprehension retained only the final row. The smallest safe correction sums
all source rows for an account before applying the existing variable/fixed
classification. A dedicated duplicate-label regression test covers the defect.

Because this is a production business-code change, the prior deployed-code
alignment is invalid. The Golden result applies to this branch after the fix;
staging must be rebuilt and redeployed from the accepted commit before release.

## Business and security non-regressions

- LC remains 4 inch.
- FS remains LENGTH/m; finished goods remain PCS; the two bases are never summed.
- JPY remains direct KRW/JPY with no division by 100.
- MCM is not promoted to a separate general raw-material Effect.
- Customer freight is counted once in sales price; Tariff remains separate.
- Same-group SKU composition is not V1 Mix.
- Residual stays separately classified and is never converted into an Effect.
- The backend remains the deterministic calculation authority; AI is not a
  calculation engine.
- No company workbook, credential, `.env`, or business-number evidence artifact
  is tracked by Git.

## Validation

- Golden targeted tests: 24 passed.
- Full Python: 391 passed, 18 existing private-Golden skips.
- Google readiness/worker lifecycle: 37 passed.
- React: 24 passed.
- TypeScript and production frontend build: passed.
- Frontend lint: passed with pre-existing unused-code warnings.
- npm audit: zero vulnerabilities.
- Python `compileall`: passed.
- Cloud Run web and runtime images: local `linux/amd64` builds passed; no push.
- `git diff --check`: passed.
- Credential and workbook tracking scan: passed. One pre-existing synthetic
  secret-format fixture remains unchanged from the frozen base.

## Verdict

- `GOLDEN EXCEL RECALCULATION = PASS`
- `GOLDEN BASE P&L = PASS`
- `GOLDEN COMPARISON P&L = PASS`
- `GOLDEN DELTA P&L = PASS`
- `GOLDEN MONTHLY RECONCILIATION = PASS`
- `GOLDEN PRODUCT GROUP RECONCILIATION = PASS`
- `GOLDEN EFFECT INDEPENDENT REFERENCE = PASS`
- `GOLDEN OP BRIDGE = PASS`
- `GOLDEN RESIDUAL CLASSIFICATION = PASS`
- `GOLDEN BUSINESS REGRESSION = PASS`
- `EXCEL EFFECT ORACLE = NOT_PRESENT`
- `GOLDEN BUSINESS GATE = PASS`
- `V1 BUSINESS RELEASE CANDIDATE = READY`
- `STAGING REDEPLOYMENT = REQUIRED`

# Frontend–Backend Integration Contract (T01/T02)

Status: `T01 PASS`; `T02 CONTRACT BASELINE PASS`. The React Core overlay adds a tested FastAPI transport and one runnable login→model pair→submit→poll→stored-result slice on top of Migration 005, plus additive Migration 006 for atomic published-model eligibility. This remains neither full React integration nor production/live Supabase readiness.

Evidence notation uses paths relative to the backend repository or to the root of the read-only frontend ZIP. `READY` means the complete browser-to-source contract already exists; a useful backend primitive alone is not enough.

## 1. Baselines and commit verification

### Backend baseline

| Item | Verified value |
|---|---|
| Repository | `jybae01/pnl-dashboard` |
| Base | PR #21 exact HEAD |
| SHA | `d54545db771aec97799f1af4f76ac36e71db415f` |
| New branch | `agent/frontend-backend-integration-contract` |
| New worktree initial state | branch above, exact SHA above, clean |
| Original divergent worktree | `agent/supabase-phase25-integration` at `1520b4e5f853d7e4dfd0a212aa1396124a962830`, clean and excluded from this Goal |

The current checkout's `origin` pointed to another local clone, not GitHub. That clone's config identified `https://github.com/jybae01/pnl-dashboard.git` as its upstream. The exact PR ref was fetched into `refs/remotes/github-pr21/pr-21-head`; `git rev-parse` returned the required SHA and `git cat-file -t` returned `commit`. The divergent worktree was not checked out, reset, rebased, or updated.

### Frontend baseline

| Item | Verified value |
|---|---|
| Source of truth | `C:\Users\bjy01\Desktop\profit-analysis-frontend-handoff.zip` |
| Size | 147,480 bytes |
| SHA-256 | `5B81AFA4EA14AA43B88D22B6C6190DEE35D0D7414BEEB248BA9BE91BB3D8AD1A` |
| Archive entries | 69: one directory entry plus 68 files |
| ZIP root | `package.json`, `package-lock.json`, `src`, and project configuration directly present |
| Inspection | read-only ZIP; extracted only to an OS temp analysis directory, never into the backend repository |

## 2. Frontend inventory

### 2.1 Package and build

| Concern | Inventory | Evidence |
|---|---|---|
| Package manager | npm; lockfile version 3 | `package-lock.json:1-6` |
| Framework | React 19.2 | `package.json:12-16` |
| Build | Vite 8; `tsc -b && vite build` | `package.json:6-10,21-27`, `vite.config.ts:1-7` |
| Language | TypeScript 6 | `package.json:21-27`, `tsconfig.app.json` |
| Source/entry | `src`; `src/main.tsx` mounts `App` | `src/main.tsx`, `src/App.tsx:18` |
| Runtime dependencies | React, React DOM, `lucide-react` only | `package.json:12-16` |
| Environment/config | no runtime API base URL or browser environment contract | `vite.config.ts:1-7`; no `import.meta.env` use in `src` |
| Router | no React Router dependency; manual `window.location.hash` | `package.json:12-16`, `src/App.tsx:19-24,39-53` |
| API/auth SDK | no HTTP client abstraction and no Auth/Supabase SDK | `package.json:12-27`, `src/services/*` |
| Service boundary | TypeScript interfaces → in-memory mock classes → dummy data | `src/types/service.ts:22-50`, `src/services/index.ts:1-4` |

### 2.2 Four hash routes and component trees

| Hash/path | View | Main component tree | Current actions/evidence |
|---|---|---|---|
| `#pnl` (default for unknown hash) | `PnlStatusView` | KPI overview, monthly trend, P&L, manufacturing, SGA, item segment, key notes | Seven parallel mock reads; navigate to variance by product group. `src/App.tsx:19-24,50,74-79`; `src/views/PnlStatusView.tsx:56-92` |
| `#forecast` | `ForecastGenerationView` | static hero and three planned-integration cards | Placeholder only; no input/service/action. `src/App.tsx:21,51,81-83`; `src/views/ForecastGenerationView.tsx:4-92` |
| `#variance` | `VarianceAnalysisView` | period/comparison/product filters, summary, narrative, waterfall, detail table | Mock analysis fetch, effect selection, fake Evidence download. `src/App.tsx:22,52,85-90`; `src/views/VarianceAnalysisView.tsx:25-67,123-161` |
| `#management` | `DataManagementView` | upload, model table/detail/delete, Base/Comparison selector, runner, history | local model filtering/selection, simulated upload/job/delete/history/download. `src/App.tsx:23,53,92-100`; `src/views/DataManagementView.tsx:29-199,249-278,470-495` |

`Navigation` renders the same four tabs and has no role filtering (`src/components/common/Navigation.tsx:5-55`). Route state is component state synchronized to the hash, not a router data model.

### 2.3 Important components, actions, and state

| Component / symbol | State/input | Output/callback | Mock dependency and issue | Evidence |
|---|---|---|---|---|
| `App` | `activeTab`, `targetProductGroup`, modal flag, `globalModels`, empty simulation | hash mutation; passes only product group across views | initial models loaded without error path; selected model IDs/result IDs are not global | `src/App.tsx:18-58,74-113` |
| `PnlStatusView.loadData` | `PnlFilterState`; seven result states; `loading` | populates seven view blocks | `Promise.all` has `try/finally` but no `catch`/error state | `src/views/PnlStatusView.tsx:41-92` |
| `VarianceAnalysisView` | filter lacks model IDs; `analysis`, selected effect, loading, download notice | refetch on filter; navigation to management | `.then` has no rejection handler; no invalid-payload state | `src/views/VarianceAnalysisView.tsx:25-67,123-133`; `src/types/variance.ts:75-80` |
| `DataManagementView.fetchModels` | filters, models, local Base/Comparison selections | modal defaults receive IDs only inside this view | selection is not passed to `VarianceAnalysisView`; result navigation carries no job/result ID | `src/views/DataManagementView.tsx:29-71,139-157,185-199,489-495`; `src/App.tsx:93-99` |
| `ModelUploadArea.handleSubmitUpload` | model metadata, optional `File`, uploading/success | `UploadModelPayload` contains file name but not bytes | succeeds after `setTimeout` even when `selectedFile` is null | `src/components/management/ModelUploadArea.tsx:17-34,36-79` |
| file input | selected `File` | local state only | accepts `.xlsx,.xls,.csv`; caption says `.xlsx,.csv`; no type/size/content validation | `src/components/management/ModelUploadArea.tsx:263-287` |
| template action | none | browser `alert` | no artifact or service | `src/components/management/ModelUploadArea.tsx:93-100` |
| `CalculationRunnerModal.handleStartCalculation` | local Base/Comparison, simulated error, local `CalculationJob` | fake interval mutates in-memory job | percentages/stages/retry are simulated; no backend stage source | `src/components/management/CalculationRunnerModal.tsx:24-30,46-109` |
| runner download | local toast | none | no binary/URL | `src/components/management/CalculationRunnerModal.tsx:122-124,389-399` |
| `CalculationHistoryTable` | static `DUMMY_CALC_HISTORY`, toast | route-only result navigation | history and Excel download are dummy/toast | `src/components/management/CalculationHistoryTable.tsx:4-61,110-150` |
| `VarianceSummaryHeader` | frontend effect array | recomputes effect total and residual | presentation currently recalculates reconciliation instead of rendering canonical backend fields | `src/components/variance/VarianceSummaryHeader.tsx:11-16,85` |
| `VarianceDetailTable` | frontend effect array | recomputes displayed effect sum | acceptable only as display checksum, never canonical accounting | `src/components/variance/VarianceDetailTable.tsx:28,167-172` |

### 2.4 Types and ViewModels

| Type | Purpose | Contract mismatch | Evidence |
|---|---|---|---|
| `DataModelItem` | model table ViewModel | description/row count/eligibility/base month/creator display are not DB `models` columns; frontend checksum is `sha256:...` while DB SHA is bare 64-hex | `src/types/model.ts:13-28`; DB: `supabase/migrations/202608090001_phase1_foundation.sql:27-60`; `004:30-31` |
| `CalculationJob` / `CalculationStage` | simulated modal ViewModel | frontend-only progress/stages; lacks attempts, lease, provenance, `result_id` | `src/types/model.ts:30-52`; backend: `forecast/persistence/contracts.py:21-52` |
| `ErrorCode` / `CalculationJob.errorDetail` | simulated error ViewModel | only four mock codes and string detail; backend emits provenance/preflight/worker/integrity codes with JSONB detail | `src/types/model.ts:7-11,37-52`; backend: `forecast/worker_runtime.py:346-375` |
| `VarianceFilterState` | analysis filter | has no `baseline_model_id`, `comparison_model_id`, start/end month, or FX pair | `src/types/variance.ts:75-80` |
| `VarianceAnalysisResult` | variance UI ViewModel | not `analysis_view`, `comparison_result`, DB row, or canonical payload | `src/types/variance.ts:54-73`; backend adapter: `forecast/presentation/analysis_view.py:304-336` |
| `PnlFilterState` and seven P&L VMs | dashboard-only mock contract | no canonical backend endpoint/payload supplies the complete shapes | `src/types/pnl.ts:20-188`; `src/types/service.ts:22-30` |
| `CalculationHistoryRecord` | history-table VM | names/status text only; no canonical job/result/provenance identifiers | `src/components/management/CalculationHistoryTable.tsx:4-16` |
| service interfaces | replaceable frontend seams | interfaces are useful adapter boundaries, not proof that API methods exist | `src/types/service.ts:22-50` |

Frontend ViewModels are explicitly presentation models. They must not become the DB schema or force changes to the backend canonical result.

### 2.5 Mock, hard-coded, and state findings

- All service implementations are mock/in-memory and inject latency (`src/services/pnlService.ts:22-115`, `varianceService.ts:9-23`, `modelService.ts:5-79`, `calculationService.ts:6-91`).
- `MockPnlService` performs product-share scaling and hard-coded margin calculations (`src/services/pnlService.ts:31-65,74-86`). These are prototype business calculations and must disappear behind the adapter, not be ported into production React.
- `dummyVarianceData` calculates mock OP variance and waterfall (`src/mocks/dummyVarianceData.ts:167-279`). The UI's eight items combine Mix into price and combine manufacturing/SG&A categories differently from backend taxonomy; stage text claims “10개 Effect” (`src/mocks/dummyModelData.ts:119-122`) while the analysis header says “8 Effects” (`src/views/VarianceAnalysisView.tsx:96-99`). This is a ViewModel/copy mismatch, not a backend formula gap.
- `MAX_ACTUAL_MONTH = 6` is repeated in four P&L tables (`PnlTable.tsx:11`, `MfgCostTable.tsx:11`, `SgaTable.tsx:11`, `ProductSegmentPnlTable.tsx:11`). `MfgCostTable` hard-codes P&L COGS `9060` (`src/components/pnl/MfgCostTable.tsx:51-54`).
- `ProductGroup` contains `ALL|SW|BW|LC` only (`src/types/common.ts:1,19-24`), while backend canonical groups are `SW/BW/LC/FS/신사업` with FS=`LENGTH` and others=`PCS` (`config/analysis_v1.json:5-11`). This requires an explicit code/display adapter.
- UI arithmetic for formatting, sorting, chart coordinates, and display checksum is allowed. Revenue/COGS/GP/OP, margins, eight effects, residual, inventory realization, FX, tariff, and material/manufacturing formulas remain backend-owned.

### 2.6 State coverage

| State | Current frontend | Required integration disposition |
|---|---|---|
| local/filter | per-view `useState`; hash routes | retain as draft selection only |
| cross-view | only product group is passed from P&L to variance | add job/result URL identity; never infer executed provenance from current filter |
| model selection | local to `DataManagementView` and runner modal | submit exact IDs; result page reads stored provenance |
| loading | present on P&L/variance/models; simulated upload/job | drive from requests and canonical job states |
| empty | prototype toggle or null result | distinguish genuine empty from network/error/invalid payload |
| error | selection/range and simulated job error only | add request error and payload validation states; no silent `.then` rejection |
| upload progress | boolean spinner only | either indeterminate BFF upload or measured byte progress; never fake percentage |
| job progress | fake interval/percentage/stage | remove fake progress unless backend adds a durable source |
| download | toast only | track preparing/downloading/failure; use server stream or signed URL |

There is no login, session, role guard, authorization SDK, or route guard in the frontend package. Button visibility is therefore neither present nor an authorization mechanism.

## 3. Backend inventory

### 3.1 Repositories, model, and upload

- `ModelMeta` includes publication/default/mapping provenance and `workbook_sha256` (`forecast/storage.py:18-60`).
- `ModelRepository` defines list/get/default/path/add/publication (`forecast/persistence/contracts.py:94-116`). Local and Supabase adapters are selected by `create_repository_bundle`; local is the default (`forecast/persistence/factory.py:37-76`).
- Trusted `SupabaseModelRepositoryAdapter.add` accepts bytes server-side, writes `models/{uuid}/source.xlsx`, records exact-byte SHA-256, and inserts metadata (`forecast/persistence/supabase.py:181-227`). It is a compatibility primitive, not an HTTP/BFF contract. It also honors caller-supplied publication metadata, so a BFF reuse must force a draft/non-default insert and require the named Admin publication operation afterward.
- The private `pnl-models` bucket enforces 50 MiB and XLSX MIME (`001:965-977`). Canonical paths are DB-validated (`001:45-47,87-89`; `004:824-850`).
- Model publication/default uses `set_model_publication` through the adapter (`forecast/persistence/supabase.py:229-245`). There is no archive field/capability; FK `ON DELETE RESTRICT` protects referenced models (`001:84,128-130`).
- Migration 004 deliberately revokes the old signed-upload initializer/finalizer because it cannot hash actual uploaded bytes before durable Job creation (`004:894-903`). Therefore the optional Edge upload flow is not a current V1 durable upload path.

### 3.2 Durable Job and worker

- `CalculationJob` contains legacy `model_id`, pinned Base/Comparison IDs and SHA snapshots, engine/mapping/schema provenance, attempts, claim/lease, errors, queue receipt, and request (`forecast/persistence/contracts.py:21-61`).
- `create_durable_calculation_job` requires explicit distinct models, same year, both hashes, and published mapping; it snapshots provenance and enqueues (`004:478-560`). `model_id` is the Comparison alias.
- `analysis_request` currently parses contiguous `months` plus baseline/comparison sales FX; legacy publication flags are ignored (`forecast/worker_runtime.py:50-84`). The proposed frontend start/end fields therefore require an adapter to create `months = range(start_month,end_month+1)`.
- Worker downloads the two pinned models, verifies both byte hashes before preflight/calculation, and builds one payload with `comparison_result`, persisted `analysis_view`, `fact_pack`, and both preflight reports (`forecast/worker_runtime.py:109-227`). Durable execution never performs runtime default lookup; only the explicitly isolated local compatibility path may do so (`forecast/worker_runtime.py:137-152`; `worker_cli.py:35-41`).
- `complete_calculation_job` copies input and release provenance from the locked Job, creates the Result unpublished/non-default, archives the receipt, then completes the Job (`004:564-636`). A failed Job creates no Result.

### 3.3 Queue reliability

| Concern | Implemented semantics | Evidence |
|---|---|---|
| queue | pgmq queue `calculation_jobs` | `002:11-16`; `forecast/persistence/contracts.py:46` |
| claim | `pgmq.read(..., visibility_timeout, 1)`; 1–3600 sec; expired processing jobs may be reclaimed | `004:388-474` |
| durable unresolved | receipt visibility deferred at least 3600 sec; no status rewrite | `004:419-435`; precheck `004:321-339` |
| heartbeat | Job lease and pgmq VT renewed; false means lease lost | `002:302-330`; `forecast/worker_runtime.py:238-296` |
| retry | only `OSError`, `TimeoutError`, `ConnectionError` are retryable; SQL returns to pending while attempt < max | `forecast/worker_runtime.py:346-375`; `002:441-478` |
| attempts | default 3, DB range 1–20; incremented on claim | `001:99-100`; `004:462-471` |
| completion/terminal failure | archive preserves queue history | `004:628-634`; `002:465-476` |
| explicit settle | archive or delete RPC exists for worker control | `002:333-367`; adapter `forecast/persistence/supabase.py:349-366` |
| stale cleanup | pg_cron every 5 minutes; pending-upload timeout and attempts-exhausted cleanup | `002:481-536,604-614` |
| DLQ equivalent | none; failed rows plus pgmq archive are the audit trail | no DLQ creation/routing in `001-004` |
| cancel | none | no cancel RPC/status transition in `001-004` or worker contract |
| progress/stage | none in durable Job schema | `001:82-118`; `004` adds provenance, not progress |

Reliability limits: retry has no progressive backoff; the retryable `set_vt` and terminal-repair `pgmq.archive` paths do not verify their Boolean results before recording the corresponding state (`002:465-476,524-533`). These are monitoring/hardening gaps, not frontend progress signals.

### 3.4 Result, presentation, Evidence, Forecast

- Result and Job input/release provenance are immutable (`004:275-318`). `audit_logs` has row audit triggers and rejects update/delete/truncate (`001:393-425,477-493,910-914`).
- Worker payload is canonical persistence: `comparison_result` is deterministic output, `analysis_view` is the only presentation adapter, and `fact_pack` is AI-safe facts (`forecast/worker_runtime.py:212-227`; `forecast/presentation/analysis_view.py:304-336`; `forecast/ai_analysis.py:116-328`).
- `analysis_view` contains metadata, summary, sales, material, manufacturing, and SGA; raw money remains KRW and display is KRW million (`forecast/presentation/analysis_view.py:310-336`). It is not the frontend `VarianceAnalysisResult`.
- Viewer rendering reads only persisted `analysis_view`, never Excel or the engine, and reports null/invalid payload separately in Streamlit (`forecast/presentation/viewer_dashboard.py:15-48`).
- `build_comparison_audit_workbook` is the Evidence Excel generator (`forecast/analysis_export.py:468-499`). Current delivery is on-demand bytes cached in `st.session_state` and sent by `st.download_button`; it reads local registry paths (`forecast/analysis_export_hook.py:37-95`). The durable worker currently supplies no result workbook artifact path (`CalculationResultWrite` defaults and `worker_runtime.py:224-227`).
- `ForecastEngine` and its existing Streamlit workflow are production assets (`forecast/engine.py:26-117`; `app.py:322-1105`). Streamlit handles editable assumptions, calculation, workbook download, confirmation, and model registration. React is a placeholder (`src/views/ForecastGenerationView.tsx:43-86`). The engine must not be reimplemented in React.
- Existing Streamlit comparison picks two registry models, constructs a contiguous `PeriodOption`, accepts both sales FX values, runs `GenericComparisonEngine`, stores result in session, renders analysis, and offers Evidence (`app.py:1171-1307`).

### 3.5 Auth and backend factory

- Streamlit authenticates `VIEWER_CODE`/`ADMIN_CODE` server-side and stores only `st.session_state.role` (`app.py:64-95`). Data management and comparison independently require `admin` (`app.py:1115-1119,1171-1175`).
- Phase 2 Option A is the selected boundary: Browser → trusted server → narrow Viewer/Admin gateways; JWT Edge is optional future (`docs/phase2_auth_bridge_design.md:3-19,38-67,77-81`).
- `AdminResultPublicationGateway` calls `require_admin()` on every publication request (`forecast/persistence/publication.py:9-37`). Equivalent implemented application gateways do not yet exist for model administration, Job submission/status, Viewer-by-ID, upload, Evidence, or Forecast.
- Supabase secret/service-role clients bypass RLS, so RLS cannot substitute for BFF authorization. The browser must never receive `VIEWER_CODE`, `ADMIN_CODE`, `SUPABASE_SECRET_KEY`, or `SUPABASE_SERVICE_ROLE_KEY`.
- The current Streamlit implementation uses direct string equality and has no inactivity expiry, explicit logout, rate limiting, CSRF/session-cookie boundary, or per-request correlation ID. Those controls are target BFF requirements, not capabilities already supplied by the current access-code screen (`app.py:71-95`; `docs/phase2_auth_bridge_design.md:38-44,95-109`).

## 4. Service-method mapping matrix

Abbreviations: L/E/Err = loading/empty/error. `TS` = trusted server/BFF. Evidence lines are from the frontend ZIP first and backend repository second.

| Frontend Page | Caller | Action/service | Frontend request | Frontend VM | Required data | Backend source | Backend function/RPC | Backend DTO/payload | Mapping rule | Auth role | Transport | L/E/Err | Acceptance test | Evidence | Open decision | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P&L | `PnlStatusView` | `getKpiSummary` | `PnlFilterState` | `PnlKpiSummary` | monthly/YTD/annual revenue, OP, adjusted OP/margins | no canonical complete source | none | partial `analysis_view.summary` only | never derive missing KPI in browser | Viewer | React→TS JSON | L spinner; E no data; Err explicit | values trace to stored backend facts | FE `service.ts:23`; BE `analysis_view.py:285-301` | KPI definition/source | `BACKEND_GAP` |
| P&L | same | `getMonthlyTrends` | year, group | `MonthlyTrendItem[]` | 12-month plan/actual/forecast | no stored canonical series contract | none | none | no dummy scaling | Viewer | JSON | L/E/Err separate | month/source reconciliation | FE `service.ts:24`; mock `pnlService.ts:69-86` | model vs Result source | `BACKEND_GAP` |
| P&L | same | `getPnlTable` | filter | hierarchical `PnlLineItem[]` | P&L hierarchy/month/YTD | selected-period `comparison_result.pnl` is insufficient | none | engine P&L rows | server adapter only after hierarchy contract | Viewer | JSON | L/E/Err separate | Revenue→OP ties to canonical outputs | FE `service.ts:25`; BE `comparison.py:329-332` | hierarchy and period source | `BACKEND_GAP` |
| P&L | same | `getMfgCostBreakdown` | filter | `MfgCostBreakdownItem[]` | actual/plan/YTD manufacturing detail | one comparison's `analysis_view.manufacturing` | no P&L endpoint | accounts/effects | do not use frontend 9060 or recompute realization | Viewer | JSON | L/E/Err separate | COGS/detail provenance validated | FE `service.ts:26`, `MfgCostTable.tsx:51-54`; BE `analysis_view.py:186-203` | dashboard vs analysis semantics | `BACKEND_GAP` |
| P&L | same | `getSgaBreakdown` | filter | `SgaBreakdownItem[]` | account/month/YTD SGA | one comparison's `analysis_view.sga` | no P&L endpoint | accounts/effects | transport Bridge remains non-duplicated | Viewer | JSON | L/E/Err separate | totals match backend facts | FE `service.ts:27`; BE `analysis_view.py:205-222` | P&L source | `BACKEND_GAP` |
| P&L | same | `getItemSegmentPnl` | filter | `ProductSegmentPnl[]` | product P&L, PCS/LENGTH | comparison products are not this VM | none | partial `comparison_result.products` | preserve unit basis; no mixed total | Viewer | JSON | L/E/Err separate | SW/BW/LC PCS; FS LENGTH | FE `service.ts:28`; BE `config/analysis_v1.json:5-11` | product-segment source | `BACKEND_GAP` |
| P&L | same | `getKeyNotes` | filter | `KeyVarianceNote[]` | curated notes | fact pack/narrative are analysis-specific | none | `fact_pack`, summary narrative | server-owned narrative; label AI vs deterministic | Viewer | JSON | L/E/Err separate | no invented facts | FE `service.ts:29`; BE `ai_analysis.py:116-328` | approval/source policy | `BACKEND_GAP` |
| Analysis | `VarianceAnalysisView` | `getVarianceAnalysis` | current filter lacks model/result ID | `VarianceAnalysisResult` | published result by stable ID | published Result JSONB | Migration 005 available-result by-ID RPC + `ResultQueryService.viewer_read` | `ViewerResultResponse` (`analysis_view` + provenance) | frontend adapter maps fields; canonical remains unchanged | Viewer | React→HTTP adapter→BFF→RPC | L spinner; E no available result; Err/invalid separate | mapping fixture validates every field/unit | FE `VarianceAnalysisView.tsx:25-57`; BE `forecast/bff/application.py`, `005` | HTTP route and frontend adapter | `ADAPTER_NEEDED` |
| Analysis | effect table | `getEffectDrilldown` | effect ID + filter | `DrilldownDetailRow[]` | stored analysis rows | `analysis_view` sales/material/mfg/SGA | same Viewer capability | nested rows/accounts | map canonical code→display; no recalculation | Viewer | JSON | L per drilldown; E empty rows; Err explicit | source rows retained | FE `service.ts:32-35`; BE `analysis_view.py:30-222` | canonical effect-code map | `ADAPTER_NEEDED` |
| Models | App/Data Mgmt | `getModels` | `ModelFilterState` | `DataModelItem[]` | role-scoped model list | `models` | `ModelRepository.list` | `ModelMeta`/row | map names, dates, publication, hash; derive eligibility server-side | Viewer published; Admin broader | React→TS | L; E zero rows; Err explicit | Viewer never receives drafts | FE `service.ts:38`; BE `contracts.py:94-116`, `supabase.py:129-161` | model-list policy | `ADAPTER_NEEDED` |
| Models | detail modal | `getModelById` | model ID | `DataModelItem|null` | one allowed model | `models` | `ModelRepository.get` | `ModelMeta` | same as list | Viewer/Admin | JSON | L; E 404/not available; Err explicit | no IDOR | FE `service.ts:39`; BE `supabase.py:133-139` | URL/visibility | `ADAPTER_NEEDED` |
| Models | upload area | `createModel` | currently metadata only/no bytes | `DataModelItem` | actual XLSX bytes + metadata | private Storage + `models` | trusted `SupabaseModelRepositoryAdapter.add` | `ModelMeta` | multipart to TS; TS validates XLSX/50MiB, hashes exact bytes | Admin | React→TS upload; no secret | L upload; E n/a; Err validation/storage | null file rejected; non-XLSX/oversize rejected; SHA matches | FE `ModelUploadArea.tsx:49-79,263-287`; BE `supabase.py:181-227`, `001:965-977` | cleanup/orphan strategy | `ADAPTER_NEEDED` |
| Models | future admin action | `updateModelStatus(PUBLISHED/DRAFT)` | ID/status | bool/Model VM | publication/default metadata | `models` | `set_model_publication` | `ModelMeta` | server rechecks Admin; default implies published | Admin | React→TS→RPC | L disable; E 404; Err explicit | Viewer visibility changes immediately | FE `service.ts:41`; BE `supabase.py:229-245` | unpublish/default UX | `ADAPTER_NEEDED` |
| Models | same interface | `updateModelStatus(ARCHIVED)` | ID/ARCHIVED | bool | archive policy/state | no archive state | none | none | cannot map to delete/unpublish implicitly | Admin | n/a | explicit unavailable | archive semantics tests | FE `service.ts:41`; DB `001:27-60` | archive definition | `BACKEND_GAP` |
| Models | table | `deleteModels` | IDs | bool | safe delete/archive semantics | FKs restrict used models; no narrow delete | none | none | never map mock deletion to DB delete | Admin | n/a | confirmation; failure explicit | referenced model cannot disappear | FE `service.ts:42`, `DataManagementView.tsx:166-183`; DB `001:84,128-130` | delete vs archive/retention | `BACKEND_GAP` |
| Calculation | runner | `startJob` | IDs only today | `CalculationJob` | canonical submit + retry-safe key | actor/key/fingerprint Job contract | Migration 005 idempotent create + `AnalysisSubmissionService` | `AnalysisSubmitRequest/Response` | server validates and pins months/FX/release; never publish | Admin | React→HTTP adapter→BFF→RPC | L submitting; E n/a; Err taxonomy | timeout retry returns same job; collision conflicts | FE `service.ts:46`; BE `forecast/bff/application.py`, `005` | HTTP/frontend adapter | `ADAPTER_NEEDED` |
| Calculation | runner/poll | `getJobStatus` | job ID | `CalculationJob|null` | status/attempt/timestamps/error/result ID | `calculation_jobs` + result link | no shaped BFF/repository read method | Job row + optional result ID | omit fake percent/stages | submitting Admin; Viewer only if policy allows result | React→TS polling | L poll; E 404; Err retry | PENDING/PROCESSING/COMPLETED/FAILED exact | FE `service.ts:47`; BE `contracts.py:21-52` | who may poll and retention | `ADAPTER_NEEDED` |
| Calculation | runner | `cancelJob` | job ID | bool | atomic durable cancellation | none | none | none | do not map to local `IDLE` | Admin | n/a | show unsupported/NOT_V1 | race tests required if added | FE `service.ts:48`, mock `calculationService.ts:42-48`; no BE RPC | `NOT_V1` vs future cancel | `BACKEND_GAP` |
| Evidence | runner/analysis/history | `downloadAnalysisWorkbook` | optional job ID | bool | Evidence bytes/artifact for exact Result | generator exists, durable delivery does not | `build_comparison_audit_workbook` | XLSX bytes | identify by result; generate server-side or reuse artifact | authorized Viewer for available result; Admin diagnostics | React→TS stream or private signed download | preparing/empty/error explicit | workbook binds job/result/provenance | FE `service.ts:49`; BE `analysis_export.py:468-499`, `analysis_export_hook.py:37-95` | on-demand vs Storage/reuse | `BACKEND_GAP` |
| History | `CalculationHistoryTable` | list history | none | `CalculationHistoryRecord[]` | jobs/results scoped by role | tables contain data | no narrow list RPC/BFF | rows | map IDs/status/provenance, not display text as identity | Admin; Viewer published history only if approved | React→TS | L/E/Err separate | no unpublished leak | FE `CalculationHistoryTable.tsx:4-61`; DB `001:82-151` | retention/filter/scope | `ADAPTER_NEEDED` |
| Template | upload area | template download | none | binary | approved template artifact | none | none | none | no dummy file | Admin | n/a | preparing/error | hash/version response | FE `ModelUploadArea.tsx:93-100` | owner/version/storage | `BACKEND_GAP` |
| Forecast | placeholder | Forecast workflow | not defined | not defined | assumptions, generated workbook/model | engine + Streamlit workflow exist | no React/BFF orchestration | `ForecastInput/Result` | reuse engine server-side; never port formulas | Admin | React→TS | full workflow states | parity fixture with Streamlit | FE `ForecastGenerationView.tsx:43-86`; BE `engine.py:26-117`, `app.py:322-1105` | scope/API/artifact lifecycle | `BACKEND_GAP` |
| Viewer availability | result route | `validate_result_availability` | result ID | availability DTO | exact result eligibility | Migration 005 by-ID predicate | `ResultQueryService.validate_result_availability` + RPC | Boolean application capability | DB is source; no stale fallback | Viewer/Admin | React→HTTP adapter→BFF→RPC | L/READY/EMPTY/ERROR/INVALID | unpublish/republish matrix | BE `forecast/bff/application.py`, `005` | HTTP/frontend adapter | `ADAPTER_NEEDED` |
| Auth | app shell | login/session/logout | access code | session role | server session and expiry | `AccessCodeSessionService` | `TrustedBffApplication.login/validate_session/logout` | `SessionResponse`; token is internal cookie handoff | HttpOnly server session; no code/secret in client state | Viewer/Admin | HTTPS same-origin HTTP adapter | submitting/invalid/expired | forged role denied; expiry/logout verified | FE package no auth; BE `forecast/bff/auth.py`, `application.py` | cookie/CSRF/rate-limit transport | `ADAPTER_NEEDED` |

## 5. READY / ADAPTER_NEEDED / BACKEND_GAP

### READY

No React service/action is end-to-end READY. The following backend primitives are ready to reuse: deterministic Forecast/Comparison engine, eight-effect/reconciliation computation, durable pgmq worker lifecycle, Job/Result provenance and SHA checks, model/result publication boundaries, latest published-result availability guard, and Evidence generator.

### ADAPTER_NEEDED

Model list/detail/upload/publication, Job status polling, published analysis mapping, effect drilldown, and history have reusable backend primitives but need trusted-server endpoints, shaped DTOs, role checks, frontend state/error handling, and acceptance fixtures.

### BACKEND_GAP

Durable cancel, durable progress/stage, the later HTTP/cookie adapter, archive/delete policy, complete P&L seven-block sources, template artifact, Forecast BFF orchestration, and an authorized durable/on-demand Evidence delivery capability remain absent. Actor-scoped idempotent submit, narrow Admin Job by-ID, separate Admin/Viewer Result by-ID, and DB-authoritative by-ID availability are resolved by Migration 005 and `forecast/bff`. The retired signed-upload saga is still not a valid Phase 2.5 path.

### BFF foundation resolution overlay

- Session/auth: `AccessCodeSessionService` performs server-only digest comparison, unpredictable opaque sessions stored by digest, expiry, logout invalidation, and `require_viewer`/`require_admin` (`forecast/bff/auth.py`). The single V1 `ADMIN_CODE` credential is the idempotency actor; an HMAC with a required stable server-only namespace secret prevents exposing the code or a reversible actor identifier.
- Capability boundary: `TrustedBffApplication` composes separate submission, Job, Admin-preview, and Viewer-read services. Every service method revalidates the server session; no browser role assertion or button state is trusted (`forecast/bff/application.py`, `factory.py`).
- Submit idempotency: Migration 005 uses a partial unique `(idempotency_actor,idempotency_key)` index, DB-owned canonical JSONB request fingerprint, and transaction advisory lock. Same semantic request returns the existing Job; a different request raises `IDEMPOTENCY_CONFLICT`.
- Job by-ID: `get_calculation_job_status_by_id` returns only the V1 fields and a sanitized error message; claim token, queue receipt, paths, and DB row internals are excluded.
- Result by-ID: Admin preview permits an unpublished completed stored Result with matching immutable provenance. Viewer read uses a separate by-ID RPC whose single-query predicate rechecks publication, both current model hashes/states, Job/Result provenance, published mapping, supported schema, and payload shape on every call. V1 uses `result_id`; resolving a Result from a completed `job_id` is not required by this chosen path.

## 6. Canonical DTO

### Analysis submission

```json
{
  "baseline_model_id": "uuid",
  "comparison_model_id": "uuid",
  "start_month": 1,
  "end_month": 6,
  "baseline_sales_fx": 1480.0,
  "comparison_sales_fx": 1480.0,
  "idempotency_key": "opaque-client-request-id"
}
```

Validation: both IDs required and distinct; same model year; hashes and published mapping present; `1 <= start_month <= end_month <= 12`; both FX values positive. The server converts to contiguous `months = range(start_month, end_month + 1)`. The Job row, not current frontend filters/defaults, is executed provenance.

### Job status DTO

```json
{
  "job_id": "uuid",
  "status": "PENDING|PROCESSING|COMPLETED|FAILED",
  "attempt": 1,
  "max_attempts": 3,
  "created_at": "UTC timestamptz",
  "updated_at": "UTC timestamptz",
  "completed_at": null,
  "result_id": null,
  "error": null
}
```

No percentage or stage is returned until a durable backend source exists. Internal error detail and traceback are never returned.

### Published result DTO

The response identifies `result_id`, `job_id`, Base/Comparison IDs and SHA snapshots, engine/mapping/schema versions, and the persisted `analysis_view`. `comparison_result` and `fact_pack` are server-side canonical/audit payloads and should be exposed only when a named endpoint requires them. The frontend adapter maps `analysis_view` into `VarianceAnalysisResult`; the backend schema is not changed to match mocks.

## 7. Auth and trust boundary

Recommended V1:

```text
React browser
  -> trusted Python server / BFF
       -> Viewer application gateway -> published, available DTOs only
       -> Admin application gateway  -> named model/upload/job/publication operations
       -> Worker gateway              -> not browser-reachable
            -> Supabase DB / private Storage / pgmq
```

- Login posts the access code over HTTPS to the trusted server. The server compares it and creates an opaque, Secure, HttpOnly, SameSite session; the code is not stored in browser state/storage.
- Session expiry, inactivity expiry, logout invalidation, CSRF protection, rate limiting, and login audit/correlation ID are required decisions.
- Viewer/Admin role is server-owned. Every Admin endpoint and callback reauthorizes; button visibility is only UX.
- Admin publication should support reauthorization for sensitive actions if selected.
- Service-role/secret keys remain server/worker only. Direct React→Supabase service-role is forbidden. Supabase Auth/JWT remains an optional future decision, not the default path.
- Because Option A service keys bypass RLS, narrow gateway methods and DTO allowlists are mandatory even when RLS exists.

## 8. Model/upload sequence

Recommended V1 candidate A, because 004 retired the old signed-upload saga:

1. Admin selects one `.xlsx`; client may precheck extension/size but server is authoritative.
2. React sends multipart bytes and metadata to the trusted server. Missing file, `.xls`, `.csv`, oversized, wrong MIME/ZIP structure, or invalid Golden structure fails.
3. BFF streams with a hard 50 MiB limit, computes SHA-256 over exact bytes, preflights structure/year, and calls the trusted model repository.
4. Repository writes canonical private path and inserts the Model with SHA; rollback/orphan cleanup on partial failure must be specified.
5. Response maps `ModelMeta` to `DataModelItem`; no secret or Storage credential is returned.
6. Publication/default is a separate Admin action. Upload does not silently publish/default.

The current adapter can perform step 4 but has no HTTP upload session, request idempotency, or specified orphan cleanup. It also accepts caller publication flags. The BFF must therefore force draft/non-default and treat transport/finalization/idempotency as integration work, not expose this repository method directly.

Candidate B (BFF issues a signed URL) remains optional and requires a server-side finalizer that hashes actual Storage bytes, CORS, expiry, replay, orphan cleanup, and no client-declared SHA. It is not implemented at PR #21.

## 9. Analysis submit sequence

1. Data Management stores selected Base/Comparison IDs as draft UI state.
2. Admin opens execution form and supplies period/FX. The submit body is the canonical DTO above.
3. BFF reauthorizes Admin, validates syntax/business constraints, resolves release provenance, and uses an idempotency key.
4. Durable RPC snapshots model IDs/hashes and release provenance, creates one PENDING Job, and enqueues one receipt.
5. Response returns `job_id`; route becomes `/analysis/jobs/{job_id}`.
6. Completion returns/links `result_id`; result route becomes `/analysis/results/{result_id}` only after availability authorization.

Migration 005 resolves step 3/4 for the BFF path: the actor/key lock and DB fingerprint return the original Job after a lost response, while the same key with a different normalized request fails `IDEMPOTENCY_CONFLICT`. The older 004 RPC remains available for non-BFF compatibility and is not the canonical React submission path.

## 10. Job lifecycle

```text
Submit -> Job(PENDING) -> claim -> PROCESSING
PROCESSING -> complete transaction -> Result(unpublished, non-default) + Job(COMPLETED)
PROCESSING -> retryable failure and attempt remaining -> PENDING
PROCESSING -> terminal/nonretryable/attempts exhausted -> FAILED (no Result)
```

No pending Result is pre-created. Publication is later Admin action. A FAILED Job never resolves to a completed Result.

The current React modal navigates to analysis immediately after its simulated COMPLETED state (`src/components/management/CalculationRunnerModal.tsx:101-120`). Real completion yields an unpublished Result, so the contract must distinguish Admin calculation completion, optional Admin publication, and Viewer availability. Navigation alone cannot publish or make the Result visible.

## 11. Job polling/subscription

V1 recommendation is React → trusted server/BFF polling, not direct Supabase Realtime/JWT.

- Start immediately after submit or opening a nonterminal job route.
- One in-flight request per `job_id`; abort on unmount/route change.
- Poll every 2 seconds for the first 30 seconds, then back off to 5 seconds and at most 10 seconds with jitter.
- On browser focus/online restore, issue one immediate revalidation and cancel any duplicate timer.
- Retry transient network/5xx with bounded exponential backoff; authentication/validation/404 are not hidden as pending.
- Stop on COMPLETED/FAILED. COMPLETED fetches the linked result/availability once; FAILED renders the presentation error category.
- SSE/Realtime is deferred. It requires an explicit session/JWT and authorization decision.

## 12. Failure/retry/idempotency

- Worker retry policy is exact: only OS/network timeout/connection failures are retryable; integrity, provenance, preflight, and deterministic execution failures are terminal unless explicitly classified otherwise.
- Frontend “retry” of a FAILED Job means a new idempotent submission/resubmit contract, not mutation of the terminal row.
- `idempotency_key` must be unique per logical submit and return the original Job for a matching normalized request. Same key/different body must fail conflict.
- No durable cancel exists. Mark cancel `NOT_V1` or design atomic cancellation/claim races later; do not map cancel to frontend `IDLE`.
- No DLQ exists. Archived pgmq messages plus FAILED Job/audit records are the current equivalent and must be monitored.

## 13. Viewer availability

For every Viewer read, DB/RPC is source of truth. Availability requires:

- Result published;
- linked Job completed;
- Base and Comparison models currently published;
- both current model hashes equal Result snapshots;
- Job/Result model IDs, hashes, engine/mapping/schema provenance match;
- `result.model_id = result.comparison_model_id`;
- mapping version/hash is currently published.

These predicates exist in the service-role-only narrow latest-result RPC (`004:738-775`). The authenticated table RLS and Storage policies are not equivalent public-availability filters: each also has a creator-owned branch (`004:817-822,844-846`). The trusted Viewer BFF must use a narrow RPC, not generic service-role table/Storage reads. Migration 005 adds stable `result_id` capabilities: Admin preview, `validate_calculation_result_availability(result_id, supported_schema_versions)`, and an atomic available-result read. The latest-result compatibility RPC remains unchanged.

Acceptance matrix: both models + Result published → visible; either model unpublished → invisible even if `Result.is_published`; republishing the same immutable-hash Model with valid provenance → visible again. Comparison behaves identically.

## 14. Viewer loading/error/empty

Viewer state is independent of Job state:

| State | Meaning |
|---|---|
| `LOADING` | availability/result request in flight |
| `READY` | authorized payload passes schema validation |
| `EMPTY` | no published available Result for this Viewer/query |
| `ERROR` | network/RPC/server failure |
| `INVALID_PAYLOAD` | returned Result violates the versioned DTO/schema |

Never turn ERROR or INVALID_PAYLOAD into EMPTY, and never use stale/local fallback. Viewer messages must not reveal `BASE_UNPUBLISHED`, `PROVENANCE_MISMATCH`, or mapping internals; Admin diagnostics may expose a controlled reason code.

## 15. Result mapping

| Backend `analysis_view` | Frontend target | Rule |
|---|---|---|
| `metadata.baseline/comparison/period` | names/baseMonth/comparison context | add exact IDs/provenance to route/state; do not infer from filters |
| `summary.baseline_operating_profit`, `comparison_operating_profit`, `operating_profit_delta` | plan/actual/totalVariance | rename only; preserve KRW raw then format million |
| `summary.effects_total`, `residual`, `reconciled`, `status` | effect total/reconciliation display | render canonical values; frontend reduce may be diagnostic only |
| `summary.bridge`, `effect_ranking`, `narrative` | effects/waterfall/narrative | canonical code→label mapping; do not use mock eight-item identity |
| `sales.rows/totals` | sales effect/drilldown | preserve quantity unit and transport/tariff once |
| `material` | material effect/drilldown | preserve nonwoven price, JPY KRW/JPY, materials-ex-nonwoven |
| `manufacturing.accounts` | manufacturing detail | preserve FS LENGTH vs SW/BW/LC PCS and realization metadata |
| `sga.accounts` | SGA detail | customer freight is not re-added to SGA Bridge; tariff remains separate |

Effect count is a frontend taxonomy mismatch: the mock eight combines Mix/price and cost groups; the stage copy says ten; backend bridge exposes versioned canonical categories and residual. Resolve through a versioned label/order adapter, not formula changes.

## 16. P&L Dashboard data sources

The frontend requests seven blocks: KPI summary, monthly trend, hierarchical P&L, manufacturing breakdown, SGA breakdown, item segment P&L, and key notes (`PnlStatusView.tsx:68-83`). PR #21 provides a selected-comparison `analysis_view` and raw `comparison_result`, not a canonical current-period P&L dashboard query that satisfies these seven VMs. Treat all seven as BACKEND_GAP until source ownership, period semantics, publication availability, and DTOs are specified. Mock/hard-coded values are not backend evidence.

## 17. Evidence Excel

The backend generator is reusable and must remain the sole generator. Contract options:

- A: on-demand server stream for an authorized available Result;
- B: server-generated private Storage artifact plus short-lived download URL;
- C: reuse a Worker artifact if Worker generation is intentionally added.

V1 decision remains open. Any option binds the workbook to `job_id`, `result_id`, model IDs/hashes, mapping/engine/schema, and audit correlation ID. Frontend never generates the workbook. Current Streamlit local-path/session cache delivery is not a durable React delivery contract.

## 18. Forecast

Streamlit already owns upload/active baseline, editable monthly assumptions/reasons, ForecastEngine execution, generated workbook download, confirmation, and model registration. React currently contains only explanatory placeholder cards. React parity therefore requires a trusted-server orchestration contract around existing Python functions; it must not reproduce Forecast, Excel formulas, validation, or model registration logic in TypeScript.

## 19. Storage/RLS/capability matrix

| Capability | Viewer | Admin | Worker | Trusted server/BFF | Enforcement/evidence |
|---|---|---|---|---|---|
| read model metadata | published only | published + authorized drafts | needed pinned rows | shaped list/detail | RLS `001:892-897`; service-key BFF must reproduce role boundary |
| read source workbook | no named Browser capability; authenticated creator branch exists below BFF | authorized only through a named operation | pinned Base/Comparison | private Storage gateway | `004:824-850`; canonical path guard |
| upload model | deny | allow through named BFF | deny | exact-byte SHA and canonical path | adapter `supabase.py:181-227`; bucket `001:965-977` |
| publish/default model | deny | allow | deny | `set_model_publication` after role check | `supabase.py:229-245`; service-role-only RPC grant |
| create Job | deny | allow | deny | `create_durable_calculation_job` | `004:478-560,879-884` |
| claim/heartbeat/fail/complete | deny | deny | allow | worker-only process | grants `002:572-600`, `004:890-910` |
| publish/default Result | deny | allow | deny logically | `AdminResultPublicationGateway` + RPC | `publication.py:9-37`; `004:639-736,912-915` |
| read published available Result | allow shaped DTO from narrow RPC | allow; diagnostics separately scoped | not presentation role | Viewer gateway calls narrow RPC, never generic table read | `004:738-775,917-919`; creator-owned exceptions `004:817-822,844-846` |
| mutate payload/provenance | deny | deny | insert only via completion | deny | immutable trigger `004:298-318` |
| audit log update/delete | deny | deny | deny | append via triggers | `001:393-425,910-914` |

RLS policies use `authenticated`, but Option A's server secret bypasses RLS. Application authorization and capability separation remain mandatory. The strict publication/provenance availability contract belongs to `get_published_calculation_result`; direct authenticated policies deliberately include creator-owned rows/objects and must not be presented as the Viewer contract. The Viewer RPC and Admin publication RPC are both granted to `service_role`, so “Worker deny” is currently a logical process/gateway separation, not a distinct DB credential role; separate credentials/roles remain an open hardening decision.

## 20. Environment/secret matrix

| Name | Consumer | Server/browser | Secret? | Required? | Local/Supabase | Current source | Notes |
|---|---|---|---|---|---|---|---|
| `PNL_REPOSITORY_BACKEND` | app/worker factory | server | no | optional; default `local` | both | env, `factory.py:51` | Supabase opt-in; fail closed |
| `VIEWER_CODE` | Streamlit/current future BFF auth | server only | yes | current app yes | both | `st.secrets`/env, `app.py:64-95` | never browser/session payload/log |
| `ADMIN_CODE` | same | server only | yes | current app yes | both | same | admin recheck every mutation |
| `BFF_ACTOR_NAMESPACE_SECRET` | BFF composition/transport config | server only | yes | BFF yes; minimum 32 characters | Supabase BFF | passed explicitly to `create_supabase_bff_application` | stable across restarts; rotation changes the credential-principal idempotency namespace; never derive from or expose with access codes |
| `SUPABASE_URL` | Python/Edge | server | no, but config | Supabase backend | Supabase | `factory.py:79-94`, Edge `index.ts:3` | no direct React client in V1 |
| `SUPABASE_SECRET_KEY` | Python trusted server/worker | server only | yes | preferred Supabase key | Supabase | `factory.py:80-88` | bypasses RLS |
| `SUPABASE_SERVICE_ROLE_KEY` | Python fallback/Edge | server only | yes | legacy fallback/Edge | Supabase | `factory.py:81-88`, Edge `index.ts:5` | never browser |
| `PNL_WORKER_ID` | worker CLI | worker | no | optional | both | `worker_cli.py:22-29` | defaults host-pid |
| `SUPABASE_ANON_KEY` | optional Edge JWT gateway | Edge | not secret, but not used by React V1 | optional path only | Supabase | Edge `index.ts:4,41` | JWT path deferred |
| `ENGINE_VERSION` | optional Edge initializer | Edge | no | optional path | Supabase | Edge `index.ts:6` | initializer retired by 004 |
| `RESULT_SCHEMA_VERSION` | optional Edge initializer | Edge | no | optional path | Supabase | Edge `index.ts:7` | release source must be unified |
| `ALLOWED_ORIGINS` | optional Edge | Edge | no | optional path | Supabase | Edge `index.ts:18` | BFF same-origin preferred |
| mapping/release versions | app/worker | server | no, integrity-sensitive | yes | both | `config/model_mapping.json`, registry/release files | Job snapshots version/hash/schema |

## 21. Cache/stale policy

- Submit invalidates model-selection eligibility and Job query for the returned ID.
- Job completion invalidates Job and fetches linked Result/availability.
- Result publication/default changes invalidate Viewer lists/result routes.
- Either model publication change invalidates availability immediately.
- Browser focus/online restore revalidates nonterminal Job and visible Result availability.
- A cached Result cannot remain visible after Base/Comparison unpublication or provenance failure. No stale/local fallback is allowed.
- Cache keys include stable job/result ID and schema version, not only filters/model names.

## 22. Streamlit↔React parity

| Capability | Streamlit | React handoff | Classification |
|---|---|---|---|
| access-code login/session | implemented server-side | absent | `PARITY_GAP` |
| model upload | real XLSX validation/local registry; Supabase adapter primitive | simulation, optional file | `PARITY_GAP` |
| model list/detail | real local registry | dummy models | `PARITY_GAP` |
| model publication/default | backend capability; limited current UI wiring | display/filter only | `PARITY_GAP` |
| Base/Comparison selection | session state feeds real compare | local selection feeds mock runner but not result view | `PARITY_GAP` |
| period/FX analysis | real engine | mock filter lacks IDs/FX/start-end | `PARITY_GAP` |
| result presentation | persisted adapter/backend result | mock `VarianceAnalysisResult` | `PARITY_GAP` |
| Evidence Excel | real on-demand generator/download | toast | `PARITY_GAP` |
| Forecast editable workflow | implemented | placeholder | `PARITY_GAP` |
| generated workbook/model registration | implemented | placeholder copy | `PARITY_GAP` |
| loading/error/empty | partial Streamlit states | partial mock states | `PARITY_GAP` |

## 23. Error taxonomy

| Backend code/source | Presentation category | Viewer message rule | Retry |
|---|---|---|---|
| request/range/same-model/missing model | `VALIDATION_ERROR` | field-specific, no internals | after correction |
| incompatible months/FX/business precondition | `BUSINESS_ERROR` | controlled business message | after correction |
| `INPUT_INTEGRITY_MISMATCH`, `INPUT_PROVENANCE_UNRESOLVED`, mapping/provenance mismatch | `INTEGRITY_ERROR` | generic Viewer unavailable; detailed Admin diagnostic | no automatic retry |
| missing/expired session or role denial | `AUTH_ERROR` | login/forbidden | reauthenticate |
| unpublished/unavailable/404 authorized resource | `NOT_AVAILABLE` | generic unavailable/empty per endpoint | revalidate on publication change |
| network timeout/connection and retryable 5xx | `TRANSIENT_SYSTEM_ERROR` | temporary failure | bounded retry |
| `preflight_failed`, `worker_execution_failed`, `upload_timeout`, `attempts_exhausted` | `TERMINAL_SYSTEM_ERROR` (or validation/integrity when mapped) | correlation ID, no traceback | admin resubmit after diagnosis |

Raw Postgres exceptions, headers, access codes, signed URLs, hashes beyond necessary Admin diagnostics, and Python tracebacks are never exposed. Backend codes are inventory (`worker_runtime.py:346-375`; `002:441-536`; `004:227-315,357-366,591-715`), not a stable public API until the BFF mapping is versioned.

## 24. Open decisions

1. **RESOLVED — BFF FOUNDATION:** server-side access-code session store, expiry, logout, stable credential actor, and per-call Viewer/Admin reauthorization. Secure/HttpOnly/SameSite cookie binding, CSRF/origin, rate-limit, and HTTP correlation middleware belong to the next transport Goal.
2. Whether Viewer can list models or only consume available Results; model detail field allowlist.
3. Model archive/delete/retention semantics and publication/default UX.
4. Trusted-server upload A versus redesigned signed upload B; partial-failure cleanup and CORS.
5. **RESOLVED — BFF FOUNDATION:** actor/key uniqueness, DB-owned normalized request fingerprint, replay, collision conflict, and concurrent serialization are Migration 005 contracts.
6. Job status access, retention, resubmit semantics, and whether cancel is `NOT_V1`.
7. **RESOLVED — BFF FOUNDATION:** narrow Admin Job by-ID, Admin unpublished preview, Viewer Result by-ID, and explicit availability RPC exist. Actual HTTP route/cookie binding remains next-Goal transport work.
8. Whether any durable stage/progress will be added; until then only state and attempts display.
9. Exact P&L seven-block source, period/publication semantics, and DTO ownership.
10. Evidence on-demand stream versus private artifact versus Worker reuse; audit/download lifetime.
11. Forecast BFF scope and generated model publication sequence.
12. Model/result publication cache invalidation channel (poll/version headers are sufficient for V1).
13. Public error-code versioning and Admin diagnostic detail.
14. Date/currency/unit/product map: month integer; DB UTC `timestamptz` displayed Asia/Seoul; KRW raw/KRW million display; USD sales FX; JPY as `KRW/JPY`; SW/BW/LC/FS/신사업 labels; LC=4-inch; PCS and LENGTH never combined.
15. Whether Worker and trusted application server receive distinct DB credentials/roles; current service-role grants do not enforce that separation at DB role level.

## 25. Acceptance criteria

### T01 gate

- [x] exact frontend size/hash/file count/root verified
- [x] backend exact PR #21 commit/ref/worktree verified
- [x] four routes/pages and component/actions inventoried
- [x] major types/ViewModels and service seams inventoried
- [x] mock/hard-coded/business-calculation findings recorded
- [x] repository/RPC/result/worker/Forecast/Evidence inventory recorded
- [x] RLS/Storage/immutable/audit capability inventory recorded
- [x] pgmq lease/retry/stale/archive and absent DLQ/cancel/progress recorded
- [x] environment/secret matrix recorded
- [x] Streamlit↔React parity recorded

### T02 gate

- [x] every current service method/action classified with code evidence
- [x] no unsupported READY classification
- [x] adapter rows define mapping/auth/transport/state/test/open decision
- [x] backend gaps have technical evidence and are not implemented here
- [x] canonical submit/Job/Result DTO boundaries defined
- [x] lifecycle/retry/idempotency/polling contracts defined
- [x] Viewer availability and loading/error/empty split defined
- [x] trusted BFF/auth/upload/download/Evidence/Forecast boundary defined
- [x] P&L source gap and cache invalidation defined
- [x] error/date/currency/unit/product contracts defined

T01 is `PASS`; T02 is `CONTRACT BASELINE PASS`. The five BFF-foundation decisions are implemented, but “PASS” does not mean the React integration is runnable.

## 26. Explicit non-goals

This implementation overlay includes only the framework-neutral BFF application services and additive Migration 005. No frontend edit/import, npm install, package/lock change, HTTP server/route adapter, model-upload saga, Evidence delivery, P&L seven-query implementation, Forecast orchestration, cancel/progress, Worker calculation, Edge deployment, Supabase live operation, engine/formula/residual change, mock removal, UI redesign, deployment, main merge, rebase, reset, or PR #20/#21 modification is included.

Existing assets are reused: deterministic Forecast/Comparison engine, effect/reconciliation rules, pgmq lifecycle, provenance/SHA checks, publication/default boundary, and Evidence source-cell/formula generator.

## 27. Recommended next implementation order

1. Add the trusted HTTP/cookie adapter around the resolved BFF application services, then incorporate React session handling without exposing secrets.
2. Connect model list/detail and the existing publication capability; keep upload finalization/cleanup as its separate open design.
3. Replace the frontend mock calculation runner with canonical submit + Job by-ID polling (no fake stage/percentage).
4. Implement the `analysis_view` frontend adapter and Viewer state machine with by-ID availability revalidation.
5. Implement Evidence delivery around the existing generator.
6. Specify and build P&L seven-block backend sources.
7. Implement Forecast orchestration last, reusing the existing Python engine and Streamlit behavior as parity reference.

## React Core Vertical Slice overlay

The HTTP/session transport decision is now resolved for this slice: FastAPI exposes named session, model-list, canonical-submit, Admin Job, Admin Result preview, and strict Viewer Result routes. The session identifier is HttpOnly; CSRF is an HMAC-bound cookie/header pair; CORS is allowlist-only; every application operation rechecks Viewer/Admin capability. The built-in session store and login limiter are single-process development implementations, so multi-instance production remains open until shared stores are supplied.

React now retains one idempotency key for each logical submit, polls only real `PENDING/PROCESSING/COMPLETED/FAILED` state with bounded backoff, reads the completed stored Result by `result_id`, and clears stale Viewer Result data whenever strict availability denies the next read. The reachable core route no longer executes the handoff's fake calculation timer, dummy history, or mock Result service.

Migration 006 is additive and leaves 001–005 unchanged. It locks the selected Base and Comparison model rows at durable Job insertion and rejects unpublished inputs or workbook SHA snapshot drift, closing direct-ID and model-list bypass races.

Still open: shared production session storage/rate limiting, model upload finalization/cleanup, complete field-level `analysis_view` presentation mapping, Evidence delivery, P&L seven-source DTOs, Forecast orchestration, cancel, and real progress/stage.

## Model Ingestion Vertical Slice overlay

The confirmed Streamlit login character is preserved through the HTTP auth adapter: the React screen keeps the light radial background, dark NanoH2O brand card, masked access-code input, server-authoritative failure/lockout countdown, role purpose, and logout. Codes and lockout authority remain server-only.

Model ingestion finalization/cleanup is resolved for the trusted-server V1 slice. `POST /api/admin/models` accepts only `.xlsx` multipart uploads, caps both declared and streamed request bytes, stages to a temporary file, hashes the exact source bytes, performs bounded OOXML package and existing structural preflight, uploads to private `pnl-models/models/{model_id}/source.xlsx`, verifies stored bytes, and finalizes a draft Model. The browser cannot supply Model identity, Storage path, mapping provenance, or publication flags.

Migration 007 adds actor/key/metadata/SHA idempotency reservations, canonical draft finalization, durable `cleanup_required` state, a narrow operator recovery queue, lost-finalize-response recovery, and hardened explicit publication. Same actor/key with the same canonical request replays the Model; a changed request or workbook is `IDEMPOTENCY_CONFLICT`; the same SHA under a new key remains a distinct business Model.

Admin management and analysis selection use separate DTOs. Management can show unpublished or legacy unresolved Models without exposing paths; analysis options remain published-only with workbook SHA provenance. The reachable React management route uses the real multipart adapter and explicit upload states; the handoff's `setTimeout` upload component remains isolated from `App` and is not canonical.

Still open after this slice: shared production session storage and rate limiting; production proxy/body/temp-volume and workbook-parser isolation budgets; live Storage/DB migration validation; user archive/delete; Evidence delivery; full `analysis_view` mapping; P&L seven-source DTOs; Forecast orchestration; cancel; and real progress/stage. Cleanup recovery is an operator RPC, not a browser delete capability.

## Evidence + History vertical-slice overlay

Evidence delivery and Admin Calculation History are resolved by additive Migration 008 and `forecast.bff.evidence_history`. Evidence is identified by `result_id`, generated on demand from the stored `comparison_result` plus the exact pinned Base/Comparison source bytes, and never invokes the comparison engine. Admin may download a completed unpublished Result after provenance/source checks; Viewer delivery is gated by the same strict current availability predicate as Viewer Result read. The HTTP adapter streams a temporary XLSX with cleanup and the React adapter exposes the exact `분석 근거 엑셀 내려받기` action only for completed/READY results.

Admin History uses a narrow safe DTO and bounded keyset pagination ordered by `(created_at DESC, job_id DESC)`. Pending, processing, failed, and completed-without-result rows never receive a fabricated `result_id`; only a completed row with a stored Result exposes the Evidence action. Browser DTOs omit claim, lease, queue receipt, Storage path, and raw worker/database errors.

Still open after this overlay: shared production session storage/rate limiting, production temp-volume quotas, explicit access-code actor attribution for read/download audit events, live Migration 008/Storage validation, full `analysis_view` presentation, P&L seven-source DTOs, Forecast orchestration, cancel, and real progress/stage.

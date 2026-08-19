// TEST-ONLY browser harness. This entry is not reachable from the production Vite entry.
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/index.css';
import '../src/styles/pnl-dashboard.css';
import { createPnlReportingVisualFixture } from '../src/test-support/pnlReportingVisualFixture';
import type { PnlReportingLoadResult, PnlReportingState } from '../src/types/pnlReporting';
import { PnlStatusView } from '../src/views/PnlStatusView';

const params = new URLSearchParams(window.location.search);
const throughDraft = Number(params.get('through') ?? 12);
const through = Number.isInteger(throughDraft) && throughDraft >= 1 && throughDraft <= 12 ? throughDraft : 12;
const stateDraft = params.get('state') ?? 'READY';
const reportingState: PnlReportingState = ['MISSING_BOTH', 'MISSING_PLAN', 'MISSING_ACTUAL', 'READY'].includes(stateDraft)
  ? stateDraft as PnlReportingState
  : 'READY';
const report = createPnlReportingVisualFixture(through);
const hasPlan = reportingState === 'READY' || reportingState === 'MISSING_ACTUAL';
const hasActual = reportingState === 'READY' || reportingState === 'MISSING_PLAN';
const result: PnlReportingLoadResult = {
  reportingState,
  metadata: {
    selectedYear: 2026,
    availableYears: [2026, 2025],
    plan: { exists: hasPlan, datasetId: hasPlan ? '11111111-1111-4111-8111-111111111111' : null, lastUpdated: hasPlan ? '2026-08-18T01:00:00Z' : null },
    actual: { exists: hasActual, datasetId: hasActual ? '22222222-2222-4222-8222-222222222222' : null, lastUpdated: hasActual ? '2026-08-19T01:00:00Z' : null, actualThroughMonth: hasActual ? through : null },
    lastUpdated: hasActual ? '2026-08-19T01:00:00Z' : hasPlan ? '2026-08-18T01:00:00Z' : null,
  },
  report: reportingState === 'READY' ? report : null,
} as PnlReportingLoadResult;

const reportingSource = {
  async load() {
    return result;
  },
};

createRoot(document.getElementById('root')!).render(<StrictMode><main className="app-content"><PnlStatusView reportingSource={reportingSource} onNavigateToVariance={() => undefined} /></main></StrictMode>);

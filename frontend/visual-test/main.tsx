// TEST-ONLY browser harness. This entry is not reachable from the production Vite entry.
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/index.css';
import '../src/styles/pnl-dashboard.css';
import { pnlReportingVisualFixture } from '../src/test-support/pnlReportingVisualFixture';
import { PnlStatusView } from '../src/views/PnlStatusView';

const reportingSource = {
  async load() {
    return { state: 'DATA_READY' as const, report: pnlReportingVisualFixture };
  },
};

createRoot(document.getElementById('root')!).render(<StrictMode><main className="app-content"><PnlStatusView initialYear={2026} reportingSource={reportingSource} onNavigateToVariance={() => undefined} /></main></StrictMode>);

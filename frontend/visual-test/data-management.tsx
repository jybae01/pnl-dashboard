// TEST-ONLY browser harness. This entry is not reachable from the production Vite entry.
import { createRoot } from 'react-dom/client';
import '../src/index.css';
import '../src/styles/data-management.css';
import '../src/styles/calculation-history.css';
import { ModelManagementView } from '../src/integration/ModelManagementView';

const models = [
  { model_id: '11111111-1111-4111-8111-111111111111', display_name: '2026년 연간 계획', model_type: 'PLAN', model_year: 2026, start_month: 1, end_month: 12, version: 'V3', file_name: '2026_annual_plan_final.xlsx', workbook_sha256: 'a'.repeat(64), has_workbook_sha256: true, is_published: true, is_default: true, uploaded_at: '2026-08-18T02:15:00Z', dto_version: '1' },
  { model_id: '22222222-2222-4222-8222-222222222222', display_name: '2026년 7월 누적 실적', model_type: 'ACTUAL', model_year: 2026, start_month: 1, end_month: 7, version: 'V7', file_name: 'actual_2026_07.xlsx', workbook_sha256: 'b'.repeat(64), has_workbook_sha256: true, is_published: true, is_default: false, uploaded_at: '2026-08-17T08:40:00Z', dto_version: '1' },
  { model_id: '33333333-3333-4333-8333-333333333333', display_name: '2026년 하반기 추정', model_type: 'FORECAST', model_year: 2026, start_month: 8, end_month: 12, version: 'V2', file_name: 'forecast_2026_h2.xlsx', workbook_sha256: null, has_workbook_sha256: false, is_published: false, is_default: false, uploaded_at: '2026-08-16T05:05:00Z', dto_version: '1' },
];

const history = [
  { job_id: '44444444-4444-4444-8444-444444444444', result_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', status: 'COMPLETED', baseline_model_id: models[0].model_id, baseline_model_name: models[0].display_name, comparison_model_id: models[1].model_id, comparison_model_name: models[1].display_name, start_month: 1, end_month: 7, attempt: 1, max_attempts: 3, created_at: '2026-08-18T03:10:00Z', completed_at: '2026-08-18T03:11:00Z', error_code: null, error_message: null, is_published: true, is_default: true, published_at: '2026-08-18T03:12:00Z' },
  { job_id: '55555555-5555-4555-8555-555555555555', result_id: null, status: 'PROCESSING', baseline_model_id: models[1].model_id, baseline_model_name: models[1].display_name, comparison_model_id: models[2].model_id, comparison_model_name: models[2].display_name, start_month: 8, end_month: 12, attempt: 1, max_attempts: 3, created_at: '2026-08-19T01:20:00Z', completed_at: null, error_code: null, error_message: null, is_published: false, is_default: false, published_at: null },
];

const mode = new URLSearchParams(window.location.search).get('state') || 'ready';

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
}

window.fetch = async (input, init) => {
  const path = String(input);
  if (mode === 'error' && (path.includes('/api/admin/models') || path.includes('/api/admin/calculation-history'))) {
    return json({ error: { code: 'INTERNAL_ERROR', message: 'visual harness error', field_errors: {}, correlation_id: null, dto_version: '1' } }, 500);
  }
  if (path.includes('/api/admin/calculation-history')) return json({ items: mode === 'empty' ? [] : history, next_before_created_at: mode === 'ready' ? '2026-08-01T00:00:00Z' : null, next_before_job_id: mode === 'ready' ? '66666666-6666-4666-8666-666666666666' : null, dto_version: '1' });
  if (path.endsWith('/api/admin/models') && (!init?.method || init.method === 'GET')) return json({ models: mode === 'empty' ? [] : models, dto_version: '1' });
  if (path.includes('/publication')) return json({ model: models[0], dto_version: '1' });
  if (path.includes('/delete')) return json({ resource_type: 'model', requested_count: 1, deleted_count: 1, blocked_count: 0, failed_count: 0, items: [{ resource_id: models[0].model_id, status: 'DELETED', reason: 'DELETED', reference_counts: {}, idempotent_replayed: false }], dto_version: '1' });
  return json({ error: { code: 'NOT_FOUND', message: path, field_errors: {}, correlation_id: null, dto_version: '1' } }, 404);
};

createRoot(document.getElementById('root')!).render(<main className="app-content"><ModelManagementView onNavigateToForecast={() => undefined} onNavigateToAnalysis={() => undefined} onNavigateToAnalysisResult={() => undefined} /></main>);

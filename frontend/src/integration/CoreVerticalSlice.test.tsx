import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { CoreAnalysisView } from './CoreAnalysisView';
import { presentationFixture } from './presentationTestFixture';

const BASE = '11111111-1111-4111-8111-111111111111';
const COMP = '22222222-2222-4222-8222-222222222222';
const JOB = '33333333-3333-4333-8333-333333333333';
const RESULT = '44444444-4444-4444-8444-444444444444';

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe('React core vertical slice', () => {
  it('runs login -> model selection -> submit -> polling -> stored result', async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input); calls.push(`${init?.method || 'GET'} ${path}`);
      if (path.endsWith('/api/session') && !init?.method) return json({ error: { code: 'AUTH_REQUIRED', message: 'Authentication required' } }, 401);
      if (path.endsWith('/api/session/login')) {
        document.cookie = 'pnl_csrf=test-csrf; Path=/';
        return json({ authenticated: true, role: 'admin', expires_at: '2026-08-12T00:00:00Z', dto_version: '1' });
      }
      if (path.endsWith('/api/models')) return json({ models: [
        { model_id: BASE, display_name: 'Base', model_type: 'PLAN', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: true, dto_version: '1' },
        { model_id: COMP, display_name: 'Comparison', model_type: 'ACTUAL', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: false, dto_version: '1' },
      ], dto_version: '1' });
      if (path.endsWith('/api/analyses')) return json({ job_id: JOB, status: 'PENDING', execution_state: 'STARTING_WORKER', idempotency_replayed: false, dto_version: '1' });
      if (path.endsWith(`/api/jobs/${JOB}`)) return json({
        job_id: JOB, status: 'COMPLETED', baseline_model_id: BASE, comparison_model_id: COMP,
        start_month: 1, end_month: 12, attempt: 1, max_attempts: 3,
        created_at: '2026-08-11T00:00:00Z', heartbeat_at: null,
        completed_at: '2026-08-11T00:00:01Z', result_id: RESULT,
        error_code: null, error_message: null, execution_state: 'COMPLETED', dto_version: '1',
      });
      if (path.endsWith(`/api/admin/results/${RESULT}/presentation`)) return json(presentationFixture({
        identity: { ...presentationFixture().identity, is_published: false, published_at: null },
      }));
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    expect(await screen.findByText('손익 데이터 모니터링')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Access Code'), { target: { value: 'admin-code' } });
    fireEvent.click(screen.getByRole('button', { name: '접속' }));
    expect(await screen.findByText('Base / Comparison 분석 실행')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '분석 실행' }));
    expect(await screen.findByTestId('stored-result', {}, { timeout: 3500 })).toHaveTextContent('영업이익 증감');
    expect(screen.getAllByRole('button', { name: '분석 근거 엑셀 내려받기' })).toHaveLength(2);
    expect(calls.some((value) => value.includes(`/api/jobs/${JOB}`))).toBe(true);
    expect(calls.some((value) => value.includes(`/api/admin/results/${RESULT}/presentation`))).toBe(true);
    const submitCall = fetchMock.mock.calls.find((value) => String(value[0]).endsWith('/api/analyses'));
    expect(submitCall).toBeDefined();
    if (!submitCall) throw new Error('submit request was not observed');
    const submitInit = submitCall[1] as RequestInit;
    expect(JSON.parse(String(submitInit.body)).idempotency_key).toMatch(/^[0-9a-f-]{36}$/);
    expect((submitInit.headers as Headers).get('X-CSRF-Token')).toBe('test-csrf');
  }, 5000);

  it('clears cached Viewer result after the backend later denies availability', async () => {
    let reads = 0;
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (!String(input).includes('/api/viewer/results/') || !String(input).endsWith('/presentation')) throw new Error('unexpected request');
      reads += 1;
      if (reads === 1) return json(presentationFixture());
      return json({ error: { code: 'RESULT_NOT_AVAILABLE', message: 'Result not available', field_errors: {}, correlation_id: null, dto_version: '1' } }, 404);
    }));
    render(<CoreAnalysisView role="viewer" />);
    fireEvent.change(screen.getByLabelText('Result ID'), { target: { value: RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByTestId('stored-result')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(() => expect(screen.queryByTestId('stored-result')).not.toBeInTheDocument());
    expect(screen.getByTestId('viewer-empty')).toBeInTheDocument();
  });

  it('reuses the same idempotency key after a lost submit response', async () => {
    const keys: string[] = [];
    let submits = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith('/api/models')) return json({ models: [
        { model_id: BASE, display_name: 'Base', model_type: 'PLAN', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: true, dto_version: '1' },
        { model_id: COMP, display_name: 'Comparison', model_type: 'ACTUAL', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: false, dto_version: '1' },
      ] });
      if (path.endsWith('/api/analyses')) {
        const body = JSON.parse(String(init?.body)); keys.push(body.idempotency_key); submits += 1;
        if (submits === 1) throw new TypeError('response lost');
        return json({ job_id: JOB, status: 'PENDING', execution_state: 'QUEUED', idempotency_replayed: true, dto_version: '1' });
      }
      if (path.endsWith(`/api/jobs/${JOB}`)) return json({
        job_id: JOB, status: 'FAILED', baseline_model_id: BASE, comparison_model_id: COMP,
        start_month: 1, end_month: 12, attempt: 1, max_attempts: 3,
        created_at: '', heartbeat_at: null, completed_at: null, result_id: null,
        error_code: 'worker_execution_failed', error_message: 'Job failed', execution_state: 'FAILED', dto_version: '1',
      });
      throw new Error(`unexpected request ${path}`);
    }));
    render(<CoreAnalysisView role="admin" />);
    expect(await screen.findByText('Base / Comparison 분석 실행')).toBeInTheDocument();
    const run = screen.getByRole('button', { name: '분석 실행' });
    fireEvent.click(run);
    expect(await screen.findByText('서버에 연결할 수 없습니다.')).toBeInTheDocument();
    fireEvent.click(run);
    expect(await screen.findByText(/QUEUED/)).toBeInTheDocument();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('treats malformed Result payload as INVALID_PAYLOAD rather than READY', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ result_id: RESULT, job_id: JOB, analysis_view: null, provenance: {} })));
    render(<CoreAnalysisView role="viewer" />);
    fireEvent.change(screen.getByLabelText('Result ID'), { target: { value: RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByText('서버 응답 형식이 올바르지 않습니다.')).toBeInTheDocument();
    expect(screen.queryByTestId('stored-result')).not.toBeInTheDocument();
  });

  it('shows Admin-only demand Worker status and invokes controlled emergency wake', async () => {
    document.cookie = 'pnl_csrf=test-csrf; path=/';
    const calls: Array<[string, RequestInit | undefined]> = [];
    const worker = (desired: 0 | 1) => ({
      desired_instance_count: desired, configured_instance_count: desired,
      actual_instance_count: desired, queue_depth: 0, claimable_count: 0,
      pending_count: 0, processing_count: 0, active_lease_count: 0,
      active_heartbeat_count: 0, recovery_pending_count: 0, work_exists: false,
      idle_seconds: 0, last_worker_activity_at: '2026-08-12T00:00:00Z',
      last_scaling_result: 'scaled', platform_reconciling: false, platform_ready: true,
      operating_policy: 'DEMAND_ONLY', idle_policy_seconds: 1800, dto_version: '1',
    });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input); calls.push([path, init]);
      if (path.endsWith('/api/models')) return json({ models: [] });
      if (path.endsWith('/api/admin/worker/emergency-wake')) return json(worker(1));
      if (path.endsWith('/api/admin/worker')) return json(worker(0));
      throw new Error(`unexpected request ${path}`);
    }));
    render(<CoreAnalysisView role="admin" />);
    expect(await screen.findByText('Worker: 0')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Emergency wake' }));
    expect(await screen.findByText('Worker: 1')).toBeInTheDocument();
    const wake = calls.find(([path]) => path.endsWith('/api/admin/worker/emergency-wake'));
    expect(wake).toBeDefined();
    if (!wake?.[1]) throw new Error('wake request was not observed');
    expect(wake[1].method).toBe('POST');
    expect((wake[1].headers as Headers).get('X-CSRF-Token')).toBe('test-csrf');
  });

  it('hides Worker controls when the backend has no demand-lifecycle capability', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/models')) return json({ models: [] });
      if (path.endsWith('/api/admin/worker')) return json({
        error: { code: 'TRANSIENT_SYSTEM_ERROR', message: 'not configured', field_errors: {}, correlation_id: null, dto_version: '1' },
      }, 503);
      throw new Error(`unexpected request ${path}`);
    }));
    render(<CoreAnalysisView role="admin" />);
    await waitFor(() => expect(screen.queryByTestId('worker-control')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Emergency wake' })).not.toBeInTheDocument();
  });
});

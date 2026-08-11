import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { CoreAnalysisView } from './CoreAnalysisView';

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
      if (path.endsWith('/api/analyses')) return json({ job_id: JOB, status: 'PENDING', idempotency_replayed: false, dto_version: '1' });
      if (path.endsWith(`/api/jobs/${JOB}`)) return json({
        job_id: JOB, status: 'COMPLETED', baseline_model_id: BASE, comparison_model_id: COMP,
        start_month: 1, end_month: 12, attempt: 1, max_attempts: 3,
        created_at: '2026-08-11T00:00:00Z', heartbeat_at: null,
        completed_at: '2026-08-11T00:00:01Z', result_id: RESULT,
        error_code: null, error_message: null, dto_version: '1',
      });
      if (path.endsWith(`/api/admin/results/${RESULT}`)) return json({
        result_id: RESULT, job_id: JOB, analysis_view: { summary: { status: 'PASS' } },
        provenance: { baseline_model_id: BASE, comparison_model_id: COMP },
        is_published: false, is_default: false, published_at: null,
        created_at: '2026-08-11T00:00:01Z', dto_version: '1',
      });
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    expect(await screen.findByText('손익 데이터 모니터링')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Access Code'), { target: { value: 'admin-code' } });
    fireEvent.click(screen.getByRole('button', { name: '접속' }));
    expect(await screen.findByText('Base / Comparison 분석 실행')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '분석 실행' }));
    expect(await screen.findByText(/PENDING/)).toBeInTheDocument();
    expect(await screen.findByTestId('stored-result', {}, { timeout: 3500 })).toHaveTextContent('PASS');
    expect(calls.some((value) => value.includes(`/api/jobs/${JOB}`))).toBe(true);
    expect(calls.some((value) => value.includes(`/api/admin/results/${RESULT}`))).toBe(true);
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
      if (!String(input).includes('/api/viewer/results/')) throw new Error('unexpected request');
      reads += 1;
      if (reads === 1) return json({
        result_id: RESULT, job_id: JOB, analysis_view: { summary: { status: 'PASS' } },
        provenance: { baseline_model_id: BASE }, is_default: false,
        published_at: '2026-08-11T00:00:01Z', created_at: '2026-08-11T00:00:01Z', dto_version: '1',
      });
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
        return json({ job_id: JOB, status: 'PENDING', idempotency_replayed: true, dto_version: '1' });
      }
      if (path.endsWith(`/api/jobs/${JOB}`)) return json({
        job_id: JOB, status: 'FAILED', baseline_model_id: BASE, comparison_model_id: COMP,
        start_month: 1, end_month: 12, attempt: 1, max_attempts: 3,
        created_at: '', heartbeat_at: null, completed_at: null, result_id: null,
        error_code: 'worker_execution_failed', error_message: 'Job failed', dto_version: '1',
      });
      throw new Error(`unexpected request ${path}`);
    }));
    render(<CoreAnalysisView role="admin" />);
    expect(await screen.findByText('Base / Comparison 분석 실행')).toBeInTheDocument();
    const run = screen.getByRole('button', { name: '분석 실행' });
    fireEvent.click(run);
    expect(await screen.findByText('서버에 연결할 수 없습니다.')).toBeInTheDocument();
    fireEvent.click(run);
    expect(await screen.findByText(/PENDING/)).toBeInTheDocument();
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
});

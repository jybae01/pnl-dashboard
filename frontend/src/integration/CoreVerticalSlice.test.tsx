import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { CoreAnalysisView } from './CoreAnalysisView';
import { presentationFixture } from './presentationTestFixture';

const BASE = '11111111-1111-4111-8111-111111111111';
const COMP = '22222222-2222-4222-8222-222222222222';
const JOB = '33333333-3333-4333-8333-333333333333';
const RESULT = '44444444-4444-4444-8444-444444444444';
const OTHER_RESULT = '55555555-5555-4555-8555-555555555555';
const THIRD_RESULT = '66666666-6666-4666-8666-666666666666';

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }));
}

function viewerResults(...ids: string[]) {
  return {
    results: ids.map((result_id, index) => ({
      result_id,
      label: index === 0 ? '2026 계획 대비 12월 실적 · 12월' : `공개 분석 ${index + 1}`,
      completed_at: `2026-08-${12 - index}T00:00:00Z`,
      published_at: `2026-08-${12 - index}T00:01:00Z`,
    })),
    dto_version: '1',
  };
}

async function fillMonthlyFx(key: string, baseline: string, comparison: string) {
  const baselineInput = await screen.findByLabelText(`${key} 기준 매출환율 (KRW/USD)`);
  const comparisonInput = screen.getByLabelText(`${key} 비교 매출환율 (KRW/USD)`);
  fireEvent.change(baselineInput, { target: { value: baseline } });
  fireEvent.change(comparisonInput, { target: { value: comparison } });
}

afterEach(() => vi.unstubAllGlobals());

describe('React core vertical slice', () => {
  it('keeps the mockup condition field order and compact primary/secondary actions', async () => {
    window.sessionStorage.removeItem('pnl.active-analysis-job-id');
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (!String(input).endsWith('/api/models')) throw new Error(`unexpected request ${String(input)}`);
      return json({ models: [
        { model_id: BASE, display_name: 'Base', model_type: 'PLAN', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: true, dto_version: '1' },
        { model_id: COMP, display_name: 'Comparison', model_type: 'ACTUAL', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: false, dto_version: '1' },
      ], dto_version: '1' });
    }));

    render(<CoreAnalysisView role="admin" />);
    expect(await screen.findByText('분석 조건 설정')).toBeInTheDocument();
    const condition = screen.getByTestId('analysis-condition-card');
    expect(Array.from(condition.querySelectorAll('.filter-label')).map((node) => node.textContent)).toEqual([
      '기준 모형',
      '비교 모형',
      '시작 월',
      '종료 월',
    ]);
    expect(screen.getByLabelText('월별 매출환율 입력')).toBeInTheDocument();
    expect(within(condition).getByRole('button', { name: '분석 실행' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '1' } });
    await fillMonthlyFx('2026-01', '1480', '1490');
    expect(within(condition).getByRole('button', { name: '분석 실행' })).toBeEnabled();
    const comparisonFx = screen.getByLabelText('2026-01 비교 매출환율 (KRW/USD)');
    fireEvent.change(comparisonFx, { target: { value: '0' } });
    expect(within(condition).getByRole('button', { name: '분석 실행' })).toBeDisabled();
    fireEvent.change(comparisonFx, { target: { value: '-1' } });
    expect(within(condition).getByRole('button', { name: '분석 실행' })).toBeDisabled();
    fireEvent.change(comparisonFx, { target: { value: '1490' } });
    expect(within(condition).getByRole('button', { name: '분석 실행' })).toBeEnabled();
    expect(within(condition).getByRole('button', { name: '새 분석' })).toBeEnabled();
  });

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
    expect(await screen.findByRole('heading', { name: '손익 모형 데이터 관리' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '손익분석 결과' }));
    expect(await screen.findByText('분석 조건 설정')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '1' } });
    await fillMonthlyFx('2026-01', '1480', '1490');
    fireEvent.click(screen.getByRole('button', { name: '분석 실행' }));
    expect(await screen.findByTestId('stored-result', {}, { timeout: 3500 })).toHaveTextContent('영업이익 증감');
    const condition = screen.getByTestId('analysis-condition-card');
    const summary = screen.getByTestId('analysis-summary-header');
    expect(condition.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(summary).getByRole('button', { name: '분석 근거 엑셀 내려받기' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '분석 근거 엑셀 내려받기' })).toHaveLength(1);
    expect(calls.some((value) => value.includes(`/api/jobs/${JOB}`))).toBe(true);
    expect(calls.some((value) => value.includes(`/api/admin/results/${RESULT}/presentation`))).toBe(true);
    const submitCall = fetchMock.mock.calls.find((value) => String(value[0]).endsWith('/api/analyses'));
    expect(submitCall).toBeDefined();
    if (!submitCall) throw new Error('submit request was not observed');
    const submitInit = submitCall[1] as RequestInit;
    const submitted = JSON.parse(String(submitInit.body));
    expect(submitted.idempotency_key).toMatch(/^[0-9a-f-]{36}$/);
    expect(submitted.baseline_sales_fx_monthly).toEqual({ '2026-01': 1480 });
    expect(submitted.comparison_sales_fx_monthly).toEqual({ '2026-01': 1490 });
    expect(submitted.baseline_sales_fx).toBeUndefined();
    expect((submitInit.headers as Headers).get('X-CSRF-Token')).toBe('test-csrf');
  }, 5000);

  it('preserves overlapping monthly FX values and sends exact YYYY-MM maps', async () => {
    window.sessionStorage.removeItem('pnl.active-analysis-job-id');
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith('/api/models')) return json({ models: [
        { model_id: BASE, display_name: 'Base', model_type: 'PLAN', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: true, dto_version: '1' },
        { model_id: COMP, display_name: 'Comparison', model_type: 'ACTUAL', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: false, dto_version: '1' },
      ], dto_version: '1' });
      if (path.endsWith('/api/analyses')) return json({ job_id: JOB, status: 'PENDING', execution_state: 'QUEUED', idempotency_replayed: false, dto_version: '1' });
      if (path.endsWith(`/api/jobs/${JOB}`)) return json({
        job_id: JOB, status: 'PENDING', baseline_model_id: BASE, comparison_model_id: COMP,
        start_month: 8, end_month: 10, attempt: 1, max_attempts: 3,
        created_at: '', heartbeat_at: null, completed_at: null, result_id: null,
        error_code: null, error_message: null, execution_state: 'QUEUED', dto_version: '1',
      });
      throw new Error(`unexpected request ${path} ${init?.method || 'GET'}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<CoreAnalysisView role="admin" />);
    expect(await screen.findByText('분석 조건 설정')).toBeInTheDocument();

    const start = screen.getByLabelText('시작 월') as HTMLInputElement;
    expect(start).toHaveValue('01');
    expect(screen.getByLabelText('종료 월')).toHaveValue('12');
    expect(start.type).toBe('text');
    expect(start.inputMode).toBe('numeric');

    fireEvent.focus(start);
    expect(start.selectionStart).toBe(0);
    expect(start.selectionEnd).toBe(start.value.length);
    fireEvent.change(start, { target: { value: '' } });
    expect(start).toHaveValue('');
    fireEvent.change(start, { target: { value: '7' } });
    expect(start).toHaveValue('7');
    fireEvent.blur(start);
    expect(start).toHaveValue('07');
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '9' } });
    await fillMonthlyFx('2026-07', '1480', '1385');
    await fillMonthlyFx('2026-08', '1480.25', '1402.5');
    await fillMonthlyFx('2026-09', '1481', '1417');
    const august = screen.getByLabelText('2026-08 기준 매출환율 (KRW/USD)') as HTMLInputElement;
    expect(august.type).toBe('text');
    expect(august.inputMode).toBe('decimal');
    fireEvent.focus(august);
    expect(august.selectionStart).toBe(0);
    expect(august.selectionEnd).toBe(august.value.length);

    fireEvent.change(start, { target: { value: '8' } });
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '10' } });
    expect(await screen.findByLabelText('2026-10 기준 매출환율 (KRW/USD)')).toHaveValue('');
    expect(screen.queryByLabelText('2026-07 기준 매출환율 (KRW/USD)')).not.toBeInTheDocument();
    expect(screen.getByLabelText('2026-08 기준 매출환율 (KRW/USD)')).toHaveValue('1480.25');
    expect(screen.getByLabelText('2026-09 비교 매출환율 (KRW/USD)')).toHaveValue('1417');
    expect(screen.getByRole('button', { name: '분석 실행' })).toBeDisabled();
    await fillMonthlyFx('2026-10', '1482', '1430');
    fireEvent.click(screen.getByRole('button', { name: '분석 실행' }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/api/analyses'))).toBe(true));
    const submitCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/api/analyses'));
    if (!submitCall) throw new Error('submit request was not observed');
    const body = JSON.parse(String((submitCall[1] as RequestInit).body));
    expect(body.start_month).toBe(8);
    expect(body.end_month).toBe(10);
    expect(body.baseline_sales_fx_monthly).toEqual({
      '2026-08': 1480.25, '2026-09': 1481, '2026-10': 1482,
    });
    expect(body.comparison_sales_fx_monthly).toEqual({
      '2026-08': 1402.5, '2026-09': 1417, '2026-10': 1430,
    });
    expect(body.baseline_sales_fx).toBeUndefined();
    window.sessionStorage.removeItem('pnl.active-analysis-job-id');
  });

  it('clears cached Viewer result after the backend later denies availability', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/viewer/analysis-results')) return json(viewerResults(RESULT, OTHER_RESULT));
      if (path.endsWith(`/api/viewer/results/${RESULT}/presentation`)) return json(presentationFixture());
      if (path.endsWith(`/api/viewer/results/${OTHER_RESULT}/presentation`)) {
        return json({ error: { code: 'RESULT_NOT_AVAILABLE', message: 'Result not available', field_errors: {}, correlation_id: null, dto_version: '1' } }, 404);
      }
      throw new Error(`unexpected request ${path}`);
    }));
    render(<CoreAnalysisView role="viewer" />);
    expect(await screen.findByTestId('stored-result')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('분석 결과 선택'), { target: { value: OTHER_RESULT } });
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
    expect(await screen.findByText('분석 조건 설정')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '1' } });
    await fillMonthlyFx('2026-01', '1480', '1490');
    const run = screen.getByRole('button', { name: '분석 실행' });
    fireEvent.click(run);
    expect(await screen.findByText('서버에 연결할 수 없습니다.')).toBeInTheDocument();
    fireEvent.click(run);
    expect(await screen.findByText('분석 요청 접수')).toBeInTheDocument();
    expect(screen.queryByText('QUEUED')).not.toBeInTheDocument();
    expect(screen.getByLabelText('기준 모형')).toBeDisabled();
    expect(screen.getByLabelText('비교 모형')).toBeDisabled();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    expect(await screen.findByText('분석 계산에 실패했습니다.', {}, { timeout: 3_500 })).toBeInTheDocument();
    expect(screen.getAllByText('Job failed')).toHaveLength(1);
    expect(screen.queryByText('분석 결과를 불러오지 못했습니다.')).not.toBeInTheDocument();
  });

  it('treats malformed Result payload as INVALID_PAYLOAD rather than READY', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => String(input).endsWith('/api/viewer/analysis-results')
      ? json(viewerResults(RESULT))
      : json({ result_id: RESULT, job_id: JOB, analysis_view: null, provenance: {} })));
    render(<CoreAnalysisView role="viewer" />);
    expect(await screen.findByText('서버 응답 형식이 올바르지 않습니다.')).toBeInTheDocument();
    expect(screen.queryByTestId('stored-result')).not.toBeInTheDocument();
  });

  it('keeps EMPTY, ERROR and FORBIDDEN presentation states distinct', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/viewer/analysis-results')) return json(viewerResults(RESULT, OTHER_RESULT, THIRD_RESULT));
      if (path.endsWith(`/api/viewer/results/${RESULT}/presentation`)) return json({ error: { code: 'RESULT_NOT_AVAILABLE', message: 'Result not available' } }, 404);
      if (path.endsWith(`/api/viewer/results/${OTHER_RESULT}/presentation`)) return json({ error: { code: 'TRANSIENT_SYSTEM_ERROR', message: 'temporary' } }, 503);
      if (path.endsWith(`/api/viewer/results/${THIRD_RESULT}/presentation`)) return json({ error: { code: 'FORBIDDEN', message: 'Forbidden' } }, 403);
      throw new Error(`unexpected request ${path}`);
    }));
    const view = render(<CoreAnalysisView role="viewer" />);
    const select = screen.getByLabelText('분석 결과 선택');
    expect(await screen.findByText('조회 가능한 공개 분석 결과가 없습니다.')).toBeInTheDocument();

    fireEvent.change(select, { target: { value: OTHER_RESULT } });
    expect(await screen.findByText('분석 결과를 불러오지 못했습니다.')).toBeInTheDocument();
    expect(screen.queryByTestId('viewer-empty')).not.toBeInTheDocument();

    fireEvent.change(select, { target: { value: THIRD_RESULT } });
    expect(await screen.findByText('이 분석 결과를 볼 권한이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('분석 결과를 불러오지 못했습니다.')).not.toBeInTheDocument();
    view.unmount();
  });

  it('restores an actual in-flight Job from session storage without inventing progress', async () => {
    window.sessionStorage.setItem('pnl.active-analysis-job-id', JOB);
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/models')) return json({ models: [
        { model_id: BASE, display_name: 'Base', model_type: 'PLAN', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: true, dto_version: '1' },
        { model_id: COMP, display_name: 'Comparison', model_type: 'ACTUAL', model_year: 2026, start_month: 1, end_month: 12, is_published: true, is_default: false, dto_version: '1' },
      ] });
      if (path.endsWith('/api/admin/worker')) return json({ error: { code: 'TRANSIENT_SYSTEM_ERROR', message: 'not configured' } }, 503);
      if (path.endsWith(`/api/jobs/${JOB}`)) return json({
        job_id: JOB, status: 'PROCESSING', baseline_model_id: BASE, comparison_model_id: COMP,
        start_month: 1, end_month: 12, attempt: 1, max_attempts: 3,
        created_at: '2026-08-11T00:00:00Z', heartbeat_at: '2026-08-11T00:00:01Z',
        completed_at: null, result_id: null, error_code: null, error_message: null,
        execution_state: 'PROCESSING', dto_version: '1',
      });
      throw new Error(`unexpected request ${path}`);
    }));
    render(<CoreAnalysisView role="admin" />);
    expect(await screen.findByText('손익 분석 중')).toBeInTheDocument();
    expect(screen.queryByText('PROCESSING')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '분석 실행' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '새 분석' })).toBeDisabled();
  });

});

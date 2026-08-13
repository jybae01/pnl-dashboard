import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CoreAnalysisView } from './CoreAnalysisView';
import { CalculationHistoryView } from './CalculationHistoryView';
import { presentationFixture, TEST_BASE, TEST_COMPARISON, TEST_JOB, TEST_RESULT } from './presentationTestFixture';

const RESULT = TEST_RESULT;
const JOB = TEST_JOB;
const OTHER_JOB = '55555555-5555-4555-8555-555555555555';
const OTHER_RESULT = '66666666-6666-4666-8666-666666666666';

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }));
}

function historyItem(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    job_id: JOB,
    result_id: RESULT,
    status: 'COMPLETED',
    baseline_model_id: TEST_BASE,
    baseline_model_name: 'Base Plan',
    comparison_model_id: TEST_COMPARISON,
    comparison_model_name: 'Actual August',
    start_month: 1,
    end_month: 12,
    attempt: 1,
    max_attempts: 3,
    created_at: '2026-08-11T00:00:00Z',
    completed_at: '2026-08-11T00:01:00Z',
    error_code: null,
    error_message: null,
    is_published: true,
    ...overrides,
  };
}

function historyPage(items: unknown[], cursor: { created_at: string; job_id: string } | null = null) {
  return json({
    items,
    next_before_created_at: cursor?.created_at || null,
    next_before_job_id: cursor?.job_id || null,
    dto_version: '1',
  });
}

function apiError(code: string, status = 500) {
  return json({ error: { code, message: `raw ${code} / ${RESULT}`, field_errors: {}, correlation_id: null, dto_version: '1' } }, status);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Evidence and history vertical slice', () => {
  it('shows status rows, hides IDs in the table, opens technical detail, and exposes exact completed actions', async () => {
    const onOpenResult = vi.fn();
    const revoke = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: revoke });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes('/api/admin/calculation-history')) return historyPage([
        historyItem(),
        historyItem({ job_id: OTHER_JOB, result_id: null, status: 'PROCESSING', completed_at: null, is_published: false }),
        historyItem({ job_id: '77777777-7777-4777-8777-777777777777', result_id: null, status: 'PENDING', completed_at: null, is_published: false }),
        historyItem({ job_id: '88888888-8888-4888-8888-888888888888', result_id: null, status: 'FAILED', completed_at: '2026-08-11T00:02:00Z', error_code: 'preflight_failed', error_message: `preflight_failed ${RESULT}`, is_published: false }),
      ]);
      if (path.endsWith('/evidence')) return Promise.resolve(new Response(new Blob(['xlsx']), {
        status: 200,
        headers: {
          'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'Content-Disposition': "attachment; filename*=utf-8''evidence.xlsx",
        },
      }));
      throw new Error(path);
    }));
    render(<CalculationHistoryView onOpenResult={onOpenResult} />);
    expect((await screen.findAllByText('Base Plan')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('완료').length).toBeGreaterThan(1);
    expect(screen.getAllByText('분석 중').length).toBeGreaterThan(0);
    expect(screen.getAllByText('분석 대기').length).toBeGreaterThan(0);
    expect(screen.getAllByText('분석 실패').length).toBeGreaterThan(0);
    expect(screen.getByText('워크북 사전 검증을 통과하지 못했습니다.')).toBeInTheDocument();
    expect(screen.queryByText(/preflight_failed/)).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '결과 보기' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: '분석 근거 엑셀 내려받기' })).toHaveLength(1);
    expect(screen.queryByText(RESULT)).not.toBeInTheDocument();
    expect(screen.queryByText(JOB)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '결과 보기' }));
    expect(onOpenResult).toHaveBeenCalledWith(RESULT);
    fireEvent.click(screen.getAllByRole('button', { name: '상세' })[0]);
    expect(screen.getByText('관리자 기술 정보')).toBeInTheDocument();
    fireEvent.click(screen.getByText('관리자 기술 정보'));
    expect(screen.getByText(RESULT)).toBeInTheDocument();
    expect(screen.getByText(JOB)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '분석 근거 엑셀 내려받기' }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:test'));
  });

  it('filters only loaded history by model name and status, with a distinct filter-empty state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(historyPage([
      historyItem({ baseline_model_name: 'Budget Base', comparison_model_name: 'Actual Result' }),
      historyItem({ job_id: OTHER_JOB, result_id: null, baseline_model_name: 'Forecast Base', comparison_model_name: 'Forecast Result', status: 'FAILED', error_code: 'MODEL_NOT_FOUND', error_message: 'raw MODEL_NOT_FOUND' }),
    ])));
    render(<CalculationHistoryView />);
    expect((await screen.findAllByText('Budget Base')).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText('계산 이력 검색'), { target: { value: 'Forecast' } });
    expect(screen.getByText('Forecast Base')).toBeInTheDocument();
    expect(screen.queryByText('Budget Base')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('계산 이력 상태 필터'), { target: { value: 'COMPLETED' } });
    expect(screen.getByText('조건에 맞는 계산 이력이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('raw MODEL_NOT_FOUND')).not.toBeInTheDocument();
  });

  it('keeps empty, error, and forbidden states distinct', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(historyPage([])));
    render(<CalculationHistoryView />);
    expect(await screen.findByText('계산 이력이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('계산 이력을 불러오지 못했습니다.')).not.toBeInTheDocument();

    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(apiError('TRANSIENT_SYSTEM_ERROR')));
    render(<CalculationHistoryView />);
    expect(await screen.findByText('계산 이력을 불러오지 못했습니다.')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('일시적인 오류가 발생했습니다.');
    expect(screen.queryByText(/raw TRANSIENT/)).not.toBeInTheDocument();

    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(apiError('FORBIDDEN', 403)));
    render(<CalculationHistoryView />);
    expect(await screen.findByText('계산 이력에 접근할 수 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('계산 이력이 없습니다.')).not.toBeInTheDocument();
  });

  it('uses the server keyset cursor for the next page and appends server order', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(historyPage([historyItem({ baseline_model_name: 'First Page' })], { created_at: '2026-08-10T00:00:00Z', job_id: JOB }))
      .mockResolvedValueOnce(historyPage([historyItem({ job_id: OTHER_JOB, result_id: OTHER_RESULT, baseline_model_name: 'Second Page' })]));
    vi.stubGlobal('fetch', fetchMock);
    render(<CalculationHistoryView />);
    expect((await screen.findAllByText('First Page')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '다음 이력 보기' }));
    expect(await screen.findByText('Second Page')).toBeInTheDocument();
    const nextCall = fetchMock.mock.calls[1];
    expect(String(nextCall[0])).toContain('before_created_at=2026-08-10T00%3A00%3A00Z');
    expect(String(nextCall[0])).toContain(`before_job_id=${JOB}`);
  });

  it('opens the exact requested Result in the admin analysis route without active-job recovery or submit', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith(`/api/admin/results/${RESULT}/presentation`)) return json(presentationFixture());
      if (path.endsWith('/api/models')) return json({ models: [], dto_version: '1' });
      if (path.endsWith('/api/admin/worker')) return json({});
      throw new Error(`${init?.method || 'GET'} ${path}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    window.sessionStorage.setItem('pnl.active-analysis-job-id', 'stale-job-that-must-not-load');
    render(<CoreAnalysisView role="admin" initialResultId={RESULT} />);
    expect(await screen.findByTestId('analysis-presentation')).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith(`/api/admin/results/${RESULT}/presentation`))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/jobs/'))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/api/analyses'))).toBe(false);
  });
});

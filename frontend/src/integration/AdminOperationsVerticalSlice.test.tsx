import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { CoreAnalysisView } from './CoreAnalysisView';
import { ModelManagementView } from './ModelManagementView';
import { AdminOperationsView } from './AdminOperationsView';

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }));
}

function worker(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    desired_instance_count: 0,
    configured_instance_count: 0,
    actual_instance_count: 0,
    queue_depth: 0,
    claimable_count: 0,
    pending_count: 0,
    processing_count: 0,
    active_lease_count: 0,
    active_heartbeat_count: 0,
    recovery_pending_count: 0,
    work_exists: false,
    idle_seconds: 1800,
    last_worker_activity_at: '2026-08-12T00:00:00Z',
    last_scaling_result: null,
    platform_reconciling: false,
    platform_ready: false,
    operating_policy: 'DEMAND_ONLY',
    idle_policy_seconds: 1800,
    dto_version: '1',
    ...overrides,
  };
}

function apiError(code: string, status = 500) {
  return json({ error: { code, message: `raw ${code}`, field_errors: {}, correlation_id: null, dto_version: '1' } }, status);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('admin operations vertical slice', () => {
  it('maps idle, starting, active, and stopping from direct DTO fields and refreshes only on demand', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json(worker()))
      .mockResolvedValueOnce(json(worker({ desired_instance_count: 1, configured_instance_count: 1, actual_instance_count: null, platform_reconciling: true })))
      .mockResolvedValueOnce(json(worker({ desired_instance_count: 1, configured_instance_count: 1, actual_instance_count: 1, platform_ready: true })))
      .mockResolvedValueOnce(json(worker({ desired_instance_count: 0, configured_instance_count: 0, actual_instance_count: 1, platform_reconciling: true })));
    vi.stubGlobal('fetch', fetchMock);
    render(<AdminOperationsView />);

    expect(await screen.findByText('대기 상태')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText('수요 발생 시 운영')).toBeInTheDocument();
    expect(screen.getAllByText('약 30분 기준').length).toBeGreaterThan(0);
    expect(screen.queryByText('DEMAND_ONLY')).not.toBeInTheDocument();
    expect(screen.queryByText('STARTING_WORKER')).not.toBeInTheDocument();

    const refresh = screen.getByRole('button', { name: '상태 새로고침' });
    fireEvent.click(refresh);
    expect(await screen.findByText('분석 엔진 시작 중')).toBeInTheDocument();
    fireEvent.click(refresh);
    expect(await screen.findByText('분석 엔진 가동 중')).toBeInTheDocument();
    fireEvent.click(refresh);
    expect(await screen.findByText('분석 엔진 종료 중')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it('confirms wake and stop separately, preserves CSRF, and applies returned state', async () => {
    document.cookie = 'pnl_csrf=operations-csrf; Path=/';
    const calls: Array<[string, RequestInit | undefined]> = [];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      calls.push([path, init]);
      if (path.endsWith('/api/admin/worker/emergency-wake')) return json(worker({ desired_instance_count: 1, configured_instance_count: 1, actual_instance_count: 1, platform_ready: true }));
      if (path.endsWith('/api/admin/worker/safe-stop')) return json(worker());
      if (path.endsWith('/api/admin/worker')) return json(worker());
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<AdminOperationsView />);
    await screen.findByText('대기 상태');

    fireEvent.click(screen.getByRole('button', { name: '분석 엔진 긴급 가동' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('분석 엔진을 긴급 가동할까요?');
    fireEvent.click(screen.getByRole('button', { name: '확인' }));
    expect(await screen.findByText('분석 엔진 가동 중')).toBeInTheDocument();
    const wake = calls.find(([path]) => path.endsWith('/api/admin/worker/emergency-wake'));
    if (!wake?.[1]) throw new Error('wake request was not observed');
    expect(wake[1].method).toBe('POST');
    expect((wake[1].headers as Headers).get('X-CSRF-Token')).toBe('operations-csrf');

    fireEvent.click(screen.getByRole('button', { name: '분석 엔진 긴급 종료' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('분석 엔진을 긴급 종료할까요?');
    fireEvent.click(screen.getByRole('button', { name: '확인' }));
    expect(await screen.findByText('대기 상태')).toBeInTheDocument();
    const stop = calls.find(([path]) => path.endsWith('/api/admin/worker/safe-stop'));
    if (!stop?.[1]) throw new Error('stop request was not observed');
    expect(stop[1].method).toBe('POST');
    expect((stop[1].headers as Headers).get('X-CSRF-Token')).toBe('operations-csrf');
  });

  it('blocks duplicate mutation while pending and maps WORKER_BUSY without raw diagnostics', async () => {
    let resolveStop: (value: Response) => void = () => undefined;
    const pendingStop = new Promise<Response>((resolve) => { resolveStop = resolve; });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/admin/worker/safe-stop')) return pendingStop;
      if (path.endsWith('/api/admin/worker')) return json(worker({ desired_instance_count: 1, configured_instance_count: 1, actual_instance_count: 1, platform_ready: true, work_exists: true }));
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<AdminOperationsView />);
    await screen.findByText('분석 엔진 가동 중');
    fireEvent.click(screen.getByRole('button', { name: '분석 엔진 긴급 종료' }));
    fireEvent.click(screen.getByRole('button', { name: '확인' }));
    const confirm = screen.getByRole('button', { name: '처리 중…' });
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/api/admin/worker/safe-stop'))).toHaveLength(1);
    resolveStop(await apiError('WORKER_BUSY', 409));
    expect(await screen.findByText('현재 진행 중인 작업이 있어 분석 엔진 긴급 종료를 완료하지 못했습니다.')).toBeInTheDocument();
    expect(screen.queryByText('raw WORKER_BUSY')).not.toBeInTheDocument();
  });

  it('separates GET error and forbidden from an operational attention state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(apiError('TRANSIENT_SYSTEM_ERROR', 503)));
    render(<AdminOperationsView />);
    expect(await screen.findByText('분석 엔진 상태를 확인하지 못했습니다.')).toBeInTheDocument();
    expect(screen.queryByText('운영 상태 확인 필요')).not.toBeInTheDocument();

    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(apiError('FORBIDDEN', 403)));
    render(<AdminOperationsView />);
    expect(await screen.findByText('운영 화면에 접근할 수 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('분석 엔진 상태를 확인하지 못했습니다.')).not.toBeInTheDocument();

    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json(worker({ desired_instance_count: 1, configured_instance_count: 0, actual_instance_count: null, platform_reconciling: false, platform_ready: false }))));
    render(<AdminOperationsView />);
    expect(await screen.findByText('분석 엔진 시작 중')).toBeInTheDocument();

    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json(worker({ desired_instance_count: 1, configured_instance_count: 1, actual_instance_count: 1, platform_reconciling: false, platform_ready: false }))));
    render(<AdminOperationsView />);
    expect(await screen.findByText('운영 상태 확인 필요')).toBeInTheDocument();
  });

  it('keeps history CTA on the existing management route and hides operations from Viewer navigation', async () => {
    const onHistory = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json(worker())));
    render(<AdminOperationsView onNavigateToHistory={onHistory} />);
    await screen.findByText('대기 상태');
    fireEvent.click(screen.getByRole('button', { name: '계산 이력 보기' }));
    expect(onHistory).toHaveBeenCalledTimes(1);

    cleanup();
    vi.unstubAllGlobals();
    window.location.hash = '#operations';
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/session')) return json({ authenticated: true, role: 'viewer', expires_at: '2026-08-12T00:00:00Z', dto_version: '1' });
      throw new Error(`unexpected request ${String(input)}`);
    }));
    render(<App />);
    expect(await screen.findByText('VIEWER · 공개 결과 조회')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '손익 분석' })).toBeInTheDocument();
    expect(screen.queryByText('분석 엔진 운영')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /운영 관리/ })).not.toBeInTheDocument();
  });

  it('opens the existing Calculation History section only when explicitly requested', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/admin/models')) return json({ models: [], dto_version: '1' });
      if (path.includes('/api/admin/calculation-history')) return json({ items: [], next_before_created_at: null, next_before_job_id: null, dto_version: '1' });
      throw new Error(`unexpected request ${path}`);
    }));
    render(<ModelManagementView initialHistoryOpen />);
    expect(await screen.findByText('계산 이력이 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '계산 이력' })).toBeInTheDocument();
  });
});

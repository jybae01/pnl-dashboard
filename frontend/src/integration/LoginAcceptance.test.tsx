import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { LoginView } from './LoginView';

function response(body: unknown, status: number, headers: Record<string, string> = {}) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = 'pnl_csrf=; Max-Age=0; Path=/';
  window.location.hash = '';
});

describe('confirmed Streamlit login UX adapter', () => {
  it('uses one concise login card with the official raster and no marketing prose', () => {
    render(<LoginView onAuthenticated={() => undefined} />);
    expect(document.querySelectorAll('.login-card')).toHaveLength(1);
    expect(document.querySelector('.login-brand-card')).not.toBeInTheDocument();
    const logo = screen.getByRole('img', { name: 'NANOH2O' });
    expect(logo).toHaveAttribute('src', expect.stringContaining('nanoh2o-logo-dark'));
    expect(screen.getByText('손익 데이터 모니터링')).toBeInTheDocument();
    expect(screen.getByText('접속 코드를 입력하여 대시보드를 확인하세요.')).toBeInTheDocument();
    expect(screen.getByLabelText('Access Code')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: '접속' })).toBeInTheDocument();
    expect(screen.queryByText('MANAGEMENT ACCOUNTING')).not.toBeInTheDocument();
    expect(screen.queryByText('정확한 데이터와 검증된 계산으로 손익 의사결정을 지원합니다.')).not.toBeInTheDocument();
    expect(screen.queryByText('접속 권한이 필요하면 시스템 관리자에게 문의하세요.')).not.toBeInTheDocument();
  });

  it('disables submit and exposes the real pending state while login is in flight', async () => {
    let resolveLogin: (value: Response) => void = () => undefined;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { resolveLogin = resolve; })));
    render(<LoginView onAuthenticated={() => undefined} />);
    fireEvent.change(screen.getByLabelText('Access Code'), { target: { value: 'pending-code' } });
    fireEvent.click(screen.getByRole('button', { name: '접속' }));
    expect(await screen.findByRole('button', { name: '확인 중…' })).toBeDisabled();
    resolveLogin(await response({ authenticated: true, role: 'admin', expires_at: '2026-08-12T00:00:00Z', dto_version: '1' }, 200));
  });

  it('shows the safe backend invalid-code error without client credential validation', async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => response({
      error: { code: 'AUTH_REQUIRED', message: '접속 코드가 올바르지 않습니다.', correlation_id: null },
    }, 401));
    vi.stubGlobal('fetch', fetchMock);
    render(<LoginView onAuthenticated={() => undefined} />);
    fireEvent.change(screen.getByLabelText('Access Code'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: '접속' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('접속 코드가 올바르지 않습니다.');
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/session/login'),
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ access_code: 'wrong' }),
      }),
    );
    const loginHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(loginHeaders.has('X-CSRF-Token')).toBe(false);
  });

  it('renders server-authoritative lockout time from Retry-After', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({
      error: { code: 'AUTH_REQUIRED', message: 'Login temporarily unavailable', correlation_id: null },
    }, 429, { 'Retry-After': '30' })));
    render(<LoginView onAuthenticated={() => undefined} />);
    fireEvent.change(screen.getByLabelText('Access Code'), { target: { value: 'attempt' } });
    fireEvent.click(screen.getByRole('button', { name: '접속' }));
    expect(await screen.findByText('남은 잠금시간: 30초')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '접속' })).toBeDisabled();
  });

  it('shows role purpose and invalidates the server session on logout', async () => {
    document.cookie = 'pnl_csrf=test; Path=/';
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith('/api/session') && !init?.method) {
        return response({ authenticated: true, role: 'viewer', expires_at: '2026-08-12T00:00:00Z', dto_version: '1' }, 200);
      }
      if (String(input).endsWith('/api/viewer/analysis-results')) return response({ results: [], dto_version: '1' }, 200);
      if (String(input).endsWith('/api/session/logout')) return response({ authenticated: false }, 200);
      throw new Error('unexpected request');
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    expect(await screen.findByLabelText('현재 권한: VIEWER')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    expect(await screen.findByText('손익 데이터 모니터링')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/session/logout'),
      expect.objectContaining({ method: 'POST' }),
    ));
    const logoutCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/api/session/logout'));
    if (!logoutCall?.[1]) throw new Error('logout request was not observed');
    expect(logoutCall[1]).toEqual(expect.objectContaining({ method: 'POST', credentials: 'include' }));
    expect((logoutCall[1].headers as Headers).get('X-CSRF-Token')).toBe('test');
  });

  it('keeps loading, anonymous, and server-error session states in the compact login family', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)));
    render(<App />);
    expect(screen.getByRole('status')).toHaveTextContent('세션 확인 중');
    expect(screen.getByRole('status').querySelector('.login-card--status')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'NANOH2O' })).toBeInTheDocument();

    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal('fetch', vi.fn(() => response({ error: { code: 'AUTH_REQUIRED', message: 'Authentication required' } }, 401)));
    render(<App />);
    expect(await screen.findByText('손익 데이터 모니터링')).toBeInTheDocument();

    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal('fetch', vi.fn(() => response({ error: { code: 'TRANSIENT_SYSTEM_ERROR', message: 'Unavailable' } }, 503)));
    render(<App />);
    const errorPanel = await screen.findByRole('alert');
    expect(errorPanel).toHaveTextContent('서버 세션을 확인할 수 없습니다');
    expect(within(errorPanel).getByRole('button', { name: '다시 시도' })).toBeInTheDocument();
    expect(within(errorPanel).getByRole('img', { name: 'NANOH2O' })).toBeInTheDocument();
  });

  it('keeps role-filtered routes, clamps Viewer hashes, and marks the active route', async () => {
    window.location.hash = '#operations';
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/session')) return response({ authenticated: true, role: 'viewer', expires_at: '2026-08-12T00:00:00Z', dto_version: '1' }, 200);
      if (path.endsWith('/api/viewer/analysis-results')) return response({ results: [], dto_version: '1' }, 200);
      throw new Error(`unexpected request ${path}`);
    }));
    render(<App />);
    const viewerNav = await screen.findByRole('navigation', { name: '주요 화면' });
    expect(within(viewerNav).getAllByRole('button')).toHaveLength(2);
    expect(Array.from(viewerNav.querySelectorAll('.nav-tab-btn')).map((button) => button.querySelector('span')?.textContent)).toEqual([
      '손익현황', '손익 분석',
    ]);
    expect(within(viewerNav).getByRole('button', { name: /손익 분석/ })).toHaveAttribute('aria-current', 'page');
    expect(within(viewerNav).getByRole('button', { name: /손익현황/ })).toBeInTheDocument();
    expect(within(viewerNav).queryByText(/^\d+\./)).not.toBeInTheDocument();
    expect(screen.getByLabelText('현재 권한: VIEWER')).toHaveTextContent('VIEWER');
    expect(screen.queryByRole('button', { name: /운영 관리/ })).not.toBeInTheDocument();

    cleanup();
    window.location.hash = '#management';
    vi.unstubAllGlobals();
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/session')) return response({ authenticated: true, role: 'admin', expires_at: '2026-08-12T00:00:00Z', dto_version: '1' }, 200);
      if (path.endsWith('/api/admin/models')) return response({ models: [], dto_version: '1' }, 200);
      if (path.includes('/api/admin/calculation-history')) return response({ items: [], next_before_created_at: null, next_before_job_id: null, dto_version: '1' }, 200);
      throw new Error(`unexpected request ${path}`);
    }));
    render(<App />);
    const adminNav = await screen.findByRole('navigation', { name: '주요 화면' });
    expect(within(adminNav).getAllByRole('button')).toHaveLength(5);
    expect(Array.from(adminNav.querySelectorAll('.nav-tab-btn')).map((button) => button.querySelector('span')?.textContent)).toEqual([
      '손익현황', '추정 산출', '손익 분석', '데이터 관리', '운영 관리',
    ]);
    expect(within(adminNav).getByRole('button', { name: /데이터 관리/ })).toHaveAttribute('aria-current', 'page');
    for (const label of ['손익현황', '추정 산출', '손익 분석', '데이터 관리', '운영 관리']) {
      expect(within(adminNav).getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(within(adminNav).queryByText(/^\d+\./)).not.toBeInTheDocument();
    expect(screen.getByLabelText('현재 권한: ADMIN')).toHaveTextContent('ADMIN');
    expect(screen.getByRole('button', { name: '로그아웃' })).toHaveAttribute('title', '로그아웃');
  });

  it('reveals an off-screen active tab by moving only the navigation scroller', async () => {
    window.location.hash = '#management';
    const scrollBy = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollBy', { configurable: true, value: scrollBy });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const isNavigation = this.getAttribute('aria-label') === '주요 화면';
      const isActive = this.getAttribute('aria-current') === 'page';
      const left = isActive ? 400 : 0;
      const width = isActive ? 120 : isNavigation ? 320 : 0;
      return {
        x: left, y: 0, left, right: left + width, top: 0, bottom: 46,
        width, height: 46, toJSON: () => ({}),
      } as DOMRect;
    });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/session')) return response({ authenticated: true, role: 'admin', expires_at: '2026-08-12T00:00:00Z', dto_version: '1' }, 200);
      if (path.endsWith('/api/admin/models')) return response({ models: [], dto_version: '1' }, 200);
      if (path.includes('/api/admin/calculation-history')) return response({ items: [], next_before_created_at: null, next_before_job_id: null, dto_version: '1' }, 200);
      throw new Error(`unexpected request ${path}`);
    }));
    render(<App />);
    expect(await screen.findByRole('button', { name: /데이터 관리/, current: 'page' })).toBeInTheDocument();
    await waitFor(() => expect(scrollBy).toHaveBeenCalledWith({ left: 200, top: 0, behavior: 'auto' }));
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).scrollBy;
  });
});

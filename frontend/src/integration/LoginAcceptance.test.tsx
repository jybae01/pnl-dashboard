import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
});

describe('confirmed Streamlit login UX adapter', () => {
  it('preserves the confirmed brand, copy, masked input and guidance', () => {
    render(<LoginView onAuthenticated={() => undefined} />);
    expect(screen.getByLabelText('NanoH2O 브랜드')).toBeInTheDocument();
    expect(screen.getByLabelText('NANOH2O Logo')).toBeInTheDocument();
    expect(screen.getByText('손익 데이터 모니터링')).toBeInTheDocument();
    expect(screen.getByText('접속 코드를 입력하여 대시보드를 확인하세요.')).toBeInTheDocument();
    expect(screen.getByLabelText('Access Code')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: '접속' })).toBeInTheDocument();
    expect(screen.getByText('접속 권한이 필요하면 시스템 관리자에게 문의하세요.')).toBeInTheDocument();
  });

  it('shows the safe backend invalid-code error without client credential validation', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({
      error: { code: 'AUTH_REQUIRED', message: '접속 코드가 올바르지 않습니다.', correlation_id: null },
    }, 401)));
    render(<LoginView onAuthenticated={() => undefined} />);
    fireEvent.change(screen.getByLabelText('Access Code'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: '접속' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('접속 코드가 올바르지 않습니다.');
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
      if (String(input).endsWith('/api/session/logout')) return response({ authenticated: false }, 200);
      throw new Error('unexpected request');
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    expect(await screen.findByText('VIEWER · 공개 결과 조회')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    expect(await screen.findByText('손익 데이터 모니터링')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/session/logout'),
      expect.objectContaining({ method: 'POST' }),
    ));
  });
});

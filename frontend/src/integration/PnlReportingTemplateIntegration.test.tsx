import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { bffClient } from './client';
import { ModelManagementView } from './ModelManagementView';


const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';


function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }));
}


function shellResponse(input: RequestInfo | URL) {
  const path = String(input);
  if (path.includes('/api/admin/models')) return json({ models: [], dto_version: '1' });
  if (path.includes('/api/admin/calculation-history')) {
    return json({ items: [], next_before_created_at: null, next_before_job_id: null, dto_version: '1' });
  }
  throw new Error(`unexpected request: ${path}`);
}


afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});


describe('P&L Reporting exact template delivery', () => {
  it('uses authenticated no-store GET and safely delivers the server filename with Blob cleanup', async () => {
    const createObjectURL = vi.fn(() => 'blob:pnl-reporting-template');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL });
    let clicked: { filename: string; hidden: boolean; connected: boolean } | null = null;
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked = { filename: this.download, hidden: this.hidden === true, connected: this.isConnected };
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(['approved-template-bytes']), {
      status: 200,
      headers: {
        'Content-Type': XLSX_MIME,
        'Content-Disposition': "attachment; filename=\"PNL_REPORTING_TEMPLATE_V1.xlsx\"; filename*=utf-8''PNL_REPORTING_TEMPLATE_V1.xlsx",
      },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await bffClient.downloadPnlReportingTemplate();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    expect(String(input)).toBe('/api/admin/pnl-reporting/template');
    expect(init).toMatchObject({ method: 'GET', credentials: 'include', cache: 'no-store' });
    expect(new Headers(init?.headers).has('X-CSRF-Token')).toBe(false);
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(clicked).toEqual({ filename: 'PNL_REPORTING_TEMPLATE_V1.xlsx', hidden: true, connected: true });
    expect(document.querySelector('a[download]')).not.toBeInTheDocument();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:pnl-reporting-template');
  });

  it('enables the mounted D-1 action and guards duplicate clicks while one download is pending', async () => {
    let resolveTemplate!: (response: Response) => void;
    const pendingTemplate = new Promise<Response>((resolve) => { resolveTemplate = resolve; });
    const fetchMock = vi.fn((input: RequestInfo | URL) => (
      String(input).endsWith('/api/admin/pnl-reporting/template')
        ? pendingTemplate
        : shellResponse(input)
    ));
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:pnl-template'), revokeObjectURL });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', fetchMock);
    render(<ModelManagementView />);
    await screen.findByText('등록된 모형이 없습니다.');

    const button = screen.getByRole('button', { name: 'P&L Reporting 표준 양식' });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    fireEvent.click(button);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/api/admin/pnl-reporting/template'))).toHaveLength(1);

    await act(async () => {
      resolveTemplate(new Response(new Blob(['approved-template-bytes']), {
        status: 200,
        headers: {
          'Content-Type': XLSX_MIME,
          'Content-Disposition': "attachment; filename*=utf-8''PNL_REPORTING_TEMPLATE_V1.xlsx",
        },
      }));
      await pendingTemplate;
    });
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:pnl-template'));
  });

  it('preserves structured non-2xx identity and shows safe system feedback without a fake Blob', async () => {
    const createObjectURL = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL: vi.fn() });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/admin/pnl-reporting/template')) {
        return json({ error: {
          code: 'TRANSIENT_SYSTEM_ERROR',
          message: 'private C:\\runtime\\resources actual_sha=secret',
          field_errors: {},
          correlation_id: 'safe-correlation',
          dto_version: '1',
        } }, 503);
      }
      return shellResponse(input);
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(bffClient.downloadPnlReportingTemplate()).rejects.toMatchObject({
      status: 503,
      code: 'TRANSIENT_SYSTEM_ERROR',
      correlationId: 'safe-correlation',
    });
    expect(createObjectURL).not.toHaveBeenCalled();

    render(<ModelManagementView />);
    await screen.findByText('등록된 모형이 없습니다.');

    fireEvent.click(screen.getByRole('button', { name: 'P&L Reporting 표준 양식' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('P&L Reporting 표준 양식을 내려받을 수 없습니다. 시스템 관리자에게 문의하세요.');
    expect(alert).not.toHaveTextContent(/private|resources|actual_sha|secret/);
    expect(createObjectURL).not.toHaveBeenCalled();
  });
});

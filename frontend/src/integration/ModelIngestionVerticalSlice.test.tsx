import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ModelManagementView } from './ModelManagementView';

const MODEL = '11111111-1111-4111-8111-111111111111';
const BASE = '22222222-2222-4222-8222-222222222222';
const SHA = 'a'.repeat(64);

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }));
}

const managementModel = (published: boolean) => ({
  model_id: MODEL, display_name: '2026 Actual', model_type: 'ACTUAL', model_year: 2026,
  start_month: 1, end_month: 12, version: 'V1', file_name: 'actual.xlsx',
  workbook_sha256: SHA, has_workbook_sha256: true,
  is_published: published, is_default: false,
  uploaded_at: '2026-08-11T00:00:00Z', dto_version: '1',
});

afterEach(() => vi.unstubAllGlobals());

describe('model ingestion vertical slice', () => {
  it('uploads exact selected file through multipart, publishes, and refreshes analysis options', async () => {
    document.cookie = 'pnl_csrf=test-csrf; Path=/';
    let uploaded = false;
    let published = false;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith('/api/admin/models') && (!init?.method || init.method === 'GET')) {
        return json({ models: uploaded ? [managementModel(published)] : [], dto_version: '1' });
      }
      if (path.endsWith('/api/admin/models') && init?.method === 'POST') {
        uploaded = true;
        return json({ model: managementModel(false), idempotency_replayed: false, dto_version: '1' });
      }
      if (path.includes(`/api/admin/models/${MODEL}/publication`)) {
        published = true;
        return json({ model: managementModel(true), dto_version: '1' });
      }
      if (path.endsWith('/api/models')) {
        const base = {
          model_id: BASE, display_name: '2026 Plan', model_type: 'PLAN', model_year: 2026,
          start_month: 1, end_month: 12, is_published: true, is_default: true, dto_version: '1',
        };
        const actual = {
          model_id: MODEL, display_name: '2026 Actual', model_type: 'ACTUAL', model_year: 2026,
          start_month: 1, end_month: 12, is_published: true, is_default: false, dto_version: '1',
        };
        return json({ models: published ? [base, actual] : [base], dto_version: '1' });
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<ModelManagementView />);
    expect(await screen.findByText('등록된 모델이 없습니다.')).toBeInTheDocument();
    const file = new File(['exact-browser-bytes'], 'actual.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    fireEvent.change(screen.getByLabelText('워크북 파일'), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText('모델명'), { target: { value: '2026 Actual' } });
    fireEvent.click(screen.getByRole('button', { name: '모형 등록' }));
    expect(await screen.findByText('2026 Actual 등록 완료 · 현재 비공개')).toBeInTheDocument();
    const uploadCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/api/admin/models') && init?.method === 'POST');
    if (!uploadCall) throw new Error('upload request is missing');
    const uploadInit = uploadCall[1] as RequestInit;
    const multipart = uploadInit.body;
    expect(multipart).toBeInstanceOf(FormData);
    if (!(multipart instanceof FormData)) throw new Error('multipart payload is missing');
    const sentFile = multipart.get('file');
    expect(sentFile).toBeInstanceOf(File);
    if (!(sentFile instanceof File)) throw new Error('multipart file is missing');
    expect(sentFile.name).toBe('actual.xlsx');
    expect(sentFile.size).toBe(new TextEncoder().encode('exact-browser-bytes').byteLength);
    expect((uploadInit.headers as Headers).get('Content-Type')).toBeNull();
    expect((uploadInit.headers as Headers).get('X-CSRF-Token')).toBe('test-csrf');
    expect(await screen.findByText('비공개')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '공개' }));
    expect(await screen.findByText('2026 Actual 공개 완료')).toBeInTheDocument();
    expect(await screen.findAllByRole('option', { name: /2026 Actual/ })).toHaveLength(2);
  });

  it('rejects a non-xlsx file before issuing an upload request', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/admin/models')) return json({ models: [] });
      if (String(input).endsWith('/api/models')) return json({ models: [] });
      throw new Error('unexpected upload');
    }));
    render(<ModelManagementView />);
    await screen.findByText('등록된 모델이 없습니다.');
    fireEvent.change(screen.getByLabelText('워크북 파일'), {
      target: { files: [new File(['csv'], 'bad.csv')] },
    });
    fireEvent.click(screen.getByRole('button', { name: '모형 등록' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('.xlsx 파일만 등록할 수 있습니다.');
  });
});

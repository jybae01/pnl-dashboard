import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ModelManagementView } from './ModelManagementView';

const MODEL = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const THIRD = '33333333-3333-4333-8333-333333333333';
const SHA = 'a'.repeat(64);

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }));
}

function model(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    model_id: MODEL, display_name: '2026 Actual', model_type: 'ACTUAL', model_year: 2026,
    start_month: 1, end_month: 12, version: 'V1', file_name: 'actual.xlsx',
    workbook_sha256: SHA, has_workbook_sha256: true,
    is_published: false, is_default: false, uploaded_at: '2026-08-11T00:00:00Z', dto_version: '1',
    ...overrides,
  };
}

function list(rows: unknown[]) { return response({ models: rows, dto_version: '1' }); }

function withEmptyHistory(fetcher: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes('/api/admin/calculation-history')) {
      return response({ items: [], next_before_created_at: null, next_before_job_id: null, dto_version: '1' });
    }
    return fetcher(input, init);
  });
}

function openUpload() {
  expect(screen.getByRole('heading', { name: '손익 데이터 모형 등록' })).toBeInTheDocument();
}

function apiError(code: string, status = 422) {
  return response({ error: { code, message: `raw ${code}`, field_errors: {}, correlation_id: null, dto_version: '1' } }, status);
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('model management vertical slice', () => {
  it('renders scenario badges, dense metadata, default state, and hides technical SHA in the table', async () => {
    const longVersion = 'QA-LC-FINAL-69006d5';
    const rows = [
      model({ display_name: 'Plan Base', model_type: 'PLAN', is_published: true, is_default: true }),
      model({ model_id: OTHER, display_name: '2026 Forecast', model_type: 'FORECAST', start_month: 7, end_month: 12, version: longVersion, is_published: true }),
      model({ model_id: THIRD, display_name: '2026 Actual', model_type: 'ACTUAL', is_published: true }),
    ];
    vi.stubGlobal('fetch', withEmptyHistory(vi.fn().mockResolvedValueOnce(list(rows))));
    render(<ModelManagementView />);
    expect(await screen.findByText('Plan Base')).toBeInTheDocument();
    expect(screen.getAllByText('계획').some((element) => element.classList.contains('data-management__scenario--plan'))).toBe(true);
    expect(screen.getAllByText('추정').some((element) => element.classList.contains('data-management__scenario--forecast'))).toBe(true);
    expect(screen.getAllByText('실적').some((element) => element.classList.contains('data-management__scenario--actual'))).toBe(true);
    expect(screen.getByText('기본')).toBeInTheDocument();
    expect(screen.getAllByText('7~12월').length).toBeGreaterThan(0);
    expect(screen.queryByText(SHA)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^2026 Forecast/ }));
    expect(screen.getByText(SHA)).toBeInTheDocument();
    const table = screen.getAllByRole('table')[0];
    expect(within(table).getAllByRole('columnheader')).toHaveLength(10);
    expect(within(table).getByTitle(longVersion)).toHaveClass('data-management__version-cell');
  });

  it('supports name/file/period search and type/publication filters', async () => {
    const rows = [
      model({ display_name: 'Plan Budget', model_type: 'PLAN', file_name: 'budget.xlsx', is_published: true }),
      model({ model_id: OTHER, display_name: 'Forecast July', model_type: 'FORECAST', file_name: 'july.xlsx', start_month: 7, end_month: 12, is_published: false }),
    ];
    vi.stubGlobal('fetch', withEmptyHistory(vi.fn().mockResolvedValueOnce(list(rows))));
    render(<ModelManagementView />);
    await screen.findByText('Plan Budget');
    fireEvent.change(screen.getByLabelText('모형 검색'), { target: { value: 'july' } });
    expect(screen.getByText('Forecast July')).toBeInTheDocument();
    expect(screen.queryByText('Plan Budget')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('공개 상태 필터'), { target: { value: 'PUBLISHED' } });
    expect(screen.getByText('조건에 맞는 모형이 없습니다.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('모형 검색'), { target: { value: '' } });
    fireEvent.click(within(screen.getByRole('group', { name: '유형 필터' })).getByRole('button', { name: '계획' }));
    expect(screen.getByText('Plan Budget')).toBeInTheDocument();
    expect(screen.queryByText('Forecast July')).not.toBeInTheDocument();
  });

  it('distinguishes full empty from filter empty', async () => {
    vi.stubGlobal('fetch', withEmptyHistory(vi.fn().mockResolvedValueOnce(list([]))));
    render(<ModelManagementView />);
    expect(await screen.findByText('등록된 모형이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('조건에 맞는 모형이 없습니다.')).not.toBeInTheDocument();

    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal('fetch', withEmptyHistory(vi.fn().mockResolvedValueOnce(list([model()]))));
    render(<ModelManagementView />);
    await screen.findByText('2026 Actual');
    fireEvent.change(screen.getByLabelText('모형 검색'), { target: { value: '없는 이름' } });
    expect(screen.getByText('조건에 맞는 모형이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('등록된 모형이 없습니다.')).not.toBeInTheDocument();
  });

  it('uploads exact selected bytes via multipart and renders parsed period/publication summary', async () => {
    document.cookie = 'pnl_csrf=test-csrf; Path=/';
    let uploaded = false;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith('/api/admin/models') && (!init?.method || init.method === 'GET')) return list(uploaded ? [model()] : []);
      if (path.endsWith('/api/admin/models') && init?.method === 'POST') {
        uploaded = true;
        return response({ model: model({ display_name: 'Uploaded Forecast', model_type: 'FORECAST', start_month: 7, end_month: 12 }), idempotency_replayed: false, dto_version: '1' });
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('등록된 모형이 없습니다.');
    openUpload();
    const file = new File(['exact-browser-bytes'], 'forecast.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    fireEvent.change(screen.getByLabelText('워크북 파일'), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText('모형명'), { target: { value: 'Uploaded Forecast' } });
    fireEvent.change(screen.getByLabelText('모형 유형'), { target: { value: 'FORECAST' } });
    fireEvent.change(screen.getByLabelText('모델 연도'), { target: { value: '2026' } });
    fireEvent.click(screen.getByRole('button', { name: /^모형 등록$/ }));
    expect(await screen.findByText(/Uploaded Forecast · 2026년 7~12월 · 비공개 등록 완료/)).toBeInTheDocument();
    const uploadCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/api/admin/models') && init?.method === 'POST');
    if (!uploadCall) throw new Error('upload request is missing');
    const uploadInit = uploadCall[1] as RequestInit;
    expect(uploadInit.body).toBeInstanceOf(FormData);
    expect((uploadInit.headers as Headers).get('Content-Type')).toBeNull();
    expect((uploadInit.headers as Headers).get('X-CSRF-Token')).toBe('test-csrf');
    const sentFile = (uploadInit.body as FormData).get('file');
    expect((uploadInit.body as FormData).get('name')).toBe('Uploaded Forecast');
    expect((uploadInit.body as FormData).get('model_type')).toBe('FORECAST');
    expect((uploadInit.body as FormData).get('model_year')).toBe('2026');
    expect((uploadInit.body as FormData).get('version')).toBe('V1');
    expect(String((uploadInit.body as FormData).get('idempotency_key'))).not.toBe('');
    expect(sentFile).toBeInstanceOf(File);
    expect((sentFile as File).name).toBe('forecast.xlsx');
    expect((sentFile as File).size).toBe(new TextEncoder().encode('exact-browser-bytes').byteLength);
  });

  it('rejects upload validation and maps server errors without exposing raw backend text', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(list([]))
      .mockResolvedValueOnce(apiError('IDEMPOTENCY_CONFLICT', 409));
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('등록된 모형이 없습니다.');
    openUpload();
    expect(screen.getByRole('button', { name: /^모형 등록$/ })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('워크북 파일'), { target: { files: [new File(['csv'], 'bad.csv')] } });
    fireEvent.click(screen.getByRole('button', { name: /^모형 등록$/ }));
    expect(await screen.findByText('.xlsx 파일만 등록할 수 있습니다.')).toHaveAttribute('role', 'alert');
    fireEvent.change(screen.getByLabelText('워크북 파일'), { target: { files: [new File(['xls'], 'legacy.xls')] } });
    fireEvent.click(screen.getByRole('button', { name: /^모형 등록$/ }));
    expect(await screen.findByText('.xlsx 파일만 등록할 수 있습니다.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('워크북 파일'), { target: { files: [new File(['xlsx'], 'good.xlsx')] } });
    const year = screen.getByLabelText('모델 연도') as HTMLInputElement;
    fireEvent.change(year, { target: { value: '' } });
    expect(year.value).toBe('');
    fireEvent.click(screen.getByRole('button', { name: /^모형 등록$/ }));
    expect(await screen.findByText('모형명, 연도, 버전을 확인하세요.')).toHaveAttribute('role', 'alert');
    expect(year.value).toBe('');
    fireEvent.change(year, { target: { value: 'invalid' } });
    fireEvent.click(screen.getByRole('button', { name: /^모형 등록$/ }));
    expect(await screen.findByText('모형명, 연도, 버전을 확인하세요.')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.change(year, { target: { value: '2026' } });
    fireEvent.click(screen.getByRole('button', { name: /^모형 등록$/ }));
    expect(await screen.findByText(/같은 등록 키가 다른 내용에 사용되었습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/raw IDEMPOTENCY/)).not.toBeInTheDocument();
  });

  it('locks duplicate upload clicks while the synchronous request is pending', async () => {
    let resolveUpload: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => { resolveUpload = resolve; });
    const fetchMock = vi.fn().mockResolvedValueOnce(list([])).mockReturnValueOnce(pending).mockResolvedValueOnce(list([model({ display_name: 'Uploaded Forecast', model_type: 'FORECAST', is_published: true })]));
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('등록된 모형이 없습니다.');
    openUpload();
    fireEvent.change(screen.getByLabelText('워크북 파일'), { target: { files: [new File(['xlsx'], 'good.xlsx')] } });
    fireEvent.click(screen.getByRole('button', { name: /^모형 등록$/ }));
    fireEvent.click(screen.getByRole('button', { name: '등록 처리 중…' }));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: '등록 처리 중…' })).toBeDisabled();
    resolveUpload(await response({ model: model({ display_name: 'Uploaded' }), idempotency_replayed: false, dto_version: '1' }));
    expect(await screen.findByText(/Uploaded ·/)).toBeInTheDocument();
  });

  it('requires publication confirmation and sends publish+default as separate flags', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(list([model()]))
      .mockResolvedValueOnce(response({ model: model({ is_published: true, is_default: true }), dto_version: '1' }))
      .mockResolvedValueOnce(list([model({ is_published: true, is_default: true })]));
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('2026 Actual');
    fireEvent.click(screen.getByRole('button', { name: /^2026 Actual/ }));
    fireEvent.click(screen.getByRole('button', { name: /^공개 \+ 기본$/ }));
    expect(screen.getByRole('dialog')).toHaveTextContent('2026 Actual');
    expect(screen.getByRole('dialog')).toHaveTextContent('공개 및 기본 지정');
    fireEvent.click(screen.getByRole('dialog').querySelector('button.data-management__primary')!);
    await screen.findByText(/공개 및 기본 지정 완료/);
    const call = fetchMock.mock.calls[1];
    expect(JSON.parse(String((call[1] as RequestInit).body))).toEqual({ is_published: true, is_default: true });
  });

  it('supports publish without changing the default designation', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(list([model()]))
      .mockResolvedValueOnce(response({ model: model({ is_published: true, is_default: false }), dto_version: '1' }))
      .mockResolvedValueOnce(list([model({ is_published: true, is_default: false })]));
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('2026 Actual');
    fireEvent.click(screen.getByRole('button', { name: /^2026 Actual/ }));
    fireEvent.click(screen.getByRole('button', { name: /^공개$/ }));
    expect(screen.getByRole('dialog')).toHaveTextContent('이 모형을 공개합니다.');
    fireEvent.click(screen.getByRole('dialog').querySelector('button.data-management__primary')!);
    await screen.findByText(/공개 완료/);
    const call = fetchMock.mock.calls[1];
    expect(JSON.parse(String((call[1] as RequestInit).body))).toEqual({ is_published: true, is_default: false });
  });

  it('unpublishes with is_published=false and is_default=false', async () => {
    const published = model({ is_published: true, is_default: true });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(list([published]))
      .mockResolvedValueOnce(response({ model: model(), dto_version: '1' }))
      .mockResolvedValueOnce(list([model()]));
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('2026 Actual');
    fireEvent.click(screen.getByRole('button', { name: /^2026 Actual/ }));
    fireEvent.click(screen.getByRole('button', { name: /^공개 해제$/ }));
    expect(screen.getByRole('dialog')).toHaveTextContent('기본 모형 지정도 함께 해제');
    fireEvent.click(screen.getByRole('dialog').querySelector('button.data-management__danger')!);
    await screen.findByText(/공개 해제 완료/);
    const call = fetchMock.mock.calls[1];
    expect(JSON.parse(String((call[1] as RequestInit).body))).toEqual({ is_published: false, is_default: false });
  });

  it('keeps the publication confirmation open and maps publication errors safely', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(list([model()]))
      .mockResolvedValueOnce(apiError('MODEL_NOT_FOUND', 404));
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('2026 Actual');
    fireEvent.click(screen.getByRole('button', { name: /^2026 Actual/ }));
    fireEvent.click(screen.getByRole('button', { name: /^공개$/ }));
    fireEvent.click(screen.getByRole('dialog').querySelector('button.data-management__primary')!);
    expect(await screen.findByRole('alert')).toHaveTextContent('선택한 모형을 찾을 수 없습니다.');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.queryByText(/raw MODEL_NOT_FOUND/)).not.toBeInTheDocument();
  });

  it('supports CTA callbacks without inferring model context', async () => {
    vi.stubGlobal('fetch', withEmptyHistory(vi.fn().mockResolvedValueOnce(list([]))));
    const onForecast = vi.fn();
    const onAnalysis = vi.fn();
    render(<ModelManagementView onNavigateToForecast={onForecast} onNavigateToAnalysis={onAnalysis} />);
    await screen.findByText('등록된 모형이 없습니다.');
    fireEvent.click(screen.getByRole('button', { name: '추정 산출' }));
    fireEvent.click(screen.getByRole('button', { name: '손익분석 결과' }));
    expect(onForecast).toHaveBeenCalledTimes(1);
    expect(onAnalysis).toHaveBeenCalledTimes(1);
  });

  it('separates forbidden list state from empty state', async () => {
    vi.stubGlobal('fetch', withEmptyHistory(vi.fn().mockResolvedValueOnce(apiError('FORBIDDEN', 403))));
    render(<ModelManagementView />);
    expect(await screen.findByRole('heading', { name: '데이터 관리 권한이 없습니다.' })).toBeInTheDocument();
    expect(screen.queryByText('등록된 모형이 없습니다.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '새 모형 업로드' })).not.toBeInTheDocument();
  });

  it('confirms model hard delete, sends only selected IDs, shows partial results, and refetches', async () => {
    document.cookie = 'pnl_csrf=delete-csrf; Path=/';
    let reads = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith('/api/admin/models/delete')) return response({
        resource_type: 'model', requested_count: 2, deleted_count: 1, blocked_count: 1, failed_count: 0,
        items: [
          { resource_id: MODEL, status: 'DELETED', reason: 'DELETED', reference_counts: {}, idempotent_replayed: false },
          { resource_id: OTHER, status: 'BLOCKED_IN_USE', reason: 'MODEL_IN_USE', reference_counts: { analysis_jobs: 1 }, idempotent_replayed: false },
        ], dto_version: '1',
      });
      if (path.endsWith('/api/admin/models')) {
        reads += 1;
        return list(reads === 1 ? [model(), model({ model_id: OTHER, display_name: 'Referenced Model' })] : [model({ model_id: OTHER, display_name: 'Referenced Model' })]);
      }
      throw new Error(path);
    });
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('Referenced Model');
    fireEvent.click(screen.getByLabelText('표시된 모형 전체 선택'));
    fireEvent.click(screen.getByRole('button', { name: '선택 모형 삭제' }));
    expect(screen.getByRole('dialog', { name: /선택한 모형 2건/ })).toHaveTextContent('복구할 수 없습니다');
    fireEvent.click(screen.getByRole('button', { name: '영구 삭제' }));

    expect(await screen.findByText('2건 요청 / 1건 삭제 / 0건 Storage 정리 필요 / 1건 차단 / 0건 상태 확인 필요 / 0건 실패')).toBeInTheDocument();
    expect(screen.getByText(/분석·Forecast 등에서 사용 중입니다/)).toBeInTheDocument();
    expect(screen.queryByText('2026 Actual')).not.toBeInTheDocument();
    expect(screen.getByText('Referenced Model')).toBeInTheDocument();
    expect(reads).toBe(2);
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/api/admin/models/delete'));
    expect(call?.[1]?.method).toBe('POST');
    expect(new Headers(call?.[1]?.headers).get('X-CSRF-Token')).toBe('delete-csrf');
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ ids: [MODEL, OTHER] });
    expect(JSON.stringify(JSON.parse(String(call?.[1]?.body)))).not.toContain('storage');
  });

  it('keeps a retry action for DB-deleted models whose Storage cleanup failed', async () => {
    let reads = 0;
    let deletes = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/api/admin/models/delete')) {
        deletes += 1;
        return response({
          resource_type: 'model', requested_count: 1,
          deleted_count: 0, cleanup_required_count: 1, blocked_count: 0, uncertain_count: 0, failed_count: 0,
          items: [{ resource_id: MODEL, status: 'CLEANUP_REQUIRED', reason: 'DB_DELETED_STORAGE_CLEANUP_REQUIRED', reference_counts: {}, idempotent_replayed: false }],
          dto_version: '1',
        });
      }
      if (path.endsWith('/api/admin/models/delete/retry')) {
        deletes += 1;
        return response({
          resource_type: 'model', requested_count: 1,
          deleted_count: 1, cleanup_required_count: 0, blocked_count: 0, uncertain_count: 0, failed_count: 0,
          items: [{ resource_id: MODEL, status: 'DELETED', reason: 'DELETED', reference_counts: {}, idempotent_replayed: true }],
          dto_version: '1',
        });
      }
      if (path.endsWith('/api/admin/models')) { reads += 1; return list(reads === 1 ? [model()] : []); }
      throw new Error(path);
    });
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('2026 Actual');
    fireEvent.click(screen.getByLabelText('2026 Actual 삭제 선택'));
    fireEvent.click(screen.getByRole('button', { name: '선택 모형 삭제' }));
    fireEvent.click(screen.getByRole('button', { name: '영구 삭제' }));
    expect(await screen.findByRole('button', { name: '모형 Storage 정리 재시도' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '모형 Storage 정리 재시도' }));
    expect(await screen.findByText('1건 요청 / 1건 삭제 / 0건 Storage 정리 필요 / 0건 차단 / 0건 상태 확인 필요 / 0건 실패')).toBeInTheDocument();
    expect(deletes).toBe(2);
  });

  it('discovers a cleanup receipt after reload and retries without a Storage path', async () => {
    document.cookie = 'pnl_csrf=recovery-csrf; Path=/';
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith('/api/admin/models/delete/recovery')) return response({
        resource_type: 'model', requested_count: 1,
        deleted_count: 0, cleanup_required_count: 1, blocked_count: 0, uncertain_count: 0, failed_count: 0,
        items: [{ resource_id: MODEL, status: 'CLEANUP_REQUIRED', reason: 'DB_DELETED_STORAGE_CLEANUP_REQUIRED', reference_counts: {}, idempotent_replayed: true }],
        dto_version: '1',
      });
      if (path.endsWith('/api/admin/models/delete/retry')) return response({
        resource_type: 'model', requested_count: 1,
        deleted_count: 1, cleanup_required_count: 0, blocked_count: 0, uncertain_count: 0, failed_count: 0,
        items: [{ resource_id: MODEL, status: 'DELETED', reason: 'DELETED', reference_counts: {}, idempotent_replayed: true }],
        dto_version: '1',
      });
      if (path.endsWith('/api/admin/models')) return list([]);
      throw new Error(`${init?.method || 'GET'} ${path}`);
    });
    vi.stubGlobal('fetch', withEmptyHistory(fetchMock));
    render(<ModelManagementView />);
    await screen.findByText('등록된 모형이 없습니다.');
    fireEvent.click(screen.getByRole('button', { name: '모형 삭제 복구 상태 확인' }));
    expect(await screen.findByRole('button', { name: '모형 Storage 정리 재시도' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '모형 Storage 정리 재시도' }));
    expect(await screen.findByText('1건 요청 / 1건 삭제 / 0건 Storage 정리 필요 / 0건 차단 / 0건 상태 확인 필요 / 0건 실패')).toBeInTheDocument();
    const retry = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/api/admin/models/delete/retry'));
    expect(JSON.parse(String(retry?.[1]?.body))).toEqual({ ids: [MODEL] });
    expect(String(retry?.[1]?.body)).not.toContain('storage');
  });
});

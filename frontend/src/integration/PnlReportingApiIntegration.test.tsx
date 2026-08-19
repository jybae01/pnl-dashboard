import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { bffClient } from './client';
import { ModelManagementView } from './ModelManagementView';

const DATASET_ID = '11111111-1111-4111-8111-111111111111';
const REPLACED_ID = '22222222-2222-4222-8222-222222222222';
const SHA = 'a'.repeat(64);

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }));
}

function uploadResponse(datasetType: 'PLAN' | 'ACTUAL', replayed = false) {
  return {
    datasetId: DATASET_ID,
    datasetType,
    reportingYear: 2026,
    actualThroughMonth: datasetType === 'ACTUAL' ? 6 : null,
    templateVersion: 'PNL_REPORTING_V1',
    sourceSha256: SHA,
    uploadedAt: '2026-08-19T01:00:00Z',
    warnings: [],
    supersededDatasetId: replayed ? null : REPLACED_ID,
    replayed,
  };
}

function apiError(status: number, code: string, fieldErrors: Record<string, string> = {}) {
  return response({ error: { code, message: 'safe error', field_errors: fieldErrors, correlation_id: 'cid', dto_version: '1' } }, status);
}

function shellResponse(input: RequestInfo | URL) {
  if (String(input).includes('/api/admin/models')) return response({ models: [], dto_version: '1' });
  if (String(input).includes('/api/admin/calculation-history')) {
    return response({ items: [], next_before_created_at: null, next_before_job_id: null, dto_version: '1' });
  }
  throw new Error(`unexpected request: ${String(input)}`);
}

function postCalls(fetchMock: ReturnType<typeof vi.fn>, suffix: string) {
  return fetchMock.mock.calls.filter(([input, init]) => String(input).endsWith(suffix) && init?.method === 'POST');
}

function postIdempotencyKeys(fetchMock: ReturnType<typeof vi.fn>, suffix: string) {
  return postCalls(fetchMock, suffix).map(([, init]) => {
    if (!init || !(init.body instanceof FormData)) throw new Error('expected multipart POST body');
    return init.body.get('idempotency_key');
  });
}

beforeEach(() => { document.cookie = 'pnl_csrf=reporting-csrf; Path=/'; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('P&L Reporting Admin upload API integration', () => {
  it('sends exact PLAN/ACTUAL multipart fields through shared credentials and CSRF and accepts 201/200 replay', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => response(uploadResponse('PLAN'), 201))
      .mockImplementationOnce(() => response(uploadResponse('ACTUAL', true), 200));
    vi.stubGlobal('fetch', fetchMock);
    const planFile = new File(['plan'], 'plan.xlsx');
    const actualFile = new File(['actual'], 'actual.xlsx');

    const plan = await bffClient.uploadPnlReportingPlan({ reportingYear: 2026, idempotencyKey: 'plan-key', file: planFile });
    const actual = await bffClient.uploadPnlReportingActual({ reportingYear: 2026, actualThroughMonth: 6, idempotencyKey: 'actual-key', file: actualFile });
    expect(plan.replayed).toBe(false);
    expect(actual.replayed).toBe(true);

    const [planUrl, planInit] = fetchMock.mock.calls[0];
    const planBody = planInit?.body as FormData;
    expect(String(planUrl)).toBe('/api/admin/pnl-reporting/plan');
    expect(planInit).toMatchObject({ method: 'POST', credentials: 'include' });
    expect(new Headers(planInit?.headers).get('X-CSRF-Token')).toBe('reporting-csrf');
    expect([...planBody.keys()].sort()).toEqual(['file', 'idempotency_key', 'reporting_year']);
    expect(planBody.get('reporting_year')).toBe('2026');
    expect(planBody.get('idempotency_key')).toBe('plan-key');
    expect((planBody.get('file') as File).name).toBe(planFile.name);
    expect(planBody.has('actual_through_month')).toBe(false);

    const [actualUrl, actualInit] = fetchMock.mock.calls[1];
    const actualBody = actualInit?.body as FormData;
    expect(String(actualUrl)).toBe('/api/admin/pnl-reporting/actual');
    expect(actualInit).toMatchObject({ method: 'POST', credentials: 'include' });
    expect(new Headers(actualInit?.headers).get('X-CSRF-Token')).toBe('reporting-csrf');
    expect([...actualBody.keys()].sort()).toEqual(['actual_through_month', 'file', 'idempotency_key', 'reporting_year']);
    expect(actualBody.get('actual_through_month')).toBe('6');
  });

  it('keeps one idempotency key across network, 409, and 503 retries, then creates a new key after success', async () => {
    const pnlResponses: Array<() => Promise<Response>> = [
      () => Promise.reject(new TypeError('network down')),
      () => apiError(409, 'IDEMPOTENCY_CONFLICT'),
      () => apiError(503, 'TRANSIENT_SYSTEM_ERROR'),
      () => response(uploadResponse('PLAN'), 201),
      () => response(uploadResponse('PLAN'), 201),
    ];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/admin/pnl-reporting/plan')) return pnlResponses.shift()!();
      return shellResponse(input);
    });
    vi.stubGlobal('fetch', fetchMock);
    const onChanged = vi.fn();
    render(<ModelManagementView onPnlReportingChanged={onChanged} />);
    await screen.findByText('등록된 모형이 없습니다.');
    fireEvent.change(screen.getByLabelText('PLAN 기준연도'), { target: { value: '2026' } });
    const file = new File(['same logical bytes'], 'plan.xlsx');
    fireEvent.change(screen.getByLabelText('PLAN Excel 파일'), { target: { files: [file] } });

    for (const message of [
      '일시적인 연결 오류입니다. 같은 업로드 키로 다시 시도할 수 있습니다.',
      '동일한 업로드 키가 다른 입력에 사용되었습니다. 자동 재시도하지 않았습니다.',
      '일시적인 연결 오류입니다. 같은 업로드 키로 다시 시도할 수 있습니다.',
    ]) {
      fireEvent.click(screen.getByRole('button', { name: 'PLAN 업로드' }));
      expect(await screen.findByText(message)).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole('button', { name: 'PLAN 업로드' }));
    expect(await screen.findByTestId('plan-upload-status')).toHaveTextContent('PLAN 등록 완료');
    expect(onChanged).toHaveBeenCalledTimes(1);

    const firstFour = postIdempotencyKeys(fetchMock, '/api/admin/pnl-reporting/plan');
    expect(new Set(firstFour).size).toBe(1);

    fireEvent.click(screen.getByRole('button', { name: 'PLAN 업로드' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
    const allKeys = postIdempotencyKeys(fetchMock, '/api/admin/pnl-reporting/plan');
    expect(allKeys[4]).not.toBe(allKeys[3]);
  });

  it('maps top-level workbook 422 and wrapped field 422 to INVALID validation summaries without losing details', async () => {
    const workbookInvalid = {
      status: 'INVALID', errorCount: 1, warningCount: 0, truncated: false,
      errors: [{ severity: 'BLOCKING', errorCode: 'PLAN_MONTH_MISSING', sheet: '01_월별손익', rowKey: 'rev_product', month: 1, message: 'Workbook 값이 입력 계약과 일치하지 않습니다.' }],
      warnings: [],
    };
    const pnlResponses = [
      () => response(workbookInvalid, 422),
      () => apiError(422, 'VALIDATION_ERROR', { reporting_year: 'invalid value' }),
    ];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/admin/pnl-reporting/plan')) return pnlResponses.shift()!();
      return shellResponse(input);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<ModelManagementView />);
    await screen.findByText('등록된 모형이 없습니다.');
    fireEvent.change(screen.getByLabelText('PLAN 기준연도'), { target: { value: '2026' } });
    fireEvent.change(screen.getByLabelText('PLAN Excel 파일'), { target: { files: [new File(['invalid'], 'invalid.xlsx')] } });
    fireEvent.click(screen.getByRole('button', { name: 'PLAN 업로드' }));
    expect(await screen.findByText('Workbook 값이 입력 계약과 일치하지 않습니다.')).toBeInTheDocument();
    expect(screen.getByLabelText('오류 1건, 경고 0건')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'PLAN 업로드' }));
    expect(await screen.findByText('invalid value')).toBeInTheDocument();
    expect(screen.getByText('reporting_year')).toBeInTheDocument();
    const keys = postIdempotencyKeys(fetchMock, '/api/admin/pnl-reporting/plan');
    expect(keys[1]).toBe(keys[0]);
  });

  it.each([
    [401, 'AUTH_REQUIRED'],
    [403, 'CSRF_FAILED'],
    [409, 'INPUT_INTEGRITY_MISMATCH'],
    [500, 'INGESTION_CLEANUP_REQUIRED'],
    [503, 'TRANSIENT_SYSTEM_ERROR'],
  ] as const)('preserves safe HTTP %i %s error identity', async (status, code) => {
    vi.stubGlobal('fetch', vi.fn(() => apiError(status, code)));
    await expect(bffClient.uploadPnlReportingPlan({ reportingYear: 2026, idempotencyKey: 'same-key', file: new File(['x'], 'x.xlsx') }))
      .rejects.toMatchObject({ status, code });
  });
});

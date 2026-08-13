import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ForecastGenerationView } from '../views/ForecastGenerationView';

const BASE = '11111111-1111-4111-8111-111111111111';
const MODEL = '22222222-2222-4222-8222-222222222222';
const GENERATION = '33333333-3333-4333-8333-333333333333';

const modelPayload = (name = 'Base') => ({ models: [{
  model_id: BASE,
  display_name: name,
  model_type: 'ACTUAL',
  model_year: 2026,
  start_month: 1,
  end_month: 12,
  is_published: true,
  is_default: false,
  dto_version: '1',
}] });

const successPayload = () => ({
  generation_id: GENERATION,
  model_id: MODEL,
  display_name: 'Forecast Model',
  model_year: 2026,
  start_month: 7,
  end_month: 7,
  is_published: false,
  is_default: false,
  workbook_sha256: 'a'.repeat(64),
  idempotency_replayed: false,
  execution_mode: 'SYNCHRONOUS',
  dto_version: '1',
});

function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

function forbiddenResponse() {
  return response({ error: {
    code: 'FORBIDDEN',
    message: 'Admin capability required',
    field_errors: {},
    correlation_id: null,
    dto_version: '1',
  } }, 403);
}

afterEach(() => vi.unstubAllGlobals());

describe('Forecast React vertical slice', () => {
  it('keeps the synchronous POST contract, renders the result, and does not show technical identifiers', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload('2026 Actual')))
      .mockResolvedValueOnce(response(successPayload()));
    vi.stubGlobal('fetch', fetchMock);

    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [, init] = fetchMock.mock.calls[1];
    const body = JSON.parse(String((init as RequestInit).body));
    expect(body.base_model_id).toBe(BASE);
    expect(body.start_month).toBe(7);
    expect(body.end_month).toBe(7);
    expect(body.months[0].month).toBe(7);
    expect(body.idempotency_key).toBeTruthy();
    expect(screen.getByText('비공개')).toBeInTheDocument();
    expect(screen.queryByText(GENERATION)).not.toBeInTheDocument();
    expect(screen.queryByText(MODEL)).not.toBeInTheDocument();
    expect(screen.queryByText('SYNCHRONOUS')).not.toBeInTheDocument();
    expect(screen.queryByText(/23%|64%|90%/)).not.toBeInTheDocument();
  });

  it('pre-validates an over-limit range without clamping or sending a request', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response(modelPayload()));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });

    fireEvent.change(screen.getByLabelText('시작 월'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '7' } });

    const submitButton = screen.getByRole('button', { name: '추정 모형 생성' });
    expect(submitButton).toBeDisabled();
    expect(screen.getAllByText(/7개월/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/최대 6개월/).length).toBeGreaterThan(0);
    expect(screen.getByLabelText('종료 월')).toHaveValue(7);
    fireEvent.click(submitButton);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('allows the approved six-month range and sends every selected month', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response({ ...successPayload(), start_month: 7, end_month: 12 }));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '12' } });
    const submitButton = screen.getByRole('button', { name: '추정 모형 생성' });
    expect(submitButton).not.toBeDisabled();
    fireEvent.click(submitButton);
    await screen.findByText('추정 모형 생성 완료');
    const [, init] = fetchMock.mock.calls[1];
    const body = JSON.parse(String((init as RequestInit).body));
    expect(body.start_month).toBe(7);
    expect(body.end_month).toBe(12);
    expect(body.months).toHaveLength(6);
    expect(body.months.map((month: { month: number }) => month.month)).toEqual([7, 8, 9, 10, 11, 12]);
  });

  it('locks all inputs and suppresses duplicate clicks during the synchronous request', async () => {
    let resolveRequest: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => { resolveRequest = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockReturnValueOnce(pending);
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });

    const submitButton = screen.getByRole('button', { name: '추정 모형 생성' });
    fireEvent.click(submitButton);
    fireEvent.click(submitButton);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(submitButton).toBeDisabled();
    expect(screen.getByText(/접수하고 계산 중입니다/)).toBeInTheDocument();
    expect(screen.getByLabelText('시작 월')).toBeDisabled();
    expect(screen.getByLabelText('7월 Forecast 입력')).toBeDisabled();

    resolveRequest(response(successPayload()));
    await screen.findByText('추정 모형 생성 완료');
  });

  it('keeps the idempotency key across a network retry without edits', async () => {
    const keys: string[] = [];
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockImplementationOnce((_url: string, init?: RequestInit) => {
        keys.push(JSON.parse(String(init?.body)).idempotency_key);
        return Promise.reject(new TypeError('timeout'));
      })
      .mockImplementationOnce((_url: string, init?: RequestInit) => {
        keys.push(JSON.parse(String(init?.body)).idempotency_key);
        return Promise.resolve(response({ ...successPayload(), idempotency_replayed: true }));
      });
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('separates forbidden and transient error states', async () => {
    const forbiddenFetch = vi.fn().mockResolvedValueOnce(forbiddenResponse());
    vi.stubGlobal('fetch', forbiddenFetch);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출 권한이 없습니다.' });
    expect(screen.getByRole('alert')).toHaveTextContent('권한');
    expect(screen.queryByText(/사용 가능한 기준 모형이 없습니다/)).not.toBeInTheDocument();
  });

  it('renders validation errors without leaking backend enum text', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response({ error: {
        code: 'FORECAST_SCOPE_NOT_APPROVED',
        message: 'Forecast request exceeds the approved synchronous scope',
        field_errors: { period: 'must not exceed 6' },
        correlation_id: null,
        dto_version: '1',
      } }, 403));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('alert')).toHaveTextContent('최대 6개월');
    expect(screen.getByRole('alert')).not.toHaveTextContent('FORECAST_SCOPE_NOT_APPROVED');
  });

  it('supports post-completion navigation callbacks', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(successPayload()));
    vi.stubGlobal('fetch', fetchMock);
    const onNavigateToPnl = vi.fn();
    const onNavigateToAnalysis = vi.fn();
    const onNavigateToManagement = vi.fn();
    render(<ForecastGenerationView onNavigateToPnl={onNavigateToPnl} onNavigateToAnalysis={onNavigateToAnalysis} onNavigateToManagement={onNavigateToManagement} />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');
    fireEvent.click(screen.getByRole('button', { name: '손익 현황 보기' }));
    fireEvent.click(screen.getByRole('button', { name: '손익분석 보기' }));
    fireEvent.click(screen.getByRole('button', { name: '모형 관리로 이동' }));
    expect(onNavigateToPnl).toHaveBeenCalledTimes(1);
    expect(onNavigateToAnalysis).toHaveBeenCalledTimes(1);
    expect(onNavigateToManagement).toHaveBeenCalledTimes(1);
  });

  it('rejects malformed JSON before making a forecast request', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response(modelPayload()));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.change(screen.getByLabelText('7월 Forecast 입력'), { target: { value: '{bad json' } });
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('월별 입력 JSON');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('keeps business unit guidance visible without mixed-unit wording', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response(modelPayload()));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    expect(screen.getByText(/LC는 4인치\/PCS, FS는 LENGTH\/m/)).toBeInTheDocument();
    expect(screen.queryByText(/16인치|대사/)).not.toBeInTheDocument();
  });
});

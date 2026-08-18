import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  aggregateSgaRegisteredEntries,
  calculateAdjustmentExpectedAmount,
  ForecastGenerationView,
  formatCanonicalRatioAsPercentage,
  formatNumericPresentation,
  parseFormattedNumericInput,
  parsePercentageToCanonicalRatio,
  withLegacySgaAggregateEntry,
} from '../views/ForecastGenerationView';

const BASE = '11111111-1111-4111-8111-111111111111';
const MODEL = '22222222-2222-4222-8222-222222222222';
const GENERATION = '33333333-3333-4333-8333-333333333333';
const monthlyBaselineAmounts = Object.fromEntries(Array.from({ length: 12 }, (_, index) => [String(index + 1), 594_000_000 + ((index + 1) * 1_000)]));

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

const metadataPayload = (extraSga: Array<{ adjustment_key: string; display_name: string; unit: string; category: string; section: string | null }> = []) => ({
  base_model_id: BASE,
  manufacturing: [{ adjustment_key: 'mfg-energy', display_name: '전력비', unit: 'KRW', category: 'manufacturing', section: null, monthly_baseline_amounts: monthlyBaselineAmounts }],
  sga: [
    { adjustment_key: 'sga-selling', display_name: '운송비', unit: 'KRW', category: 'sga', section: 'selling', monthly_baseline_amounts: monthlyBaselineAmounts },
    { adjustment_key: 'sga-packaging', display_name: '포장비', unit: 'KRW', category: 'sga', section: 'selling', monthly_baseline_amounts: monthlyBaselineAmounts },
    ...extraSga.map((item) => ({ ...item, monthly_baseline_amounts: monthlyBaselineAmounts })),
  ],
  reason_max_length: 500,
  dto_version: '1',
});

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

async function waitForForecastReady() {
  await waitFor(() => expect(screen.getByRole('button', { name: '모형 적용' })).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button', { name: '모형 적용' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '추정 모형 생성' })).not.toBeDisabled());
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Forecast React vertical slice', () => {
  it('uses the source-mockup progressive hierarchy and one ordered adjustment grid', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response(successPayload()));
    vi.stubGlobal('fetch', fetchMock);

    const { container } = render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitFor(() => expect(screen.getByRole('button', { name: '모형 적용' })).not.toBeDisabled());

    expect(container.querySelector('.forecast-workflow__card--setup')).toBeInTheDocument();
    expect(container.querySelector('.forecast-workflow__card--bulk')).not.toBeInTheDocument();
    expect(container.querySelector('.forecast-workflow__card--inputs')).not.toBeInTheDocument();
    expect(screen.getByText(/기준 모형과 기간을 설정한 후/)).toBeInTheDocument();
    expect(screen.queryByText(/ADMIN WORKFLOW|01 SETUP|02 MONTHLY_ENTRY|03 RESULT/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '모형 적용' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '추정 모형 생성' })).not.toBeDisabled());
    expect(container.querySelector('.forecast-workflow__card--bulk')).toBeInTheDocument();
    expect(container.querySelector('.forecast-workflow__card--inputs')).toBeInTheDocument();

    const productionInputs = [
      '7월 전공정 SW 생산수량', '7월 전공정 BW 생산수량', '7월 전공정 TW 생산수량',
      '7월 후공정 SW 생산수량', '7월 후공정 BW 생산수량', '7월 후공정 LC 생산수량',
    ];
    productionInputs.forEach((label) => expect(screen.getByLabelText(label)).toBeInTheDocument());

    fireEvent.click(screen.getByText(/비용 및 원가 조정/));
    const grid = container.querySelector('.forecast-workflow__adjustment-grid');
    expect(grid).toBeInTheDocument();
    expect(container.querySelector('.forecast-workflow__adjustment-summary-grid')).not.toBeInTheDocument();
    expect(container.querySelector('.forecast-workflow__advanced-grid')).not.toBeInTheDocument();
    expect(Array.from(grid?.children ?? []).map((node) => node.querySelector('h3')?.textContent)).toEqual([
      '제조경비 조정액',
      '판관비 조정액',
      '제조경비 조정 내역 (0건)',
      '판관비 조정 내역 (0건)',
      '매출원가 조정액',
      '매출원가 조정 내역 (0건)',
      '북미·남미 관세 참고 기준값',
      '신사업 입력 및 참고 기준값',
      '원재료 관세 환급',
      '추정 모형 생성 실행',
    ]);
    expect(screen.queryByText('최종 실행')).not.toBeInTheDocument();

    expect(screen.queryByText('운반비 조정 열기')).not.toBeInTheDocument();
    expect(screen.queryByText('포장비 조정 열기')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '7월 북미·남미 관세 등록' }));
    expect(screen.getByText('판관비 조정 내역 (1건)')).toBeInTheDocument();
    expect(screen.getByText('(북미·남미 관세)')).toBeInTheDocument();
    expect(screen.queryByLabelText('7월 운송비 판관비 조정액')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '7월 IX 포장비 등록' }));
    expect(screen.getByText('판관비 조정 내역 (2건)')).toBeInTheDocument();
    expect(screen.getByText('(IX 포장비)')).toBeInTheDocument();
    expect(screen.queryByLabelText('7월 포장비 판관비 조정액')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '7월 제품 폐기손실 조정' }));
    expect(screen.getByLabelText('7월 제품 폐기손실 매출원가 조정액')).toBeInTheDocument();
    const cogsDrawer = screen.getByLabelText('7월 제품 폐기손실 매출원가 조정액').closest('.forecast-workflow__inline-drawer') as HTMLElement;
    expect(within(cogsDrawer).getByRole('button', { name: '등록' })).toBeInTheDocument();
    expect(within(cogsDrawer).getByRole('button', { name: '취소' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('7월 제품 폐기손실 매출원가 조정액'), { target: { value: '-1200' } });
    fireEvent.change(screen.getByLabelText('7월 제품 폐기손실 매출원가 조정 사유'), { target: { value: '폐기 확인' } });
    fireEvent.click(within(cogsDrawer).getByRole('button', { name: '등록' }));
    expect(screen.getByRole('button', { name: '7월 제품 폐기손실 수정' })).toBeInTheDocument();
    expect(screen.getByText('매출원가 조정 내역 (1건)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '7월 제품 폐기손실 수정' }));
    fireEvent.change(screen.getByLabelText('7월 제품 폐기손실 매출원가 조정액'), { target: { value: '-999' } });
    fireEvent.click(screen.getByRole('button', { name: '취소' }));

    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');
    const body = JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body));
    expect(body.months[0].disposal_adjustment).toBe(-1200);
    expect(body.months[0].disposal_reason).toBe('폐기 확인');
  });

  it('keeps the synchronous POST contract, renders the result, and does not show technical identifiers', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload('2026 Actual')))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response(successPayload()));
    vi.stubGlobal('fetch', fetchMock);

    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitForForecastReady();
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');

    expect(fetchMock).toHaveBeenCalledTimes(3);
    const [, init] = fetchMock.mock.calls[2];
    const body = JSON.parse(String((init as RequestInit).body));
    expect(body.base_model_id).toBe(BASE);
    expect(body.start_month).toBe(7);
    expect(body.end_month).toBe(7);
    expect(body.months[0].month).toBe(7);
    expect(body.months[0].sales).toHaveLength(11);
    expect(body.months[0].production).toBeUndefined();
    expect(body.months[0].business_production).toHaveLength(6);
    expect(body.months[0].mcm).toHaveLength(4);
    expect(body.months[0].new_business_goods_cogs_mode).toBe('ACTUAL_YTD_DEFAULT');
    expect(body.months[0].new_business_goods_cogs).toBeUndefined();
    expect(body.idempotency_key).toBeTruthy();
    expect(screen.getAllByText(/비공개 상태/).length).toBeGreaterThan(0);
    expect(screen.queryByText(GENERATION)).not.toBeInTheDocument();
    expect(screen.queryByText(MODEL)).not.toBeInTheDocument();
    expect(screen.queryByText('SYNCHRONOUS')).not.toBeInTheDocument();
    expect(screen.queryByText(/23%|64%|90%/)).not.toBeInTheDocument();
    expect(screen.queryByText('월별 입력 JSON')).not.toBeInTheDocument();
    expect(document.querySelector('textarea')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '생성 모형 내려받기 (.xlsx)' })).toBeInTheDocument();
    expect(screen.getByText(/입력반영내역/)).toBeInTheDocument();
  });

  it('downloads the exact completed Forecast model once and blocks duplicate clicks', async () => {
    let resolveDownload!: (value: Response) => void;
    const downloadResponse = new Promise<Response>((resolve) => { resolveDownload = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response(successPayload()))
      .mockReturnValueOnce(downloadResponse);
    const revoke = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(<ForecastGenerationView />);
    await waitForForecastReady();
    expect(screen.queryByRole('button', { name: '생성 모형 내려받기 (.xlsx)' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');

    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:forecast'), revokeObjectURL: revoke });
    let downloadedFilename = '';
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloadedFilename = this.download;
    });

    const download = screen.getByRole('button', { name: '생성 모형 내려받기 (.xlsx)' });
    fireEvent.click(download);
    fireEvent.click(download);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(String(fetchMock.mock.calls[3][0])).toContain(`/api/admin/forecast-models/${MODEL}/workbook`);
    expect(fetchMock.mock.calls[3][1]).toMatchObject({ credentials: 'include' });
    expect(screen.getByRole('button', { name: '다운로드 준비 중…' })).toBeDisabled();

    resolveDownload(new Response(new Blob(['PK-forecast-workbook']), {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': "attachment; filename*=utf-8''Forecast_2026_07.xlsx",
      },
    }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:forecast'));
    expect(downloadedFilename).toBe('Forecast_2026_07.xlsx');
    expect(screen.getByRole('button', { name: '생성 모형 내려받기 (.xlsx)' })).not.toBeDisabled();
    anchorClick.mockRestore();
  });

  it('shows a safe Forecast workbook download failure without exposing backend detail', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response(successPayload()))
      .mockResolvedValueOnce(response({ error: {
        code: 'INPUT_INTEGRITY_MISMATCH',
        message: 'private bucket models/internal/source.xlsx SHA mismatch',
        field_errors: {}, correlation_id: 'safe-correlation', dto_version: '1',
      } }, 409));
    vi.stubGlobal('fetch', fetchMock);

    render(<ForecastGenerationView />);
    await waitForForecastReady();
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');
    fireEvent.click(screen.getByRole('button', { name: '생성 모형 내려받기 (.xlsx)' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('생성된 추정 모형을 내려받을 수 없습니다');
    expect(alert).not.toHaveTextContent(/bucket|source\.xlsx|SHA mismatch/);
  });

  it('pre-validates an over-limit range without clamping or sending a request', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });

    fireEvent.change(screen.getByLabelText('시작 월'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '7' } });

    expect(screen.queryByRole('button', { name: '추정 모형 생성' })).not.toBeInTheDocument();
    const applyButton = screen.getByRole('button', { name: '모형 적용' });
    expect(applyButton).toBeDisabled();
    expect(screen.getAllByText(/7개월/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/최대 6개월/).length).toBeGreaterThan(0);
    expect(screen.getByLabelText('종료 월')).toHaveValue('7');
    fireEvent.click(applyButton);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('allows the approved six-month range and sends every selected month', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response({ ...successPayload(), start_month: 7, end_month: 12 }));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '12' } });
    await waitForForecastReady();
    const submitButton = screen.getByRole('button', { name: '추정 모형 생성' });
    expect(submitButton).not.toBeDisabled();
    fireEvent.click(submitButton);
    await screen.findByText('추정 모형 생성 완료');
    const [, init] = fetchMock.mock.calls[2];
    const body = JSON.parse(String((init as RequestInit).body));
    expect(body.start_month).toBe(7);
    expect(body.end_month).toBe(12);
    expect(body.months).toHaveLength(6);
    expect(body.months.map((month: { month: number }) => month.month)).toEqual([7, 8, 9, 10, 11, 12]);
  });

  it('keeps monthly direct-entry values separate while switching month tabs', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response({ ...successPayload(), start_month: 7, end_month: 8 }));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '8' } });
    await waitForForecastReady();

    fireEvent.change(screen.getByLabelText('7월 LC 판매수량'), { target: { value: '70' } });
    fireEvent.change(screen.getByLabelText('7월 후공정 SW 생산수량'), { target: { value: '10000' } });
    fireEvent.click(screen.getByRole('tab', { name: '08월' }));
    fireEvent.change(screen.getByLabelText('8월 LC 판매수량'), { target: { value: '80' } });
    fireEvent.change(screen.getByLabelText('8월 후공정 SW 생산수량'), { target: { value: '12000' } });
    fireEvent.click(screen.getByRole('tab', { name: '07월' }));
    expect(screen.getByLabelText('7월 LC 판매수량')).toHaveValue('70');
    expect(screen.getByLabelText('7월 후공정 SW 생산수량')).toHaveValue('10000');

    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');
    const body = JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body));
    expect(body.months[0].sales.find((row: { product_code: string }) => row.product_code === 'LC').quantity).toBe(70);
    expect(body.months[1].sales.find((row: { product_code: string }) => row.product_code === 'LC').quantity).toBe(80);
    expect(body.months[0].business_production.find((row: { process: string; product_group: string }) => row.process === '후공정' && row.product_group === 'SW').quantity).toBe(10000);
    expect(body.months[1].business_production.find((row: { process: string; product_group: string }) => row.process === '후공정' && row.product_group === 'SW').quantity).toBe(12000);
  });

  it('keeps month editing text-backed, selects on first focus, and normalizes on blur', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload())));
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitForForecastReady();

    const start = screen.getByLabelText('시작 월') as HTMLInputElement;
    expect(start).toHaveValue('07');
    expect(start.type).toBe('text');
    expect(start.inputMode).toBe('numeric');
    fireEvent.focus(start);
    expect(start.selectionStart).toBe(0);
    expect(start.selectionEnd).toBe(2);

    fireEvent.change(start, { target: { value: '' } });
    expect(start).toHaveValue('');
    fireEvent.blur(start);
    expect(start).toHaveValue('');

    fireEvent.change(start, { target: { value: '18' } });
    expect(start).toHaveValue('18');
    fireEvent.blur(start);
    expect(start).toHaveValue('18');

    fireEvent.change(start, { target: { value: '8' } });
    expect(start).toHaveValue('8');
    fireEvent.blur(start);
    expect(start).toHaveValue('08');

    // A first pointer entry also selects all, while a second click while
    // focused is allowed to place the caret normally.
    fireEvent.blur(start);
    fireEvent.mouseDown(start);
    expect(start.selectionStart).toBe(0);
    expect(start.selectionEnd).toBe(start.value.length);
    start.setSelectionRange(1, 1);
    fireEvent.mouseDown(start);
    expect(start.selectionStart).toBe(1);
    expect(start.selectionEnd).toBe(1);

    fireEvent.keyDown(start, { key: 'Tab' });
    fireEvent.blur(start);
    const end = screen.getByLabelText('종료 월') as HTMLInputElement;
    fireEvent.focus(end);
    expect(end.selectionStart).toBe(0);
    expect(end.selectionEnd).toBe(end.value.length);
  });

  it('locks all inputs and suppresses duplicate clicks during the synchronous request', async () => {
    let resolveRequest: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => { resolveRequest = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockReturnValueOnce(pending);
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitForForecastReady();

    fireEvent.click(screen.getByText(/비용 및 원가 조정/));
    fireEvent.click(screen.getByRole('button', { name: '7월 전력비 조정' }));
    fireEvent.click(screen.getByRole('button', { name: '7월 제품 폐기손실 조정' }));
    const manufacturingDrawer = screen.getByLabelText('7월 전력비 제조경비 조정액').closest('.forecast-workflow__inline-drawer');
    const cogsDrawer = screen.getByLabelText('7월 제품 폐기손실 매출원가 조정액').closest('.forecast-workflow__inline-drawer');
    expect(manufacturingDrawer).not.toBeNull();
    expect(cogsDrawer).not.toBeNull();

    const submitButton = screen.getByRole('button', { name: '추정 모형 생성' });
    fireEvent.click(submitButton);
    fireEvent.click(submitButton);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(submitButton).toBeDisabled();
    expect(screen.getByText(/접수하고 계산 중입니다/)).toBeInTheDocument();
    expect(screen.getByLabelText('시작 월')).toBeDisabled();
    expect(screen.getByLabelText('7월 SW400 판매수량')).toBeDisabled();
    expect(within(manufacturingDrawer as HTMLElement).getByRole('button', { name: '등록' })).toBeDisabled();
    expect(within(manufacturingDrawer as HTMLElement).getByRole('button', { name: '취소' })).toBeDisabled();
    expect(within(cogsDrawer as HTMLElement).getByRole('button', { name: '등록' })).toBeDisabled();
    expect(within(cogsDrawer as HTMLElement).getByRole('button', { name: '취소' })).toBeDisabled();

    resolveRequest(response(successPayload()));
    await screen.findByText('추정 모형 생성 완료');
  });

  it('keeps the idempotency key across a network retry without edits', async () => {
    const keys: string[] = [];
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
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
    await waitForForecastReady();
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

  it('fails closed when advanced metadata loses the Admin capability', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(forbiddenResponse());
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);

    await screen.findByRole('heading', { name: '추정 산출 권한이 없습니다.' });
    expect(screen.getByRole('alert')).toHaveTextContent('권한');
    expect(screen.queryByRole('button', { name: '추정 모형 생성' })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('renders validation errors without leaking backend enum text', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
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
    await waitForForecastReady();
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('alert')).toHaveTextContent('최대 6개월');
    expect(screen.getByRole('alert')).not.toHaveTextContent('FORECAST_SCOPE_NOT_APPROVED');
  });

  it('supports post-completion navigation callbacks', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response(successPayload()));
    vi.stubGlobal('fetch', fetchMock);
    const onNavigateToPnl = vi.fn();
    const onNavigateToAnalysis = vi.fn();
    const onNavigateToManagement = vi.fn();
    render(<ForecastGenerationView onNavigateToPnl={onNavigateToPnl} onNavigateToAnalysis={onNavigateToAnalysis} onNavigateToManagement={onNavigateToManagement} />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitForForecastReady();
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');
    fireEvent.click(screen.getByRole('button', { name: '손익 현황 보기' }));
    fireEvent.click(screen.getByRole('button', { name: '손익분석 보기' }));
    fireEvent.click(screen.getByRole('button', { name: '모형 관리로 이동' }));
    expect(onNavigateToPnl).toHaveBeenCalledTimes(1);
    expect(onNavigateToAnalysis).toHaveBeenCalledTimes(1);
    expect(onNavigateToManagement).toHaveBeenCalledTimes(1);
  });

  it('edits sales, business production, and MCM rows without frontend allocation', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response(successPayload()));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitForForecastReady();

    fireEvent.change(screen.getByLabelText('7월 SW400 판매수량'), { target: { value: '125.5' } });
    fireEvent.change(screen.getByLabelText('7월 SW400 매출액'), { target: { value: '987654' } });
    fireEvent.change(screen.getByLabelText('7월 후공정 SW 생산수량'), { target: { value: '88' } });
    fireEvent.change(screen.getByLabelText('7월 SW400 MCM 수량'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');

    const body = JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body));
    expect(body.months[0].sales[0]).toEqual({ product_code: 'SW400', quantity: 125.5, amount: 987654 });
    expect(body.months[0].production).toBeUndefined();
    expect(body.months[0].business_production).toEqual([
      { process: '전공정', product_group: 'SW', quantity: 0, unit: 'm' },
      { process: '전공정', product_group: 'BW', quantity: 0, unit: 'm' },
      { process: '전공정', product_group: 'TW', quantity: 0, unit: 'm' },
      { process: '후공정', product_group: 'SW', quantity: 88, unit: 'PCS' },
      { process: '후공정', product_group: 'BW', quantity: 0, unit: 'PCS' },
      { process: '후공정', product_group: 'LC', quantity: 0, unit: 'PCS' },
    ]);
    expect(body.months[0].mcm[0]).toEqual({ product_code: 'SW400', quantity: 7 });
    expect(body.months[0].sales.map((row: { product_code: string }) => row.product_code)).toEqual([
      'SW400', 'SW440', 'BW400', 'BW440', 'LC', 'FS_SW', 'FS_BW', 'FS_TW', 'UF_MBR', 'IX', 'OTHER',
    ]);
    expect(JSON.stringify(body.months[0].business_production)).not.toMatch(/SW400|SW440|BW400|BW440|FS_SW|FS_BW|FS_TW/);
  });

  it('serializes advanced opaque adjustments and keeps values isolated by month', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response({ ...successPayload(), start_month: 7, end_month: 8 }));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '8' } });
    await waitForForecastReady();
    fireEvent.click(screen.getByText(/비용 및 원가 조정/));
    fireEvent.click(screen.getByRole('button', { name: '7월 전력비 조정' }));
    fireEvent.change(screen.getByLabelText('7월 전력비 제조경비 조정액'), { target: { value: '-456789' } });
    fireEvent.change(screen.getByLabelText('7월 전력비 제조경비 조정 사유'), { target: { value: '전력 사유' } });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(screen.getByText(/제조경비 조정 내역 \(1건\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '7월 운송비 조정' }));
    fireEvent.change(screen.getByLabelText('7월 운송비 판관비 조정액'), { target: { value: '567890' } });
    fireEvent.change(screen.getByLabelText('7월 운송비 판관비 조정 사유'), { target: { value: '운송 사유' } });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(screen.queryByLabelText(/신사업 상품원가 산출 모드/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/신사업 매출원가 직접 반영액/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '08월' }));
    fireEvent.click(screen.getByRole('button', { name: '8월 전력비 조정' }));
    fireEvent.change(screen.getByLabelText('8월 전력비 제조경비 조정액'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));
    fireEvent.click(screen.getByRole('button', { name: '8월 운송비 조정' }));
    fireEvent.change(screen.getByLabelText('8월 운송비 판관비 조정액'), { target: { value: '-34' } });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));
    fireEvent.click(screen.getByRole('tab', { name: '07월' }));
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');

    const body = JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body));
    expect(body.months[0].manufacturing_adjustments).toEqual([
      { adjustment_key: 'mfg-energy', amount: -456789, reason: '전력 사유' },
    ]);
    expect(body.months[0].sga_adjustments).toEqual([
      { adjustment_key: 'sga-selling', amount: 567890, reason: '운송 사유' },
    ]);
    expect(body.months[0].new_business_goods_cogs_mode).toBe('ACTUAL_YTD_DEFAULT');
    expect(body.months[0].new_business_goods_cogs).toBeUndefined();
    expect(body.months[0].new_business_goods_cogs_reason).toBeUndefined();
    expect(body.months[1].manufacturing_adjustments).toEqual([
      { adjustment_key: 'mfg-energy', amount: 12, reason: '' },
    ]);
    expect(body.months[1].sga_adjustments).toEqual([
      { adjustment_key: 'sga-selling', amount: -34, reason: '' },
    ]);
    expect(body.months[1].new_business_goods_cogs_mode).toBe('ACTUAL_YTD_DEFAULT');
  });

  it('rejects an empty direct-entry value before making a forecast request', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitForForecastReady();
    fireEvent.change(screen.getByLabelText('7월 SW400 판매수량'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('7월 SW400 판매수량');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('keeps business unit guidance visible without mixed-unit wording', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitForForecastReady();
    expect(screen.getAllByText('LC (4인치)').length).toBeGreaterThan(0);
    expect(screen.getAllByText('PCS').length).toBeGreaterThan(0);
    expect(screen.getAllByText('m').length).toBeGreaterThan(0);
    expect(screen.queryByText(/16인치|대사/)).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^판매계획/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^생산계획/ })).toBeInTheDocument();
    expect(screen.getByLabelText('7월 전공정 SW 생산수량')).toBeInTheDocument();
    expect(screen.getByLabelText('7월 전공정 BW 생산수량')).toBeInTheDocument();
    expect(screen.getByLabelText('7월 전공정 TW 생산수량')).toBeInTheDocument();
    expect(screen.getByLabelText('7월 후공정 SW 생산수량')).toBeInTheDocument();
    expect(screen.getByLabelText('7월 후공정 BW 생산수량')).toBeInTheDocument();
    expect(screen.getByLabelText('7월 후공정 LC 생산수량')).toBeInTheDocument();
    expect(screen.queryByLabelText('7월 SW400 생산수량')).not.toBeInTheDocument();
    expect(screen.getByText(/동일 월 400\/440 생산구성비를 기준으로 서버에서 자동 배부/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^MCM 유상사급/ })).toBeInTheDocument();
    expect(screen.queryByText('월별 입력 JSON')).not.toBeInTheDocument();
  });

  it('keeps the selling-freight base drawer manual and serializes its isolated registered value', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response(successPayload()));
    vi.stubGlobal('fetch', fetchMock);

    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitForForecastReady();

    fireEvent.click(screen.getByText(/비용 및 원가 조정/));
    fireEvent.click(screen.getByRole('button', { name: '7월 운송비 조정' }));
    expect(screen.queryByText('자동 산출/제안 내역')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('판매비 운반비 자동 산출 제안 내역')).not.toBeInTheDocument();
    const freightAmountInput = screen.getByLabelText('7월 운송비 판관비 조정액') as HTMLInputElement;
    expect(freightAmountInput.value).toBe('0');
    fireEvent.change(freightAmountInput, { target: { value: '81500' } });
    fireEvent.blur(freightAmountInput);
    expect(freightAmountInput).toHaveValue('81,500');
    expect(getComputedStyle(freightAmountInput).textAlign).toBe('right');
    const reasonInput = screen.getByLabelText('7월 운송비 판관비 조정 사유');
    expect(reasonInput).toHaveAttribute('placeholder', '조정 사유를 입력하세요');
    expect(reasonInput).toHaveClass('forecast-workflow__reason-placeholder-centered');
    expect(getComputedStyle(reasonInput).textAlign).toBe('left');

    fireEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(screen.getByRole('button', { name: '7월 운송비 조정' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '7월 운송비 조정' }));
    fireEvent.change(screen.getByLabelText('7월 운송비 판관비 조정액'), { target: { value: '81500' } });
    fireEvent.change(screen.getByLabelText('7월 운송비 판관비 조정 사유'), { target: { value: '관세 및 신사업 운반비 반영' } });
    const drawer = screen.getByLabelText('7월 운송비 판관비 조정액').closest('.forecast-workflow__inline-drawer') as HTMLElement;
    fireEvent.click(within(drawer).getByRole('button', { name: '등록' }));
    expect(screen.getByText(/판관비 조정 내역 \(1건\)/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '7월 운송비 수정' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');

    const body = JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body));
    expect(body.months[0].sga_adjustments).toEqual([
      { adjustment_key: 'sga-selling', amount: 81500, reason: '관세 및 신사업 운반비 반영' },
    ]);
  });

  it('registers helper-derived packaging and freight as separate account entries without opening a drawer', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response(successPayload()));
    vi.stubGlobal('fetch', fetchMock);

    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitForForecastReady();

    fireEvent.change(screen.getByLabelText('7월 IX 판매수량'), { target: { value: '5000' } });
    fireEvent.change(screen.getByLabelText('7월 IX 매출액'), { target: { value: '500000' } });
    fireEvent.change(screen.getByLabelText('7월 UF_MBR 매출액'), { target: { value: '1000000' } });

    fireEvent.click(screen.getByText(/비용 및 원가 조정/));
    fireEvent.click(screen.getByRole('button', { name: '7월 IX 포장비 등록' }));
    expect(screen.getByText('판관비 조정 내역 (1건)')).toBeInTheDocument();
    expect(screen.getByText('(IX 포장비)')).toBeInTheDocument();
    expect(screen.queryByLabelText('7월 포장비 판관비 조정액')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '7월 신사업 운반비 등록' }));
    expect(screen.getByText('판관비 조정 내역 (2건)')).toBeInTheDocument();
    expect(screen.getByText('(신사업 운반비)')).toBeInTheDocument();
    expect(screen.queryByLabelText('7월 운송비 판관비 조정액')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');

    const body = JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body));
    expect(body.months[0].sga_adjustments).toEqual([
      { adjustment_key: 'sga-selling', amount: 75000, reason: '신사업 운반비 기준값 등록' },
      { adjustment_key: 'sga-packaging', amount: 76000, reason: 'IX 포장비 기준값 등록' },
    ]);
  });

  it('formats every canonical ratio as one-decimal percent and parses it back without changing the DTO unit', () => {
    expect(formatCanonicalRatioAsPercentage('0.10')).toBe('10.0');
    expect(formatCanonicalRatioAsPercentage('0.13')).toBe('13.0');
    expect(formatCanonicalRatioAsPercentage('0.05')).toBe('5.0');
    expect(formatCanonicalRatioAsPercentage('0.85')).toBe('85.0');
    expect(formatCanonicalRatioAsPercentage('0.013')).toBe('1.3');
    expect(parsePercentageToCanonicalRatio('10.0%')).toBe('0.1');
    expect(parsePercentageToCanonicalRatio('13.0')).toBe('0.13');
    expect(parsePercentageToCanonicalRatio('1.3%')).toBe('0.013');
    expect(formatCanonicalRatioAsPercentage(parsePercentageToCanonicalRatio('10.0%'))).toBe('10.0');
    expect(formatNumericPresentation('12000000')).toBe('12,000,000');
    expect(parseFormattedNumericInput('12,000,000')).toBe('12000000');
  });

  it('uses authoritative monthly plans in read-only plan/expected columns and preserves the mockup reference form hierarchy', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()));
    vi.stubGlobal('fetch', fetchMock);
    const { container } = render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '추정 산출' });
    fireEvent.change(screen.getByLabelText('종료 월'), { target: { value: '8' } });
    await waitForForecastReady();
    fireEvent.click(screen.getByText(/비용 및 원가 조정/));

    const manufacturing = screen.getByRole('region', { name: '제조경비 조정액' });
    expect(within(manufacturing).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      '계정명', '계획', '예상금액(자동)', '조정액', '조정',
    ]);
    const sga = screen.getByRole('region', { name: '판관비 조정액' });
    expect(within(sga).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      '구분', '계정명', '계획', '예상금액(자동)', '조정액', '조정',
    ]);
    const cogs = screen.getByRole('region', { name: '매출원가 조정액' });
    expect(within(cogs).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      '계정명', '계획', '예상금액(자동)', '조정액', '조정',
    ]);
    expect(cogs.querySelectorAll('[data-contract-missing="cogs-baseline"]')).toHaveLength(4);
    expect(within(manufacturing).getAllByRole('columnheader')[0]).toHaveClass('forecast-workflow__cell--center');
    expect(within(manufacturing).getAllByRole('columnheader')[1]).toHaveClass('forecast-workflow__cell--number');
    expect(within(sga).getAllByRole('columnheader')[0]).toHaveClass('forecast-workflow__cell--center');
    expect(within(sga).getAllByRole('columnheader')[1]).toHaveClass('forecast-workflow__cell--center');
    expect(within(sga).getAllByRole('columnheader')[2]).toHaveClass('forecast-workflow__cell--number');
    expect(within(cogs).getAllByRole('columnheader')[4]).toHaveClass('forecast-workflow__cell--action');

    const julyPlan = monthlyBaselineAmounts['7'].toLocaleString('ko-KR');
    const augustPlan = monthlyBaselineAmounts['8'].toLocaleString('ko-KR');
    fireEvent.click(screen.getByRole('button', { name: '7월 전력비 조정' }));
    const planOutput = screen.getByLabelText('7월 전력비 제조경비 계획');
    const expectedOutput = screen.getByLabelText('7월 전력비 제조경비 예상금액');
    expect(planOutput.tagName).toBe('OUTPUT');
    expect(planOutput).toHaveAttribute('data-readonly', 'true');
    expect(planOutput).toHaveTextContent(julyPlan);
    fireEvent.change(screen.getByLabelText('7월 전력비 제조경비 조정액'), { target: { value: '1250' } });
    expect(planOutput).toHaveTextContent(julyPlan);
    const julyExpected = calculateAdjustmentExpectedAmount(monthlyBaselineAmounts['7'], '1250').toLocaleString('ko-KR');
    expect(expectedOutput).toHaveTextContent(julyExpected);
    fireEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(screen.getByRole('region', { name: '제조경비 조정 내역 (1건)' })).toHaveTextContent(julyExpected);
    fireEvent.click(screen.getByRole('button', { name: '7월 전력비 수정' }));
    fireEvent.change(screen.getByLabelText('7월 전력비 제조경비 조정액'), { target: { value: '9999' } });
    fireEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(screen.getByRole('region', { name: '제조경비 조정 내역 (1건)' })).toHaveTextContent(julyExpected);
    fireEvent.click(screen.getByRole('tab', { name: '08월' }));
    fireEvent.click(screen.getByRole('button', { name: '8월 전력비 조정' }));
    expect(screen.getByLabelText('8월 전력비 제조경비 계획')).toHaveTextContent(augustPlan);
    fireEvent.click(screen.getByRole('button', { name: '취소' }));

    expect(screen.getByLabelText('8월 관세 적용 비율')).toHaveValue('10.0');
    expect(screen.getByLabelText('8월 관세율')).toHaveValue('13.0');
    expect(screen.queryByLabelText(/매출원가 비율/)).not.toBeInTheDocument();
    expect(screen.queryByText(/신사업 상품원가율|자동 산출 원가율/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('8월 UF/MBR 운반비율')).toHaveValue('5.0');
    expect(screen.getByLabelText('8월 원재료 관세 환급률')).toHaveValue('1.3');
    expect(screen.queryByText(/\(0~1\)/)).not.toBeInTheDocument();
    expect(screen.queryByText('운반비 조정 열기')).not.toBeInTheDocument();
    expect(screen.queryByText('포장비 조정 열기')).not.toBeInTheDocument();

    const newBusiness = screen.getByRole('region', { name: '신사업 입력 및 참고 기준값' });
    expect(newBusiness.querySelector('[data-reference-action="new-business-freight"]')).toContainElement(screen.getByRole('button', { name: '8월 신사업 운반비 등록' }));
    expect(newBusiness.querySelector('[data-reference-action="ix-packaging"]')).toContainElement(screen.getByRole('button', { name: '8월 IX 포장비 등록' }));
    const rawMaterial = screen.getByRole('region', { name: '원재료 관세 환급' });
    expect(within(rawMaterial).getByRole('group', { name: '환급 기준' })).toHaveTextContent(/모형 산출값.*구매비 예상 금액/);
    const rawRows = rawMaterial.querySelectorAll('.forecast-workflow__raw-material-row');
    expect(rawRows).toHaveLength(2);
    expect(rawRows[0]).toHaveAttribute('data-raw-material-row', 'amounts');
    expect(rawRows[0]).toHaveTextContent(/원재료 조정액 \(모형 기준\).*원재료 직접 입력액 \(구매비 기준\)/);
    expect(rawRows[1]).toHaveAttribute('data-raw-material-row', 'reason-rate');
    expect(rawRows[1]).toHaveTextContent(/원재료 사유.*원재료 관세 환급률 \(%\)/);
    const tariffSalesInput = screen.getByLabelText('8월 기준 북미·남미 매출');
    fireEvent.change(tariffSalesInput, { target: { value: '12000000' } });
    fireEvent.blur(tariffSalesInput);
    expect(tariffSalesInput).toHaveValue('12,000,000');
    const packQuantityInput = screen.getByLabelText('8월 IX 포장 기준량');
    fireEvent.change(packQuantityInput, { target: { value: '25000' } });
    fireEvent.blur(packQuantityInput);
    expect(packQuantityInput).toHaveValue('25,000');
    const refundAdjustmentInput = screen.getByLabelText('8월 원재료 조정액');
    fireEvent.change(refundAdjustmentInput, { target: { value: '12000000' } });
    fireEvent.blur(refundAdjustmentInput);
    expect(refundAdjustmentInput).toHaveValue('12,000,000');
    expect(getComputedStyle(tariffSalesInput).textAlign).toBe('right');
    expect(getComputedStyle(packQuantityInput).textAlign).toBe('right');
    expect(getComputedStyle(refundAdjustmentInput).textAlign).toBe('right');
    expect(getComputedStyle(screen.getByLabelText('8월 관세율')).textAlign).toBe('right');
    expect(container.querySelector('.forecast-workflow__adjustment-node--mfg-list')).toHaveClass('forecast-workflow__adjustment-span');
    expect(container.querySelector('.forecast-workflow__adjustment-node--sga-list')).toHaveClass('forecast-workflow__adjustment-span');
  });

  it('accumulates multiple local selling-freight entries while serializing one summed account DTO', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload()))
      .mockResolvedValueOnce(response(metadataPayload()))
      .mockResolvedValueOnce(response(successPayload()));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await waitForForecastReady();
    fireEvent.change(screen.getByLabelText('7월 UF_MBR 매출액'), { target: { value: '1000000' } });
    fireEvent.change(screen.getByLabelText('7월 IX 매출액'), { target: { value: '500000' } });
    fireEvent.click(screen.getByText(/비용 및 원가 조정/));
    fireEvent.change(screen.getByLabelText('7월 기준 북미·남미 매출'), { target: { value: '500000' } });
    fireEvent.change(screen.getByLabelText('7월 추정 북미·남미 매출'), { target: { value: '1000000' } });

    fireEvent.click(screen.getByRole('button', { name: '7월 북미·남미 관세 등록' }));
    expect(screen.getByText('판관비 조정 내역 (1건)')).toBeInTheDocument();
    expect(screen.getByText('(북미·남미 관세)')).toBeInTheDocument();
    expect(screen.queryByLabelText('판매비 운반비 자동 산출 제안 내역')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '7월 신사업 운반비 등록' }));
    expect(screen.getByText('판관비 조정 내역 (2건)')).toBeInTheDocument();
    expect(screen.getByText('(신사업 운반비)')).toBeInTheDocument();
    const accountSummary = screen.getByLabelText('판관비 계정 합계');
    expect(accountSummary).toHaveTextContent(/계정 합계.*운송비.*조정액 합계:.*\+81,500원/);
    expect(accountSummary).toHaveTextContent(`최종 예상금액: ${(monthlyBaselineAmounts['7'] + 81_500).toLocaleString('ko-KR')}원`);
    expect(screen.getByRole('region', { name: '판관비 조정액' })).toHaveTextContent('+81,500');

    expect(aggregateSgaRegisteredEntries([
      { id: 'a', adjustmentKey: 'sga-selling', sourceLabel: '관세', amount: '6500', reason: '관세 조정' },
      { id: 'b', adjustmentKey: 'sga-selling', sourceLabel: '운반비', amount: '75000', reason: '신사업 운반비' },
    ])).toEqual({ amount: '81500', reason: '관세 조정; 신사업 운반비' });

    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');
    const body = JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body));
    expect(body.months[0].sga_adjustments).toEqual([
      { adjustment_key: 'sga-selling', amount: 81500, reason: '북미·남미 관세 기준값 등록; 신사업 운반비 기준값 등록' },
    ]);
  });

  it('preserves an existing aggregate when a helper action appends the first local entry', () => {
    const seeded = withLegacySgaAggregateEntry([], 'sga-selling', {
      amount: '12000',
      reason: '기존 직접 조정',
    });
    const appended = [...seeded, {
      id: 'tariff-entry',
      adjustmentKey: 'sga-selling',
      sourceLabel: '북미·남미 관세 조정',
      amount: '6500',
      reason: '관세 조정',
    }];

    expect(aggregateSgaRegisteredEntries(appended)).toEqual({
      amount: '18500',
      reason: '기존 직접 조정; 관세 조정',
    });
  });
});

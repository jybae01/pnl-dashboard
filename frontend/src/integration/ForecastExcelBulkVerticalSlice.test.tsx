import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ForecastGenerationView } from '../views/ForecastGenerationView';

const BASE = '11111111-1111-4111-8111-111111111111';

const models = { models: [{
  model_id: BASE, display_name: 'Base', model_type: 'ACTUAL', model_year: 2026,
  start_month: 1, end_month: 12, is_published: true, is_default: false, dto_version: '1',
}] };
const metadata = {
  base_model_id: BASE,
  manufacturing: [{ adjustment_key: 'mfg-energy', display_name: '전력비', unit: 'KRW', category: 'manufacturing', section: null }],
  sga: [{ adjustment_key: 'sga-selling', display_name: '운송비', unit: 'KRW', category: 'sga', section: 'selling' }],
  reason_max_length: 500, dto_version: '1',
};
const preview = {
  source_filename: 'forecast_input.xlsx', valid: true, blocking: false,
  sales_rows: [{
    month: 7, product_code: 'SW400', product_name: 'SW400', product_group: 'SW',
    quantity: 123, amount: 456000, source_sheet: '판매계획', source_row: 2,
  }],
  business_production_rows: [{
    month: 7, process: '후공정', product_group: 'SW', quantity: 1000, unit: 'PCS',
    source_sheet: '생산계획', source_row: 2,
  }],
  issues: [],
  sales_summary: [{ unit: 'PCS', row_count: 1, quantity_total: 123 }],
  production_summary: [{ unit: 'PCS', row_count: 1, quantity_total: 1000 }],
  dto_version: '1',
};

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

function upload(fileName = 'forecast_input.xlsx') {
  const input = screen.getByLabelText('엑셀 파일 선택');
  fireEvent.change(input, { target: { files: [new File(['xlsx'], fileName, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })] } });
}

afterEach(() => vi.unstubAllGlobals());

describe('Forecast Excel bulk input vertical slice', () => {
  it('downloads the two-sheet input template through the distinct Admin artifact action', async () => {
    const revoke = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:template'), revokeObjectURL: revoke });
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json(models))
      .mockResolvedValueOnce(json(metadata))
      .mockResolvedValueOnce(new Response(new Blob(['xlsx']), { status: 200, headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': "attachment; filename*=utf-8''Forecast_Input_Template.xlsx",
      } }));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);

    await screen.findByRole('heading', { name: '판매계획' });
    await waitFor(() => expect(screen.getByRole('button', { name: '추정 모형 생성' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: '엑셀 양식 다운로드' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[2][0]).toBe('/api/admin/forecasts/input-template');
    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(revoke).toHaveBeenCalledWith('blob:template');
    expect(screen.queryByText('단가')).not.toBeInTheDocument();
    anchorClick.mockRestore();
  });

  it('previews server-normalized rows without changing current input or running Forecast', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json(models))
      .mockResolvedValueOnce(json(metadata))
      .mockResolvedValueOnce(json(preview));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '판매계획' });
    fireEvent.change(screen.getByLabelText('7월 SW400 판매수량'), { target: { value: '99' } });

    upload();
    await screen.findByRole('heading', { name: 'Excel 입력 확인' });
    expect(screen.getByText('완제품 판매')).toBeInTheDocument();
    expect(screen.getByText('123 PCS')).toBeInTheDocument();
    expect(screen.getByText('후공정 생산')).toBeInTheDocument();
    expect(screen.getByText('1,000 PCS')).toBeInTheDocument();
    expect(screen.getByLabelText('7월 SW400 판매수량')).toHaveValue('99');
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const [url, init] = fetchMock.mock.calls[2];
    expect(url).toBe('/api/admin/forecasts/input-preview');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('start_month')).toBe('7');
    expect((init.body as FormData).get('end_month')).toBe('7');
    expect(screen.queryByText(/총 매출액|평균단가|Margin/)).not.toBeInTheDocument();
  });

  it('requires confirmation, replaces only sales and business production, and remains directly editable', async () => {
    const success = {
      generation_id: '33333333-3333-4333-8333-333333333333', model_id: '22222222-2222-4222-8222-222222222222',
      display_name: 'Forecast Model', model_year: 2026, start_month: 7, end_month: 7,
      is_published: false, is_default: false, workbook_sha256: 'a'.repeat(64),
      idempotency_replayed: false, execution_mode: 'SYNCHRONOUS', dto_version: '1',
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json(models))
      .mockResolvedValueOnce(json(metadata))
      .mockResolvedValueOnce(json(preview))
      .mockResolvedValueOnce(json(success));
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '판매계획' });
    fireEvent.change(screen.getByLabelText('7월 SW400 판매수량'), { target: { value: '99' } });
    fireEvent.change(screen.getByLabelText('7월 SW400 MCM 수량'), { target: { value: '77' } });
    fireEvent.click(screen.getByText(/고급 입력 및 조정/));
    fireEvent.click(await screen.findByRole('button', { name: '7월 전력비 조정' }));
    fireEvent.change(screen.getByLabelText('7월 전력비 제조경비 조정액'), { target: { value: '-66' } });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(screen.getByText(/조정금액:/)).toBeInTheDocument();
    upload();
    await screen.findByRole('heading', { name: 'Excel 입력 확인' });

    fireEvent.click(screen.getByRole('button', { name: '추정 입력값으로 적용' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(screen.getByLabelText('7월 SW400 판매수량')).toHaveValue('99');

    fireEvent.click(screen.getByRole('button', { name: '추정 입력값으로 적용' }));
    fireEvent.click(screen.getByRole('button', { name: '적용' }));
    expect(screen.getByLabelText('7월 SW400 판매수량')).toHaveValue('123');
    expect(screen.getByLabelText('7월 후공정 SW 생산수량')).toHaveValue('1000');
    expect(screen.getByLabelText('7월 SW400 MCM 수량')).toHaveValue('77');
    expect(screen.getByText(/조정금액:/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);

    fireEvent.change(screen.getByLabelText('7월 SW400 판매수량'), { target: { value: '124' } });
    expect(screen.getByLabelText('7월 SW400 판매수량')).toHaveValue('124');
    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');
    const body = JSON.parse(String((fetchMock.mock.calls[3][1] as RequestInit).body));
    expect(body.months[0].sales[0].quantity).toBe(124);
    expect(body.months[0].business_production.find((row: { process: string; product_group: string }) => row.process === '후공정' && row.product_group === 'SW').quantity).toBe(1000);
    expect(body.months[0].mcm[0].quantity).toBe(77);
    expect(body.months[0].manufacturing_adjustments[0]).toEqual({ adjustment_key: 'mfg-energy', amount: -66, reason: '' });
  });

  it('renders structured blocking issues and keeps Apply disabled', async () => {
    const invalid = {
      ...preview, valid: false, blocking: true, sales_rows: [], business_production_rows: [],
      sales_summary: [], production_summary: [],
      issues: [{
        code: 'PRODUCT_NOT_MAPPED', message: '등록되지 않은 제품코드입니다.', severity: 'ERROR', blocking: true,
        source_sheet: '판매계획', source_row: 12, field: '제품코드',
      }],
    };
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(json(models))
      .mockResolvedValueOnce(json(metadata))
      .mockResolvedValueOnce(json(invalid)));
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '판매계획' });
    upload('invalid.xlsx');

    expect(await screen.findByText('등록되지 않은 제품코드입니다.')).toBeInTheDocument();
    expect(screen.getAllByText('판매계획').length).toBeGreaterThan(0);
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getAllByText('제품코드').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: '추정 입력값으로 적용' })).toBeDisabled();
  });

  it('fails closed when preview blocking flags are inconsistent', async () => {
    const inconsistent = {
      ...preview,
      issues: [{
        code: 'INVALID_ROW', message: '차단 오류', severity: 'ERROR', blocking: true,
        source_sheet: '판매계획', source_row: 2, field: '수량',
      }],
    };
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(json(models))
      .mockResolvedValueOnce(json(metadata))
      .mockResolvedValueOnce(json(inconsistent)));
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '판매계획' });
    upload();

    expect(await screen.findByRole('alert')).toHaveTextContent('파일 형식과 입력 내용을 확인');
    expect(screen.queryByRole('heading', { name: 'Excel 입력 확인' })).not.toBeInTheDocument();
  });

  it('locks duplicate preview requests and exposes only a safe upload error', async () => {
    let resolvePreview: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => { resolvePreview = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json(models))
      .mockResolvedValueOnce(json(metadata))
      .mockReturnValueOnce(pending);
    vi.stubGlobal('fetch', fetchMock);
    render(<ForecastGenerationView />);
    await screen.findByRole('heading', { name: '판매계획' });
    upload();
    upload('second.xlsx');
    expect(await screen.findByText('업로드 및 확인 중...')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    resolvePreview(json({ error: { code: 'VALIDATION_ERROR', message: 'raw zip path detail', field_errors: {}, correlation_id: null, dto_version: '1' } }, 422));
    expect(await screen.findByRole('alert')).toHaveTextContent('파일 형식과 입력 내용을 확인');
    expect(screen.getByRole('alert')).not.toHaveTextContent('raw zip path detail');
  });
});

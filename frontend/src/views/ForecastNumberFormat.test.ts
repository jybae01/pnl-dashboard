import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  formatNumericPresentation,
  ForecastGenerationView,
  parseFormattedNumericInput,
} from './ForecastGenerationView';

const BASE = '11111111-1111-4111-8111-111111111111';
const MODEL = '22222222-2222-4222-8222-222222222222';
const GENERATION = '33333333-3333-4333-8333-333333333333';

const modelPayload = {
  models: [{
    model_id: BASE,
    display_name: 'Base',
    model_type: 'ACTUAL',
    model_year: 2026,
    start_month: 1,
    end_month: 12,
    is_published: true,
    is_default: false,
    dto_version: '1',
  }],
};

const metadataPayload = {
  base_model_id: BASE,
  manufacturing: [],
  sga: [],
  reason_max_length: 500,
  dto_version: '1',
};

const successPayload = {
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
};

function response(value: unknown) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('forecast numeric presentation', () => {
  it('renders amount and quantity strings as whole numbers with thousands separators', () => {
    expect(formatNumericPresentation('1234.56')).toBe('1,235');
    expect(formatNumericPresentation('1234567.4')).toBe('1,234,567');
    expect(formatNumericPresentation('-150000.2')).toBe('-150,000');
    expect(formatNumericPresentation('0')).toBe('0');
  });

  it('keeps the canonical numeric value free of presentation separators', () => {
    expect(parseFormattedNumericInput('1,250,000')).toBe('1250000');
    expect(parseFormattedNumericInput('-150,000')).toBe('-150000');
  });

  it('formats forecast amounts before blur, preserves intermediates, and submits canonical values', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(modelPayload))
      .mockResolvedValueOnce(response(metadataPayload))
      .mockResolvedValueOnce(response(successPayload));
    vi.stubGlobal('fetch', fetchMock);

    render(createElement(ForecastGenerationView));
    await screen.findByRole('heading', { name: '추정 산출' });
    await waitFor(() => expect(screen.getByRole('button', { name: '모형 적용' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: '모형 적용' }));

    const salesAmount = await screen.findByLabelText('7월 SW400 매출액');
    fireEvent.change(salesAmount, { target: { value: '-' } });
    expect(salesAmount).toHaveValue('-');
    fireEvent.change(salesAmount, { target: { value: '' } });
    expect(salesAmount).toHaveValue('');
    fireEvent.change(salesAmount, { target: { value: '1250000' } });
    expect(salesAmount).toHaveValue('1,250,000');

    const rawMaterialAdjustment = screen.getByLabelText('7월 원재료 조정액');
    fireEvent.change(rawMaterialAdjustment, { target: { value: '-150000' } });
    expect(rawMaterialAdjustment).toHaveValue('-150,000');

    const refundRate = screen.getByLabelText('7월 원재료 관세 환급률');
    expect(refundRate).toHaveValue('1.3');
    fireEvent.change(refundRate, { target: { value: '2.34' } });
    fireEvent.blur(refundRate);
    expect(refundRate).toHaveValue('2.3');

    fireEvent.click(screen.getByRole('button', { name: '추정 모형 생성' }));
    await screen.findByText('추정 모형 생성 완료');

    const body = JSON.parse(String((fetchMock.mock.calls[2][1] as RequestInit).body));
    const sw400 = body.months[0].sales.find((row: { product_code: string }) => row.product_code === 'SW400');
    expect(sw400.amount).toBe(1250000);
    expect(typeof sw400.amount).toBe('number');
    expect(body.months[0].raw_material_adjustment).toBe(-150000);
    expect(body.months[0].refund_rate).toBe(0.023);
  });
});

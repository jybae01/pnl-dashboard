import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  calculateAdjustmentExpectedAmount,
  calculateAdjustmentFromTargetAmount,
  calculateEntryAdjustmentFromTargetAmount,
  ForecastGenerationView,
} from './ForecastGenerationView';

const BASE = '11111111-1111-4111-8111-111111111111';
const baseline = 1_000_000;
const modelPayload = { models: [{
  model_id: BASE,
  display_name: 'Base',
  model_type: 'ACTUAL',
  model_year: 2026,
  start_month: 1,
  end_month: 12,
  is_published: true,
  is_default: false,
  dto_version: '1',
}] };
const metadataPayload = {
  base_model_id: BASE,
  manufacturing: [{ adjustment_key: 'mfg-energy', display_name: '전력비', unit: 'KRW', category: 'manufacturing', section: null, monthly_baseline_amounts: { '7': baseline } }],
  sga: [
    { adjustment_key: 'sga-selling', display_name: '운송비', unit: 'KRW', category: 'sga', section: 'selling', monthly_baseline_amounts: { '7': baseline } },
    { adjustment_key: 'sga-admin', display_name: '사무비', unit: 'KRW', category: 'sga', section: 'general_admin', monthly_baseline_amounts: { '7': baseline } },
  ],
  reason_max_length: 500,
  dto_version: '1',
};

function response(value: unknown) {
  return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

async function ready() {
  await screen.findByRole('heading', { name: '추정 산출' });
  await waitFor(() => expect(screen.getByRole('button', { name: '모형 적용' })).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button', { name: '모형 적용' }));
  fireEvent.click(screen.getByText('비용 및 원가 조정'));
}

afterEach(() => vi.unstubAllGlobals());

describe('forecast bidirectional adjustment input', () => {
  it('keeps the arithmetic contract symmetric and preserves other SGA entries', () => {
    expect(calculateAdjustmentFromTargetAmount(baseline, '1,200,000')).toBe('200000');
    expect(calculateAdjustmentExpectedAmount(baseline, '-150000')).toBe(850_000);
    expect(calculateEntryAdjustmentFromTargetAmount(baseline, '1,300,000', 100_000)).toBe('200000');
  });

  it('allows either manufacturing actual total or adjustment to drive the other field', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(response(modelPayload))
      .mockResolvedValueOnce(response(metadataPayload)));
    const { container } = render(<ForecastGenerationView />);
    await ready();
    fireEvent.click(screen.getByRole('button', { name: '7월 전력비 조정' }));

    const actual = screen.getByLabelText('7월 전력비 제조경비 실적금액');
    const adjustment = screen.getByLabelText('7월 전력비 제조경비 조정액');
    const drawer = actual.closest('.forecast-workflow__inline-drawer') as HTMLElement;
    const topGrid = drawer.querySelector('.forecast-workflow__drawer-readonly-grid') as HTMLElement;
    expect(within(topGrid).getByLabelText('7월 전력비 제조경비 조정액')).toBe(adjustment);
    expect(within(topGrid).queryByLabelText('7월 전력비 제조경비 실적금액')).not.toBeInTheDocument();

    fireEvent.change(actual, { target: { value: '1200000' } });
    expect(adjustment).toHaveValue('200,000');
    fireEvent.change(adjustment, { target: { value: '-150000' } });
    expect(actual).toHaveValue('850,000');
    expect(container).toHaveTextContent('실적금액 또는 조정액 중 어느 쪽을 입력해도 다른 금액을 자동 계산합니다.');
  });

  it('restores selling positions and supports two-way input', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(response(modelPayload))
      .mockResolvedValueOnce(response(metadataPayload)));
    render(<ForecastGenerationView />);
    await ready();
    fireEvent.click(screen.getByRole('button', { name: '7월 운송비 조정' }));

    const actual = screen.getByLabelText('7월 운송비 판매비 실적금액');
    const adjustment = screen.getByLabelText('7월 운송비 판매비 조정액');
    const drawer = actual.closest('.forecast-workflow__inline-drawer') as HTMLElement;
    const topGrid = drawer.querySelector('.forecast-workflow__drawer-readonly-grid') as HTMLElement;
    expect(within(topGrid).getByLabelText('7월 운송비 판매비 실적금액')).toBe(actual);
    expect(within(topGrid).queryByLabelText('7월 운송비 판매비 조정액')).not.toBeInTheDocument();

    fireEvent.change(actual, { target: { value: '1300000' } });
    expect(adjustment).toHaveValue('300,000');
    fireEvent.change(adjustment, { target: { value: '50000' } });
    expect(actual).toHaveValue('1,050,000');
  });

  it('restores general-admin positions and supports two-way input', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(response(modelPayload))
      .mockResolvedValueOnce(response(metadataPayload)));
    render(<ForecastGenerationView />);
    await ready();
    fireEvent.click(screen.getByRole('tab', { name: '일반관리비' }));
    fireEvent.click(screen.getByRole('button', { name: '7월 사무비 조정' }));

    const actual = screen.getByLabelText('7월 사무비 일반관리비 실적금액');
    const adjustment = screen.getByLabelText('7월 사무비 일반관리비 조정액');
    const drawer = actual.closest('.forecast-workflow__inline-drawer') as HTMLElement;
    const topGrid = drawer.querySelector('.forecast-workflow__drawer-readonly-grid') as HTMLElement;
    expect(within(topGrid).getByLabelText('7월 사무비 일반관리비 조정액')).toBe(adjustment);
    expect(within(topGrid).queryByLabelText('7월 사무비 일반관리비 실적금액')).not.toBeInTheDocument();

    fireEvent.change(actual, { target: { value: '1100000' } });
    expect(adjustment).toHaveValue('100,000');
    fireEvent.change(adjustment, { target: { value: '-25000' } });
    expect(actual).toHaveValue('975,000');
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PnlStatusView } from '../views/PnlStatusView';
import { PnlDashboardDto } from './types';

const BASE = '11111111-1111-4111-8111-111111111111';
const COMP = '22222222-2222-4222-8222-222222222222';

function line(code: string, label: string, baseline: number, comparison: number, ratio: number | null = null) {
  return { code, label, baseline, comparison, delta: comparison - baseline, comparison_ratio_to_revenue: ratio };
}

function fixture(): PnlDashboardDto {
  const revenue1 = line('revenue', '매출액', 100, 120);
  const gp1 = line('gross_profit', '매출총이익', 40, 50);
  const op1 = line('operating_profit', '영업이익', 20, 27);
  const revenue2 = line('revenue', '매출액', 110, 105);
  const gp2 = line('gross_profit', '매출총이익', 44, 42);
  const op2 = line('operating_profit', '영업이익', 22, 18);
  const revenue3 = line('revenue', '매출액', 120, 140);
  const gp3 = line('gross_profit', '매출총이익', 48, 56);
  const op3 = line('operating_profit', '영업이익', 24, 32);
  const periodRevenue = line('revenue', '매출액', 330, 365);
  const periodGp = line('gross_profit', '매출총이익', 132, 148);
  const periodOp = line('operating_profit', '영업이익', 66, 77);
  const cost = line('cogs', '매출원가', 60, 70);
  const effects = [
    { code: 'sales_price', label: '판가', profit_effect: 1 },
    { code: 'material_total', label: '원재료', profit_effect: -2 },
    { code: 'sales_quantity', label: '판매수량', profit_effect: 2 },
    { code: 'sales_mix', label: '제품 Mix', profit_effect: 0 },
    { code: 'sales_fx', label: '매출환율', profit_effect: 0 },
    { code: 'manufacturing_realized', label: '제조', profit_effect: -2 },
    { code: 'sga_variable', label: '변동 판매관리비', profit_effect: 2 },
    { code: 'sga_fixed', label: '고정 판매관리비', profit_effect: -2 },
    { code: 'tariff', label: '관세', profit_effect: -1 },
  ];
  return {
    result_id: '44444444-4444-4444-8444-444444444444',
    job_id: '33333333-3333-4333-8333-333333333333',
    identity: {
      baseline_model_id: BASE,
      baseline_model_name: '계획 모형',
      comparison_model_id: COMP,
      comparison_model_name: '실적 모형',
      model_year: 2026,
      start_month: 1,
      end_month: 3,
      available_months: [1, 2, 3],
      actual_months: [1],
      actual_through_month: 1,
    },
    kpis: {
      latest_month: 3,
      revenue: { latest: revenue3, period: periodRevenue },
      gross_profit: { latest: gp3, period: periodGp },
      operating_profit: { latest: op3, period: periodOp },
      latest_operating_margin: { baseline: 20, comparison: 22.857142857, delta_percentage_points: 2.857142857 },
      period_operating_margin: { baseline: 20, comparison: 21.0958904, delta_percentage_points: 1.0958904 },
    },
    monthly_series: [
      { month: 1, comparison_period_type: '실적', revenue: revenue1, cogs: cost, gross_profit: gp1, operating_profit: op1, baseline_operating_margin: 20, comparison_operating_margin: 22.5 },
      { month: 2, comparison_period_type: '추정', revenue: revenue2, cogs: line('cogs', '매출원가', 66, 63), gross_profit: gp2, operating_profit: op2, baseline_operating_margin: 20, comparison_operating_margin: 17.142857142857 },
      { month: 3, comparison_period_type: '계획', revenue: revenue3, cogs: line('cogs', '매출원가', 72, 84), gross_profit: gp3, operating_profit: op3, baseline_operating_margin: 20, comparison_operating_margin: 22.857142857 },
    ],
    pnl_statement: [periodRevenue, line('cogs', '매출원가', 198, 217), periodGp, periodOp],
    manufacturing: {
      cost_lines: [line('raw_material', '원재료비', 30, 33)],
      material_components: { nonwoven_price_ex_fx: -1, nonwoven_jpy: -2, materials_ex_nonwoven: -3, total: -6, jpy_fx_unit: 'KRW/JPY', mcm_is_separate_effect: false },
      accounts: [{ account: '고정 제조경비', classification: 'fixed', section: 'manufacturing', baseline: 4, comparison: 5, delta: 1, profit_effect: -1, inventory_realization_rate: 1, activity_effect: 0, unit_effect: 0, fixed_effect: -1 }],
      fixed_cost_policy: { manufacturing_effect_includes_variable_and_fixed: true, fixed_manufacturing_is_not_a_separate_top_level_effect: true },
    },
    sga: { fixed_scope: 'internal scope', accounts: [{ account: '판매관리비 계정', classification: 'variable', section: 'sga', baseline: 3, comparison: 4, delta: 1, profit_effect: -1, inventory_realization_rate: null, activity_effect: null, unit_effect: null, fixed_effect: null }] },
    product_groups: [
      { code: 'LC', display_name: '4인치 LC', quantity_unit: 'PCS', baseline_quantity: 3, comparison_quantity: 4, baseline_revenue: 20, comparison_revenue: 25, revenue_delta: 5, baseline_cogs: 12, comparison_cogs: 14, baseline_gross_profit: 8, comparison_gross_profit: 11 },
      { code: 'FS', display_name: 'FS', quantity_unit: 'm', baseline_quantity: 100, comparison_quantity: 110, baseline_revenue: 30, comparison_revenue: 35, revenue_delta: 5, baseline_cogs: 15, comparison_cogs: 17, baseline_gross_profit: 15, comparison_gross_profit: 18 },
    ],
    key_facts: { effects, effects_total: -2, residual: 9, operating_profit_delta: 7, reconciled: false },
    result_schema_version: '1', completed_at: '2026-08-11T00:00:00Z', published_at: '2026-08-11T01:00:00Z', currency_unit: 'KRW', dto_version: '1',
  };
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
}

afterEach(() => vi.unstubAllGlobals());

describe('P&L Dashboard seven-source vertical slice', () => {
  it('renders authoritative KPI, trend scenarios, seven stored blocks, and separate units', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json(fixture())));
    render(<PnlStatusView />);

    expect(await screen.findByRole('heading', { name: '손익 현황' })).toBeInTheDocument();
    expect(screen.getAllByText('₩365').length).toBeGreaterThan(0);
    expect(screen.getByText('기준 대비 영업이익 증감')).toBeInTheDocument();
    expect(screen.getByText('실적')).toBeInTheDocument();
    expect(screen.getByText('추정')).toBeInTheDocument();
    expect(screen.getByText('계획')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '손익계산서' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: '제조원가' }));
    expect(screen.getByText('고정 제조경비')).toBeInTheDocument();
    expect(screen.getByText('고정')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '판매관리비' }));
    expect(screen.getByText('판매관리비 계정')).toBeInTheDocument();
    expect(screen.getByText('변동')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '제품군 손익' }));
    expect(screen.getByText('4인치 LC')).toBeInTheDocument();
    expect(screen.getByText('PCS')).toBeInTheDocument();
    expect(screen.getByText('FS')).toBeInTheDocument();
    expect(screen.getByText('m')).toBeInTheDocument();
    expect(screen.getByText('기타 요인')).toBeInTheDocument();
    expect(screen.queryByText('백만원')).not.toBeInTheDocument();
    expect(screen.queryByText('16인치')).not.toBeInTheDocument();
    expect(screen.queryByText('대사')).not.toBeInTheDocument();
    expect(screen.queryByText(BASE)).not.toBeInTheDocument();
  });

  it('preserves backend key-fact order and sends the analysis CTA to the existing route callback', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json(fixture())));
    const onNavigate = vi.fn();
    render(<PnlStatusView onNavigateToVariance={onNavigate} />);
    await screen.findByRole('heading', { name: '손익 현황' });
    const labels = screen.getAllByText(/^(판가|원재료|판매수량|제품 Mix|매출환율|제조|변동 판매관리비|고정 판매관리비|관세)$/).map((node) => node.textContent);
    expect(labels.slice(-9)).toEqual(['판가', '원재료', '판매수량', '제품 Mix', '매출환율', '제조', '변동 판매관리비', '고정 판매관리비', '관세']);
    expect(screen.queryByText(/Top|주요 긍정|주요 부정/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '손익분석 상세 보기' }));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it('uses green/red/neutral tones from authoritative profit effects', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json(fixture())));
    render(<PnlStatusView />);
    await screen.findByRole('heading', { name: '손익 현황' });
    expect(screen.getAllByText('+₩11').some((node) => node.className.includes('pnl-dashboard__tone--positive'))).toBe(true);
    expect(screen.getAllByText('-₩2').some((node) => node.className.includes('pnl-dashboard__tone--negative'))).toBe(true);
    expect(screen.getAllByText('₩0').some((node) => node.className.includes('pnl-dashboard__tone--neutral'))).toBe(true);
  });

  it('keeps EMPTY, ERROR, FORBIDDEN, and invalid payload distinct', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ error: { code: 'RESULT_NOT_AVAILABLE', message: 'none' } }, 404)));
    const { unmount } = render(<PnlStatusView />);
    expect(await screen.findByText('아직 확인할 수 있는 손익 데이터가 없습니다.')).toBeInTheDocument();
    unmount();

    vi.stubGlobal('fetch', vi.fn(() => json({ error: { code: 'TRANSIENT_SYSTEM_ERROR', message: 'failed' } }, 500)));
    render(<PnlStatusView />);
    expect(await screen.findByText('손익 현황을 불러오지 못했습니다.')).toBeInTheDocument();
    expect(screen.queryByText('아직 확인할 수 있는 손익 데이터가 없습니다.')).not.toBeInTheDocument();
    document.body.innerHTML = '';

    vi.stubGlobal('fetch', vi.fn(() => json({ error: { code: 'FORBIDDEN', message: 'forbidden' } }, 403)));
    render(<PnlStatusView />);
    expect(await screen.findByText('손익 현황을 조회할 권한이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText('아직 확인할 수 있는 손익 데이터가 없습니다.')).not.toBeInTheDocument();
  });

  it('does not render a server contract failure as a dashboard', async () => {
    const broken = fixture();
    broken.pnl_statement[2].comparison = 51;
    vi.stubGlobal('fetch', vi.fn(() => json(broken)));
    render(<PnlStatusView />);
    await waitFor(() => expect(screen.getByText('손익 현황 데이터 형식을 확인할 수 없습니다.')).toBeInTheDocument());
    expect(screen.queryByTestId('pnl-dashboard')).not.toBeInTheDocument();
  });
});

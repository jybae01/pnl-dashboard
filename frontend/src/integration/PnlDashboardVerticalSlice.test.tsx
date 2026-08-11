import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PnlStatusView } from '../views/PnlStatusView';
import { PnlDashboardDto } from './types';

const BASE = '11111111-1111-4111-8111-111111111111';
const COMP = '22222222-2222-4222-8222-222222222222';

function line(code: string, label: string, baseline: number, comparison: number) {
  return { code, label, baseline, comparison, delta: comparison - baseline, comparison_ratio_to_revenue: null };
}

function fixture(): PnlDashboardDto {
  const revenue = line('revenue', '매출액', 100, 120);
  const gp = line('gross_profit', '매출총이익', 40, 50);
  const op = line('operating_profit', '영업이익', 20, 27);
  return {
    result_id: '44444444-4444-4444-8444-444444444444', job_id: '33333333-3333-4333-8333-333333333333',
    identity: { baseline_model_id: BASE, baseline_model_name: 'Plan', comparison_model_id: COMP,
      comparison_model_name: 'Actual', model_year: 2026, start_month: 1, end_month: 1,
      available_months: [1], actual_months: [1], actual_through_month: 1 },
    kpis: { latest_month: 1, revenue: { latest: revenue, period: revenue },
      gross_profit: { latest: gp, period: gp }, operating_profit: { latest: op, period: op },
      latest_operating_margin: { baseline: 20, comparison: 22.5, delta_percentage_points: 2.5 },
      period_operating_margin: { baseline: 20, comparison: 22.5, delta_percentage_points: 2.5 } },
    monthly_series: [{ month: 1, comparison_period_type: '실적', revenue,
      cogs: line('cogs', '매출원가', 60, 70), gross_profit: gp,
      operating_profit: op, baseline_operating_margin: 20, comparison_operating_margin: 22.5 }],
    pnl_statement: [revenue, line('cogs', '매출원가', 60, 70), gp, op],
    manufacturing: { cost_lines: [line('raw_material', '원재료비', 30, 33)],
      material_components: { nonwoven_price_ex_fx: -1, nonwoven_jpy: -2, materials_ex_nonwoven: -3,
        total: -6, jpy_fx_unit: 'KRW/JPY', mcm_is_separate_effect: false },
      accounts: [{ account: '고정 제조경비', classification: 'fixed', section: '', baseline: 4,
        comparison: 5, delta: 1, profit_effect: -1, inventory_realization_rate: 1,
        activity_effect: 0, unit_effect: 0, fixed_effect: -1 }],
      fixed_cost_policy: { manufacturing_effect_includes_variable_and_fixed: true,
        fixed_manufacturing_is_not_a_separate_top_level_effect: true } },
    sga: { fixed_scope: 'fixed SG&A accounts excluding customer freight and tariff', accounts: [] },
    product_groups: [{ code: 'LC', display_name: '4인치 LC', quantity_unit: 'PCS',
      baseline_quantity: 3, comparison_quantity: 4, baseline_revenue: 20, comparison_revenue: 25,
      revenue_delta: 5, baseline_cogs: 12, comparison_cogs: 14,
      baseline_gross_profit: 8, comparison_gross_profit: 11 },
      { code: 'FS', display_name: 'FS', quantity_unit: 'm', baseline_quantity: 100,
        comparison_quantity: 110, baseline_revenue: 30, comparison_revenue: 35, revenue_delta: 5,
        baseline_cogs: 15, comparison_cogs: 17, baseline_gross_profit: 15, comparison_gross_profit: 18 }],
    key_facts: { effects: [
      { code: 'manufacturing_realized', label: '제조경비', profit_effect: -2 },
      { code: 'material_total', label: '원재료', profit_effect: -2 },
      { code: 'sales_quantity', label: '판매수량', profit_effect: 2 },
      { code: 'sga_fixed', label: '고정 판관비', profit_effect: -2 },
      { code: 'sga_variable', label: '변동 판관비', profit_effect: 2 },
      { code: 'sales_price', label: '판매단가', profit_effect: 1 },
      { code: 'tariff', label: '관세', profit_effect: -1 },
      { code: 'sales_fx', label: '매출환율', profit_effect: 0 },
      { code: 'sales_mix', label: '제품 Mix', profit_effect: 0 },
    ],
      effects_total: -2, residual: 9, operating_profit_delta: 7, reconciled: false },
    result_schema_version: '1', completed_at: '2026-08-11T00:00:00Z',
    published_at: '2026-08-11T01:00:00Z', currency_unit: 'KRW', dto_version: '1',
  };
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
}

afterEach(() => vi.unstubAllGlobals());

describe('P&L Dashboard seven-source vertical slice', () => {
  it('renders all seven stored blocks with LC and separate units', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json(fixture())));
    render(<PnlStatusView />);
    expect(await screen.findByText('월별 손익 추이')).toBeInTheDocument();
    expect(screen.getAllByText('매출액').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '제조원가' }));
    expect(screen.getByText('고정 제조경비')).toBeInTheDocument();
    expect(screen.getByText(/JPY 환율 단위: KRW\/JPY/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '판매관리비' }));
    expect(screen.getByText(/fixed SG&A accounts/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '제품군 손익' }));
    expect(screen.getByText('4인치 LC')).toBeInTheDocument();
    expect(screen.getByText('주요 손익 변동')).toBeInTheDocument();
    expect(screen.queryByText('9060')).not.toBeInTheDocument();
  });

  it('keeps EMPTY separate from ERROR and clears stale data', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ error: { code: 'RESULT_NOT_AVAILABLE', message: 'not available' } }, 404)));
    render(<PnlStatusView />);
    expect(await screen.findByText('공개된 손익 현황이 없습니다')).toBeInTheDocument();
    expect(screen.queryByText('월별 손익 추이')).not.toBeInTheDocument();
  });

  it('rejects a broken P&L identity as INVALID_PAYLOAD', async () => {
    const broken = fixture(); broken.pnl_statement[2].comparison = 51;
    vi.stubGlobal('fetch', vi.fn(() => json(broken)));
    render(<PnlStatusView />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('손익 현황 데이터 계약'));
    expect(screen.queryByText('월별 손익 추이')).not.toBeInTheDocument();
  });
});

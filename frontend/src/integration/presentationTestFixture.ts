import { AnalysisPresentationDto } from './types';

export const TEST_BASE = '11111111-1111-4111-8111-111111111111';
export const TEST_COMPARISON = '22222222-2222-4222-8222-222222222222';
export const TEST_JOB = '33333333-3333-4333-8333-333333333333';
export const TEST_RESULT = '44444444-4444-4444-8444-444444444444';

const effectValues = [10, 5, 20, -4, -8, -6, 0, -3, 2, -1];
const effectCodes = [
  'sales_quantity', 'sales_mix', 'sales_price', 'sales_fx', 'material_total',
  'manufacturing_realized', 'inventory_timing', 'sga_variable', 'sga_fixed', 'tariff',
] as const;

export function presentationFixture(overrides: Partial<AnalysisPresentationDto> = {}): AnalysisPresentationDto {
  const effects = effectCodes.map((code, index) => ({
    code,
    label: ['판매수량', '제품 Mix', '판매단가', '매출환율', '원재료', '제조경비', '재고·원가 반영시차', '변동 판관비', '고정 판관비', '관세'][index],
    category: (['sales_fx', 'tariff'].includes(code) ? 'EXTERNAL' : ['material_total', 'manufacturing_realized', 'inventory_timing', 'sga_variable', 'sga_fixed'].includes(code) ? 'COST' : 'INTERNAL') as 'INTERNAL' | 'EXTERNAL' | 'COST',
    profit_effect: effectValues[index],
    description: `${code} persisted fact`,
    drilldown: code === 'sales_mix'
      ? { kind: 'unavailable' as const, available: false, rows: [], unavailable_reason: 'persisted detail unavailable' }
      : { kind: (code === 'material_total' ? 'material' : code === 'manufacturing_realized' ? 'manufacturing' : code === 'inventory_timing' ? 'inventory' : code.startsWith('sga_') ? 'sga' : code === 'tariff' ? 'tariff' : 'sales') as 'sales' | 'material' | 'manufacturing' | 'inventory' | 'sga' | 'tariff', available: true, rows: [{ row_id: `${code}:1`, label: `${code} source`, unit: 'KRW', baseline: null, comparison: null, delta: null, profit_effect: effectValues[index], note: 'persisted source' }], unavailable_reason: null },
  }));
  const effectsTotal = effectValues.reduce((sum, value) => sum + value, 0);
  const residual = { amount: 5, classification: 'UNEXPLAINED' as const, display_label: '미설명 잔여차이' };
  const value: AnalysisPresentationDto = {
    identity: {
      result_id: TEST_RESULT, job_id: TEST_JOB,
      baseline_model_id: TEST_BASE, comparison_model_id: TEST_COMPARISON,
      baseline_model_name: 'Base', comparison_model_name: 'Comparison',
      start_month: 1, end_month: 12, baseline_sales_fx: 1450, comparison_sales_fx: 1500,
      result_schema_version: 'comparison-v1', completed_at: '2026-08-11T00:00:01Z',
      is_published: true, is_default: false, published_at: '2026-08-11T00:00:02Z',
    },
    kpis: {
      baseline_revenue: 1000, comparison_revenue: 1100, revenue_delta: 100,
      baseline_operating_profit: 100, comparison_operating_profit: 120,
      operating_profit_delta: effectsTotal + residual.amount,
      effects_total: effectsTotal, residual: residual.amount,
    },
    effects,
    residual,
    product_groups: [{ code: 'LC', display_name: '4인치 LC', quantity_unit: 'PCS', baseline_quantity: 10, comparison_quantity: 12, baseline_revenue: 100, comparison_revenue: 120 }],
    manufacturing_activities: [
      { process: '전공정', production_basis: 'SW', unit: 'PCS', baseline: 10, comparison: 12, delta: 2 },
      { process: '후공정', production_basis: 'FS', unit: 'm', baseline: 20, comparison: 19, delta: -1 },
    ],
    executive_summary: {
      operating_profit_delta: effectsTotal + residual.amount,
      top_positive_effects: effects.filter((effect) => effect.profit_effect > 0).slice(0, 3),
      top_negative_effects: effects.filter((effect) => effect.profit_effect < 0).slice(0, 3),
      residual,
    },
    currency_unit: 'KRW',
    dto_version: '1',
  };
  return { ...value, ...overrides };
}

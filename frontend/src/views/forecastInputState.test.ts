import { describe, expect, it } from 'vitest';
import {
  adaptForecastInput,
  createForecastMonthFormState,
  ensureForecastMonths,
  MCM_PRODUCTS,
  PRODUCTION_PRODUCTS,
  SALES_PRODUCTS,
} from './forecastInputState';

describe('forecast direct-input adapter', () => {
  const metadata = {
    base_model_id: '11111111-1111-4111-8111-111111111111',
    manufacturing: [{ adjustment_key: 'mfg-energy', display_name: '전력비', unit: 'KRW', category: 'manufacturing' as const, section: null }],
    sga: [{ adjustment_key: 'sga-selling', display_name: '운송비', unit: 'KRW', category: 'sga' as const, section: 'selling' }],
    reason_max_length: 500 as const,
    dto_version: '1' as const,
  };

  it('creates every canonical row exactly once without calculating financial values', () => {
    const month = createForecastMonthFormState(7);
    month.sales.SW400.quantity = '12.5';
    month.sales.SW400.amount = '1000';
    month.production.SW400.quantity = '8';
    month.mcm.SW400.quantity = '3';

    const adapted = adaptForecastInput([7], { 7: month });
    expect(adapted.error).toBe('');
    expect(adapted.value).toHaveLength(1);
    expect(adapted.value?.[0].sales).toHaveLength(SALES_PRODUCTS.length);
    expect(adapted.value?.[0].production).toHaveLength(PRODUCTION_PRODUCTS.length);
    expect(adapted.value?.[0].mcm).toHaveLength(MCM_PRODUCTS.length);
    expect(adapted.value?.[0].sales[0]).toEqual({ product_code: 'SW400', quantity: 12.5, amount: 1000 });
    expect(adapted.value?.[0].manufacturing_adjustments).toEqual([]);
    expect(adapted.value?.[0].sga_adjustments).toEqual([]);
  });

  it('rejects blank, negative, and non-finite editing values instead of coercing them to zero', () => {
    const blank = createForecastMonthFormState(7);
    blank.sales.SW400.quantity = '';
    expect(adaptForecastInput([7], { 7: blank })).toMatchObject({ value: null });

    const negative = createForecastMonthFormState(7);
    negative.production.SW400.quantity = '-1';
    expect(adaptForecastInput([7], { 7: negative })).toMatchObject({ value: null });

    const infinite = createForecastMonthFormState(7);
    infinite.mcm.SW400.quantity = 'Infinity';
    expect(adaptForecastInput([7], { 7: infinite })).toMatchObject({ value: null });
  });

  it('adds newly selected months without replacing edits in an existing month', () => {
    const july = createForecastMonthFormState(7);
    july.sales.LC.quantity = '44';
    const current = { 7: july };
    const next = ensureForecastMonths(current, [7, 8]);

    expect(next[7].sales.LC.quantity).toBe('44');
    expect(next[8].month).toBe(8);
    expect(next[8].sales.LC.quantity).toBe('0');
  });

  it('round-trips opaque adjustment keys and scalar advanced fields without deriving amounts', () => {
    const month = createForecastMonthFormState(7, metadata);
    month.manufacturingAdjustments['mfg-energy'] = { amount: '-456789', reason: '전력 단가 반영' };
    month.sgaAdjustments['sga-selling'] = { amount: '567890', reason: '운송 계약 조정' };
    month.disposalAdjustment = '-1200';
    month.disposalReason = '폐기 사유';
    month.obsolescenceAdjustment = '2300';
    month.obsolescenceReason = '진부화 사유';
    month.newBusinessGoodsCogs = '890123';
    month.newBusinessGoodsCogsReason = '신사업 직접 반영';
    month.ufMbrCogsRate = '0.8';
    month.ixCogsRate = '0.81';
    month.ufMbrTransportRate = '0.04';
    month.ixTransportRate = '0.06';
    month.ixPackLiters = '24';
    month.ixPackCost = '390';
    month.planNaSaSales = '100000';
    month.naSaSales = '120000';
    month.tariffApplicableRate = '0.11';
    month.tariffRate = '0.14';
    month.rawMaterialBasis = 'direct';
    month.rawMaterialDirect = '7000000000';
    month.rawMaterialAdjustment = '-3456';
    month.rawMaterialReason = '구매팀 입력';
    month.refundRate = '0.02';

    const adapted = adaptForecastInput([7], { 7: month }, metadata);
    expect(adapted.error).toBe('');
    expect(adapted.value?.[0].manufacturing_adjustments).toEqual([
      { adjustment_key: 'mfg-energy', amount: -456789, reason: '전력 단가 반영' },
    ]);
    expect(adapted.value?.[0].sga_adjustments).toEqual([
      { adjustment_key: 'sga-selling', amount: 567890, reason: '운송 계약 조정' },
    ]);
    expect(adapted.value?.[0].disposal_adjustment).toBe(-1200);
    expect(adapted.value?.[0].disposal_reason).toBe('폐기 사유');
    expect(adapted.value?.[0].obsolescence_adjustment).toBe(2300);
    expect(adapted.value?.[0].obsolescence_reason).toBe('진부화 사유');
    expect(adapted.value?.[0].new_business_goods_cogs).toBe(890123);
    expect(adapted.value?.[0].new_business_goods_cogs_reason).toBe('신사업 직접 반영');
    expect(adapted.value?.[0].uf_mbr_cogs_rate).toBe(0.8);
    expect(adapted.value?.[0].ix_cogs_rate).toBe(0.81);
    expect(adapted.value?.[0].uf_mbr_transport_rate).toBe(0.04);
    expect(adapted.value?.[0].ix_transport_rate).toBe(0.06);
    expect(adapted.value?.[0].ix_pack_liters).toBe(24);
    expect(adapted.value?.[0].ix_pack_cost).toBe(390);
    expect(adapted.value?.[0].plan_na_sa_sales).toBe(100000);
    expect(adapted.value?.[0].na_sa_sales).toBe(120000);
    expect(adapted.value?.[0].tariff_applicable_rate).toBe(0.11);
    expect(adapted.value?.[0].tariff_rate).toBe(0.14);
    expect(adapted.value?.[0].raw_material_basis).toBe('direct');
    expect(adapted.value?.[0].raw_material_direct).toBe(7000000000);
    expect(adapted.value?.[0].raw_material_adjustment).toBe(-3456);
    expect(adapted.value?.[0].raw_material_reason).toBe('구매팀 입력');
    expect(adapted.value?.[0].refund_rate).toBe(0.02);
  });

  it('keeps advanced values isolated by month and rejects invalid advanced input before POST boundary', () => {
    const july = createForecastMonthFormState(7, metadata);
    july.manufacturingAdjustments['mfg-energy'] = { amount: '10', reason: '7월' };
    const august = createForecastMonthFormState(8, metadata);
    august.manufacturingAdjustments['mfg-energy'] = { amount: '-20', reason: '8월' };
    const adapted = adaptForecastInput([7, 8], { 7: july, 8: august }, metadata);
    expect(adapted.value?.map((item) => item.manufacturing_adjustments[0].amount)).toEqual([10, -20]);

    const invalid = createForecastMonthFormState(7, metadata);
    invalid.tariffRate = 'not-a-number';
    expect(adaptForecastInput([7], { 7: invalid }, metadata)).toMatchObject({ value: null });
  });
});

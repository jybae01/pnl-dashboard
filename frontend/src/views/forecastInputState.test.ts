import { describe, expect, it } from 'vitest';
import {
  adaptForecastInput,
  applyForecastExcelPreview,
  BUSINESS_PRODUCTION_ROWS,
  createForecastMonthFormState,
  ensureForecastMonths,
  MCM_PRODUCTS,
  SALES_PRODUCTS,
} from './forecastInputState';

describe('forecast direct-input adapter', () => {
  const baselineAmounts = {
    '1': 1000000,
    '2': 2000000,
    '3': 3000000,
    '4': 4000000,
    '5': 5000000,
    '6': 6000000,
    '7': 7000000,
    '8': 8000000,
    '9': 9000000,
    '10': 10000000,
    '11': 11000000,
    '12': 12000000,
  };

  const metadata = {
    base_model_id: '11111111-1111-4111-8111-111111111111',
    manufacturing: [{
      adjustment_key: 'mfg-energy',
      display_name: '전력비',
      unit: 'KRW',
      category: 'manufacturing' as const,
      section: null,
      monthly_baseline_amounts: baselineAmounts,
    }],
    sga: [{
      adjustment_key: 'sga-selling',
      display_name: '운송비',
      unit: 'KRW',
      category: 'sga' as const,
      section: 'selling',
      monthly_baseline_amounts: baselineAmounts,
    }],
    reason_max_length: 500 as const,
    dto_version: '1' as const,
  };

  it('creates six business production rows without allocating canonical products', () => {
    const month = createForecastMonthFormState(7);
    month.sales.SW400.quantity = '12.5';
    month.sales.SW400.amount = '1000';
    month.production['back:SW'].quantity = '8';
    month.mcm.SW400.quantity = '3';

    const adapted = adaptForecastInput([7], { 7: month });
    expect(adapted.error).toBe('');
    expect(adapted.value).toHaveLength(1);
    expect(adapted.value?.[0].sales).toHaveLength(SALES_PRODUCTS.length);
    expect(adapted.value?.[0].production).toBeUndefined();
    expect(adapted.value?.[0].business_production).toHaveLength(BUSINESS_PRODUCTION_ROWS.length);
    expect(adapted.value?.[0].business_production?.[3]).toEqual({
      process: '후공정', product_group: 'SW', quantity: 8, unit: 'PCS',
    });
    expect(adapted.value?.[0].mcm).toHaveLength(MCM_PRODUCTS.length);
    expect(adapted.value?.[0].sales[0]).toEqual({ product_code: 'SW400', quantity: 12.5, amount: 1000 });
    expect(adapted.value?.[0].manufacturing_adjustments).toEqual([]);
    expect(adapted.value?.[0].sga_adjustments).toEqual([]);
    expect(adapted.value?.[0].new_business_goods_cogs_mode).toBe('ACTUAL_YTD_DEFAULT');
    expect(adapted.value?.[0].new_business_goods_cogs).toBeUndefined();
  });

  it('rejects blank, negative, and non-finite editing values instead of coercing them to zero', () => {
    const blank = createForecastMonthFormState(7);
    blank.sales.SW400.quantity = '';
    expect(adaptForecastInput([7], { 7: blank })).toMatchObject({ value: null });

    const blankProduction = createForecastMonthFormState(7);
    blankProduction.production['front:SW'].quantity = '';
    expect(adaptForecastInput([7], { 7: blankProduction })).toMatchObject({ value: null });

    const negative = createForecastMonthFormState(7);
    negative.production['front:SW'].quantity = '-1';
    expect(adaptForecastInput([7], { 7: negative })).toMatchObject({ value: null });

    const infinite = createForecastMonthFormState(7);
    infinite.mcm.SW400.quantity = 'Infinity';
    expect(adaptForecastInput([7], { 7: infinite })).toMatchObject({ value: null });
  });

  it('adds newly selected months without replacing edits in an existing month', () => {
    const july = createForecastMonthFormState(7);
    july.sales.LC.quantity = '44';
    july.production['back:SW'].quantity = '12000';
    const current = { 7: july };
    const next = ensureForecastMonths(current, [7, 8]);

    expect(next[7].sales.LC.quantity).toBe('44');
    expect(next[7].production['back:SW'].quantity).toBe('12000');
    expect(next[8].month).toBe(8);
    expect(next[8].sales.LC.quantity).toBe('0');
    expect(next[8].production['back:SW'].quantity).toBe('0');
  });

  it('round-trips opaque adjustment keys and scalar advanced fields without deriving amounts', () => {
    const month = createForecastMonthFormState(7, metadata);
    month.manufacturingAdjustments['mfg-energy'] = { amount: '-456789', reason: '전력 단가 반영' };
    month.sgaAdjustments['sga-selling'] = { amount: '567890', reason: '운송 계약 조정' };
    month.disposalAdjustment = '-1200';
    month.disposalReason = '폐기 사유';
    month.obsolescenceAdjustment = '2300';
    month.obsolescenceReason = '진부화 사유';
    month.newBusinessGoodsCogsMode = 'MANUAL_OVERRIDE';
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
    expect(adapted.value?.[0].new_business_goods_cogs_mode).toBe('MANUAL_OVERRIDE');
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

  it('applies only sales and business production while preserving MCM and every advanced field', () => {
    const july = createForecastMonthFormState(7, metadata);
    july.sales.SW400.quantity = '99';
    july.production['back:SW'].quantity = '88';
    july.mcm.SW400.quantity = '77';
    july.manufacturingAdjustments['mfg-energy'] = { amount: '-66', reason: '제조 유지' };
    july.sgaAdjustments['sga-selling'] = { amount: '55', reason: '판관비 유지' };
    july.disposalAdjustment = '44';
    july.newBusinessGoodsCogsMode = 'MANUAL_OVERRIDE';
    july.newBusinessGoodsCogs = '33';
    july.newBusinessGoodsCogsReason = '직접 반영 유지';
    july.naSaSales = '22';
    july.rawMaterialAdjustment = '11';

    const preview = {
      source_filename: 'forecast_input.xlsx', valid: true, blocking: false,
      sales_rows: [{
        month: 7, product_code: 'SW400', product_name: 'SW400', product_group: 'SW',
        quantity: 123, amount: 456, source_sheet: '판매계획' as const, source_row: 2,
      }],
      business_production_rows: [{
        month: 7, process: '후공정' as const, product_group: 'SW' as const,
        quantity: 1000, unit: 'PCS' as const, source_sheet: '생산계획' as const, source_row: 2,
      }],
      issues: [], sales_summary: [{ unit: 'PCS' as const, row_count: 1, quantity_total: 123 }],
      production_summary: [{ unit: 'PCS' as const, row_count: 1, quantity_total: 1000 }], dto_version: '1' as const,
    };
    const applied = applyForecastExcelPreview({ 7: july }, [7], preview, metadata);

    expect(applied[7].sales.SW400).toEqual({ quantity: '123', amount: '456' });
    expect(applied[7].sales.SW440).toEqual({ quantity: '0', amount: '0' });
    expect(applied[7].production['back:SW']).toEqual({ quantity: '1000' });
    expect(applied[7].production['front:SW']).toEqual({ quantity: '0' });
    expect(applied[7].mcm.SW400.quantity).toBe('77');
    expect(applied[7].manufacturingAdjustments['mfg-energy']).toEqual({ amount: '-66', reason: '제조 유지' });
    expect(applied[7].sgaAdjustments['sga-selling']).toEqual({ amount: '55', reason: '판관비 유지' });
    expect(applied[7].disposalAdjustment).toBe('44');
    expect(applied[7].newBusinessGoodsCogs).toBe('33');
    expect(applied[7].newBusinessGoodsCogsMode).toBe('MANUAL_OVERRIDE');
    expect(applied[7].newBusinessGoodsCogsReason).toBe('직접 반영 유지');
    expect(applied[7].naSaSales).toBe('22');
    expect(applied[7].rawMaterialAdjustment).toBe('11');
  });

  it('requires explicit manual amount and reason while preserving zero override', () => {
    const missing = createForecastMonthFormState(7);
    missing.newBusinessGoodsCogsMode = 'MANUAL_OVERRIDE';
    expect(adaptForecastInput([7], { 7: missing })).toMatchObject({ value: null });

    const zero = createForecastMonthFormState(7);
    zero.newBusinessGoodsCogsMode = 'MANUAL_OVERRIDE';
    zero.newBusinessGoodsCogs = '0';
    zero.newBusinessGoodsCogsReason = '명시적 0원';
    const adapted = adaptForecastInput([7], { 7: zero });
    expect(adapted.value?.[0]).toMatchObject({
      new_business_goods_cogs_mode: 'MANUAL_OVERRIDE',
      new_business_goods_cogs: 0,
      new_business_goods_cogs_reason: '명시적 0원',
    });
  });
});

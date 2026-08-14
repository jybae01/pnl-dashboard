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
});

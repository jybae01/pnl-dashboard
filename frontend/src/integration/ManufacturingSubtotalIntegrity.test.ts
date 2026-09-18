import { afterEach, describe, expect, it, vi } from 'vitest';
import { bffClient } from './client';
import { presentationFixture, TEST_RESULT } from './presentationTestFixture';

function presentationWithManufacturingSubtotals() {
  const value = presentationFixture();
  const manufacturing = value.effects.find((effect) => effect.code === 'manufacturing_realized')!;
  manufacturing.drilldown.rows = [
    {
      row_id: 'manufacturing:subtotal:labor',
      label: 'A. 노무비 소계',
      unit: 'KRW',
      baseline: 20,
      comparison: 22,
      delta: 2,
      profit_effect: -2,
      note: 'display subtotal',
      section: 'manufacturing',
    },
    {
      row_id: 'manufacturing:subtotal:expense',
      label: 'B. 기타 제조경비 소계',
      unit: 'KRW',
      baseline: 30,
      comparison: 34,
      delta: 4,
      profit_effect: -4,
      note: 'display subtotal',
      section: 'manufacturing',
    },
    ...manufacturing.drilldown.rows,
  ];
  return value;
}

function json(value: unknown) {
  return Promise.resolve(new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe('manufacturing subtotal presentation integrity', () => {
  it('keeps display subtotal rows but reconciles manufacturing effect from detail rows only', async () => {
    const value = presentationWithManufacturingSubtotals();
    vi.stubGlobal('fetch', vi.fn(() => json(value)));

    const result = await bffClient.adminPresentation(TEST_RESULT);
    const manufacturing = result.effects.find((effect) => effect.code === 'manufacturing_realized')!;

    expect(manufacturing.profit_effect).toBe(-6);
    expect(manufacturing.drilldown.rows.filter((row) => row.row_id.startsWith('manufacturing:subtotal:'))).toHaveLength(2);
    expect(manufacturing.drilldown.rows
      .filter((row) => !row.row_id.startsWith('manufacturing:subtotal:'))
      .reduce((sum, row) => sum + Number(row.profit_effect ?? 0), 0)).toBe(-6);
  });

  it('still rejects a real manufacturing detail mismatch', async () => {
    const value = presentationWithManufacturingSubtotals();
    const manufacturing = value.effects.find((effect) => effect.code === 'manufacturing_realized')!;
    const detail = manufacturing.drilldown.rows.find((row) => row.row_id === 'manufacturing:1:수도광열비')!;
    detail.profit_effect = -2;
    vi.stubGlobal('fetch', vi.fn(() => json(value)));

    await expect(bffClient.adminPresentation(TEST_RESULT))
      .rejects.toThrow('서버 응답 형식이 올바르지 않습니다.');
  });
});

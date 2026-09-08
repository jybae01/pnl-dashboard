import { describe, expect, it } from 'vitest';
import {
  aggregateSgaRegisteredEntries,
  calculateAdjustmentExpectedAmount,
  calculateAdjustmentFromTargetAmount,
  calculateEntryAdjustmentFromTargetAmount,
} from './ForecastGenerationView';

describe('forecast cost total input', () => {
  it.each([
    ['increase', '1,250', '250'],
    ['decrease', '900', '-100'],
    ['unchanged', '1,000', '0'],
  ])('derives the %s adjustment from a total input', (_label, target, adjustment) => {
    expect(calculateAdjustmentFromTargetAmount(1_000, target)).toBe(adjustment);
  });

  it('keeps manufacturing expected amount as plan plus the derived adjustment', () => {
    const adjustment = calculateAdjustmentFromTargetAmount(1_000, '1,250');

    expect(calculateAdjustmentExpectedAmount(1_000, adjustment)).toBe(1_250);
  });

  it('uses total-input semantics for a selling expense entry', () => {
    expect(calculateEntryAdjustmentFromTargetAmount(1_000, '1,300', 100)).toBe('200');
  });

  it('uses total-input semantics for a general-admin entry', () => {
    expect(calculateEntryAdjustmentFromTargetAmount(1_000, '1,300', 100)).toBe('200');
  });

  it.each(['selling', 'general_admin'])('preserves other %s entries when editing one entry', (section) => {
    const adjustmentKey = `sga-${section}`;
    const editedAmount = calculateEntryAdjustmentFromTargetAmount(1_000, '1,300', 100);
    const aggregate = aggregateSgaRegisteredEntries([
      {
        id: 'other-entry',
        adjustmentKey,
        sourceLabel: '다른 조정',
        amount: '100',
        reason: '기존 조정',
      },
      {
        id: 'edited-entry',
        adjustmentKey,
        sourceLabel: '일반 조정',
        amount: editedAmount,
        reason: '수정 조정',
      },
    ]);

    expect(editedAmount).toBe('200');
    expect(aggregate.amount).toBe('300');
    expect(calculateAdjustmentExpectedAmount(1_000, aggregate.amount)).toBe(1_300);
  });
});

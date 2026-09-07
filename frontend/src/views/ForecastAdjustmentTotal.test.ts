import { describe, expect, it } from 'vitest';
import {
  calculateAdjustmentExpectedAmount,
  calculateAdjustmentFromTargetAmount,
  calculateEntryAdjustmentFromTargetAmount,
} from './ForecastGenerationView';

describe('forecast cost total input', () => {
  it('derives manufacturing adjustment from the entered actual total', () => {
    expect(calculateAdjustmentFromTargetAmount(1_000, '1,250')).toBe('250');
    expect(calculateAdjustmentExpectedAmount(1_000, '250')).toBe(1_250);
  });

  it('supports reductions below plan', () => {
    expect(calculateAdjustmentFromTargetAmount(1_000, '900')).toBe('-100');
  });

  it('derives the edited general-admin entry after preserving other registered adjustments', () => {
    expect(calculateEntryAdjustmentFromTargetAmount(1_000, '1,300', 100)).toBe('200');
  });
});

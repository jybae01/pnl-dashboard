import { describe, expect, it } from 'vitest';
import { formatNumericPresentation, parseFormattedNumericInput } from './ForecastGenerationView';

describe('forecast numeric presentation', () => {
  it('renders amount and quantity strings as whole numbers with thousands separators', () => {
    expect(formatNumericPresentation('1234.56')).toBe('1,235');
    expect(formatNumericPresentation('1234567.4')).toBe('1,234,567');
    expect(formatNumericPresentation('-150000.2')).toBe('-150,000');
    expect(formatNumericPresentation('0')).toBe('0');
  });

  it('keeps the canonical numeric value free of presentation separators', () => {
    expect(parseFormattedNumericInput('1,250,000')).toBe('1250000');
    expect(parseFormattedNumericInput('-150,000')).toBe('-150000');
  });
});

import { describe, expect, it } from 'vitest';
import { formatReportingDisplayText } from './ReportingTableControls';

describe('reporting numeric presentation', () => {
  it('renders amounts and quantities as whole numbers with thousands separators', () => {
    expect(formatReportingDisplayText('1234.56')).toBe('1,235');
    expect(formatReportingDisplayText('1234567.4')).toBe('1,234,567');
    expect(formatReportingDisplayText('-150000.2')).toBe('-150,000');
    expect(formatReportingDisplayText('+25000.49')).toBe('+25,000');
  });

  it('renders percentages and percentage points with exactly one decimal place', () => {
    expect(formatReportingDisplayText('12.34%')).toBe('12.3%');
    expect(formatReportingDisplayText('12%')).toBe('12.0%');
    expect(formatReportingDisplayText('+2.57%p')).toBe('+2.6%p');
    expect(formatReportingDisplayText('-1.04%p')).toBe('-1.0%p');
  });

  it('preserves empty and unavailable presentation values', () => {
    expect(formatReportingDisplayText('—')).toBe('—');
    expect(formatReportingDisplayText(null)).toBe('—');
  });
});

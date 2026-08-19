import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPnlReportingVisualFixture } from '../test-support/pnlReportingVisualFixture';
import type { PnlReportingReadModel, PnlReportingState } from '../types/pnlReporting';
import { PnlReportingSourceError } from '../types/pnlReporting';
import { __testOnlyAdaptPnlReportingViewerDto, pnlReportingSource } from './pnlReportingSource';

function metadata(state: PnlReportingState, report: PnlReportingReadModel | null, selectedYear = 2026, availableYears = [2026, 2025]) {
  const planExists = state === 'READY' || state === 'MISSING_ACTUAL';
  const actualExists = state === 'READY' || state === 'MISSING_PLAN';
  return {
    selectedYear,
    availableYears,
    plan: { exists: planExists, datasetId: planExists ? 'plan-id' : null, lastUpdated: planExists ? '2026-08-19T00:00:00Z' : null },
    actual: { exists: actualExists, datasetId: actualExists ? 'actual-id' : null, actualThroughMonth: actualExists ? (report?.actualThroughMonth ?? 6) : null, lastUpdated: actualExists ? '2026-08-19T01:00:00Z' : null },
    lastUpdated: planExists || actualExists ? '2026-08-19T01:00:00Z' : null,
  };
}

function reportDto(report: PnlReportingReadModel) {
  const {
    reportKey,
    year,
    templateVersion,
    actualThroughMonth,
    availableYears,
    periods,
    selectedPeriodKey,
    actualPeriodKeys,
    defaultCustomRangeKey,
    ...presentation
  } = report;
  return {
    identity: {
      reportKey,
      year,
      templateVersion,
      actualThroughMonth,
      availableYears,
      periods: periods.map((period, index) => ({
        periodKey: period.key,
        month: index + 1,
        label: period.label,
        actualAvailable: period.isActual,
      })),
      selectedPeriodKey,
      actualPeriodKeys,
      defaultCustomRangeKey,
    },
    ...presentation,
  };
}

function viewerDto(state: PnlReportingState, report: PnlReportingReadModel | null = null, selectedYear = 2026, availableYears = [2026, 2025]) {
  return {
    dtoVersion: '1',
    state: state === 'READY' ? 'DATA_READY' : 'REPORTING_GAP',
    reportingState: state,
    metadata: metadata(state, report, selectedYear, availableYears),
    report: state === 'READY' && report ? reportDto(report) : null,
  };
}

afterEach(() => vi.restoreAllMocks());

describe('real P&L Reporting viewer source', () => {
  it('bootstraps without a query year, uses credentials, omits CSRF on GET, adapts identity, and freezes the model', async () => {
    const report = createPnlReportingVisualFixture(6);
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(viewerDto('READY', report)), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));

    const result = await pnlReportingSource.load(null, new AbortController().signal);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('/api/viewer/pnl-reporting');
    expect(init).toMatchObject({ credentials: 'include', cache: 'no-store' });
    expect(new Headers(init?.headers).has('X-CSRF-Token')).toBe(false);
    expect(result).toMatchObject({ reportingState: 'READY', metadata: { selectedYear: 2026 } });
    expect((result as { report: PnlReportingReadModel }).report.periods[5]).toEqual({ key: '2026-06', label: '6월', isActual: true });
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen((result as { report: PnlReportingReadModel }).report.kpis)).toBe(true);
  });

  it.each(['MISSING_BOTH', 'MISSING_PLAN', 'MISSING_ACTUAL'] as const)('preserves %s metadata as a normal backend business state', (state) => {
    const result = __testOnlyAdaptPnlReportingViewerDto(viewerDto(state));
    expect(result.reportingState).toBe(state);
    expect(result.metadata).toMatchObject({ selectedYear: 2026, availableYears: [2026, 2025] });
    expect(result.report).toBeNull();
  });

  it('sends an explicit backend-listed year only after bootstrap', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(viewerDto('MISSING_BOTH', null, 2025, [2026, 2025])), { status: 200 }));
    await pnlReportingSource.load(2025, new AbortController().signal);
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/viewer/pnl-reporting?year=2025');
  });

  it('accepts available numeric zero with nullable zero-denominator margins and never fills them', () => {
    const report = createPnlReportingVisualFixture(6);
    const result = __testOnlyAdaptPnlReportingViewerDto(viewerDto('READY', report));
    expect(result.report?.monthlyTrends[4]).toMatchObject({
      actualAvailable: true,
      actualRevenue: 0,
      actualOperatingProfit: 0,
      actualOperatingMargin: null,
      actualOperatingMarginText: null,
    });
  });

  it('rejects state contradictions and malformed available-month amounts', () => {
    const report = createPnlReportingVisualFixture(6);
    expect(() => __testOnlyAdaptPnlReportingViewerDto({ ...viewerDto('READY', report), state: 'REPORTING_GAP' })).toThrow(PnlReportingSourceError);
    const malformed = structuredClone(viewerDto('READY', report));
    if (malformed.report) malformed.report.monthlyTrends[0].actualRevenue = null;
    expect(() => __testOnlyAdaptPnlReportingViewerDto(malformed)).toThrow(PnlReportingSourceError);
  });

  it.each([
    [403, 'FORBIDDEN', 'FORBIDDEN'],
    [409, 'INPUT_INTEGRITY_MISMATCH', 'INVALID_PAYLOAD'],
  ] as const)('maps HTTP %i %s safely', async (status, code, expected) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ error: { code, message: 'safe', field_errors: {}, correlation_id: 'cid', dto_version: '1' } }), { status }));
    await expect(pnlReportingSource.load(null, new AbortController().signal)).rejects.toMatchObject({ code: expected });
  });
});

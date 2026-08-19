import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { dirname, extname, resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { pnlReportingVisualFixture } from '../test-support/pnlReportingVisualFixture';
import { parsePnlReportingLoadResult, PnlReportingSourceError, type PnlProductSegmentSlot, type PnlReportingSource } from '../types/pnlReporting';
import { PnlStatusView } from '../views/PnlStatusView';

function source(result: unknown): PnlReportingSource {
  return { load: vi.fn().mockResolvedValue(result) };
}

function readySource(): PnlReportingSource {
  return source({ state: 'DATA_READY', report: pnlReportingVisualFixture });
}

async function renderReady(onNavigateToVariance?: () => void) {
  render(<PnlStatusView reportingSource={readySource()} initialYear={2026} onNavigateToVariance={onNavigateToVariance} />);
  await screen.findByTestId('revenue-trend-card');
}

function productionImportGraph(entry: string): string[] {
  const visited = new Set<string>();
  const visit = (file: string) => {
    if (visited.has(file)) return;
    visited.add(file);
    const sourceText = readFileSync(file, 'utf8');
    for (const match of sourceText.matchAll(/from\s+['"](\.[^'"]+)['"]/g)) {
      const base = resolve(dirname(file), match[1]);
      const candidates = extname(base) ? [base] : [`${base}.ts`, `${base}.tsx`];
      const target = candidates.find((candidate) => {
        try { readFileSync(candidate); return true; } catch { return false; }
      });
      if (target) visit(target);
    }
  };
  visit(entry);
  return [...visited];
}

afterEach(() => vi.restoreAllMocks());

describe('P&L Status exact visual skeleton port', () => {
  it('renders three exact KPIs and two vertically ordered Mockup trend cards', async () => {
    await renderReady();
    const kpis = [...document.querySelectorAll('[data-kpi-key]')];
    expect(kpis).toHaveLength(3);
    expect(kpis.map((node) => node.getAttribute('data-kpi-key'))).toEqual(['revenue', 'operating_profit', 'adjusted_operating_profit']);
    expect(kpis.map((node) => node.querySelector('.pnl-report__kpi-label')?.textContent)).toEqual(['매출액', '영업이익', '조정 영업이익']);

    const trends = document.querySelector('.pnl-report__trends');
    expect(trends?.children).toHaveLength(2);
    expect(trends?.children[0]).toHaveAttribute('data-testid', 'revenue-trend-card');
    expect(trends?.children[1]).toHaveAttribute('data-testid', 'profit-trend-card');
    const revenueChart = within(screen.getByTestId('revenue-trend-card')).getByRole('img');
    const profitChart = within(screen.getByTestId('profit-trend-card')).getByRole('img');
    const months = Array.from({ length: 12 }, (_, index) => `${index + 1}월`);
    expect(revenueChart).toHaveAttribute('viewBox', '0 0 920 195');
    expect(profitChart).toHaveAttribute('viewBox', '0 0 920 275');
    expect([...revenueChart.querySelectorAll('[data-axis-label="month"]')].map((node) => node.textContent)).toEqual(months);
    expect([...profitChart.querySelectorAll('[data-axis-label="month"]')].map((node) => node.textContent)).toEqual(months);
  });

  it('renders annual PLAN, available ACTUAL only, fixed grouped slots, and a margin line ending at June', async () => {
    await renderReady();
    const revenue = screen.getByTestId('revenue-trend-card');
    const profit = screen.getByTestId('profit-trend-card');
    expect(revenue.querySelectorAll('rect[data-series="plan"]')).toHaveLength(12);
    expect(revenue.querySelectorAll('rect[data-series="actual"]')).toHaveLength(6);
    expect(profit.querySelectorAll('rect[data-series="plan"]')).toHaveLength(12);
    expect(profit.querySelectorAll('rect[data-series="actual"]')).toHaveLength(6);
    expect(profit.querySelectorAll('g[data-actual-available="false"] rect[data-series="actual"]')).toHaveLength(0);
    expect(profit.querySelector('path[data-series="actual-margin"]')).toHaveAttribute('data-last-period-key', '2026-06');
    expect(profit.querySelectorAll('circle[data-series="actual-margin-point"]')).toHaveLength(6);
    expect(profit.querySelector('g[data-period-key="2026-05"] rect[data-series="actual"]')).toHaveAttribute('height', '2');
    expect(profit.querySelector('circle[data-series="actual-margin-point"][data-period-key="2026-05"]')).toBeInTheDocument();
    expect(profit.querySelector('circle[data-series="actual-margin-point"][data-period-key="2026-06"]')).toBeInTheDocument();
    expect(profit.querySelector('circle[data-series="actual-margin-point"][data-period-key="2026-07"]')).not.toBeInTheDocument();

    const mayRevenue = revenue.querySelector('g[data-period-key="2026-05"]');
    const julyRevenue = revenue.querySelector('g[data-period-key="2026-07"]');
    expect(mayRevenue).toHaveAttribute('data-actual-available', 'true');
    expect(mayRevenue?.querySelector('rect[data-series="actual"]')).toBeInTheDocument();
    expect(mayRevenue?.querySelector('rect[data-series="actual"]')).toHaveAttribute('height', '2');
    expect(julyRevenue).toHaveAttribute('data-actual-available', 'false');
    expect(julyRevenue?.querySelector('rect[data-series="plan"]')).toBeInTheDocument();
    expect(julyRevenue?.querySelector('rect[data-series="actual"]')).not.toBeInTheDocument();
    const julyPlan = julyRevenue?.querySelector('rect[data-series="plan"]');
    const julyLabel = julyRevenue?.querySelector('[data-axis-label="month"]');
    const julyPlanCenter = Number(julyPlan?.getAttribute('x')) + Number(julyPlan?.getAttribute('width')) / 2;
    expect(julyPlanCenter).toBeLessThan(Number(julyLabel?.getAttribute('x')));

    expect(within(profit).getAllByRole('button').map((button) => button.textContent)).toEqual(['영업이익', '조정 영업이익', '월별 데이터표']);
    fireEvent.click(within(profit).getByRole('button', { name: '조정 영업이익' }));
    expect(profit.querySelectorAll('rect[data-series="plan"]')).toHaveLength(12);
    expect(profit.querySelectorAll('rect[data-series="actual"]')).toHaveLength(6);
    expect(profit.querySelectorAll('circle[data-series="actual-margin-point"]')).toHaveLength(6);
    expect(profit.querySelector('g[data-period-key="2026-05"] rect[data-series="actual"]')).toHaveAttribute('height', '2');
    expect(profit.querySelector('circle[data-series="actual-margin-point"][data-period-key="2026-05"]')).toBeInTheDocument();
    expect(profit.querySelector('path[data-series="actual-margin"]')).toHaveAttribute('data-last-period-key', '2026-06');

    fireEvent.click(within(profit).getByRole('button', { name: '월별 데이터표' }));
    const monthlyTable = profit.querySelector('.pnl-report__monthly-table');
    expect(monthlyTable).toHaveAttribute('data-column-count', '13');
    expect([...monthlyTable!.querySelectorAll('thead th')].map((cell) => cell.textContent)).toEqual(['손익 지표', ...Array.from({ length: 12 }, (_, index) => `${index + 1}월`)]);
    expect([...profit.querySelectorAll('[data-tone]')].map((row) => row.getAttribute('data-tone'))).toEqual([
      'revenue-plan', 'revenue-actual', 'operating-plan', 'operating-actual', 'operating-margin', 'adjusted-plan', 'adjusted-actual', 'adjusted-margin',
    ]);
    const revenueActualCells = [...profit.querySelectorAll('tr[data-tone="revenue-actual"] td')].map((cell) => cell.textContent);
    expect(revenueActualCells[5]).toBe('0');
    expect(revenueActualCells.slice(7)).toEqual(['—', '—', '—', '—', '—', '—']);
    for (const tone of ['operating-actual', 'operating-margin', 'adjusted-actual', 'adjusted-margin']) {
      const cells = [...profit.querySelectorAll(`tr[data-tone="${tone}"] td`)].map((cell) => cell.textContent);
      expect(cells.slice(7)).toEqual(['—', '—', '—', '—', '—', '—']);
    }
  });

  it('requires a unique sequential ACTUAL availability prefix while accepting an available zero', () => {
    const ready = { state: 'DATA_READY', report: pnlReportingVisualFixture };
    expect(parsePnlReportingLoadResult(ready)?.state).toBe('DATA_READY');

    const duplicateActualKeys = {
      ...ready,
      report: { ...pnlReportingVisualFixture, actualPeriodKeys: Array(6).fill('2026-01') },
    };
    expect(parsePnlReportingLoadResult(duplicateActualKeys)).toBeNull();

    const nonPrefixActualKeys = {
      ...ready,
      report: { ...pnlReportingVisualFixture, actualPeriodKeys: pnlReportingVisualFixture.periods.slice(6).map((period) => period.key) },
    };
    expect(parsePnlReportingLoadResult(nonPrefixActualKeys)).toBeNull();

    const availableWithMissingCoreValue = {
      ...ready,
      report: {
        ...pnlReportingVisualFixture,
        monthlyTrends: pnlReportingVisualFixture.monthlyTrends.map((trend) => trend.periodKey === '2026-06'
          ? { ...trend, actualOperatingProfit: null, actualOperatingProfitText: null }
          : trend),
      },
    };
    expect(parsePnlReportingLoadResult(availableWithMissingCoreValue)).toBeNull();
    expect(pnlReportingVisualFixture.monthlyTrends[4]).toMatchObject({ actualAvailable: true, actualRevenue: 0, actualOperatingProfit: 0 });

    const aprilCutoff = {
      ...ready,
      report: {
        ...pnlReportingVisualFixture,
        selectedPeriodKey: '2026-04',
        actualPeriodKeys: pnlReportingVisualFixture.actualPeriodKeys.slice(0, 4),
        periods: pnlReportingVisualFixture.periods.map((period, index) => ({ ...period, isActual: index < 4 })),
        monthlyTrends: pnlReportingVisualFixture.monthlyTrends.map((trend, index) => index < 4 ? trend : {
          ...trend,
          actualAvailable: false,
          actualRevenue: null,
          actualRevenueText: null,
          actualOperatingProfit: null,
          actualOperatingProfitText: null,
          actualOperatingMargin: null,
          actualOperatingMarginText: null,
          actualAdjustedOperatingProfit: null,
          actualAdjustedOperatingProfitText: null,
          actualAdjustedOperatingMargin: null,
          actualAdjustedOperatingMarginText: null,
        }),
      },
    };
    expect(parsePnlReportingLoadResult(aprilCutoff)?.state).toBe('DATA_READY');
  });

  it('keeps the exact four-tab order, default tab, table shells, and Analysis callback', async () => {
    const onNavigate = vi.fn();
    await renderReady(onNavigate);
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual(['1. 손익계산서 (P&L)', '2. 제품/반제품 매출원가 내역', '3. 판매관리비 내역', '4. Item별 구분손익']);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('pnl-table-shell')).toBeInTheDocument();
    fireEvent.click(tabs[1]);
    expect(screen.getByTestId('cogs-table-shell')).toBeInTheDocument();
    fireEvent.click(tabs[2]);
    expect(screen.getByTestId('sga-table-shell')).toBeInTheDocument();
    fireEvent.click(tabs[3]);
    expect(screen.getByTestId('product-table-shell')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /손익 요인 Waterfall 분석 바로가기/ }));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it('matches exact table column counts for every supported mode', async () => {
    await renderReady();
    const pnl = screen.getByTestId('pnl-table-shell');
    expect(pnl.querySelector('table')).toHaveAttribute('data-column-count', '10');
    expect(within(pnl).getByText('월 선택:')).toBeInTheDocument();
    expect(within(pnl).getByRole('button', { name: '6월(당월)' })).toBeInTheDocument();
    fireEvent.click(within(pnl).getByRole('button', { name: '실적만 보기' }));
    expect(pnl.querySelector('table')).toHaveAttribute('data-column-count', '9');
    expect(within(pnl).queryByText('월 선택:')).not.toBeInTheDocument();
    fireEvent.click(within(pnl).getByRole('button', { name: '기간 설정 비교' }));
    expect(pnl.querySelector('table')).toHaveAttribute('data-column-count', '6');

    fireEvent.click(screen.getAllByRole('tab')[1]);
    expect(screen.getByTestId('cogs-table-shell').querySelector('table')).toHaveAttribute('data-column-count', '15');

    fireEvent.click(screen.getAllByRole('tab')[2]);
    const sga = screen.getByTestId('sga-table-shell');
    expect(sga.querySelector('table')).toHaveAttribute('data-column-count', '10');
    fireEvent.click(within(sga).getByRole('button', { name: '실적만 보기' }));
    expect(sga.querySelector('table')).toHaveAttribute('data-column-count', '9');
    fireEvent.click(within(sga).getByRole('button', { name: '기간 설정 비교' }));
    expect(sga.querySelector('table')).toHaveAttribute('data-column-count', '6');

    fireEvent.click(screen.getAllByRole('tab')[3]);
    const product = screen.getByTestId('product-table-shell');
    expect(product.querySelector('table')).toHaveAttribute('data-column-count', '10');
    fireEvent.click(within(product).getByRole('button', { name: '실적만 보기' }));
    expect(product.querySelector('table')).toHaveAttribute('data-column-count', '9');
    fireEvent.click(within(product).getByRole('button', { name: '기간 설정 비교' }));
    expect(product.querySelector('table')).toHaveAttribute('data-column-count', '5');
  });

  it('uses the exact Mockup selector while preserving stable PCS, 4-inch LC, and future LENGTH/m slots', async () => {
    await renderReady();
    fireEvent.click(screen.getAllByRole('tab')[3]);
    const selectors = [...screen.getByTestId('product-table-shell').querySelectorAll('[data-unit]')];
    expect(selectors.map((node) => [node.textContent, node.getAttribute('data-unit'), node.getAttribute('data-dimension')])).toEqual([
      ['8인치 SW', 'PCS', '8-inch'],
      ['8인치 BW', 'PCS', '8-inch'],
      ['4인치 LC', 'PCS', '4-inch'],
      ['신사업', 'PCS', 'item'],
    ]);
    const fsSlot: PnlProductSegmentSlot = { key: 'FS', label: 'FS', businessUnit: 'm', dimensionLabel: 'LENGTH', rows: [] };
    expect([fsSlot.key, fsSlot.businessUnit, fsSlot.dimensionLabel]).toEqual(['FS', 'm', 'LENGTH']);
    expect(screen.queryByText(/통합 수량 합계|mixed-unit/i)).not.toBeInTheDocument();
  });

  it('keeps Mockup fixture row hierarchy counts isolated to DATA_READY rendering', () => {
    expect(pnlReportingVisualFixture.periods.map((period) => period.label)).toEqual(Array.from({ length: 12 }, (_, index) => `${index + 1}월`));
    expect(pnlReportingVisualFixture.periods.map((period) => period.isActual)).toEqual([true, true, true, true, true, true, false, false, false, false, false, false]);
    expect(pnlReportingVisualFixture.monthlyTrends.map((trend) => trend.actualAvailable)).toEqual([true, true, true, true, true, true, false, false, false, false, false, false]);
    expect(pnlReportingVisualFixture.monthlyTrends[4].actualRevenue).toBe(0);
    expect(pnlReportingVisualFixture.monthlyTrends[6].actualRevenue).toBeNull();
    expect(pnlReportingVisualFixture.pnlRows).toHaveLength(25);
    expect(pnlReportingVisualFixture.pnlRows.filter((row) => !row.parentKey).map((row) => row.label)).toEqual([
      'Ⅰ. 매출액', 'Ⅱ. 매출수량', 'Ⅲ. 매출원가', '매출원가율', 'Ⅳ. 매출총이익', '매출총이익률', 'Ⅴ. 판매비와 관리비', 'Ⅵ. 영업이익', '영업이익률', 'Ⅶ. 조정 영업이익', '조정 영업이익률',
    ]);
    expect(pnlReportingVisualFixture.pnlRows.find((row) => row.key === 'sales_volume')?.compareByPeriod['2026-06'].every((value) => value.text === '—')).toBe(true);
    expect(pnlReportingVisualFixture.sgaRows.filter((row) => !row.parentKey)).toHaveLength(16);
    expect(pnlReportingVisualFixture.sgaRows.filter((row) => row.parentKey)).toHaveLength(7);
    expect(pnlReportingVisualFixture.sgaRows.filter((row) => row.parentKey).every((row) => row.category === '세부항목')).toBe(true);
    expect(pnlReportingVisualFixture.sgaRows.filter((row) => !row.parentKey).map((row) => row.label)).toEqual([
      '일반관리비 소계', '1. 인건비', '2. 감가상각비', '3. 경상개발비', '4. 수수료', '5. 기타', '판매비 소계', '1. 운반비', '2. 수수료', '3. 브랜드사용료', '4. 인건비', '5. 견본비', '6. 대손상각', '7. 잡비', '8. 기타', '판관비 총계',
    ]);
    expect(pnlReportingVisualFixture.productSegments.map((segment) => segment.rows.length)).toEqual([10, 10, 10, 8]);
  });

  it('keeps REPORTING_GAP, EMPTY, ERROR, FORBIDDEN, INVALID_PAYLOAD, and LOADING distinct', async () => {
    const loadingSource: PnlReportingSource = { load: vi.fn(() => new Promise(() => undefined)) };
    const loading = render(<PnlStatusView initialYear={2026} reportingSource={loadingSource} />);
    expect(screen.getByText('손익 현황을 불러오는 중…').closest('[role="status"]')).toBeInTheDocument();
    loading.unmount();

    const gap = render(<PnlStatusView initialYear={2026} />);
    expect(await screen.findByText('손익현황 데이터가 아직 등록되지 않았습니다.')).toBeInTheDocument();
    gap.unmount();

    const empty = render(<PnlStatusView initialYear={2026} reportingSource={source({ state: 'EMPTY' })} />);
    expect(await screen.findByText('선택한 조건의 손익 데이터가 없습니다.')).toBeInTheDocument();
    empty.unmount();

    const failedSource: PnlReportingSource = { load: vi.fn().mockRejectedValue(new Error('failed')) };
    const error = render(<PnlStatusView initialYear={2026} reportingSource={failedSource} />);
    expect(await screen.findByText('손익 현황을 불러오지 못했습니다.')).toBeInTheDocument();
    error.unmount();

    const forbiddenSource: PnlReportingSource = { load: vi.fn().mockRejectedValue(new PnlReportingSourceError('FORBIDDEN', 'forbidden')) };
    const forbidden = render(<PnlStatusView initialYear={2026} reportingSource={forbiddenSource} />);
    expect(await screen.findByText('손익 현황을 조회할 권한이 없습니다.')).toBeInTheDocument();
    forbidden.unmount();

    render(<PnlStatusView initialYear={2026} reportingSource={source({ broken: true })} />);
    expect(await screen.findByText('손익 현황 데이터 형식을 확인할 수 없습니다.')).toBeInTheDocument();
  });

  it('aborts an earlier request and ignores stale results', async () => {
    const resolvers: Array<(value: unknown) => void> = [];
    const signals: AbortSignal[] = [];
    const reportingSource: PnlReportingSource = { load: vi.fn((_year, signal) => {
      signals.push(signal);
      return new Promise((resolvePromise) => resolvers.push(resolvePromise));
    }) };
    render(<PnlStatusView initialYear={2026} reportingSource={reportingSource} />);
    await waitFor(() => expect(resolvers).toHaveLength(1));
    fireEvent.click(screen.getByRole('button', { name: '손익 현황 새로고침' }));
    await waitFor(() => expect(resolvers).toHaveLength(2));
    expect(signals[0].aborted).toBe(true);
    resolvers[0]({ state: 'EMPTY' });
    resolvers[1]({ state: 'DATA_READY', report: pnlReportingVisualFixture });
    expect(await screen.findByTestId('revenue-trend-card')).toBeInTheDocument();
    expect(screen.queryByText('선택한 조건의 손익 데이터가 없습니다.')).not.toBeInTheDocument();
  });

  it('isolates fixtures and removes legacy runtime dependencies and business formulas from the production import graph', () => {
    const entry = resolve(process.cwd(), 'src/views/PnlStatusView.tsx');
    const graph = productionImportGraph(entry);
    const sourceText = graph.map((file) => readFileSync(file, 'utf8')).join('\n');
    expect(graph.some((file) => file.includes('test-support') || file.includes('__tests__') || file.includes('fixtures'))).toBe(false);
    expect(sourceText).not.toMatch(/MockPnlService|dummyPnlData|dummyPnl|pnlService/);
    expect(sourceText).not.toContain('/api/viewer/pnl-dashboard');
    expect(sourceText).not.toContain('PnlDashboardPanel');
    expect(sourceText).not.toMatch(/inventory_timing|key_facts|baseline_model_name|comparison_model_name/);
    expect(sourceText).not.toMatch(/\.reduce\s*\(/);
    expect(sourceText).not.toMatch(/actual\s*[-/]\s*plan|operatingProfit\s*\/\s*revenue|grossProfit\s*\/\s*revenue/i);
  });

  it('locks the audited Mockup CSS metrics and excludes the old two-column trend grid', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/styles/pnl-dashboard.css'), 'utf8');
    expect(css).toContain('grid-template-columns: repeat(3, 1fr)');
    expect(css).toContain('gap: 16px');
    expect(css).toContain('min-height: 118px');
    expect(css).toContain('padding: 16px 20px');
    expect(css).toContain('gap: 14px');
    expect(css).toContain('padding: 14px 18px');
    expect(css).toContain('padding: 18px 20px 36px');
    expect(css).toContain('height: 40px');
    expect(css).toContain('height: 36px');
    expect(css).toContain('height: 42px');
    expect(css).toContain('height: 44px');
    expect(css).toContain('padding-left: 32px');
    expect(css).toContain('padding-left: 48px');
    expect(css).toMatch(/pnl-report__filter-item \{ gap: 7px; \}/);
    expect(css).toMatch(/pnl-report__filter-label \{[^}]*font-size: 13px/);
    expect(css).toMatch(/pnl-report__financial-table th \{ position: sticky; top: 0; z-index: 10;/);
    expect(css).not.toMatch(/pnl-report__trends[^}]*grid-template-columns/s);
  });
});

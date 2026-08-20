import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { dirname, extname, resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPnlReportingVisualFixture, pnlReportingVisualFixture } from '../test-support/pnlReportingVisualFixture';
import { parsePnlReportingLoadResult, PnlReportingSourceError, type PnlReportingReadModel, type PnlReportingSource, type PnlReportingState, type PnlStatementRowSlot } from '../types/pnlReporting';
import { PnlStatusView } from '../views/PnlStatusView';

function source(result: unknown): PnlReportingSource {
  return { load: vi.fn().mockResolvedValue(result) };
}

function reportingResult(state: PnlReportingState, report: PnlReportingReadModel | null = null, selectedYear = 2026, availableYears = [2026, 2025]) {
  const planExists = state === 'READY' || state === 'MISSING_ACTUAL';
  const actualExists = state === 'READY' || state === 'MISSING_PLAN';
  return {
    reportingState: state,
    metadata: {
      selectedYear,
      availableYears,
      plan: { exists: planExists, datasetId: planExists ? 'plan-id' : null, lastUpdated: planExists ? '2026-08-19T00:00:00Z' : null },
      actual: { exists: actualExists, datasetId: actualExists ? 'actual-id' : null, actualThroughMonth: actualExists ? (report?.actualThroughMonth ?? 6) : null, lastUpdated: actualExists ? '2026-08-19T01:00:00Z' : null },
      lastUpdated: planExists || actualExists ? '2026-08-19T01:00:00Z' : null,
    },
    report: state === 'READY' ? report : null,
  };
}

function readySource(report: PnlReportingReadModel = pnlReportingVisualFixture): PnlReportingSource {
  return source(reportingResult('READY', report, report.year, report.availableYears));
}

function reportingRowForYear<T extends PnlStatementRowSlot>(row: T, year: number): T {
  return {
    ...row,
    compareByPeriod: Object.fromEntries(Object.entries(row.compareByPeriod).map(([key, cells]) => [
      key.replace(/^\d{4}/, String(year)),
      cells,
    ])),
  } as T;
}

async function renderReady(onNavigateToVariance?: () => void, report: PnlReportingReadModel = pnlReportingVisualFixture) {
  const result = render(<PnlStatusView reportingSource={readySource(report)} initialYear={2026} onNavigateToVariance={onNavigateToVariance} />);
  await screen.findByTestId('revenue-trend-card');
  return result;
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
    expect(kpis.every((node) => node.querySelector('.pnl-report__kpi-unit')?.textContent === '백만원')).toBe(true);
    expect(kpis[0]).toHaveTextContent('진도율 61.8% | 계획 대비 달성률 104.5%');

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
    expect([...revenueChart.querySelectorAll('[data-axis-label="amount"]')].map((node) => node.textContent)).toEqual(['0', '5,000', '11,000', '16,000']);
    expect([...profitChart.querySelectorAll('[data-axis-label="amount"]')].map((node) => node.textContent)).toEqual(['0', '500', '1,000', '1,600']);
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
    expect(profit.querySelectorAll('circle[data-series="actual-margin-point"]')).toHaveLength(5);
    expect(profit.querySelector('g[data-period-key="2026-05"] rect[data-series="actual"]')).toHaveAttribute('height', '2');
    expect(profit.querySelector('circle[data-series="actual-margin-point"][data-period-key="2026-05"]')).not.toBeInTheDocument();
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
    expect(profit.querySelectorAll('circle[data-series="actual-margin-point"]')).toHaveLength(5);
    expect(profit.querySelector('g[data-period-key="2026-05"] rect[data-series="actual"]')).toHaveAttribute('height', '2');
    expect(profit.querySelector('circle[data-series="actual-margin-point"][data-period-key="2026-05"]')).not.toBeInTheDocument();
    expect(profit.querySelector('path[data-series="actual-margin"]')).toHaveAttribute('data-last-period-key', '2026-06');

    fireEvent.click(within(profit).getByRole('button', { name: '월별 데이터표' }));
    const monthlyTable = profit.querySelector('.pnl-report__monthly-table');
    expect(monthlyTable).toHaveAttribute('data-column-count', '13');
    expect([...monthlyTable!.querySelectorAll('thead th')].map((cell) => cell.textContent)).toEqual(['손익 지표', ...Array.from({ length: 12 }, (_, index) => `${index + 1}월`)]);
    expect([...profit.querySelectorAll('[data-tone]')].map((row) => row.getAttribute('data-tone'))).toEqual([
      'revenue-plan', 'revenue-actual', 'operating-plan', 'operating-actual', 'operating-margin', 'adjusted-plan', 'adjusted-actual', 'adjusted-margin',
    ]);
    expect([...profit.querySelectorAll('[data-row-key]')].map((row) => row.getAttribute('data-row-key'))).toEqual([
      'revenue_plan', 'revenue_actual', 'operating_plan', 'operating_actual', 'operating_margin', 'adjusted_plan', 'adjusted_actual', 'adjusted_margin',
    ]);
    expect([...profit.querySelectorAll('[data-row-key] td:first-child')].map((cell) => cell.textContent)).toEqual([
      '매출액 계획', '매출액 실적', '영업이익 계획', '영업이익 실적', '영업이익률', '조정 영업이익 계획', '조정 영업이익 실적', '조정 영업이익률',
    ]);
    expect(profit.querySelector('tr[data-tone="operating-margin"] td:nth-child(2)')).toHaveTextContent('140.0%');
    expect(profit.querySelector('tr[data-tone="adjusted-margin"] td:nth-child(2)')).toHaveTextContent('170.0%');
    const revenueActualCells = [...profit.querySelectorAll('tr[data-tone="revenue-actual"] td')].map((cell) => cell.textContent);
    expect(revenueActualCells[5]).toBe('0');
    expect(revenueActualCells.slice(7)).toEqual(['—', '—', '—', '—', '—', '—']);
    for (const tone of ['operating-actual', 'operating-margin', 'adjusted-actual', 'adjusted-margin']) {
      const cells = [...profit.querySelectorAll(`tr[data-tone="${tone}"] td`)].map((cell) => cell.textContent);
      expect(cells.slice(7)).toEqual(['—', '—', '—', '—', '—', '—']);
    }
  });

  it('requires a unique sequential ACTUAL availability prefix while accepting an available zero', () => {
    const ready = reportingResult('READY', pnlReportingVisualFixture);
    expect(parsePnlReportingLoadResult(ready)?.reportingState).toBe('READY');

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
    expect(pnlReportingVisualFixture.monthlyTrends[4]).toMatchObject({ actualAvailable: true, actualRevenue: 0, actualOperatingProfit: 0, actualOperatingMargin: null });

    const aprilReport = createPnlReportingVisualFixture(4);
    const aprilCutoff = reportingResult('READY', aprilReport, aprilReport.year, aprilReport.availableYears);
    expect(parsePnlReportingLoadResult(aprilCutoff)?.reportingState).toBe('READY');
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
    expect([...pnl.querySelectorAll('tr[data-row-key="cogs_ratio"] td')].map((cell) => cell.textContent)).toEqual([
      '매출원가율', '%', '80.7%', '78.8%', '-1.9%p', '-1.9%p', '80.6%', '79.7%', '-0.9%p', '-0.9%p',
    ]);
    fireEvent.click(within(pnl).getByRole('button', { name: '실적만 보기' }));
    expect(pnl.querySelector('table')).toHaveAttribute('data-column-count', '9');
    expect(within(pnl).queryByText('월 선택:')).not.toBeInTheDocument();
    fireEvent.click(within(pnl).getByRole('button', { name: '기간 설정 비교' }));
    expect(pnl.querySelector('table')).toHaveAttribute('data-column-count', '6');

    fireEvent.click(screen.getAllByRole('tab')[1]);
    const cogs = screen.getByTestId('cogs-table-shell');
    expect(cogs.querySelector('table')).toHaveAttribute('data-column-count', '15');
    expect(cogs.querySelector('.pnl-report__table-toolbar > .pnl-report__table-unit--toolbar')).toHaveTextContent('(단위: 백만원, %)');
    expect(cogs.querySelector('.pnl-report__table-wrap > .pnl-report__table-unit')).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('tab')[2]);
    const sga = screen.getByTestId('sga-table-shell');
    expect(sga.querySelector('table')).toHaveAttribute('data-column-count', '9');
    fireEvent.click(within(sga).getByRole('button', { name: '실적만 보기' }));
    expect(sga.querySelector('table')).toHaveAttribute('data-column-count', '8');
    fireEvent.click(within(sga).getByRole('button', { name: '기간 설정 비교' }));
    expect(sga.querySelector('table')).toHaveAttribute('data-column-count', '5');

    fireEvent.click(screen.getAllByRole('tab')[3]);
    const product = screen.getByTestId('product-table-shell');
    expect(product.querySelector('table')).toHaveAttribute('data-column-count', '10');
    fireEvent.click(within(product).getByRole('button', { name: '실적만 보기' }));
    expect(product.querySelector('table')).toHaveAttribute('data-column-count', '9');
    fireEvent.click(within(product).getByRole('button', { name: '기간 설정 비교' }));
    expect(product.querySelector('table')).toHaveAttribute('data-column-count', '5');
  });

  it.each([1, 6, 12])('renders COGS and all actual-only tables through month %i plus backend-provided YTD', async (actualThroughMonth) => {
    const report = createPnlReportingVisualFixture(actualThroughMonth);
    expect(parsePnlReportingLoadResult(reportingResult('READY', report, report.year, report.availableYears))?.reportingState).toBe('READY');
    const rendered = await renderReady(undefined, report);

    const pnl = screen.getByTestId('pnl-table-shell');
    expect(within(pnl).getByText(`${actualThroughMonth}월 당월 실적 비교`)).toBeInTheDocument();
    expect(within(pnl).getByRole('button', { name: `${actualThroughMonth}월(당월)` })).toBeInTheDocument();
    if (actualThroughMonth === 12) {
      fireEvent.click(within(pnl).getByRole('button', { name: '6월' }));
      expect(within(pnl).getByText('6월 실적 비교')).toBeInTheDocument();
      expect(within(pnl).queryByText('6월 당월 실적 비교')).not.toBeInTheDocument();
    }
    fireEvent.click(within(pnl).getByRole('button', { name: '실적만 보기' }));
    expect(pnl.querySelector('table')).toHaveAttribute('data-column-count', String(actualThroughMonth + 3));
    expect(pnl.querySelector('tr[data-row-key="revenue"]')?.querySelectorAll('td')).toHaveLength(actualThroughMonth + 3);
    if (actualThroughMonth >= 5) {
      expect(pnl.querySelector('tr[data-row-key="revenue"]')?.querySelectorAll('td')[6]).toHaveTextContent('0');
    }
    fireEvent.click(within(pnl).getByRole('button', { name: '기간 설정 비교' }));
    expect(within(pnl).getByRole('combobox', { name: '시작월' })).toHaveValue('1월');
    expect(within(pnl).getByRole('combobox', { name: '종료월' })).toHaveValue(`${actualThroughMonth}월`);

    fireEvent.click(screen.getAllByRole('tab')[1]);
    const cogs = screen.getByTestId('cogs-table-shell');
    expect(cogs.querySelector('table')).toHaveAttribute('data-column-count', String(actualThroughMonth * 2 + 3));
    expect(cogs.querySelector('tr[data-row-key="mfg_material"]')?.querySelectorAll('td')).toHaveLength(actualThroughMonth * 2 + 3);
    expect(within(cogs).getByText(`${actualThroughMonth}월`)).toBeInTheDocument();
    if (actualThroughMonth < 12) expect(within(cogs).queryByText(`${actualThroughMonth + 1}월`)).not.toBeInTheDocument();
    if (actualThroughMonth === 12) {
      for (const month of ['7월', '8월', '9월', '10월', '11월', '12월']) expect(within(cogs).getByText(month)).toBeInTheDocument();
    }

    fireEvent.click(screen.getAllByRole('tab')[2]);
    const sga = screen.getByTestId('sga-table-shell');
    expect(within(sga).getByText(`${actualThroughMonth}월 당월 실적 비교`)).toBeInTheDocument();
    expect(within(sga).getByRole('button', { name: `${actualThroughMonth}월(당월)` })).toBeInTheDocument();
    if (actualThroughMonth === 12) {
      fireEvent.click(within(sga).getByRole('button', { name: '6월' }));
      expect(within(sga).getByText('6월 실적 비교')).toBeInTheDocument();
      expect(within(sga).queryByText('6월 당월 실적 비교')).not.toBeInTheDocument();
    }
    fireEvent.click(within(sga).getByRole('button', { name: '실적만 보기' }));
    expect(sga.querySelector('table')).toHaveAttribute('data-column-count', String(actualThroughMonth + 2));
    expect(sga.querySelector('tr[data-row-key="admin"]')?.querySelectorAll('td')).toHaveLength(actualThroughMonth + 2);

    fireEvent.click(screen.getAllByRole('tab')[3]);
    const product = screen.getByTestId('product-table-shell');
    expect(within(product).getByText(`${actualThroughMonth}월 당월 실적 비교`)).toBeInTheDocument();
    expect(within(product).getByRole('button', { name: `${actualThroughMonth}월(당월)` })).toBeInTheDocument();
    if (actualThroughMonth === 12) {
      fireEvent.click(within(product).getByRole('button', { name: '6월' }));
      expect(within(product).getByText('6월 실적 비교')).toBeInTheDocument();
      expect(within(product).queryByText('6월 당월 실적 비교')).not.toBeInTheDocument();
    }
    fireEvent.click(within(product).getByRole('button', { name: '실적만 보기' }));
    expect(product.querySelector('table')).toHaveAttribute('data-column-count', String(actualThroughMonth + 3));
    expect(product.querySelector('tr[data-row-key="SW_revenue"]')?.querySelectorAll('td')).toHaveLength(actualThroughMonth + 3);
    rendered.unmount();
  });

  it('keeps SGA groups open, hides other-detail controls, and removes only the category column', async () => {
    const fullYearReport = createPnlReportingVisualFixture(12);
    const report = {
      ...fullYearReport,
      sgaRows: fullYearReport.sgaRows.map((row) => {
        if (row.key === 'admin' || row.key === 'sales') return { ...row, collapsible: true };
        if (row.level !== 1) return row;
        return {
          ...row,
          parentKey: row.category === '일반관리비' ? 'admin' : row.category === '판매비' ? 'sales' : row.parentKey,
        };
      }),
    };
    expect(parsePnlReportingLoadResult(reportingResult('READY', report, report.year, report.availableYears))?.reportingState).toBe('READY');
    await renderReady(undefined, report);
    fireEvent.click(screen.getAllByRole('tab')[2]);

    const sga = screen.getByTestId('sga-table-shell');
    const table = sga.querySelector('table');
    const rowByKey = (key: string) => sga.querySelector<HTMLTableRowElement>(`tr[data-row-key="${key}"]`);
    const cellTexts = (row: HTMLTableRowElement) => [...row.querySelectorAll('td')].map((cell) => cell.textContent);
    const admin = rowByKey('admin');
    const sales = rowByKey('sales');
    expect(admin).toHaveTextContent('일반관리비 소계');
    expect(sales).toHaveTextContent('판매비 소계');
    expect(within(admin!).queryByRole('button')).not.toBeInTheDocument();
    expect(within(sales!).queryByRole('button')).not.toBeInTheDocument();
    for (const key of ['admin_labor', 'admin_depr', 'admin_rnd', 'admin_fee', 'admin_other']) expect(rowByKey(key)).toBeInTheDocument();
    for (const key of ['sales_freight', 'sales_commission', 'sales_brand', 'sales_labor', 'sales_sample', 'sales_bad_debt', 'sales_sundry', 'sales_other']) expect(rowByKey(key)).toBeInTheDocument();

    const adminOther = rowByKey('admin_other');
    const salesOther = rowByKey('sales_other');
    expect(adminOther).toHaveTextContent('5. 기타');
    expect(salesOther).toHaveTextContent('8. 기타');
    expect(within(adminOther!).queryByRole('button')).not.toBeInTheDocument();
    expect(within(salesOther!).queryByRole('button')).not.toBeInTheDocument();
    expect(report.sgaRows.find((row) => row.key === 'admin_other')).toMatchObject({ parentKey: 'admin', collapsible: true });
    expect(report.sgaRows.find((row) => row.key === 'sales_other')).toMatchObject({ parentKey: 'sales', collapsible: true });
    expect(report.sgaRows.filter((row) => row.parentKey === 'admin_other')).toHaveLength(4);
    expect(report.sgaRows.filter((row) => row.parentKey === 'sales_other')).toHaveLength(3);
    expect(rowByKey('admin_other_1')).not.toBeInTheDocument();
    expect(rowByKey('sales_other_1')).not.toBeInTheDocument();

    expect(within(sga).getByRole('columnheader', { name: '판관비 항목' })).toBeInTheDocument();
    expect(within(sga).queryByRole('columnheader', { name: '구분' })).not.toBeInTheDocument();
    expect(sga.querySelectorAll('tbody td.pnl-report__unit-cell')).toHaveLength(0);
    expect(table).toHaveAttribute('data-column-count', '9');
    expect(table).toHaveStyle('width: 1150px');
    expect(table?.querySelector('thead tr:first-child th:first-child')).toHaveStyle('width: 270px');
    expect([...table!.querySelectorAll<HTMLTableCellElement>('thead tr:first-child th')].map((cell) => cell.colSpan)).toEqual([1, 4, 4]);
    expect(admin?.querySelectorAll('td')).toHaveLength(9);
    expect(cellTexts(admin!)).toEqual(['일반관리비 소계', '60', '55', '-5', '-8.3%', '360', '340', '-20', '-5.6%']);
    expect(sga.querySelector('.pnl-report__table-unit')).toHaveTextContent('(단위: 백만원, %)');

    expect(within(sga).getByText('12월 당월 실적 비교')).toBeInTheDocument();
    fireEvent.click(within(sga).getByRole('button', { name: '6월' }));
    expect(within(sga).getByText('6월 실적 비교')).toBeInTheDocument();
    expect(within(sga).queryByText('6월 당월 실적 비교')).not.toBeInTheDocument();
    fireEvent.click(within(sga).getByRole('button', { name: '12월(당월)' }));
    expect(within(sga).getByText('12월 당월 실적 비교')).toBeInTheDocument();

    fireEvent.click(within(sga).getByRole('button', { name: '실적만 보기' }));
    expect(table).toHaveAttribute('data-column-count', '14');
    expect(table).toHaveStyle('width: 1343px');
    expect(table?.querySelector('thead th:first-child')).toHaveStyle('width: 264px');
    expect(table?.querySelectorAll('thead th')).toHaveLength(14);
    expect(rowByKey('admin')?.querySelectorAll('td')).toHaveLength(14);
    expect(cellTexts(rowByKey('admin')!).slice(1)).toEqual(['101', '102', '103', '104', '0', '106', '107', '108', '109', '110', '111', '112', '1,173']);

    fireEvent.click(within(sga).getByRole('button', { name: '기간 설정 비교' }));
    expect(table).toHaveAttribute('data-column-count', '5');
    expect(table).toHaveStyle('width: 760px');
    expect(table?.querySelector('thead th:first-child')).toHaveStyle('width: 284px');
    expect(table?.querySelectorAll('thead th')).toHaveLength(5);
    expect(cellTexts(rowByKey('admin')!)).toEqual(['일반관리비 소계', '60', '55', '-5', '-8.3%']);
  });

  it('preserves regular product units and omits inapplicable NEW_BUSINESS quantity metadata and rows', async () => {
    await renderReady();
    fireEvent.click(screen.getAllByRole('tab')[3]);
    const product = screen.getByTestId('product-table-shell');
    const selector = within(product).getByRole('group', { name: '제품군 선택' });
    const selectors = within(selector).getAllByRole('button');
    expect(selectors.map((node) => [node.textContent, node.getAttribute('data-unit'), node.getAttribute('data-dimension')])).toEqual([
      ['8인치 SW', 'PCS', '8-inch'],
      ['8인치 BW', 'PCS', '8-inch'],
      ['4인치 LC', 'PCS', '4-inch'],
      ['FS', 'm', 'LENGTH'],
      ['신사업', null, null],
    ]);
    expect(product.querySelector('tr[data-row-key="SW_asp"] .pnl-report__unit-cell')).toHaveTextContent('원');
    fireEvent.click(within(selector).getByRole('button', { name: '신사업' }));
    expect(product.querySelector('.pnl-report__table-unit')).toHaveTextContent('(단위: 백만원, 원, %)');
    expect(product.querySelector('.pnl-report__table-unit')).not.toHaveTextContent(/PCS|null|undefined|N\/A/);
    expect(product.querySelectorAll('tbody tr')).toHaveLength(8);
    expect(within(product).queryByText(/매출수량|평균 판매 단가\(ASP\)/)).not.toBeInTheDocument();
    expect(screen.queryByText(/통합 수량 합계|mixed-unit/i)).not.toBeInTheDocument();

    const invalidLcUnit = {
      ...reportingResult('READY', pnlReportingVisualFixture),
      report: {
        ...pnlReportingVisualFixture,
        productSegments: pnlReportingVisualFixture.productSegments.map((segment) => segment.key === 'LC' ? { ...segment, businessUnit: null } : segment),
      },
    };
    const invalidFsUnit = {
      ...reportingResult('READY', pnlReportingVisualFixture),
      report: {
        ...pnlReportingVisualFixture,
        productSegments: pnlReportingVisualFixture.productSegments.map((segment) => segment.key === 'FS' ? { ...segment, businessUnit: null } : segment),
      },
    };
    expect(parsePnlReportingLoadResult(invalidLcUnit)).toBeNull();
    expect(parsePnlReportingLoadResult(invalidFsUnit)).toBeNull();

    const missingPeriodCells = {
      ...reportingResult('READY', pnlReportingVisualFixture),
      report: {
        ...pnlReportingVisualFixture,
        pnlRows: pnlReportingVisualFixture.pnlRows.map((row, index) => index === 0 ? {
          ...row,
          compareByPeriod: {},
        } : row),
      },
    };
    expect(parsePnlReportingLoadResult(missingPeriodCells)).toBeNull();
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
    expect(pnlReportingVisualFixture.productSegments.map((segment) => segment.rows.length)).toEqual([10, 10, 10, 10, 8]);
  });

  it('keeps the four backend reporting states plus frontend-only LOADING and ERROR, with error-specific copy', async () => {
    const loadingSource: PnlReportingSource = { load: vi.fn(() => new Promise(() => undefined)) };
    const loading = render(<PnlStatusView reportingSource={loadingSource} />);
    expect(screen.getByText('손익 현황을 불러오는 중…').closest('[role="status"]')).toBeInTheDocument();
    loading.unmount();

    for (const [reportingState, copy] of [
      ['MISSING_BOTH', 'PLAN과 ACTUAL 데이터가 아직 등록되지 않았습니다.'],
      ['MISSING_PLAN', 'PLAN 데이터가 아직 등록되지 않았습니다.'],
      ['MISSING_ACTUAL', 'ACTUAL 데이터가 아직 등록되지 않았습니다.'],
    ] as const) {
      const gap = render(<PnlStatusView reportingSource={source(reportingResult(reportingState))} />);
      expect(await screen.findByText(copy)).toBeInTheDocument();
      expect(screen.getByRole('combobox', { name: '기준년도' })).toHaveValue('2026');
      expect(within(screen.getByRole('combobox', { name: '기준년도' })).getAllByRole('option').map((option) => option.textContent)).toEqual(['2026년', '2025년']);
      gap.unmount();
    }

    const failedSource: PnlReportingSource = { load: vi.fn().mockRejectedValue(new Error('failed')) };
    const error = render(<PnlStatusView reportingSource={failedSource} />);
    expect(await screen.findByText('손익 현황을 불러오지 못했습니다.')).toBeInTheDocument();
    expect(screen.getByTestId('pnl-report')).toHaveAttribute('data-state', 'ERROR');
    error.unmount();

    const forbiddenSource: PnlReportingSource = { load: vi.fn().mockRejectedValue(new PnlReportingSourceError('FORBIDDEN', 'forbidden')) };
    const forbidden = render(<PnlStatusView reportingSource={forbiddenSource} />);
    expect(await screen.findByText('손익 현황을 조회할 권한이 없습니다.')).toBeInTheDocument();
    expect(screen.getByTestId('pnl-report')).toHaveAttribute('data-state', 'ERROR');
    forbidden.unmount();

    render(<PnlStatusView reportingSource={source({ broken: true })} />);
    expect(await screen.findByText('손익 현황 데이터 형식을 확인할 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByTestId('pnl-report')).toHaveAttribute('data-state', 'ERROR');
  });

  it('bootstraps without a frontend year, switches using backend years, aborts stale requests, and resets report state', async () => {
    const resolvers: Array<(value: unknown) => void> = [];
    const signals: AbortSignal[] = [];
    const reportingSource: PnlReportingSource = { load: vi.fn((_year, signal) => {
      signals.push(signal);
      return new Promise((resolvePromise) => resolvers.push(resolvePromise));
    }) };
    render(<PnlStatusView reportingSource={reportingSource} />);
    await waitFor(() => expect(resolvers).toHaveLength(1));
    expect(reportingSource.load).toHaveBeenNthCalledWith(1, null, expect.any(AbortSignal));
    resolvers[0](reportingResult('MISSING_BOTH'));
    expect(await screen.findByText('PLAN과 ACTUAL 데이터가 아직 등록되지 않았습니다.')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: '기준년도' }), { target: { value: '2025' } });
    await waitFor(() => expect(resolvers).toHaveLength(2));
    expect(reportingSource.load).toHaveBeenNthCalledWith(2, 2025, expect.any(AbortSignal));
    fireEvent.click(screen.getByRole('button', { name: '손익 현황 새로고침' }));
    await waitFor(() => expect(resolvers).toHaveLength(3));
    expect(signals[1].aborted).toBe(true);
    resolvers[1](reportingResult('MISSING_BOTH', null, 2025, [2026, 2025]));
    const report2025 = {
      ...pnlReportingVisualFixture,
      reportKey: 'test-only-2025',
      year: 2025,
      periods: pnlReportingVisualFixture.periods.map((period) => ({ ...period, key: period.key.replace('2026', '2025') })),
      selectedPeriodKey: pnlReportingVisualFixture.selectedPeriodKey.replace('2026', '2025'),
      actualPeriodKeys: pnlReportingVisualFixture.actualPeriodKeys.map((key) => key.replace('2026', '2025')),
      monthlyTrends: pnlReportingVisualFixture.monthlyTrends.map((trend) => ({ ...trend, periodKey: trend.periodKey.replace('2026', '2025') })),
      pnlRows: pnlReportingVisualFixture.pnlRows.map((row) => reportingRowForYear(row, 2025)),
      sgaRows: pnlReportingVisualFixture.sgaRows.map((row) => reportingRowForYear(row, 2025)),
      productSegments: pnlReportingVisualFixture.productSegments.map((segment) => ({
        ...segment,
        rows: segment.rows.map((row) => reportingRowForYear(row, 2025)),
      })),
    };
    resolvers[2](reportingResult('READY', report2025, 2025, [2026, 2025]));
    expect(await screen.findByTestId('revenue-trend-card')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '기준년도' })).toHaveValue('2025');
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
    expect(css).toMatch(/\.pnl-report__trends\s*\{[^}]*gap: 16px/s);
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
    const cogsShareRule = css.match(/pnl-report__financial-table\[data-table-kind="cogs"\] tbody td:nth-child\(2n\+3\) \{([^}]*)\}/)?.[1] ?? '';
    expect(cogsShareRule).toContain('color: #475569');
    expect(cogsShareRule).not.toContain('font-size');
    expect(css).toMatch(/pnl-report__table-unit--toolbar \{[^}]*margin: 0 0 0 auto;[^}]*white-space: normal;/);
    expect(css).not.toMatch(/pnl-report__trends[^}]*grid-template-columns/s);
  });
});

export type PnlReportingViewMode = 'PLAN_ACTUAL_COMPARE' | 'ACTUAL_ONLY' | 'CUSTOM_PERIOD_COMPARE';

export type PnlDetailTab =
  | 'pnl_statement'
  | 'mfg_cost_breakdown'
  | 'sga_breakdown'
  | 'item_segment_pnl';

export type PnlValueTone = 'favorable' | 'unfavorable' | 'neutral';
export type PnlRowKind = 'default' | 'header' | 'total';
export type PnlProductUnit = 'PCS' | 'm';

export interface PnlDisplayCell {
  text: string;
  tone?: PnlValueTone;
  emphasis?: 'normal' | 'strong';
}

export interface PnlKpiSlot {
  key: 'revenue' | 'operating_profit' | 'adjusted_operating_profit';
  label: '매출액' | '영업이익' | '조정 영업이익';
  amountText: string | null;
  unitText: string;
  progressText: string | null;
  achievementText: string | null;
  tone: PnlValueTone;
}

export interface PnlPeriodSlot {
  key: string;
  label: string;
  isActual: boolean;
}

export interface PnlMonthlyTrendSlot {
  periodKey: string;
  label: string;
  isActual: boolean;
  planRevenue: number | null;
  actualRevenue: number | null;
  planRevenueText: string | null;
  actualRevenueText: string | null;
  planOperatingProfit: number | null;
  actualOperatingProfit: number | null;
  actualOperatingMargin: number | null;
  planOperatingProfitText: string | null;
  actualOperatingProfitText: string | null;
  actualOperatingMarginText: string | null;
  planAdjustedOperatingProfit: number | null;
  actualAdjustedOperatingProfit: number | null;
  actualAdjustedOperatingMargin: number | null;
  planAdjustedOperatingProfitText: string | null;
  actualAdjustedOperatingProfitText: string | null;
  actualAdjustedOperatingMarginText: string | null;
}

export interface PnlMonthlyDataRow {
  key: string;
  label: string;
  tone: 'revenue-plan' | 'revenue-actual' | 'operating-plan' | 'operating-actual' | 'operating-margin' | 'adjusted-plan' | 'adjusted-actual' | 'adjusted-margin';
  cells: PnlDisplayCell[];
}

export interface PnlStatementRowSlot {
  key: string;
  label: string;
  unit: string;
  level: 0 | 1 | 2;
  kind: PnlRowKind;
  parentKey?: string;
  collapsible?: boolean;
  compareByPeriod: Record<string, PnlDisplayCell[]>;
  actualOnly: PnlDisplayCell[];
  customByRange: Record<string, PnlDisplayCell[]>;
}

export interface PnlCogsRowSlot {
  key: string;
  label: string;
  kind: PnlRowKind;
  cells: PnlDisplayCell[];
}

export interface PnlSgaRowSlot extends PnlStatementRowSlot {
  category: string;
}

export interface PnlProductSegmentSlot {
  key: string;
  label: string;
  businessUnit: PnlProductUnit;
  dimensionLabel: string;
  rows: PnlStatementRowSlot[];
}

export interface PnlReportingReadModel {
  reportKey: string;
  year: number;
  availableYears: number[];
  periods: PnlPeriodSlot[];
  selectedPeriodKey: string;
  actualPeriodKeys: string[];
  defaultCustomRangeKey: string;
  kpis: PnlKpiSlot[];
  monthlyTrends: PnlMonthlyTrendSlot[];
  monthlyDataRows: PnlMonthlyDataRow[];
  pnlRows: PnlStatementRowSlot[];
  cogsRows: PnlCogsRowSlot[];
  sgaRows: PnlSgaRowSlot[];
  productSegments: PnlProductSegmentSlot[];
}

export type PnlReportingLoadResult =
  | { state: 'DATA_READY'; report: PnlReportingReadModel }
  | { state: 'REPORTING_GAP' }
  | { state: 'EMPTY' };

export interface PnlReportingSource {
  load(year: number, signal: AbortSignal): Promise<unknown>;
}

export class PnlReportingSourceError extends Error {
  constructor(
    public readonly code: 'FORBIDDEN' | 'INVALID_PAYLOAD' | 'ERROR',
    message: string,
  ) {
    super(message);
    this.name = 'PnlReportingSourceError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value));
}

function isDisplayCell(value: unknown): value is PnlDisplayCell {
  return isRecord(value) && typeof value.text === 'string';
}

function isCellArray(value: unknown, expected: number): value is PnlDisplayCell[] {
  return Array.isArray(value) && value.length === expected && value.every(isDisplayCell);
}

function isCellMap(value: unknown, expected: number): boolean {
  return isRecord(value) && Object.values(value).every((cells) => isCellArray(cells, expected));
}

function isStatementRow(value: unknown, customCellCount: 3 | 4): boolean {
  return isRecord(value)
    && typeof value.key === 'string'
    && typeof value.label === 'string'
    && typeof value.unit === 'string'
    && (value.level === 0 || value.level === 1 || value.level === 2)
    && (value.kind === 'default' || value.kind === 'header' || value.kind === 'total')
    && isCellMap(value.compareByPeriod, 8)
    && isCellArray(value.actualOnly, 7)
    && isCellMap(value.customByRange, customCellCount);
}

export function parsePnlReportingLoadResult(value: unknown): PnlReportingLoadResult | null {
  if (!isRecord(value) || typeof value.state !== 'string') return null;
  if (value.state === 'REPORTING_GAP' || value.state === 'EMPTY') return { state: value.state };
  if (value.state !== 'DATA_READY' || !isRecord(value.report)) return null;

  const report = value.report as Partial<PnlReportingReadModel>;
  if (
    typeof report.reportKey !== 'string'
    || typeof report.year !== 'number'
    || !Array.isArray(report.availableYears)
    || !Array.isArray(report.periods)
    || !report.periods.every((period) => isRecord(period) && typeof period.key === 'string' && typeof period.label === 'string' && typeof period.isActual === 'boolean')
    || typeof report.selectedPeriodKey !== 'string'
    || !Array.isArray(report.actualPeriodKeys)
    || report.actualPeriodKeys.length !== 6
    || !report.actualPeriodKeys.every((key) => typeof key === 'string')
    || typeof report.defaultCustomRangeKey !== 'string'
    || !Array.isArray(report.kpis)
    || report.kpis.length !== 3
    || report.kpis[0]?.key !== 'revenue'
    || report.kpis[1]?.key !== 'operating_profit'
    || report.kpis[2]?.key !== 'adjusted_operating_profit'
    || !report.kpis.every((kpi) => isRecord(kpi) && typeof kpi.label === 'string' && isNullableString(kpi.amountText) && typeof kpi.unitText === 'string' && isNullableString(kpi.progressText) && isNullableString(kpi.achievementText) && (kpi.tone === 'favorable' || kpi.tone === 'unfavorable' || kpi.tone === 'neutral'))
    || !Array.isArray(report.monthlyTrends)
    || !report.monthlyTrends.every((trend) => isRecord(trend) && typeof trend.periodKey === 'string' && typeof trend.label === 'string' && typeof trend.isActual === 'boolean' && isNullableNumber(trend.planRevenue) && isNullableNumber(trend.actualRevenue) && isNullableNumber(trend.planOperatingProfit) && isNullableNumber(trend.actualOperatingProfit) && isNullableNumber(trend.actualOperatingMargin) && isNullableNumber(trend.planAdjustedOperatingProfit) && isNullableNumber(trend.actualAdjustedOperatingProfit) && isNullableNumber(trend.actualAdjustedOperatingMargin))
    || !Array.isArray(report.monthlyDataRows)
    || !report.monthlyDataRows.every((row) => isRecord(row) && typeof row.key === 'string' && typeof row.label === 'string' && isCellArray(row.cells, (report.periods as PnlPeriodSlot[]).length))
    || !Array.isArray(report.pnlRows)
    || !report.pnlRows.every((row) => isStatementRow(row, 4))
    || !Array.isArray(report.cogsRows)
    || !report.cogsRows.every((row) => isRecord(row) && typeof row.key === 'string' && typeof row.label === 'string' && isCellArray(row.cells, 14))
    || !Array.isArray(report.sgaRows)
    || !report.sgaRows.every((row) => isStatementRow(row, 4) && isRecord(row) && typeof row.category === 'string')
    || !Array.isArray(report.productSegments)
    || !report.productSegments.every((segment) => isRecord(segment) && typeof segment.key === 'string' && typeof segment.label === 'string' && (segment.businessUnit === 'PCS' || segment.businessUnit === 'm') && typeof segment.dimensionLabel === 'string' && Array.isArray(segment.rows) && segment.rows.every((row) => isStatementRow(row, 3)))
  ) return null;

  return { state: 'DATA_READY', report: report as PnlReportingReadModel };
}

export type PnlReportingViewMode = 'PLAN_ACTUAL_COMPARE' | 'ACTUAL_ONLY' | 'CUSTOM_PERIOD_COMPARE';

export type PnlDetailTab =
  | 'pnl_statement'
  | 'mfg_cost_breakdown'
  | 'sga_breakdown'
  | 'item_segment_pnl';

export type PnlValueTone = 'favorable' | 'unfavorable' | 'neutral';
export type PnlRowKind = 'default' | 'header' | 'total';
export type PnlProductUnit = 'PCS' | 'm';
export type PnlRegularProductKey = 'SW' | 'BW' | 'LC' | 'FS';

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
  actualAvailable: boolean;
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

interface PnlProductSegmentBase {
  label: string;
  rows: PnlStatementRowSlot[];
}

export interface PnlRegularProductSegmentSlot extends PnlProductSegmentBase {
  key: PnlRegularProductKey;
  businessUnit: PnlProductUnit;
  dimensionLabel: string;
}

export interface PnlNewBusinessSegmentSlot extends PnlProductSegmentBase {
  key: 'NEW_BUSINESS';
  businessUnit: null;
  dimensionLabel: null;
}

export type PnlProductSegmentSlot = PnlRegularProductSegmentSlot | PnlNewBusinessSegmentSlot;

export interface PnlReportingReadModel {
  reportKey: string;
  year: number;
  actualThroughMonth: number;
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

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isFixedTrendMonth(value: unknown, index: number, year: number): boolean {
  if (!isRecord(value)) return false;
  const month = String(index + 1).padStart(2, '0');
  const actualFields = [
    'actualRevenue',
    'actualRevenueText',
    'actualOperatingProfit',
    'actualOperatingProfitText',
    'actualOperatingMargin',
    'actualOperatingMarginText',
    'actualAdjustedOperatingProfit',
    'actualAdjustedOperatingProfitText',
    'actualAdjustedOperatingMargin',
    'actualAdjustedOperatingMarginText',
  ];
  const coreActualAvailable = isFiniteNumber(value.actualRevenue)
    && isFiniteNumber(value.actualOperatingProfit)
    && isFiniteNumber(value.actualOperatingMargin);
  return value.periodKey === `${year}-${month}`
    && value.label === `${index + 1}월`
    && typeof value.actualAvailable === 'boolean'
    && isNullableNumber(value.planRevenue)
    && isNullableNumber(value.actualRevenue)
    && isNullableString(value.planRevenueText)
    && isNullableString(value.actualRevenueText)
    && isNullableNumber(value.planOperatingProfit)
    && isNullableNumber(value.actualOperatingProfit)
    && isNullableNumber(value.actualOperatingMargin)
    && isNullableString(value.planOperatingProfitText)
    && isNullableString(value.actualOperatingProfitText)
    && isNullableString(value.actualOperatingMarginText)
    && isNullableNumber(value.planAdjustedOperatingProfit)
    && isNullableNumber(value.actualAdjustedOperatingProfit)
    && isNullableNumber(value.actualAdjustedOperatingMargin)
    && isNullableString(value.planAdjustedOperatingProfitText)
    && isNullableString(value.actualAdjustedOperatingProfitText)
    && isNullableString(value.actualAdjustedOperatingMarginText)
    && (value.actualAvailable ? coreActualAvailable : actualFields.every((field) => value[field] === null));
}

function isFixedPeriodMonth(value: unknown, index: number, year: number): boolean {
  if (!isRecord(value)) return false;
  const month = String(index + 1).padStart(2, '0');
  return value.key === `${year}-${month}`
    && value.label === `${index + 1}월`
    && typeof value.isActual === 'boolean';
}

function hasSequentialActualPeriods(periods: PnlPeriodSlot[], actualPeriodKeys: string[]): boolean {
  const periodActualKeys = periods.filter((period) => period.isActual).map((period) => period.key);
  return new Set(actualPeriodKeys).size === actualPeriodKeys.length
    && periodActualKeys.length === actualPeriodKeys.length
    && periodActualKeys.every((key, index) => key === actualPeriodKeys[index])
    && periods.every((period, index) => period.isActual === (index < actualPeriodKeys.length));
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

function isStatementRow(value: unknown, customCellCount: 3 | 4, actualCellCount: number): boolean {
  return isRecord(value)
    && typeof value.key === 'string'
    && typeof value.label === 'string'
    && typeof value.unit === 'string'
    && (value.level === 0 || value.level === 1 || value.level === 2)
    && (value.kind === 'default' || value.kind === 'header' || value.kind === 'total')
    && isCellMap(value.compareByPeriod, 8)
    && isCellArray(value.actualOnly, actualCellCount)
    && isCellMap(value.customByRange, customCellCount);
}

const PRODUCT_SEGMENT_KEYS = ['SW', 'BW', 'LC', 'FS', 'NEW_BUSINESS'] as const;
const REGULAR_PRODUCT_METADATA: Record<PnlRegularProductKey, { businessUnit: PnlProductUnit; dimensionLabel: string }> = {
  SW: { businessUnit: 'PCS', dimensionLabel: '8-inch' },
  BW: { businessUnit: 'PCS', dimensionLabel: '8-inch' },
  LC: { businessUnit: 'PCS', dimensionLabel: '4-inch' },
  FS: { businessUnit: 'm', dimensionLabel: 'LENGTH' },
};

function isQuantityRowKey(key: unknown): boolean {
  return typeof key === 'string' && (key === 'volume' || key === 'asp' || key.endsWith('_volume') || key.endsWith('_asp'));
}

function isProductSegment(value: unknown, actualCellCount: number): boolean {
  if (!isRecord(value) || typeof value.key !== 'string' || typeof value.label !== 'string' || !Array.isArray(value.rows)) return false;
  if (!value.rows.every((row) => isStatementRow(row, 3, actualCellCount))) return false;

  if (value.key === 'NEW_BUSINESS') {
    return value.businessUnit === null
      && value.dimensionLabel === null
      && value.rows.length === 8
      && !value.rows.some((row) => isRecord(row) && isQuantityRowKey(row.key));
  }

  if (!(value.key in REGULAR_PRODUCT_METADATA)) return false;
  const metadata = REGULAR_PRODUCT_METADATA[value.key as PnlRegularProductKey];
  return value.businessUnit === metadata.businessUnit
    && value.dimensionLabel === metadata.dimensionLabel
    && value.rows.length === 10;
}

export function parsePnlReportingLoadResult(value: unknown): PnlReportingLoadResult | null {
  if (!isRecord(value) || typeof value.state !== 'string') return null;
  if (value.state === 'REPORTING_GAP' || value.state === 'EMPTY') return { state: value.state };
  if (value.state !== 'DATA_READY' || !isRecord(value.report)) return null;

  const report = value.report as Partial<PnlReportingReadModel>;
  const actualThroughMonth = report.actualThroughMonth;
  const actualCellCount = typeof actualThroughMonth === 'number' ? actualThroughMonth + 1 : 0;
  if (
    typeof report.reportKey !== 'string'
    || typeof report.year !== 'number'
    || !Number.isInteger(actualThroughMonth)
    || (actualThroughMonth as number) < 1
    || (actualThroughMonth as number) > 12
    || !Array.isArray(report.availableYears)
    || !Array.isArray(report.periods)
    || report.periods.length !== 12
    || !report.periods.every((period, index) => isFixedPeriodMonth(period, index, report.year as number))
    || typeof report.selectedPeriodKey !== 'string'
    || !Array.isArray(report.actualPeriodKeys)
    || report.actualPeriodKeys.length !== actualThroughMonth
    || !report.actualPeriodKeys.every((key) => typeof key === 'string')
    || !hasSequentialActualPeriods(report.periods as PnlPeriodSlot[], report.actualPeriodKeys as string[])
    || report.selectedPeriodKey !== report.actualPeriodKeys[report.actualPeriodKeys.length - 1]
    || typeof report.defaultCustomRangeKey !== 'string'
    || !Array.isArray(report.kpis)
    || report.kpis.length !== 3
    || report.kpis[0]?.key !== 'revenue'
    || report.kpis[1]?.key !== 'operating_profit'
    || report.kpis[2]?.key !== 'adjusted_operating_profit'
    || !report.kpis.every((kpi) => isRecord(kpi) && typeof kpi.label === 'string' && isNullableString(kpi.amountText) && typeof kpi.unitText === 'string' && isNullableString(kpi.progressText) && isNullableString(kpi.achievementText) && (kpi.tone === 'favorable' || kpi.tone === 'unfavorable' || kpi.tone === 'neutral'))
    || !Array.isArray(report.monthlyTrends)
    || report.monthlyTrends.length !== 12
    || !report.monthlyTrends.every((trend, index) => isFixedTrendMonth(trend, index, report.year as number))
    || !report.monthlyTrends.every((trend, index) => isRecord(trend) && trend.actualAvailable === (report.periods as PnlPeriodSlot[])[index]?.isActual)
    || !Array.isArray(report.monthlyDataRows)
    || !report.monthlyDataRows.every((row) => isRecord(row) && typeof row.key === 'string' && typeof row.label === 'string' && isCellArray(row.cells, (report.monthlyTrends as PnlMonthlyTrendSlot[]).length))
    || !Array.isArray(report.pnlRows)
    || !report.pnlRows.every((row) => isStatementRow(row, 4, actualCellCount))
    || !Array.isArray(report.cogsRows)
    || !report.cogsRows.every((row) => isRecord(row) && typeof row.key === 'string' && typeof row.label === 'string' && isCellArray(row.cells, 26))
    || !Array.isArray(report.sgaRows)
    || !report.sgaRows.every((row) => isStatementRow(row, 4, actualCellCount) && isRecord(row) && typeof row.category === 'string')
    || !Array.isArray(report.productSegments)
    || report.productSegments.length !== PRODUCT_SEGMENT_KEYS.length
    || !report.productSegments.every((segment, index) => isRecord(segment) && segment.key === PRODUCT_SEGMENT_KEYS[index] && isProductSegment(segment, actualCellCount))
  ) return null;

  return { state: 'DATA_READY', report: report as PnlReportingReadModel };
}

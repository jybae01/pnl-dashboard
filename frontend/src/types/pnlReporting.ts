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
export type PnlReportingState = 'MISSING_BOTH' | 'MISSING_PLAN' | 'MISSING_ACTUAL' | 'READY';

export interface PnlDisplayCell {
  value: number | null;
  text: string;
  tone?: PnlValueTone;
  emphasis?: 'normal' | 'strong';
}

export interface PnlKpiSlot {
  key: 'revenue' | 'operating_profit' | 'adjusted_operating_profit';
  label: '매출액' | '영업이익' | '조정 영업이익';
  amount: number | null;
  amountText: string | null;
  unitText: string;
  annualPlan: number | null;
  ytdPlan: number | null;
  ytdActual: number | null;
  progress: number | null;
  progressText: string | null;
  achievement: number | null;
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
  templateVersion: string;
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

export interface PnlReportingDatasetMetadata {
  exists: boolean;
  datasetId: string | null;
  lastUpdated: string | null;
}

export interface PnlReportingMetadata {
  selectedYear: number;
  availableYears: number[];
  plan: PnlReportingDatasetMetadata;
  actual: PnlReportingDatasetMetadata & { actualThroughMonth: number | null };
  lastUpdated: string | null;
}

export type PnlReportingLoadResult =
  | { reportingState: 'READY'; metadata: PnlReportingMetadata; report: PnlReportingReadModel }
  | { reportingState: Exclude<PnlReportingState, 'READY'>; metadata: PnlReportingMetadata; report: null };

export interface PnlReportingSource {
  load(year: number | null, signal: AbortSignal): Promise<unknown>;
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
  return typeof value === 'object' && value !== null && !Array.isArray(value);
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
  const actualAvailableValues = isFiniteNumber(value.actualRevenue)
    && isFiniteNumber(value.actualOperatingProfit)
    && isNullableNumber(value.actualOperatingMargin)
    && isFiniteNumber(value.actualAdjustedOperatingProfit)
    && isNullableNumber(value.actualAdjustedOperatingMargin)
    && typeof value.actualRevenueText === 'string'
    && typeof value.actualOperatingProfitText === 'string'
    && isNullableString(value.actualOperatingMarginText)
    && typeof value.actualAdjustedOperatingProfitText === 'string'
    && isNullableString(value.actualAdjustedOperatingMarginText);
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
    && (value.actualAvailable ? actualAvailableValues : actualFields.every((field) => value[field] === null));
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
  return isRecord(value)
    && isNullableNumber(value.value)
    && typeof value.text === 'string'
    && (value.tone === 'favorable' || value.tone === 'unfavorable' || value.tone === 'neutral')
    && (value.emphasis === 'normal' || value.emphasis === 'strong');
}

function isCellArray(value: unknown, expected: number): value is PnlDisplayCell[] {
  return Array.isArray(value) && value.length === expected && value.every(isDisplayCell);
}

function isCellMap(value: unknown, expected: number, expectedKeys: string[]): boolean {
  return isRecord(value)
    && Object.keys(value).length === expectedKeys.length
    && expectedKeys.every((key) => Object.prototype.hasOwnProperty.call(value, key) && isCellArray(value[key], expected));
}

function isStatementRow(
  value: unknown,
  customCellCount: 3 | 4,
  actualCellCount: number,
  periodKeys: string[],
  rangeKeys: string[],
): boolean {
  return isRecord(value)
    && typeof value.key === 'string'
    && typeof value.label === 'string'
    && typeof value.unit === 'string'
    && (value.level === 0 || value.level === 1 || value.level === 2)
    && (value.kind === 'default' || value.kind === 'header' || value.kind === 'total')
    && isCellMap(value.compareByPeriod, 8, periodKeys)
    && isCellArray(value.actualOnly, actualCellCount)
    && isCellMap(value.customByRange, customCellCount, rangeKeys);
}

const PRODUCT_SEGMENT_KEYS = ['SW', 'BW', 'LC', 'FS', 'NEW_BUSINESS'] as const;
const COGS_ROW_KEYS = ['mfg_material', 'mfg_labor', 'mfg_outsourcing', 'mfg_other', 'mfg_total'] as const;
const MONTHLY_ROW_TONES: PnlMonthlyDataRow['tone'][] = [
  'revenue-plan', 'revenue-actual', 'operating-plan', 'operating-actual',
  'operating-margin', 'adjusted-plan', 'adjusted-actual', 'adjusted-margin',
];
const REGULAR_PRODUCT_METADATA: Record<PnlRegularProductKey, { businessUnit: PnlProductUnit; dimensionLabel: string }> = {
  SW: { businessUnit: 'PCS', dimensionLabel: '8-inch' },
  BW: { businessUnit: 'PCS', dimensionLabel: '8-inch' },
  LC: { businessUnit: 'PCS', dimensionLabel: '4-inch' },
  FS: { businessUnit: 'm', dimensionLabel: 'LENGTH' },
};

function isQuantityRowKey(key: unknown): boolean {
  return typeof key === 'string' && (key === 'volume' || key === 'asp' || key.endsWith('_volume') || key.endsWith('_asp'));
}

function isProductSegment(value: unknown, actualCellCount: number, periodKeys: string[], rangeKeys: string[]): boolean {
  if (!isRecord(value) || typeof value.key !== 'string' || typeof value.label !== 'string' || !Array.isArray(value.rows)) return false;
  if (!value.rows.every((row) => isStatementRow(row, 3, actualCellCount, periodKeys, rangeKeys))) return false;

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

function isYear(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 2000 && value <= 2200;
}

function isDatasetMetadata(value: unknown): value is PnlReportingDatasetMetadata {
  return isRecord(value)
    && typeof value.exists === 'boolean'
    && (value.datasetId === null || typeof value.datasetId === 'string')
    && (value.lastUpdated === null || typeof value.lastUpdated === 'string')
    && (value.exists ? typeof value.datasetId === 'string' && typeof value.lastUpdated === 'string' : value.datasetId === null && value.lastUpdated === null);
}

function isActualDatasetMetadata(value: unknown): value is PnlReportingMetadata['actual'] {
  return isDatasetMetadata(value)
    && isRecord(value)
    && (value.actualThroughMonth === null || (Number.isInteger(value.actualThroughMonth) && Number(value.actualThroughMonth) >= 1 && Number(value.actualThroughMonth) <= 12))
    && (value.exists ? value.actualThroughMonth !== null : value.actualThroughMonth === null);
}

function parseMetadata(value: unknown): PnlReportingMetadata | null {
  if (!isRecord(value)
    || !isYear(value.selectedYear)
    || !Array.isArray(value.availableYears)
    || !value.availableYears.every(isYear)
    || new Set(value.availableYears).size !== value.availableYears.length
    || !value.availableYears.every((year, index, years) => index === 0 || years[index - 1] > year)
    || !isDatasetMetadata(value.plan)
    || !isActualDatasetMetadata(value.actual)
    || !(value.lastUpdated === null || typeof value.lastUpdated === 'string')) return null;
  return value as unknown as PnlReportingMetadata;
}

function hasStateMetadata(state: PnlReportingState, metadata: PnlReportingMetadata): boolean {
  if (state === 'READY') return metadata.plan.exists && metadata.actual.exists;
  if (state === 'MISSING_PLAN') return !metadata.plan.exists && metadata.actual.exists;
  if (state === 'MISSING_ACTUAL') return metadata.plan.exists && !metadata.actual.exists;
  return !metadata.plan.exists && !metadata.actual.exists;
}

function isKpi(value: unknown, key: PnlKpiSlot['key'], label: PnlKpiSlot['label']): value is PnlKpiSlot {
  return isRecord(value)
    && value.key === key
    && value.label === label
    && isNullableNumber(value.amount)
    && isNullableString(value.amountText)
    && typeof value.unitText === 'string'
    && isNullableNumber(value.annualPlan)
    && isNullableNumber(value.ytdPlan)
    && isNullableNumber(value.ytdActual)
    && isNullableNumber(value.progress)
    && isNullableString(value.progressText)
    && isNullableNumber(value.achievement)
    && isNullableString(value.achievementText)
    && (value.tone === 'favorable' || value.tone === 'unfavorable' || value.tone === 'neutral');
}

export function parsePnlReportingLoadResult(value: unknown): PnlReportingLoadResult | null {
  if (!isRecord(value)
    || !['MISSING_BOTH', 'MISSING_PLAN', 'MISSING_ACTUAL', 'READY'].includes(String(value.reportingState))) return null;
  const reportingState = value.reportingState as PnlReportingState;
  const metadata = parseMetadata(value.metadata);
  if (!metadata || !hasStateMetadata(reportingState, metadata)) return null;
  if (reportingState !== 'READY') {
    return value.report === null ? { reportingState, metadata, report: null } : null;
  }
  if (!isRecord(value.report)) return null;

  const report = value.report as Partial<PnlReportingReadModel>;
  const actualThroughMonth = report.actualThroughMonth;
  const actualCellCount = typeof actualThroughMonth === 'number' ? actualThroughMonth + 1 : 0;
  const periodKeys = Array.isArray(report.periods)
    ? report.periods.map((period) => isRecord(period) && typeof period.key === 'string' ? period.key : '')
    : [];
  const rangeKeys = Array.from({ length: 12 }, (_, startIndex) => (
    Array.from({ length: 12 - startIndex }, (_, offset) => `${startIndex + 1}월:${startIndex + offset + 1}월`)
  )).flat();
  if (
    typeof report.reportKey !== 'string'
    || typeof report.year !== 'number'
    || report.year !== metadata.selectedYear
    || typeof report.templateVersion !== 'string'
    || !Number.isInteger(actualThroughMonth)
    || (actualThroughMonth as number) < 1
    || (actualThroughMonth as number) > 12
    || !Array.isArray(report.availableYears)
    || report.availableYears.length !== metadata.availableYears.length
    || !report.availableYears.every((year, index) => year === metadata.availableYears[index])
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
    || !isKpi(report.kpis[0], 'revenue', '매출액')
    || !isKpi(report.kpis[1], 'operating_profit', '영업이익')
    || !isKpi(report.kpis[2], 'adjusted_operating_profit', '조정 영업이익')
    || !Array.isArray(report.monthlyTrends)
    || report.monthlyTrends.length !== 12
    || !report.monthlyTrends.every((trend, index) => isFixedTrendMonth(trend, index, report.year as number))
    || !report.monthlyTrends.every((trend, index) => isRecord(trend) && trend.actualAvailable === (report.periods as PnlPeriodSlot[])[index]?.isActual)
    || !Array.isArray(report.monthlyDataRows)
    || report.monthlyDataRows.length !== 8
    || !report.monthlyDataRows.every((row, index) => isRecord(row) && typeof row.key === 'string' && typeof row.label === 'string' && row.tone === MONTHLY_ROW_TONES[index] && isCellArray(row.cells, (report.monthlyTrends as PnlMonthlyTrendSlot[]).length))
    || !Array.isArray(report.pnlRows)
    || report.pnlRows.length !== 25
    || !report.pnlRows.every((row) => isStatementRow(row, 4, actualCellCount, periodKeys, rangeKeys))
    || !Array.isArray(report.cogsRows)
    || report.cogsRows.length !== 5
    || !report.cogsRows.every((row, index) => isRecord(row) && row.key === COGS_ROW_KEYS[index] && typeof row.label === 'string' && (row.kind === 'default' || row.kind === 'total') && isCellArray(row.cells, 26))
    || !Array.isArray(report.sgaRows)
    || report.sgaRows.length !== 23
    || !report.sgaRows.every((row) => isStatementRow(row, 4, actualCellCount, periodKeys, rangeKeys) && isRecord(row) && typeof row.category === 'string')
    || !Array.isArray(report.productSegments)
    || report.productSegments.length !== PRODUCT_SEGMENT_KEYS.length
    || !report.productSegments.every((segment, index) => isRecord(segment) && segment.key === PRODUCT_SEGMENT_KEYS[index] && isProductSegment(segment, actualCellCount, periodKeys, rangeKeys))
  ) return null;

  return { reportingState: 'READY', metadata, report: report as PnlReportingReadModel };
}

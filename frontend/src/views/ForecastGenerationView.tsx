import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Calculator, CheckCircle2, Database, Download, FileSpreadsheet, FileText, Info, LockKeyhole, RotateCcw, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { bffClient } from '../integration/client';
import {
  AnalysisModelDto,
  ApiClientError,
  ForecastExcelPreviewDto,
  ForecastGenerateResponseDto,
  ForecastInputMetadataDto,
} from '../integration/types';
import {
  EditableNumericInput,
  normalizeMonthInput,
  parseMonthInput,
} from '../integration/EditableNumericInput';
import {
  adaptForecastInput,
  applyForecastExcelPreview,
  BUSINESS_PRODUCTION_ROWS,
  createForecastMonthFormState,
  ensureForecastMonths,
  findOutOfRangeForecastAdjustmentMonths,
  hasForecastAdjustmentInput,
  hasForecastAdjustmentValue,
  isForecastAdvancedFieldNonDefault,
  MCM_PRODUCTS,
  SALES_PRODUCTS,
  type ForecastAdvancedScalarField,
  type ForecastInputSection,
  type ForecastInputState,
  type ForecastMonthFormState,
} from './forecastInputState';

type ViewState =
  | 'LOADING'
  | 'READY'
  | 'SUBMITTING'
  | 'VALIDATION_ERROR'
  | 'SUCCESS'
  | 'EMPTY'
  | 'ERROR'
  | 'FORBIDDEN';

type DownloadState = 'IDLE' | 'DOWNLOADING' | 'FAILED';
type ExcelState = 'IDLE' | 'UPLOADING' | 'READY' | 'ERROR';

const V1_FORECAST_SYNC_MAX_MONTHS = 6;
const MONTH_MIN = 1;
const MONTH_MAX = 12;

const COGS_ADJUSTMENT_ROWS = [
  {
    key: 'disposal',
    displayName: '제품 폐기손실',
    amountField: 'disposalAdjustment',
    reasonField: 'disposalReason',
  },
  {
    key: 'obsolescence',
    displayName: '제품 진부화 평가손실',
    amountField: 'obsolescenceAdjustment',
    reasonField: 'obsolescenceReason',
  },
] as const;

type CogsAdjustmentKey = typeof COGS_ADJUSTMENT_ROWS[number]['key'];
const MANUAL_SGA_SOURCE_LABEL = '일반 조정';

export interface SgaRegisteredEntry {
  id: string;
  adjustmentKey: string;
  sourceLabel: string;
  amount: string;
  reason: string;
}

export function aggregateSgaRegisteredEntries(entries: SgaRegisteredEntry[]): { amount: string; reason: string } {
  const amount = entries.reduce((total, entry) => {
    const parsed = Number(entry.amount.replace(/,/g, '').trim());
    return total + (Number.isFinite(parsed) ? parsed : 0);
  }, 0);
  const reason = entries
    .map((entry) => entry.reason.trim())
    .filter(Boolean)
    .join('; ')
    .slice(0, 500);
  return { amount: amount === 0 ? '0' : String(amount), reason };
}

export function withLegacySgaAggregateEntry(
  entries: SgaRegisteredEntry[],
  adjustmentKey: string,
  row: { amount: string; reason: string },
): SgaRegisteredEntry[] {
  if (entries.some((entry) => entry.adjustmentKey === adjustmentKey)) return entries;
  const registered = hasForecastAdjustmentValue(row);
  return registered
    ? [...entries, {
        id: `existing:${adjustmentKey}`,
        adjustmentKey,
        sourceLabel: MANUAL_SGA_SOURCE_LABEL,
        amount: row.amount,
        reason: row.reason,
      }]
    : entries;
}

export function formatCanonicalRatioAsPercentage(value: string): string {
  const trimmed = value.trim();
  if (trimmed === '') return '';
  const parsed = Number(trimmed.replace(/,/g, ''));
  return Number.isFinite(parsed) ? (parsed * 100).toFixed(1) : value;
}

export function parsePercentageToCanonicalRatio(value: string): string {
  const trimmed = value.replace(/%/g, '').trim();
  if (trimmed === '') return '';
  const parsed = Number(trimmed.replace(/,/g, ''));
  return Number.isFinite(parsed) ? String(Number((parsed / 100).toFixed(12))) : trimmed;
}

export function formatNumericPresentation(value: string): string {
  const trimmed = value.trim();
  if (trimmed === '') return '';
  const parsed = Number(trimmed.replace(/,/g, ''));
  return Number.isFinite(parsed)
    ? parsed.toLocaleString('ko-KR', { maximumFractionDigits: 12 })
    : value;
}

export function parseFormattedNumericInput(value: string): string {
  return value.replace(/,/g, '').trim();
}

function parseAdjustmentAmount(value: string): number {
  const parsed = Number(value.replace(/,/g, '').trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

export function calculateAdjustmentExpectedAmount(baseline: number, adjustment: string): number {
  return baseline + parseAdjustmentAmount(adjustment);
}

function formatKrwAmount(value: number | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('ko-KR') : '—';
}

interface PercentageInputProps {
  value: string;
  disabled: boolean;
  ariaLabel: string;
  onChange: (value: string) => void;
}

function PercentageInput({ value, disabled, ariaLabel, onChange }: PercentageInputProps) {
  const [displayValue, setDisplayValue] = useState(() => formatCanonicalRatioAsPercentage(value));
  const focusedRef = useRef(false);

  useEffect(() => {
    if (!focusedRef.current) setDisplayValue(formatCanonicalRatioAsPercentage(value));
  }, [value]);

  return <span className="forecast-workflow__percentage-input">
    <input
      type="text"
      inputMode="decimal"
      disabled={disabled}
      aria-label={ariaLabel}
      value={displayValue}
      style={{ textAlign: 'right' }}
      onFocus={(event) => {
        focusedRef.current = true;
        event.currentTarget.select();
      }}
      onChange={(event) => {
        setDisplayValue(event.target.value);
        onChange(parsePercentageToCanonicalRatio(event.target.value));
      }}
      onBlur={(event) => {
        focusedRef.current = false;
        const canonical = parsePercentageToCanonicalRatio(event.currentTarget.value);
        onChange(canonical);
        setDisplayValue(formatCanonicalRatioAsPercentage(canonical));
      }}
    />
    <span aria-hidden="true">%</span>
  </span>;
}

function FormattedNumericInput({ value, disabled, ariaLabel, onChange }: PercentageInputProps) {
  const [displayValue, setDisplayValue] = useState(() => formatNumericPresentation(value));
  const focusedRef = useRef(false);

  useEffect(() => {
    if (!focusedRef.current) setDisplayValue(formatNumericPresentation(value));
  }, [value]);

  return <input
    className="forecast-workflow__reference-number-input"
    type="text"
    inputMode="decimal"
    disabled={disabled}
    aria-label={ariaLabel}
    value={displayValue}
    style={{ textAlign: 'right' }}
    onFocus={(event) => {
      focusedRef.current = true;
      event.currentTarget.select();
    }}
    onChange={(event) => {
      setDisplayValue(event.target.value);
      onChange(parseFormattedNumericInput(event.target.value));
    }}
    onBlur={(event) => {
      focusedRef.current = false;
      const canonical = parseFormattedNumericInput(event.currentTarget.value);
      onChange(canonical);
      setDisplayValue(formatNumericPresentation(canonical));
    }}
  />;
}

interface ForecastMonthSelectProps {
  ariaLabel: string;
  disabled: boolean;
  months: readonly number[];
  modelYear: number | undefined;
  preservedMonths?: readonly number[];
  value: number;
  onChange: (month: number) => void;
}

function ForecastMonthSelect({ ariaLabel, disabled, months, modelYear, preservedMonths = [], value, onChange }: ForecastMonthSelectProps) {
  const label = (month: number) => `${modelYear ?? '----'}-${String(month).padStart(2, '0')}`;
  const outOfRange = !months.includes(value);
  const unavailableMonths = [...new Set([value, ...preservedMonths])]
    .filter((month) => !months.includes(month))
    .sort((left, right) => left - right);
  return <select
    className={`forecast-workflow__adjustment-month-select ${outOfRange ? 'is-invalid' : ''}`}
    aria-label={ariaLabel}
    disabled={disabled || months.length === 0}
    value={value}
    onChange={(event) => onChange(Number(event.target.value))}
  >
    {unavailableMonths.map((month) => <option key={`preserved-${month}`} value={month}>{label(month)} (범위 밖)</option>)}
    {months.map((month) => <option key={month} value={month}>{label(month)}</option>)}
  </select>;
}

export interface ForecastGenerationViewProps {
  onNavigateToPnl?: () => void;
  onNavigateToAnalysis?: () => void;
  onNavigateToManagement?: () => void;
}

function safeErrorMessage(error: unknown): { state: ViewState; message: string } {
  if (error instanceof ApiClientError) {
    switch (error.code) {
      case 'VALIDATION_ERROR':
        return { state: 'VALIDATION_ERROR', message: '입력값과 선택 기간을 확인한 뒤 다시 시도하세요.' };
      case 'FORECAST_SCOPE_NOT_APPROVED':
        return { state: 'VALIDATION_ERROR', message: '한 번에 최대 6개월까지 추정할 수 있습니다.' };
      case 'FORBIDDEN':
        return { state: 'FORBIDDEN', message: '추정 산출을 실행할 권한이 없습니다.' };
      case 'IDEMPOTENCY_CONFLICT':
        return { state: 'VALIDATION_ERROR', message: '같은 요청 키가 다른 입력에 사용되었습니다. 입력을 수정하고 다시 시도하세요.' };
      case 'MODEL_NOT_FOUND':
        return { state: 'VALIDATION_ERROR', message: '선택한 기준 모형을 사용할 수 없습니다.' };
      case 'INPUT_INTEGRITY_MISMATCH':
        return { state: 'ERROR', message: '추정 산출 결과를 확인할 수 없습니다. 관리자에게 문의하세요.' };
    }
    if (error.status === 403) return { state: 'FORBIDDEN', message: '추정 산출을 실행할 권한이 없습니다.' };
    return { state: 'ERROR', message: '추정 산출을 완료하지 못했습니다. 잠시 후 다시 시도하세요.' };
  }
  return { state: 'ERROR', message: '추정 산출을 불러오지 못했습니다. 잠시 후 다시 시도하세요.' };
}

function sgaSectionLabel(value: string | null): string {
  switch (value) {
    case 'selling': return '판매비';
    case 'general_admin': return '일반관리비';
    case 'sga': return '판관비';
    default: return '미분류';
  }
}

export const ForecastGenerationView: React.FC<ForecastGenerationViewProps> = ({
  onNavigateToPnl,
  onNavigateToAnalysis,
  onNavigateToManagement,
}) => {
  const [models, setModels] = useState<AnalysisModelDto[]>([]);
  const [baseModelId, setBaseModelId] = useState('');
  const [startMonth, setStartMonth] = useState('07');
  const [endMonth, setEndMonth] = useState('07');
  const [name, setName] = useState('Forecast Model');
  const [version, setVersion] = useState('V1');
  const [inputs, setInputs] = useState<ForecastInputState>({ 7: createForecastMonthFormState(7) });
  const [activeInputMonth, setActiveInputMonth] = useState(7);
  const [adjustmentInputMonth, setAdjustmentInputMonth] = useState(7);
  const [manufacturingInputMonths, setManufacturingInputMonths] = useState<Record<string, number>>({});
  const [sgaInputMonths, setSgaInputMonths] = useState<Record<string, number>>({});
  const [cogsInputMonths, setCogsInputMonths] = useState<Partial<Record<CogsAdjustmentKey, number>>>({});
  const [tariffInputMonth, setTariffInputMonth] = useState(7);
  const [newBusinessInputMonth, setNewBusinessInputMonth] = useState(7);
  const [rawMaterialInputMonth, setRawMaterialInputMonth] = useState(7);
  const [state, setState] = useState<ViewState>('LOADING');
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<ForecastGenerateResponseDto | null>(null);
  const [downloadState, setDownloadState] = useState<DownloadState>('IDLE');
  const [downloadMessage, setDownloadMessage] = useState('');
  const [excelState, setExcelState] = useState<ExcelState>('IDLE');
  const [excelPreview, setExcelPreview] = useState<ForecastExcelPreviewDto | null>(null);
  const [excelMessage, setExcelMessage] = useState('');
  const [templateDownloading, setTemplateDownloading] = useState(false);
  const [applyConfirmationOpen, setApplyConfirmationOpen] = useState(false);
  const [excelApplied, setExcelApplied] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [isModelApplied, setIsModelApplied] = useState(false);
  const [adjustmentsExpanded, setAdjustmentsExpanded] = useState(false);
  const [inputMetadata, setInputMetadata] = useState<ForecastInputMetadataDto | null>(null);
  const [metadataState, setMetadataState] = useState<'LOADING' | 'READY' | 'ERROR'>('LOADING');
  const [metadataMessage, setMetadataMessage] = useState('');
  const [editingMfgKey, setEditingMfgKey] = useState<string | null>(null);
  const [editingMfgMonth, setEditingMfgMonth] = useState<number | null>(null);
  const [mfgDraftAmount, setMfgDraftAmount] = useState<string>('0');
  const [mfgDraftReason, setMfgDraftReason] = useState<string>('');
  const [editingSgaKey, setEditingSgaKey] = useState<string | null>(null);
  const [editingSgaMonth, setEditingSgaMonth] = useState<number | null>(null);
  const [editingSgaEntryId, setEditingSgaEntryId] = useState<string | null>(null);
  const [sgaDraftAmount, setSgaDraftAmount] = useState<string>('0');
  const [sgaDraftReason, setSgaDraftReason] = useState<string>('');
  const [sgaDraftSourceLabel, setSgaDraftSourceLabel] = useState<string>(MANUAL_SGA_SOURCE_LABEL);
  const [sgaRegisteredEntriesByMonth, setSgaRegisteredEntriesByMonth] = useState<Record<number, SgaRegisteredEntry[]>>({});
  const [editingCogsKey, setEditingCogsKey] = useState<CogsAdjustmentKey | null>(null);
  const [editingCogsMonth, setEditingCogsMonth] = useState<number | null>(null);
  const [cogsDraftAmount, setCogsDraftAmount] = useState<string>('0');
  const [cogsDraftReason, setCogsDraftReason] = useState<string>('');
  const [sgaTab, setSgaTab] = useState<'selling' | 'general_admin'>('selling');
  const [selectedMfgKeys, setSelectedMfgKeys] = useState<Set<string>>(new Set());
  const [selectedSgaKeys, setSelectedSgaKeys] = useState<Set<string>>(new Set());
  const [selectedCogsKeys, setSelectedCogsKeys] = useState<Set<string>>(new Set());
  const [expandedReasons, setExpandedReasons] = useState<Set<string>>(new Set());
  const idempotencyKey = useRef(crypto.randomUUID());
  const submittingRef = useRef(false);
  const downloadPendingRef = useRef(false);
  const templatePendingRef = useRef(false);
  const previewPendingRef = useRef(false);
  const mountedRef = useRef(true);
  const metadataRequestSequence = useRef(0);
  const mfgDrawerRefs = useRef<Record<string, HTMLTableRowElement | null>>({});
  const sgaDrawerRefs = useRef<Record<string, HTMLTableRowElement | null>>({});

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setState('LOADING');
    setMessage('');
    bffClient.models().then((values) => {
      if (!active) return;
      setModels(values);
      setBaseModelId((current) => current || values[0]?.model_id || '');
      setState(values.length ? 'READY' : 'EMPTY');
    }).catch((error: unknown) => {
      if (!active) return;
      const mapped = safeErrorMessage(error);
      setState(mapped.state);
      setMessage(mapped.message);
    });
    return () => {
      active = false;
    };
  }, [loadAttempt]);

  useEffect(() => {
    if (!baseModelId || !models.length) {
      setInputMetadata(null);
      setMetadataState(models.length ? 'LOADING' : 'READY');
      setMetadataMessage('');
      return;
    }
    const sequence = ++metadataRequestSequence.current;
    let active = true;
    setInputMetadata(null);
    setMetadataState('LOADING');
    setMetadataMessage('');
    bffClient.forecastInputMetadata(baseModelId).then((value) => {
      if (!active || sequence !== metadataRequestSequence.current) return;
      setResult(null);
      setMessage('');
      idempotencyKey.current = crypto.randomUUID();
      setInputs((old) => ensureForecastMonths(old, months, value));
      setInputMetadata(value);
      setMetadataState('READY');
      setMetadataMessage('');
    }).catch((error: unknown) => {
      if (!active || sequence !== metadataRequestSequence.current) return;
      const mapped = safeErrorMessage(error);
      if (mapped.state === 'FORBIDDEN') {
        setState('FORBIDDEN');
        setMessage(mapped.message);
        return;
      }
      setMetadataState('ERROR');
      setMetadataMessage(mapped.message);
    });
    return () => {
      active = false;
    };
  }, [baseModelId, models.length, loadAttempt]);

  const parsedStartMonth = parseMonthInput(startMonth);
  const parsedEndMonth = parseMonthInput(endMonth);
  const hasOrderedRange = parsedStartMonth !== null && parsedEndMonth !== null
    && MONTH_MIN <= parsedStartMonth && parsedStartMonth <= MONTH_MAX
    && MONTH_MIN <= parsedEndMonth && parsedEndMonth <= MONTH_MAX
    && parsedStartMonth <= parsedEndMonth;
  const selectedMonthCount = hasOrderedRange && parsedStartMonth !== null && parsedEndMonth !== null
    ? parsedEndMonth - parsedStartMonth + 1
    : 0;
  const rangeValid = hasOrderedRange && selectedMonthCount <= V1_FORECAST_SYNC_MAX_MONTHS;
  const rangeMessage = !hasOrderedRange
    ? '시작 월과 종료 월은 1~12월 범위에서 순서대로 선택하세요.'
    : selectedMonthCount > V1_FORECAST_SYNC_MAX_MONTHS
      ? `선택한 기간은 ${selectedMonthCount}개월입니다. 한 번에 최대 6개월까지 추정할 수 있습니다.`
      : '';
  const months = useMemo(
    () => hasOrderedRange && parsedStartMonth !== null
      ? Array.from({ length: selectedMonthCount }, (_, index) => parsedStartMonth + index)
      : [],
    [hasOrderedRange, selectedMonthCount, parsedStartMonth],
  );

  useEffect(() => {
    setInputs((old) => ensureForecastMonths(old, months, inputMetadata ?? undefined));
    setActiveInputMonth((current) => months.includes(current) ? current : (months[0] ?? current));
  }, [months]);

  useEffect(() => {
    setAdjustmentInputMonth((current) => {
      if (months.includes(current) || !months.length) return current;
      return hasForecastAdjustmentInput(inputs[current], inputMetadata ?? undefined)
        ? current
        : months[0];
    });
  }, [months, inputs, inputMetadata]);

  useEffect(() => {
    const firstMonth = months[0];
    if (firstMonth === undefined) return;
    const adjustmentRegistered = (month: number, section: 'manufacturingAdjustments' | 'sgaAdjustments', key: string) => {
      const entry = inputs[month]?.[section][key];
      return Boolean(entry && hasForecastAdjustmentValue(entry));
    };
    setManufacturingInputMonths((current) => {
      const next = { ...current };
      let changed = false;
      Object.entries(current).forEach(([key, month]) => {
        if (!months.includes(month) && !adjustmentRegistered(month, 'manufacturingAdjustments', key)) {
          next[key] = firstMonth;
          changed = true;
        }
      });
      return changed ? next : current;
    });
    setSgaInputMonths((current) => {
      const next = { ...current };
      let changed = false;
      Object.entries(current).forEach(([key, month]) => {
        const hasLocalEntry = (sgaRegisteredEntriesByMonth[month] ?? []).some((entry) => entry.adjustmentKey === key);
        if (!months.includes(month) && !hasLocalEntry && !adjustmentRegistered(month, 'sgaAdjustments', key)) {
          next[key] = firstMonth;
          changed = true;
        }
      });
      return changed ? next : current;
    });
    setCogsInputMonths((current) => {
      const next = { ...current };
      let changed = false;
      COGS_ADJUSTMENT_ROWS.forEach((row) => {
        const month = current[row.key];
        if (month === undefined || months.includes(month)) return;
        const input = inputs[month];
        const amount = String(input?.[row.amountField] ?? '0');
        const reason = String(input?.[row.reasonField] ?? '');
        if (!hasForecastAdjustmentValue({ amount, reason })) {
          next[row.key] = firstMonth;
          changed = true;
        }
      });
      return changed ? next : current;
    });
    const sectionMonth = (current: number, fields: ForecastAdvancedScalarField[]) => {
      if (months.includes(current)) return current;
      const input = inputs[current];
      if (!input) return firstMonth;
      const defaults = createForecastMonthFormState(current, inputMetadata ?? undefined);
      return fields.some((field) => isForecastAdvancedFieldNonDefault(input, defaults, field)) ? current : firstMonth;
    };
    setTariffInputMonth((current) => sectionMonth(current, ['planNaSaSales', 'naSaSales', 'tariffApplicableRate', 'tariffRate']));
    setNewBusinessInputMonth((current) => sectionMonth(current, [
      'newBusinessGoodsCogsMode', 'newBusinessGoodsCogs', 'newBusinessGoodsCogsReason',
      'ufMbrCogsRate', 'ixCogsRate', 'ufMbrTransportRate', 'ixTransportRate', 'ixPackLiters', 'ixPackCost',
    ]));
    setRawMaterialInputMonth((current) => {
      const basis = inputs[current]?.rawMaterialBasis ?? 'model';
      return sectionMonth(current, [
        'rawMaterialBasis',
        basis === 'direct' ? 'rawMaterialDirect' : 'rawMaterialAdjustment',
        'rawMaterialReason',
        'refundRate',
      ]);
    });
  }, [months, inputs, inputMetadata, sgaRegisteredEntriesByMonth]);

  useEffect(() => {
    setEditingMfgKey(null);
    setEditingMfgMonth(null);
    setMfgDraftAmount('0');
    setMfgDraftReason('');
    setEditingSgaKey(null);
    setEditingSgaMonth(null);
    setEditingSgaEntryId(null);
    setSgaDraftAmount('0');
    setSgaDraftReason('');
    setSgaDraftSourceLabel(MANUAL_SGA_SOURCE_LABEL);
    setEditingCogsKey(null);
    setEditingCogsMonth(null);
    setCogsDraftAmount('0');
    setCogsDraftReason('');
    setSelectedMfgKeys(new Set());
    setSelectedSgaKeys(new Set());
    setSelectedCogsKeys(new Set());
    setExpandedReasons(new Set());
  }, [adjustmentInputMonth]);

  useEffect(() => {
    if (!editingMfgKey) return;
    const drawer = mfgDrawerRefs.current[editingMfgKey];
    if (drawer && typeof drawer.scrollIntoView === 'function') drawer.scrollIntoView({ block: 'center' });
  }, [editingMfgKey]);

  useEffect(() => {
    if (!editingSgaKey) return;
    const drawer = sgaDrawerRefs.current[editingSgaKey];
    if (drawer && typeof drawer.scrollIntoView === 'function') drawer.scrollIntoView({ block: 'center' });
  }, [editingSgaKey, sgaTab]);

  const toggleExpandedReason = (key: string) => {
    setExpandedReasons((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const openMfgEditor = (key: string, month: number, currentAmount: string, currentReason: string) => {
    setEditingMfgKey(key);
    setEditingMfgMonth(month);
    setMfgDraftAmount(currentAmount);
    setMfgDraftReason(currentReason);
  };

  const cancelMfgEditor = () => {
    setEditingMfgKey(null);
    setEditingMfgMonth(null);
    setMfgDraftAmount('0');
    setMfgDraftReason('');
  };

  const saveMfgEditor = (key: string) => {
    if (editingMfgMonth === null) return;
    const month = editingMfgMonth;
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
      const rows = current.manufacturingAdjustments;
      const row = rows[key] ?? { amount: '0', reason: '' };
      return {
        ...old,
        [month]: {
          ...current,
          manufacturingAdjustments: {
            ...rows,
            [key]: { ...row, amount: mfgDraftAmount, reason: mfgDraftReason },
          },
        },
      };
    });
    setEditingMfgKey(null);
    setEditingMfgMonth(null);
    setMfgDraftAmount('0');
    setMfgDraftReason('');
    markDraftChanged();
  };

  const openSgaEditor = (
    key: string,
    month: number,
    currentAmount: string,
    currentReason: string,
    options: { entry?: SgaRegisteredEntry } = {},
  ) => {
    setEditingSgaKey(key);
    setEditingSgaMonth(month);
    const existingEntries = sgaRegisteredEntriesByMonth[month]?.filter((entry) => entry.adjustmentKey === key) ?? [];
    const targetEntry = options.entry ?? existingEntries.find(
      (entry) => entry.sourceLabel === MANUAL_SGA_SOURCE_LABEL || entry.sourceLabel === '직접 조정' || entry.id === `existing:${key}`,
    );
    const hasAggregateWithoutLocalEntries = existingEntries.length === 0
      && ((currentAmount.trim() !== '' && currentAmount.trim() !== '0') || currentReason.trim() !== '');
    setEditingSgaEntryId(targetEntry?.id ?? (hasAggregateWithoutLocalEntries ? `existing:${key}` : null));
    setSgaDraftSourceLabel(targetEntry?.sourceLabel ?? MANUAL_SGA_SOURCE_LABEL);
    if (targetEntry) {
      setSgaDraftAmount(targetEntry.amount);
      setSgaDraftReason(targetEntry.reason);
      return;
    }
    if (existingEntries.length > 0) {
      setSgaDraftAmount('0');
      setSgaDraftReason('');
      return;
    }
    setSgaDraftAmount(currentAmount);
    setSgaDraftReason(currentReason);
  };

  const cancelSgaEditor = () => {
    setEditingSgaKey(null);
    setEditingSgaMonth(null);
    setEditingSgaEntryId(null);
    setSgaDraftAmount('0');
    setSgaDraftReason('');
    setSgaDraftSourceLabel(MANUAL_SGA_SOURCE_LABEL);
  };

  const saveSgaEditor = (key: string) => {
    if (editingSgaMonth === null) return;
    const month = editingSgaMonth;
    const currentEntries = sgaRegisteredEntriesByMonth[month] ?? [];
    const currentInput = inputs[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
    const currentRow = currentInput.sgaAdjustments[key] ?? { amount: '0', reason: '' };
    const baseEntries = withLegacySgaAggregateEntry(currentEntries, key, currentRow);
    const nextEntry: SgaRegisteredEntry = {
      id: editingSgaEntryId ?? crypto.randomUUID(),
      adjustmentKey: key,
      sourceLabel: sgaDraftSourceLabel,
      amount: sgaDraftAmount,
      reason: sgaDraftReason,
    };
    const candidateEntries = editingSgaEntryId
      ? baseEntries.map((entry) => entry.id === editingSgaEntryId ? nextEntry : entry)
      : [...baseEntries, nextEntry];
    const nextEntryIsRegistered = hasForecastAdjustmentValue(nextEntry);
    const nextEntries = nextEntryIsRegistered
      ? candidateEntries
      : candidateEntries.filter((entry) => entry.id !== nextEntry.id);
    const aggregate = aggregateSgaRegisteredEntries(nextEntries.filter((entry) => entry.adjustmentKey === key));
    setSgaRegisteredEntriesByMonth((current) => ({ ...current, [month]: nextEntries }));
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
      const rows = current.sgaAdjustments;
      const row = rows[key] ?? { amount: '0', reason: '' };
      return {
        ...old,
        [month]: {
          ...current,
          sgaAdjustments: {
            ...rows,
            [key]: { ...row, ...aggregate },
          },
        },
      };
    });
    cancelSgaEditor();
    markDraftChanged();
  };

  const clearExcelPreview = () => {
    setExcelState('IDLE');
    setExcelPreview(null);
    setExcelMessage('');
    setExcelApplied(false);
    setApplyConfirmationOpen(false);
  };

  const markDraftChanged = () => {
    setResult(null);
    setMessage('');
    setDownloadState('IDLE');
    setDownloadMessage('');
    setState(models.length ? 'READY' : state);
    idempotencyKey.current = crypto.randomUUID();
  };

  const updateInput = (
    month: number,
    section: ForecastInputSection,
    productCode: string,
    field: 'quantity' | 'amount',
    value: string,
  ) => {
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month);
      if (section === 'sales') {
        const row = current.sales[productCode] ?? { quantity: '0', amount: '0' };
        return {
          ...old,
          [month]: {
            ...current,
            sales: { ...current.sales, [productCode]: { ...row, [field]: value } },
          },
        };
      }
      const rows = current[section];
      const row = rows[productCode] ?? { quantity: '0' };
      return {
        ...old,
        [month]: {
          ...current,
          [section]: { ...rows, [productCode]: { ...row, quantity: value } },
        },
      };
    });
    markDraftChanged();
  };

  const updateAdvanced = (
    month: number,
    field: keyof Omit<ForecastMonthFormState, 'month' | 'sales' | 'production' | 'mcm' | 'manufacturingAdjustments' | 'sgaAdjustments' | 'newBusinessGoodsCogsMode'>,
    value: string,
  ) => {
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
      return { ...old, [month]: { ...current, [field]: value } };
    });
    markDraftChanged();
  };

  const updateNewBusinessGoodsCogsMode = (
    month: number,
    mode: ForecastMonthFormState['newBusinessGoodsCogsMode'],
  ) => {
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
      return {
        ...old,
        [month]: {
          ...current,
          newBusinessGoodsCogsMode: mode,
          ...(mode === 'ACTUAL_YTD_DEFAULT' ? {
            newBusinessGoodsCogs: '',
            newBusinessGoodsCogsReason: '',
          } : {}),
        },
      };
    });
    markDraftChanged();
  };

  const resetMonthInputs = (month: number) => {
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
      const defaults = createForecastMonthFormState(month, inputMetadata ?? undefined);
      return {
        ...old,
        [month]: {
          ...current,
          sales: defaults.sales,
          production: defaults.production,
          mcm: defaults.mcm,
        },
      };
    });
    markDraftChanged();
  };

  const resetAdjustmentInputs = (month: number) => {
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
      const defaults = createForecastMonthFormState(month, inputMetadata ?? undefined);
      return {
        ...old,
        [month]: {
          ...defaults,
          sales: current.sales,
          production: current.production,
          mcm: current.mcm,
        },
      };
    });
    setSgaRegisteredEntriesByMonth((current) => ({ ...current, [month]: [] }));
    setSelectedMfgKeys(new Set());
    setSelectedSgaKeys(new Set());
    setSelectedCogsKeys(new Set());
    setExpandedReasons(new Set());
    markDraftChanged();
  };

  const openCogsEditor = (key: CogsAdjustmentKey, month: number, currentAmount: string, currentReason: string) => {
    setEditingCogsKey(key);
    setEditingCogsMonth(month);
    setCogsDraftAmount(currentAmount);
    setCogsDraftReason(currentReason);
  };

  const cancelCogsEditor = () => {
    setEditingCogsKey(null);
    setEditingCogsMonth(null);
    setCogsDraftAmount('0');
    setCogsDraftReason('');
  };

  const saveCogsEditor = (key: CogsAdjustmentKey) => {
    if (editingCogsMonth === null) return;
    const month = editingCogsMonth;
    const row = COGS_ADJUSTMENT_ROWS.find((item) => item.key === key);
    if (!row) return;
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
      return {
        ...old,
        [month]: {
          ...current,
          [row.amountField]: cogsDraftAmount,
          [row.reasonField]: cogsDraftReason,
        },
      };
    });
    cancelCogsEditor();
    markDraftChanged();
  };

  const handleApplyModel = () => {
    if (!rangeValid || !baseModelId || metadataState !== 'READY' || !inputMetadata) return;
    setInputs((old) => ensureForecastMonths(old, months, inputMetadata));
    setIsModelApplied(true);
    setExcelApplied(false);
    clearExcelPreview();
  };

  const updateBaseModel = (value: string) => {
    setBaseModelId(value);
    setIsModelApplied(false);
    setInputMetadata(null);
    setMetadataState('LOADING');
    setMetadataMessage('');
    setInputs(Object.fromEntries(months.map((month) => [month, createForecastMonthFormState(month)])));
    setSgaRegisteredEntriesByMonth({});
    setAdjustmentInputMonth(months[0] ?? 7);
    setManufacturingInputMonths({});
    setSgaInputMonths({});
    setCogsInputMonths({});
    setTariffInputMonth(months[0] ?? 7);
    setNewBusinessInputMonth(months[0] ?? 7);
    setRawMaterialInputMonth(months[0] ?? 7);
    setResult(null);
    setMessage('');
    setDownloadState('IDLE');
    setDownloadMessage('');
    setState('READY');
    clearExcelPreview();
    idempotencyKey.current = crypto.randomUUID();
  };

  const updateStartMonth = (value: string) => {
    setStartMonth(value);
    setIsModelApplied(false);
    clearExcelPreview();
    markDraftChanged();
  };

  const updateEndMonth = (value: string) => {
    setEndMonth(value);
    setIsModelApplied(false);
    clearExcelPreview();
    markDraftChanged();
  };

  const submit = async () => {
    if (submittingRef.current || state === 'SUBMITTING') return;
    setMessage('');
    setResult(null);
    if (!rangeValid || parsedStartMonth === null || parsedEndMonth === null) {
      setState('VALIDATION_ERROR');
      setMessage(rangeMessage);
      return;
    }
    const base = models.find((item) => item.model_id === baseModelId);
    if (!base) {
      setState('VALIDATION_ERROR');
      setMessage('공개된 기준 모형을 선택하세요.');
      return;
    }
    if (!inputMetadata || metadataState !== 'READY') {
      setState('VALIDATION_ERROR');
      setMessage(metadataMessage || '고급 입력 항목을 확인한 뒤 다시 시도하세요.');
      return;
    }
    if (outOfRangeAdjustmentMonths.length > 0) {
      setState('VALIDATION_ERROR');
      setMessage(`Forecast 기간 밖 비용·원가 조정 적용월을 수정하거나 초기화하세요: ${outOfRangeAdjustmentMonths.map((month) => `${base.model_year}-${String(month).padStart(2, '0')}`).join(', ')}`);
      return;
    }
    const adapted = adaptForecastInput(months, inputs, inputMetadata);
    if (!adapted.value) {
      setState('VALIDATION_ERROR');
      setMessage(adapted.error);
      return;
    }
    const parsed = adapted.value;
    submittingRef.current = true;
    setState('SUBMITTING');
    try {
      const saved = await bffClient.generateForecast({
        base_model_id: baseModelId,
        name,
        model_year: base.model_year,
        version,
        start_month: parsedStartMonth,
        end_month: parsedEndMonth,
        months: parsed,
        idempotency_key: idempotencyKey.current,
      });
      if (!mountedRef.current) return;
      setResult(saved);
      setDownloadState('IDLE');
      setDownloadMessage('');
      setState('SUCCESS');
    } catch (error: unknown) {
      if (!mountedRef.current) return;
      const mapped = safeErrorMessage(error);
      setState(mapped.state);
      setMessage(mapped.message);
    } finally {
      submittingRef.current = false;
    }
  };

  const downloadWorkbook = async () => {
    if (!result?.model_id || downloadPendingRef.current) return;
    downloadPendingRef.current = true;
    setDownloadState('DOWNLOADING');
    setDownloadMessage('');
    try {
      await bffClient.downloadForecastWorkbook(result.model_id);
      if (!mountedRef.current) return;
      setDownloadState('IDLE');
    } catch {
      if (!mountedRef.current) return;
      setDownloadState('FAILED');
      setDownloadMessage('생성된 추정 모형을 내려받을 수 없습니다. 잠시 후 다시 시도하세요.');
    } finally {
      downloadPendingRef.current = false;
    }
  };

  const downloadInputTemplate = async () => {
    if (templatePendingRef.current) return;
    templatePendingRef.current = true;
    setTemplateDownloading(true);
    setExcelMessage('');
    try {
      await bffClient.downloadForecastInputTemplate();
    } catch {
      if (mountedRef.current) setExcelMessage('엑셀 입력 양식을 내려받을 수 없습니다. 잠시 후 다시 시도하세요.');
    } finally {
      templatePendingRef.current = false;
      if (mountedRef.current) setTemplateDownloading(false);
    }
  };

  const previewExcel = async (file: File) => {
    if (previewPendingRef.current) return;
    if (!rangeValid || parsedStartMonth === null || parsedEndMonth === null) {
      setExcelState('ERROR');
      setExcelMessage(rangeMessage || '추정 기간을 먼저 확인하세요.');
      return;
    }
    previewPendingRef.current = true;
    setExcelState('UPLOADING');
    setExcelPreview(null);
    setExcelMessage('');
    setExcelApplied(false);
    setApplyConfirmationOpen(false);
    try {
      const preview = await bffClient.previewForecastExcel(file, parsedStartMonth, parsedEndMonth);
      if (!mountedRef.current) return;
      setExcelPreview(preview);
      setExcelState('READY');
      setExcelMessage(preview.blocking
        ? '오류를 수정한 엑셀 파일을 다시 업로드하세요.'
        : '검토가 완료되었습니다. 적용 전까지 현재 화면 입력은 유지됩니다.');
    } catch (error: unknown) {
      if (!mountedRef.current) return;
      setExcelState('ERROR');
      setExcelMessage(error instanceof ApiClientError && error.code === 'FORBIDDEN'
        ? '엑셀 일괄입력을 사용할 권한이 없습니다.'
        : '엑셀 파일을 확인하지 못했습니다. 파일 형식과 입력 내용을 확인하세요.');
    } finally {
      previewPendingRef.current = false;
    }
  };

  const hasExistingPlanValues = months.some((month) => {
    const monthInput = inputs[month];
    if (!monthInput) return false;
    return [...Object.values(monthInput.sales).flatMap((row) => [row.quantity, row.amount]),
      ...Object.values(monthInput.production).map((row) => row.quantity)]
      .some((value) => value.trim() !== '' && value.trim() !== '0');
  });

  const applyExcelPreview = () => {
    if (!excelPreview || excelPreview.blocking) return;
    try {
      setInputs((current) => applyForecastExcelPreview(current, months, excelPreview, inputMetadata ?? undefined));
    } catch {
      setExcelState('ERROR');
      setExcelMessage('엑셀 확인 결과를 적용할 수 없습니다. 파일을 다시 확인하세요.');
      setApplyConfirmationOpen(false);
      return;
    }
    setActiveInputMonth(months[0] ?? activeInputMonth);
    setExcelApplied(true);
    setExcelMessage('판매·생산계획을 화면 입력값으로 적용했습니다. Grid에서 수정한 뒤 추정 계산을 시작하세요.');
    setApplyConfirmationOpen(false);
    markDraftChanged();
  };

  const requestExcelApply = () => {
    if (!excelPreview || excelPreview.blocking) return;
    if (hasExistingPlanValues) {
      setApplyConfirmationOpen(true);
      return;
    }
    applyExcelPreview();
  };

  const controlsDisabled = state === 'SUBMITTING' || state === 'LOADING' || excelState === 'UPLOADING';
  const advancedControlsDisabled = controlsDisabled || metadataState !== 'READY';
  const selectedBaseModel = models.find((model) => model.model_id === baseModelId) || null;
  const outOfRangeAdjustmentMonths = findOutOfRangeForecastAdjustmentMonths(
    months,
    inputs,
    inputMetadata ?? undefined,
  );
  const submitDisabled = controlsDisabled || !isModelApplied || !baseModelId || !rangeValid || !models.length
    || metadataState !== 'READY' || !inputMetadata || outOfRangeAdjustmentMonths.length > 0;
  const activeMonthInput = inputs[activeInputMonth] ?? createForecastMonthFormState(activeInputMonth, inputMetadata ?? undefined);
  const monthInput = (month: number) => inputs[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
  const monthLabel = (month: number) => `${selectedBaseModel?.model_year ?? '----'}-${String(month).padStart(2, '0')}`;
  const adjustmentResetMonth = outOfRangeAdjustmentMonths[0] ?? adjustmentInputMonth;
  const tariffMonthInput = monthInput(tariffInputMonth);
  const newBusinessMonthInput = monthInput(newBusinessInputMonth);
  const rawMaterialMonthInput = monthInput(rawMaterialInputMonth);
  const applyAdjustmentMonthToAll = (month: number) => {
    if (month === adjustmentInputMonth) return;
    setAdjustmentInputMonth(month);
    setManufacturingInputMonths(Object.fromEntries((inputMetadata?.manufacturing ?? []).map((item) => [item.adjustment_key, month])));
    setSgaInputMonths(Object.fromEntries((inputMetadata?.sga ?? []).map((item) => [item.adjustment_key, month])));
    setCogsInputMonths(Object.fromEntries(COGS_ADJUSTMENT_ROWS.map((item) => [item.key, month])));
    setTariffInputMonth(month);
    setNewBusinessInputMonth(month);
    setRawMaterialInputMonth(month);
  };
  const mfgAdjustedList = useMemo(() => Object.entries(inputs).flatMap(([monthKey, input]) => {
    const month = Number(monthKey);
    return (inputMetadata?.manufacturing ?? []).flatMap((item) => {
      const entry = input.manufacturingAdjustments[item.adjustment_key];
      const registered = entry && hasForecastAdjustmentValue(entry);
      return registered ? [{ ...item, month, entry, selectionKey: `${month}:${item.adjustment_key}` }] : [];
    });
  }), [inputs, inputMetadata?.manufacturing]);
  const sgaAdjustedList = useMemo(() => {
    const metadataByKey = new Map((inputMetadata?.sga ?? []).map((item) => [item.adjustment_key, item]));
    return Object.entries(inputs).flatMap(([monthKey, input]) => {
      const month = Number(monthKey);
      const localEntries = sgaRegisteredEntriesByMonth[month] ?? [];
      const localKeys = new Set(localEntries.map((entry) => entry.adjustmentKey));
      const fallbackEntries: SgaRegisteredEntry[] = (inputMetadata?.sga ?? []).flatMap((item) => {
        const row = input.sgaAdjustments[item.adjustment_key];
        const registered = row && hasForecastAdjustmentValue(row);
        return registered && !localKeys.has(item.adjustment_key) ? [{
          id: `existing:${item.adjustment_key}`,
          adjustmentKey: item.adjustment_key,
          sourceLabel: MANUAL_SGA_SOURCE_LABEL,
          amount: row.amount,
          reason: row.reason,
        }] : [];
      });
      return [...localEntries, ...fallbackEntries].flatMap((entry) => {
        const metadata = metadataByKey.get(entry.adjustmentKey);
        return metadata ? [{ ...entry, metadata, month, selectionKey: `${month}:${entry.id}` }] : [];
      });
    });
  }, [inputs, inputMetadata?.sga, sgaRegisteredEntriesByMonth]);
  const sgaAccountSummaries = useMemo(() => {
    const grouped = new Map<string, typeof sgaAdjustedList>();
    sgaAdjustedList.forEach((entry) => {
      const groupKey = `${entry.month}:${entry.adjustmentKey}`;
      const current = grouped.get(groupKey) ?? [];
      grouped.set(groupKey, [...current, entry]);
    });
    return Array.from(grouped.values()).flatMap((entries) => {
      if (entries.length < 2) return [];
      const metadata = entries[0].metadata;
      const month = entries[0].month;
      const total = entries.reduce((sum, entry) => sum + parseAdjustmentAmount(entry.amount), 0);
      const baselineRaw = metadata.monthly_baseline_amounts?.[String(month)];
      const baseline = typeof baselineRaw === 'number' && Number.isFinite(baselineRaw) ? baselineRaw : undefined;
      return [{ adjustmentKey: entries[0].adjustmentKey, metadata, month, entries, total, baseline }];
    });
  }, [sgaAdjustedList]);
  const cogsAdjustedList = useMemo(() => Object.entries(inputs).flatMap(([monthKey, input]) => {
    const month = Number(monthKey);
    return COGS_ADJUSTMENT_ROWS.flatMap((row) => {
      const amount = String(input[row.amountField]);
      const reason = String(input[row.reasonField]);
      const registered = hasForecastAdjustmentValue({ amount, reason });
      return registered ? [{ ...row, month, amount, reason, selectionKey: `${month}:${row.key}` }] : [];
    });
  }), [inputs]);
  const deleteSelectedMfg = () => {
    if (!selectedMfgKeys.size) return;
    setInputs((old) => {
      const next = { ...old };
      mfgAdjustedList.filter((item) => selectedMfgKeys.has(item.selectionKey)).forEach((item) => {
        const current = next[item.month] ?? createForecastMonthFormState(item.month, inputMetadata ?? undefined);
        next[item.month] = {
          ...current,
          manufacturingAdjustments: {
            ...current.manufacturingAdjustments,
            [item.adjustment_key]: { amount: '0', reason: '' },
          },
        };
      });
      return next;
    });
    setSelectedMfgKeys(new Set());
    markDraftChanged();
  };
  const deleteSelectedSga = () => {
    if (!selectedSgaKeys.size) return;
    const selectedEntries = sgaAdjustedList.filter((item) => selectedSgaKeys.has(item.selectionKey));
    const affectedMonths = new Set(selectedEntries.map((item) => item.month));
    const affectedPairs = new Set(selectedEntries.map((item) => `${item.month}:${item.adjustmentKey}`));
    const remainingByMonth = new Map<number, SgaRegisteredEntry[]>();
    affectedMonths.forEach((month) => {
      remainingByMonth.set(month, sgaAdjustedList
        .filter((item) => item.month === month && !selectedSgaKeys.has(item.selectionKey))
        .map(({ metadata: _metadata, month: _month, selectionKey: _selectionKey, ...entry }) => entry));
    });
    setSgaRegisteredEntriesByMonth((current) => {
      const next = { ...current };
      remainingByMonth.forEach((entries, month) => { next[month] = entries; });
      return next;
    });
    setInputs((old) => {
      const next = { ...old };
      affectedPairs.forEach((pair) => {
        const separator = pair.indexOf(':');
        const month = Number(pair.slice(0, separator));
        const adjustmentKey = pair.slice(separator + 1);
        const current = next[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
        const remainingEntries = remainingByMonth.get(month) ?? [];
        next[month] = {
          ...current,
          sgaAdjustments: {
            ...current.sgaAdjustments,
            [adjustmentKey]: aggregateSgaRegisteredEntries(remainingEntries.filter((entry) => entry.adjustmentKey === adjustmentKey)),
          },
        };
      });
      return next;
    });
    setSelectedSgaKeys(new Set());
    markDraftChanged();
  };
  const deleteSelectedCogs = () => {
    if (!selectedCogsKeys.size) return;
    setInputs((old) => {
      const next = { ...old };
      cogsAdjustedList.filter((item) => selectedCogsKeys.has(item.selectionKey)).forEach((item) => {
        const current = next[item.month] ?? createForecastMonthFormState(item.month, inputMetadata ?? undefined);
        next[item.month] = { ...current, [item.amountField]: '0', [item.reasonField]: '' };
      });
      return next;
    });
    setSelectedCogsKeys(new Set());
    markDraftChanged();
  };

  if (state === 'LOADING') {
    return <section className="forecast-workflow forecast-workflow--state" aria-busy="true">
      <div className="forecast-workflow__state-card"><span className="forecast-workflow__spinner" aria-hidden="true" />
        <h2>추정 산출 준비 중</h2><p>사용 가능한 기준 모형을 확인하고 있습니다.</p>
      </div>
    </section>;
  }
  if (state === 'EMPTY') {
    return <section className="forecast-workflow forecast-workflow--state">
      <div className="forecast-workflow__state-card"><Database size={28} aria-hidden="true" />
        <h2>사용 가능한 기준 모형이 없습니다.</h2><p>공개된 모형을 먼저 준비한 뒤 추정 산출을 실행하세요.</p>
        <button type="button" className="forecast-workflow__secondary" onClick={() => setLoadAttempt((value) => value + 1)}>다시 확인</button>
        {onNavigateToManagement && <button type="button" className="forecast-workflow__link" onClick={onNavigateToManagement}>모형 관리로 이동</button>}
      </div>
    </section>;
  }
  if (state === 'FORBIDDEN') {
    return <section className="forecast-workflow forecast-workflow--state">
      <div className="forecast-workflow__state-card"><LockKeyhole size={28} aria-hidden="true" />
        <h2>추정 산출 권한이 없습니다.</h2><p role="alert">{message || '관리자 권한으로 로그인해 주세요.'}</p>
      </div>
    </section>;
  }
  if (state === 'ERROR' && !models.length) {
    return <section className="forecast-workflow forecast-workflow--state">
      <div className="forecast-workflow__state-card"><ShieldCheck size={28} aria-hidden="true" />
        <h2>추정 산출을 불러오지 못했습니다.</h2><p role="alert">{message}</p>
        <button type="button" className="forecast-workflow__secondary" onClick={() => setLoadAttempt((value) => value + 1)}>다시 시도</button>
      </div>
    </section>;
  }

  return <section className="forecast-workflow" aria-labelledby="forecast-workflow-title">
    <header className="forecast-workflow__header">
      <div className="forecast-workflow__header-mark" aria-hidden="true"><Calculator size={22} /></div>
      <div>
        <h1 id="forecast-workflow-title">추정 산출</h1>
        <p>선택한 기준 모형과 월별 판매·생산 계획 및 조정을 바탕으로 향후 손익 추정 모형을 산출합니다.</p>
      </div>
      <div className="forecast-workflow__header-badges">
        <span className="forecast-workflow__contract-badge forecast-workflow__contract-badge--violet">최대 연속 6개월</span>
        <span className="forecast-workflow__contract-badge">입력 잠금 보호 적용</span>
      </div>
    </header>

    <div className="forecast-workflow__notice"><ShieldCheck size={18} aria-hidden="true" /><span>선택한 기준 모형과 월별 입력으로 비공개 추정 모형을 생성합니다. 산출 중에는 모든 입력 필드가 안전하게 잠깁니다.</span></div>

    <div className="forecast-workflow__grid">
      <section className="forecast-workflow__card forecast-workflow__card--setup" aria-labelledby="forecast-setup-title">
        <div className="forecast-workflow__card-heading">
          <div className="forecast-workflow__card-heading-left">
            <h2 id="forecast-setup-title">모형/기간 선택</h2>
          </div>
          <span className="forecast-workflow__step-state forecast-workflow__step-state--required">필수 입력</span>
        </div>
        <div className="forecast-workflow__form-grid">
          <label className="forecast-workflow__field forecast-workflow__field--wide">기준 모형
            <select disabled={controlsDisabled} value={baseModelId} onChange={(event) => updateBaseModel(event.target.value)}>
              {models.map((model) => <option key={model.model_id} value={model.model_id}>
                {model.display_name} · {model.model_year}년 ({model.start_month}~{model.end_month}월)
              </option>)}
            </select>
          </label>
          <label className="forecast-workflow__field">시작 월
            <EditableNumericInput
              disabled={controlsDisabled}
              mode="month"
              min={MONTH_MIN}
              max={MONTH_MAX}
              value={startMonth}
              onChange={updateStartMonth}
              onValueBlur={(value) => updateStartMonth(normalizeMonthInput(value))}
            />
          </label>
          <label className="forecast-workflow__field">종료 월
            <EditableNumericInput
              disabled={controlsDisabled}
              mode="month"
              min={MONTH_MIN}
              max={MONTH_MAX}
              value={endMonth}
              onChange={updateEndMonth}
              onValueBlur={(value) => updateEndMonth(normalizeMonthInput(value))}
            />
          </label>
          <label className="forecast-workflow__field">모형 표시명
            <input disabled={controlsDisabled} value={name} onChange={(event) => { setName(event.target.value); idempotencyKey.current = crypto.randomUUID(); }} />
          </label>
          <label className="forecast-workflow__field">버전
            <input disabled={controlsDisabled} value={version} onChange={(event) => { setVersion(event.target.value); idempotencyKey.current = crypto.randomUUID(); }} />
          </label>
          <div className="forecast-workflow__field forecast-workflow__field--btn">
            <button
              type="button"
              className={`forecast-workflow__apply-model-btn ${isModelApplied ? 'is-applied' : ''}`}
              disabled={controlsDisabled || !rangeValid || !baseModelId || metadataState !== 'READY' || !inputMetadata}
              onClick={handleApplyModel}
            >
              {isModelApplied ? '✓ 적용 완료' : '모형 적용'}
            </button>
          </div>
        </div>
        {!rangeValid && <div className="forecast-workflow__range-note is-invalid" role="alert">
          <span>{rangeMessage}</span><strong>기간을 1~12월 순서대로 최대 6개월 이내로 설정해 주세요.</strong>
        </div>}
      </section>

      {!isModelApplied ? <div className="forecast-workflow__unapplied-guide" role="status">
        <Calculator size={18} color="#ff5f1f" aria-hidden="true" />
        <span>기준 모형과 기간을 설정한 후 <strong>[모형 적용]</strong> 버튼을 클릭하면 해당 모형의 계획값이 기본으로 적용되며 엑셀 업로드 및 편집이 활성화됩니다.</span>
      </div> : <>
      <section className="forecast-workflow__card forecast-workflow__card--bulk" aria-labelledby="forecast-bulk-title">
        <div className="forecast-workflow__card-heading">
          <div className="forecast-workflow__card-heading-left"><h2 id="forecast-bulk-title">판매·생산 엑셀 업로드</h2></div>
          <span className="forecast-workflow__step-state">선택 입력</span>
        </div>
        <p className="forecast-workflow__helper">판매계획과 생산계획을 엑셀로 확인한 뒤 화면 입력값으로 적용합니다. 엑셀 업로드만으로는 추정 계산이 실행되지 않습니다.</p>
        <div className="forecast-workflow__bulk-actions">
          <button type="button" className="forecast-workflow__template-button" disabled={controlsDisabled || templateDownloading} onClick={downloadInputTemplate}>
            <Download size={15} aria-hidden="true" />{templateDownloading ? '양식 준비 중...' : '엑셀 양식 다운로드 (.xlsx)'}
          </button>
          <label className={`forecast-workflow__upload-button ${(controlsDisabled || !rangeValid) ? 'is-disabled' : ''}`}>
            <Upload size={15} aria-hidden="true" />{excelState === 'UPLOADING' ? '업로드 및 확인 중...' : '엑셀 업로드 (Preview)'}
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              aria-label="엑셀 파일 선택"
              disabled={controlsDisabled || !rangeValid}
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                event.currentTarget.value = '';
                if (file) void previewExcel(file);
              }}
            />
          </label>
        </div>
        {excelMessage && <p className={`forecast-workflow__bulk-message ${(excelState === 'ERROR' || excelPreview?.blocking) ? 'is-error' : ''}`} role={(excelState === 'ERROR' || excelPreview?.blocking) ? 'alert' : 'status'}>{excelMessage}</p>}
        {excelPreview && <section className="forecast-workflow__preview" aria-labelledby="forecast-preview-title">
          <div className="forecast-workflow__preview-heading">
            <div><FileSpreadsheet size={22} color="#0284c7" aria-hidden="true" /><div><h3 id="forecast-preview-title">Excel 데이터 검증 및 Preview</h3><p>{excelPreview.source_filename}</p></div></div>
            <span className={`forecast-workflow__preview-status-pill ${excelPreview.blocking ? 'is-error' : 'is-valid'}`}>{excelPreview.blocking ? `오류 ${excelPreview.issues.filter((issue) => issue.blocking).length}건 (차단됨)` : (excelApplied ? '입력값 적용 완료' : '적용 가능')}</span>
          </div>
          <div className="forecast-workflow__preview-counts">
            <div><span>판매계획 데이터</span><strong>{excelPreview.sales_rows.length}건</strong></div>
            <div><span>생산계획 데이터</span><strong>{excelPreview.business_production_rows.length}건</strong></div>
            <div><span>검증 이슈 / 주의</span><strong>{excelPreview.issues.length}건</strong></div>
          </div>
          <div className="forecast-workflow__preview-units" aria-label="단위별 입력 요약">
            {excelPreview.sales_summary.map((summary) => <div key={`sales-${summary.unit}`}><span>{summary.unit === 'm' ? 'FS 판매' : summary.unit === 'PCS' ? '완제품 판매' : summary.unit === 'L' ? 'IX 판매' : '기타 판매'}</span><strong>{summary.quantity_total.toLocaleString('ko-KR')} {summary.unit}</strong><small>{summary.row_count}건</small></div>)}
            {excelPreview.production_summary.map((summary) => <div key={`production-${summary.unit}`}><span>{summary.unit === 'm' ? '전공정 생산' : '후공정 생산'}</span><strong>{summary.quantity_total.toLocaleString('ko-KR')} {summary.unit}</strong><small>{summary.row_count}건</small></div>)}
          </div>
          {excelPreview.issues.length > 0 && <div className="forecast-workflow__issue-table-wrap">
            <table className="forecast-workflow__issue-table">
              <thead><tr><th scope="col">Sheet</th><th scope="col">행</th><th scope="col">필드</th><th scope="col">오류 및 주의 내용</th></tr></thead>
              <tbody>{excelPreview.issues.map((issue, index) => <tr key={`${issue.source_sheet}-${issue.source_row}-${issue.field}-${issue.code}-${index}`} className={issue.blocking ? 'is-blocking' : ''}>
                <td>{issue.source_sheet}</td><td>{issue.source_row}</td><td>{issue.field}</td><td><span>{issue.message}</span><small>{issue.severity === 'ERROR' ? '오류' : '주의'}</small></td>
              </tr>)}</tbody>
            </table>
          </div>}
          <div className="forecast-workflow__preview-footer">
            <p><AlertCircle size={15} aria-hidden="true" />적용하면 판매·생산계획만 교체됩니다. MCM과 고급 조정은 유지됩니다.</p>
            <button type="button" className="forecast-workflow__primary" disabled={controlsDisabled || excelPreview.blocking || excelApplied} onClick={requestExcelApply}>
              {excelApplied ? '추정 입력값 적용 완료' : '추정 입력값으로 적용'}
            </button>
          </div>
        </section>}
        {applyConfirmationOpen && <div className="forecast-workflow__apply-dialog" role="dialog" aria-modal="true" aria-labelledby="forecast-apply-title">
          <div><h3 id="forecast-apply-title">판매·생산계획을 교체하시겠습니까?</h3><p>현재 입력된 판매·생산계획을 Excel 데이터로 교체합니다. MCM 및 고급 조정 입력은 유지됩니다.</p>
            <div><button type="button" className="forecast-workflow__secondary" onClick={() => setApplyConfirmationOpen(false)}>취소</button><button type="button" className="forecast-workflow__primary" onClick={applyExcelPreview}>적용</button></div>
          </div>
        </div>}
      </section>

      <section className="forecast-workflow__card forecast-workflow__card--inputs" aria-labelledby="forecast-inputs-title">
        <div className="forecast-workflow__card-heading">
          <div className="forecast-workflow__card-heading-left"><h2 id="forecast-inputs-title">판매·생산 계획 직접입력</h2></div>
          <span className="forecast-workflow__step-state forecast-workflow__step-state--active">월별 독립 입력</span>
        </div>
        {metadataState === 'LOADING' && <p className="forecast-workflow__metadata-note" aria-live="polite">선택한 기준 모형의 고급 입력 항목을 불러오는 중입니다.</p>}
        {metadataState === 'ERROR' && <p className="forecast-workflow__metadata-note is-error" role="alert">고급 입력 항목을 불러오지 못했습니다. 기준 모형을 다시 선택하거나 잠시 후 다시 시도하세요.</p>}
        {months.length ? <>
          <div className="forecast-workflow__month-tabs" role="tablist" aria-label="입력 월 선택">
            {months.map((month) => <button
              key={month}
              type="button"
              role="tab"
              aria-selected={activeInputMonth === month}
              className={activeInputMonth === month ? 'is-active' : ''}
              disabled={controlsDisabled}
              onClick={() => setActiveInputMonth(month)}
            >{String(month).padStart(2, '0')}월</button>)}
            <span>{activeInputMonth}월 입력 편집 중</span>
            <button type="button" className="forecast-workflow__reset" disabled={controlsDisabled} onClick={() => resetMonthInputs(activeInputMonth)}>
              <RotateCcw size={13} aria-hidden="true" /> 선택 월 판매·생산 0으로 초기화
            </button>
          </div>

          <section className="forecast-workflow__input-section" aria-labelledby="forecast-sales-title">
            <div className="forecast-workflow__input-heading"><div><h3 id="forecast-sales-title">판매계획 ({String(activeInputMonth).padStart(2, '0')}월)</h3><p>제품별 판매수량과 예상 매출액을 입력합니다.</p></div></div>
            <div className="forecast-workflow__table-scroll">
              <table className="forecast-workflow__input-table forecast-workflow__planning-table">
                <thead><tr><th scope="col" className="forecast-workflow__cell--center">구분</th><th scope="col" className="forecast-workflow__cell--center">상세 구분</th><th scope="col" className="forecast-workflow__cell--center">단위</th><th scope="col" className="forecast-workflow__cell--center">판매수량</th><th scope="col" className="forecast-workflow__cell--center">매출액 (원)</th></tr></thead>
                <tbody>{SALES_PRODUCTS.map((product) => <tr key={product.code}>
                  <th scope="row" className="forecast-workflow__cell--center">{product.category}</th><td className="forecast-workflow__cell--center"><strong>{product.label}</strong></td><td className="forecast-workflow__cell--center"><span className={`forecast-workflow__unit forecast-workflow__unit--${product.unit === 'm' ? 'length' : 'quantity'}`}>{product.unit}</span></td>
                  <td className="forecast-workflow__cell--number"><FormattedNumericInput disabled={controlsDisabled} ariaLabel={`${activeInputMonth}월 ${product.code} 판매수량`} value={activeMonthInput.sales[product.code]?.quantity ?? ''} onChange={(value) => updateInput(activeInputMonth, 'sales', product.code, 'quantity', value)} /></td>
                  <td className="forecast-workflow__cell--number"><FormattedNumericInput disabled={controlsDisabled} ariaLabel={`${activeInputMonth}월 ${product.code} 매출액`} value={activeMonthInput.sales[product.code]?.amount ?? ''} onChange={(value) => updateInput(activeInputMonth, 'sales', product.code, 'amount', value)} /></td>
                </tr>)}</tbody>
              </table>
            </div>
          </section>

          <div className="forecast-workflow__production-grid">
            <section className="forecast-workflow__input-section" aria-labelledby="forecast-production-title">
              <div className="forecast-workflow__input-heading"><div><h3 id="forecast-production-title">생산계획 ({String(activeInputMonth).padStart(2, '0')}월)</h3><p>공정과 제품군별 예상 생산수량을 입력합니다.</p></div></div>
              <div className="forecast-workflow__table-scroll">
                <table className="forecast-workflow__input-table forecast-workflow__input-table--compact forecast-workflow__planning-table">
                  <thead><tr><th scope="col" className="forecast-workflow__cell--center">공정</th><th scope="col" className="forecast-workflow__cell--center">제품군</th><th scope="col" className="forecast-workflow__cell--center">생산수량</th><th scope="col" className="forecast-workflow__cell--center">단위</th></tr></thead>
                  <tbody>{BUSINESS_PRODUCTION_ROWS.map((row) => <tr key={row.key}>
                    <th scope="row" className="forecast-workflow__cell--center">{row.process}</th><td className="forecast-workflow__cell--center">{row.label}</td>
                    <td className="forecast-workflow__cell--number"><FormattedNumericInput disabled={controlsDisabled} ariaLabel={`${activeInputMonth}월 ${row.process} ${row.productGroup} 생산수량`} value={activeMonthInput.production[row.key]?.quantity ?? ''} onChange={(value) => updateInput(activeInputMonth, 'production', row.key, 'quantity', value)} /></td>
                    <td className="forecast-workflow__cell--center"><span className={`forecast-workflow__unit forecast-workflow__unit--${row.unit === 'm' ? 'length' : 'quantity'}`}>{row.unit}</span></td>
                  </tr>)}</tbody>
                </table>
              </div>
            </section>

            <section className="forecast-workflow__input-section" aria-labelledby="forecast-mcm-title">
              <div className="forecast-workflow__input-heading"><div><h3 id="forecast-mcm-title">MCM 유상사급 ({String(activeInputMonth).padStart(2, '0')}월)</h3><p>유상사급 대상 제품의 월별 수량을 입력합니다.</p></div></div>
              <div className="forecast-workflow__table-scroll">
                <table className="forecast-workflow__input-table forecast-workflow__input-table--compact forecast-workflow__planning-table">
                  <thead><tr><th scope="col" className="forecast-workflow__cell--center">제품코드</th><th scope="col" className="forecast-workflow__cell--center">단위</th><th scope="col" className="forecast-workflow__cell--center">MCM 수량</th></tr></thead>
                  <tbody>{MCM_PRODUCTS.map((product) => <tr key={product.code}>
                    <th scope="row" className="forecast-workflow__cell--center">{product.code}</th><td className="forecast-workflow__cell--center"><span className="forecast-workflow__unit forecast-workflow__unit--quantity">{product.unit}</span></td>
                    <td className="forecast-workflow__cell--number"><FormattedNumericInput disabled={controlsDisabled} ariaLabel={`${activeInputMonth}월 ${product.code} MCM 수량`} value={activeMonthInput.mcm[product.code]?.quantity ?? ''} onChange={(value) => updateInput(activeInputMonth, 'mcm', product.code, 'quantity', value)} /></td>
                  </tr>)}</tbody>
                </table>
              </div>
              <p className="forecast-workflow__boundary-note">입력한 400/440 수량은 별도로 유지되며 화면에서 자동 배부하지 않습니다. 제품별 배부는 동일 월 400/440 생산구성비를 기준으로 서버에서 자동 배부합니다.</p>
            </section>
          </div>

          <details className="forecast-workflow__advanced" onToggle={(event) => setAdjustmentsExpanded(event.currentTarget.open)}>
            <summary aria-expanded={adjustmentsExpanded}><span>비용 및 원가 조정</span><span className="forecast-workflow__advanced-toggle-label">{adjustmentsExpanded ? '접기' : '펼치기'}</span></summary>
            <div
              className="forecast-workflow__adjustment-month-toolbar"
              role="group"
              aria-label="비용 및 원가 조정 적용월"
            >
              <div className="forecast-workflow__month-tabs forecast-workflow__month-tabs--adjustment" role="tablist" aria-label="비용 및 원가 조정 적용월 선택">
                <span id="forecast-adjustment-month-label" className="forecast-workflow__adjustment-month-label">적용월</span>
                {months.map((month) => <button
                  key={month}
                  type="button"
                  role="tab"
                  aria-selected={adjustmentInputMonth === month}
                  aria-label={`비용 및 원가 조정 ${String(month).padStart(2, '0')}월`}
                  aria-describedby="forecast-adjustment-month-help"
                  className={adjustmentInputMonth === month ? 'is-active' : ''}
                  disabled={advancedControlsDisabled}
                  onClick={() => applyAdjustmentMonthToAll(month)}
                >{String(month).padStart(2, '0')}월</button>)}
              </div>
              <p id="forecast-adjustment-month-help" className="forecast-workflow__adjustment-month-help">선택한 월을 모든 비용 행에 적용합니다. 각 행의 적용월은 이후 개별 변경할 수 있습니다.</p>
              <button type="button" className="forecast-workflow__reset" disabled={advancedControlsDisabled} onClick={() => resetAdjustmentInputs(adjustmentResetMonth)}>
                <RotateCcw size={13} aria-hidden="true" />
                {outOfRangeAdjustmentMonths.length > 0 ? `${monthLabel(adjustmentResetMonth)} 조정 초기화` : '선택 적용월 조정 초기화'}
              </button>
            </div>
            {outOfRangeAdjustmentMonths.length > 0 && <div className="forecast-workflow__range-note is-invalid forecast-workflow__adjustment-range-alert" role="alert">
              <span>Forecast 기간 밖 비용·원가 조정이 보존되어 있습니다: {outOfRangeAdjustmentMonths.map((month) => `${selectedBaseModel?.model_year ?? '----'}-${String(month).padStart(2, '0')}`).join(', ')}</span>
              <strong>해당 적용월을 선택해 조정을 초기화하거나 기간 범위 안에서 다시 입력한 뒤 제출하세요.</strong>
            </div>}
            <div className="forecast-workflow__adjustment-grid">
              <section className="forecast-workflow__input-section forecast-workflow__adjustment-span forecast-workflow__adjustment-node--mfg-table" aria-labelledby="forecast-manufacturing-adjustments-title">
                <div className="forecast-workflow__input-heading"><div><h3 id="forecast-manufacturing-adjustments-title">제조경비 조정액</h3><p>적용월별 제조 계정의 기존 조정 의미를 그대로 유지합니다.</p></div><span className="forecast-workflow__unit-badge">(단위: 원)</span></div>
                <div className="forecast-workflow__table-scroll">
                  <table className="forecast-workflow__input-table forecast-workflow__cost-table">
                    <thead><tr className="forecast-workflow__header-row--center"><th scope="col" className="forecast-workflow__cell--center">적용월</th><th scope="col" className="forecast-workflow__cell--center">구분</th><th scope="col" className="forecast-workflow__cell--center">계정명</th><th scope="col" className="forecast-workflow__cell--number">계획</th><th scope="col" className="forecast-workflow__cell--number">예상금액(자동)</th><th scope="col" className="forecast-workflow__cell--number">조정액</th><th scope="col" className="forecast-workflow__cell--action">조정</th></tr></thead>
                    <tbody>{(inputMetadata?.manufacturing ?? []).map((item) => {
                      const rowMonth = manufacturingInputMonths[item.adjustment_key] ?? (months[0] ?? adjustmentInputMonth);
                      const row = monthInput(rowMonth).manufacturingAdjustments[item.adjustment_key] ?? { amount: '0', reason: '' };
                      const baselineRaw = item.monthly_baseline_amounts?.[String(rowMonth)];
                      const baseline = typeof baselineRaw === 'number' && Number.isFinite(baselineRaw) ? baselineRaw : undefined;
                      const baselineDisplay = formatKrwAmount(baseline);
                      const adjNum = Number(row.amount.replace(/,/g, '').trim()) || 0;
                      const expectedDisplay = baseline === undefined ? '—' : formatKrwAmount(calculateAdjustmentExpectedAmount(baseline, row.amount));
                      const hasAdjustment = hasForecastAdjustmentValue(row);
                      const isEditing = editingMfgKey === item.adjustment_key && editingMfgMonth === rowMonth;

                      return (
                        <React.Fragment key={item.adjustment_key}>
                          <tr>
                            <td className="forecast-workflow__cell--center"><ForecastMonthSelect ariaLabel={`${item.display_name} 제조경비 적용월`} disabled={advancedControlsDisabled} months={months} modelYear={selectedBaseModel?.model_year} preservedMonths={outOfRangeAdjustmentMonths} value={rowMonth} onChange={(month) => { if (editingMfgKey === item.adjustment_key) cancelMfgEditor(); setManufacturingInputMonths((current) => ({ ...current, [item.adjustment_key]: month })); }} /></td>
                            <td className="forecast-workflow__cell--center"><span className="forecast-workflow__section-badge forecast-workflow__section-badge--manufacturing">제조</span></td>
                            <th scope="row" className="forecast-workflow__cell--center">{item.display_name}</th>
                            <td className="forecast-workflow__readonly-amount forecast-workflow__cell--number">{baselineDisplay}</td>
                            <td className="forecast-workflow__readonly-amount forecast-workflow__cell--number">{expectedDisplay}</td>
                            <td className="forecast-workflow__cell--number" style={{
                              fontWeight: hasAdjustment ? 700 : 400,
                              color: adjNum > 0 ? '#047857' : adjNum < 0 ? '#b91c1c' : undefined,
                            }}>
                              {hasAdjustment ? (adjNum > 0 ? `+${adjNum.toLocaleString('ko-KR')}` : adjNum.toLocaleString('ko-KR')) : '0'}
                            </td>
                            <td className="forecast-workflow__cell--action">
                              <button
                                type="button"
                                className={`forecast-workflow__btn-adjust ${hasAdjustment ? 'is-active' : ''}`}
                                disabled={advancedControlsDisabled}
                                aria-label={`${rowMonth}월 ${item.display_name} ${hasAdjustment ? '수정' : '조정'}`}
                                onClick={() => isEditing ? cancelMfgEditor() : openMfgEditor(item.adjustment_key, rowMonth, row.amount, row.reason)}
                              >
                                {hasAdjustment ? '수정' : '조정'}
                              </button>
                            </td>
                          </tr>
                          {isEditing && (
                            <tr
                              key={`${item.adjustment_key}-drawer`}
                              ref={(node) => { mfgDrawerRefs.current[item.adjustment_key] = node; }}
                              className="forecast-workflow__drawer-row"
                            >
                                <td colSpan={7}>
                                  <div className="forecast-workflow__inline-drawer">
                                  <div className="forecast-workflow__inline-drawer-header">
                                    <strong>📝 [{item.display_name}] 비용 조정 입력</strong>
                                  </div>
                                  <div className="forecast-workflow__inline-drawer-body">
                                    <div className="forecast-workflow__drawer-readonly-grid">
                                      <label>계획<output aria-label={`${rowMonth}월 ${item.display_name} 제조경비 계획`} data-readonly="true">{baselineDisplay}</output></label>
                                      <label>예상금액(자동)<output aria-label={`${rowMonth}월 ${item.display_name} 제조경비 예상금액`} data-readonly="true">{baseline === undefined ? '—' : formatKrwAmount(calculateAdjustmentExpectedAmount(baseline, mfgDraftAmount))}</output></label>
                                    </div>
                                    <label className="forecast-workflow__drawer-field">
                                      <span>조정액 (KRW)</span>
                                      <FormattedNumericInput
                                        disabled={advancedControlsDisabled}
                                        ariaLabel={`${rowMonth}월 ${item.display_name} 제조경비 조정액`}
                                        value={mfgDraftAmount}
                                        onChange={setMfgDraftAmount}
                                      />
                                    </label>
                                    <label className="forecast-workflow__drawer-field forecast-workflow__drawer-field--reason">
                                      <span>조정 사유 (최대 500자)</span>
                                      <input
                                        className="forecast-workflow__reason-placeholder-centered"
                                        style={{ textAlign: 'left' }}
                                        disabled={advancedControlsDisabled}
                                        aria-label={`${rowMonth}월 ${item.display_name} 제조경비 조정 사유`}
                                        value={mfgDraftReason}
                                        maxLength={500}
                                        placeholder="조정 사유를 입력하세요"
                                        onChange={(e) => setMfgDraftReason(e.target.value)}
                                      />
                                    </label>
                                    <div className="forecast-workflow__drawer-actions">
                                      <button
                                        type="button"
                                        className="forecast-workflow__drawer-btn-save"
                                        disabled={advancedControlsDisabled}
                                        onClick={() => saveMfgEditor(item.adjustment_key)}
                                      >
                                        등록
                                      </button>
                                      <button
                                        type="button"
                                        className="forecast-workflow__drawer-btn-cancel"
                                        disabled={advancedControlsDisabled}
                                        onClick={cancelMfgEditor}
                                      >
                                        취소
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}</tbody>
                  </table>
                </div>
              </section>
              <section className="forecast-workflow__input-section forecast-workflow__adjustment-span forecast-workflow__adjustment-node--sga-table" aria-labelledby="forecast-sga-adjustments-title">
                <div className="forecast-workflow__input-heading">
                  <div><h3 id="forecast-sga-adjustments-title">판관비 조정액</h3><p>적용월별 판관비 계정의 기존 조정 의미를 그대로 유지합니다.</p></div>
                  <div className="forecast-workflow__heading-right">
                    <div className="forecast-workflow__tab-pill-group" role="tablist" aria-label="판관비 구분">
                      <button type="button" role="tab" aria-selected={sgaTab === 'selling'} className={`forecast-workflow__tab-pill ${sgaTab === 'selling' ? 'is-active' : ''}`} onClick={() => setSgaTab('selling')}>판매비</button>
                      <button type="button" role="tab" aria-selected={sgaTab === 'general_admin'} className={`forecast-workflow__tab-pill ${sgaTab === 'general_admin' ? 'is-active' : ''}`} onClick={() => setSgaTab('general_admin')}>일반관리비</button>
                    </div>
                    <span className="forecast-workflow__unit-badge">(단위: 원)</span>
                  </div>
                </div>
                <div className="forecast-workflow__table-scroll">
                  <table className="forecast-workflow__input-table forecast-workflow__cost-table">
                    <thead><tr className="forecast-workflow__header-row--center"><th scope="col" className="forecast-workflow__cell--center">적용월</th><th scope="col" className="forecast-workflow__cell--center">구분</th><th scope="col" className="forecast-workflow__cell--center">계정명</th><th scope="col" className="forecast-workflow__cell--number">계획</th><th scope="col" className="forecast-workflow__cell--number">예상금액(자동)</th><th scope="col" className="forecast-workflow__cell--number">조정액</th><th scope="col" className="forecast-workflow__cell--action">조정</th></tr></thead>
                    <tbody>{(inputMetadata?.sga ?? []).filter((item) => item.section === sgaTab).map((item) => {
                        const rowMonth = sgaInputMonths[item.adjustment_key] ?? (months[0] ?? adjustmentInputMonth);
                        const row = monthInput(rowMonth).sgaAdjustments[item.adjustment_key] ?? { amount: '0', reason: '' };
                        const baselineRaw = item.monthly_baseline_amounts?.[String(rowMonth)];
                        const baseline = typeof baselineRaw === 'number' && Number.isFinite(baselineRaw) ? baselineRaw : undefined;
                        const baselineDisplay = formatKrwAmount(baseline);
                        const localEntriesForAccount = sgaRegisteredEntriesByMonth[rowMonth]?.filter((entry) => entry.adjustmentKey === item.adjustment_key) ?? [];
                        const accountAggregate = localEntriesForAccount.length > 0
                          ? aggregateSgaRegisteredEntries(localEntriesForAccount)
                          : row;
                        const adjNum = parseAdjustmentAmount(accountAggregate.amount);
                        const expectedDisplay = baseline === undefined ? '—' : formatKrwAmount(calculateAdjustmentExpectedAmount(baseline, accountAggregate.amount));
                        const hasAdjustment = hasForecastAdjustmentValue(accountAggregate);
                        const isEditing = editingSgaKey === item.adjustment_key && editingSgaMonth === rowMonth;
                        const editedEntryAmount = editingSgaEntryId === `existing:${item.adjustment_key}`
                          ? adjNum
                          : parseAdjustmentAmount(localEntriesForAccount.find((entry) => entry.id === editingSgaEntryId)?.amount ?? '0');
                        const draftAggregate = isEditing
                          ? adjNum - editedEntryAmount + parseAdjustmentAmount(sgaDraftAmount)
                          : adjNum;
                        return (
                          <React.Fragment key={item.adjustment_key}>
                            <tr>
                              <td className="forecast-workflow__cell--center"><ForecastMonthSelect ariaLabel={`${item.display_name} 판관비 적용월`} disabled={advancedControlsDisabled} months={months} modelYear={selectedBaseModel?.model_year} preservedMonths={outOfRangeAdjustmentMonths} value={rowMonth} onChange={(month) => { if (editingSgaKey === item.adjustment_key) cancelSgaEditor(); setSgaInputMonths((current) => ({ ...current, [item.adjustment_key]: month })); }} /></td>
                              <td className="forecast-workflow__cell--center"><span className={`forecast-workflow__section-badge forecast-workflow__section-badge--${item.section === 'selling' ? 'selling' : 'admin'}`}>{sgaSectionLabel(item.section)}</span></td>
                              <th scope="row" className="forecast-workflow__cell--center">{item.display_name}</th>
                              <td className="forecast-workflow__readonly-amount forecast-workflow__cell--number">{baselineDisplay}</td>
                              <td className="forecast-workflow__readonly-amount forecast-workflow__cell--number">{expectedDisplay}</td>
                              <td className="forecast-workflow__cell--number" style={{
                                fontWeight: hasAdjustment ? 700 : 400,
                                color: adjNum > 0 ? '#047857' : adjNum < 0 ? '#b91c1c' : undefined,
                              }}>
                                {hasAdjustment ? (adjNum > 0 ? `+${adjNum.toLocaleString('ko-KR')}` : adjNum.toLocaleString('ko-KR')) : '0'}
                              </td>
                              <td className="forecast-workflow__cell--action">
                                <button
                                  type="button"
                                  className={`forecast-workflow__btn-adjust ${hasAdjustment ? 'is-active' : ''}`}
                                  disabled={advancedControlsDisabled}
                                  aria-label={`${rowMonth}월 ${item.display_name} ${hasAdjustment ? '수정' : '조정'}`}
                                  onClick={() => isEditing
                                    ? cancelSgaEditor()
                                    : openSgaEditor(item.adjustment_key, rowMonth, row.amount, row.reason)}
                                >
                                  {hasAdjustment ? '수정' : '조정'}
                                </button>
                              </td>
                            </tr>
                            {isEditing && (
                                <tr
                                  key={`${item.adjustment_key}-drawer`}
                                  ref={(node) => { sgaDrawerRefs.current[item.adjustment_key] = node; }}
                                  className="forecast-workflow__drawer-row"
                                >
                                <td colSpan={7}>
                                  <div className="forecast-workflow__inline-drawer">
                                    <div className="forecast-workflow__inline-drawer-header">
                                      <strong>📝 [{item.display_name}] 비용 조정 입력</strong>
                                    </div>
                                    <div className="forecast-workflow__inline-drawer-body">
                                        <div className="forecast-workflow__drawer-readonly-grid">
                                          <label>계획<output aria-label={`${rowMonth}월 ${item.display_name} 판관비 계획`} data-readonly="true">{baselineDisplay}</output></label>
                                          <label>예상금액(자동)<output aria-label={`${rowMonth}월 ${item.display_name} 판관비 예상금액`} data-readonly="true">{baseline === undefined ? '—' : formatKrwAmount(baseline + draftAggregate)}</output></label>
                                        </div>
                                        <label className="forecast-workflow__drawer-field">
                                          <span>조정액 (KRW)</span>
                                          <FormattedNumericInput
                                            disabled={advancedControlsDisabled}
                                            ariaLabel={`${rowMonth}월 ${item.display_name} 판관비 조정액`}
                                            value={sgaDraftAmount}
                                            onChange={setSgaDraftAmount}
                                          />
                                        </label>
                                        <label className="forecast-workflow__drawer-field forecast-workflow__drawer-field--reason">
                                          <span>조정 사유 (최대 500자)</span>
                                          <input
                                            className="forecast-workflow__reason-placeholder-centered"
                                            style={{ textAlign: 'left' }}
                                            disabled={advancedControlsDisabled}
                                            aria-label={`${rowMonth}월 ${item.display_name} 판관비 조정 사유`}
                                            value={sgaDraftReason}
                                            maxLength={500}
                                            placeholder="조정 사유를 입력하세요"
                                            onChange={(e) => setSgaDraftReason(e.target.value)}
                                          />
                                        </label>
                                        <div className="forecast-workflow__drawer-actions">
                                          <button type="button" className="forecast-workflow__drawer-btn-save" disabled={advancedControlsDisabled} onClick={() => saveSgaEditor(item.adjustment_key)}>등록</button>
                                          <button type="button" className="forecast-workflow__drawer-btn-cancel" disabled={advancedControlsDisabled} onClick={cancelSgaEditor}>취소</button>
                                        </div>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                    })}</tbody>
                  </table>
                </div>
              </section>
              <section className="forecast-workflow__adjustment-summary-box forecast-workflow__adjustment-span forecast-workflow__adjustment-node--mfg-list" aria-labelledby="forecast-manufacturing-summary-title">
                <div className="forecast-workflow__summary-box-header">
                  <div className="forecast-workflow__summary-box-title">
                    <FileText size={15} aria-hidden="true" />
                    <h3 id="forecast-manufacturing-summary-title">제조경비 조정 내역 ({mfgAdjustedList.length}건)</h3>
                  </div>
                  {mfgAdjustedList.length > 0 && <button
                    type="button"
                    className="forecast-workflow__btn-bulk-delete"
                    disabled={controlsDisabled || selectedMfgKeys.size === 0}
                    onClick={deleteSelectedMfg}
                  >
                    <Trash2 size={13} aria-hidden="true" /> 선택 삭제 ({selectedMfgKeys.size})
                  </button>}
                </div>
                {mfgAdjustedList.length > 0 ? <div className="forecast-workflow__summary-table-wrap">
                  <table className="forecast-workflow__summary-table">
                    <thead><tr className="forecast-workflow__header-row--center">
                      <th scope="col" className="forecast-workflow__summary-check"><input
                        type="checkbox"
                        aria-label="제조경비 조정 전체 선택"
                        disabled={controlsDisabled}
                        checked={selectedMfgKeys.size === mfgAdjustedList.length}
                        onChange={(event) => setSelectedMfgKeys(event.target.checked ? new Set(mfgAdjustedList.map((item) => item.selectionKey)) : new Set())}
                      /></th>
                      <th scope="col" className="forecast-workflow__cell--center">적용월</th><th scope="col" className="forecast-workflow__cell--center">계정명</th><th scope="col" className="forecast-workflow__cell--number">계획</th><th scope="col" className="forecast-workflow__cell--number">예상금액</th><th scope="col" className="forecast-workflow__cell--number">조정액</th><th scope="col" className="forecast-workflow__cell--reason">사유</th><th scope="col" className="forecast-workflow__cell--action">수정</th>
                    </tr></thead>
                    <tbody>{mfgAdjustedList.map((item) => {
                      const row = item.entry;
                      const baseline = item.monthly_baseline_amounts?.[String(item.month)];
                      const amount = Number(row.amount.replace(/,/g, '').trim()) || 0;
                      const reasonKey = `mfg-${item.selectionKey}`;
                      const reasonExpanded = expandedReasons.has(reasonKey);
                      return <React.Fragment key={`mfg-summary-${item.selectionKey}`}>
                        <tr className={selectedMfgKeys.has(item.selectionKey) ? 'is-selected' : ''}>
                          <td className="forecast-workflow__summary-check"><input
                            type="checkbox"
                            aria-label={`${item.month}월 ${item.display_name} 제조경비 조정 선택`}
                            disabled={controlsDisabled}
                            checked={selectedMfgKeys.has(item.selectionKey)}
                            onChange={(event) => setSelectedMfgKeys((current) => {
                              const next = new Set(current);
                              if (event.target.checked) next.add(item.selectionKey); else next.delete(item.selectionKey);
                              return next;
                            })}
                          /></td>
                          <td className="forecast-workflow__cell--center"><span className="forecast-workflow__month-badge">{monthLabel(item.month)}</span></td>
                          <th scope="row" className="forecast-workflow__cell--center">{item.display_name}</th>
                          <td className="forecast-workflow__cell--number">{typeof baseline === 'number' && Number.isFinite(baseline) ? baseline.toLocaleString('ko-KR') : '—'}</td>
                          <td className="forecast-workflow__cell--number">{typeof baseline === 'number' && Number.isFinite(baseline) ? calculateAdjustmentExpectedAmount(baseline, row.amount).toLocaleString('ko-KR') : '—'}</td>
                          <td className={`forecast-workflow__cell--number ${amount > 0 ? 'is-positive' : amount < 0 ? 'is-negative' : ''}`}>{amount > 0 ? `+${amount.toLocaleString('ko-KR')}` : amount.toLocaleString('ko-KR')}</td>
                          <td className="forecast-workflow__cell--reason"><div className="forecast-workflow__reason-cell">
                            <span className="forecast-workflow__reason-text" title={row.reason}>{row.reason || '(사유 미입력)'}</span>
                            {row.reason.length > 20 && <button type="button" className="forecast-workflow__btn-expand-reason" onClick={() => toggleExpandedReason(reasonKey)}>{reasonExpanded ? '접기' : '자세히'}</button>}
                          </div></td>
                          <td className="forecast-workflow__cell--action"><button type="button" className="forecast-workflow__btn-mini" disabled={controlsDisabled} onClick={() => { setManufacturingInputMonths((current) => ({ ...current, [item.adjustment_key]: item.month })); openMfgEditor(item.adjustment_key, item.month, row.amount, row.reason); }}>수정</button></td>
                        </tr>
                        {reasonExpanded && <tr className="forecast-workflow__expanded-reason-row"><td colSpan={8}><div className="forecast-workflow__expanded-reason-box"><strong>상세 사유</strong><span>{row.reason}</span></div></td></tr>}
                      </React.Fragment>;
                    })}</tbody>
                  </table>
                </div> : <div className="forecast-workflow__summary-empty"><Info size={14} aria-hidden="true" /><span>등록된 제조경비 조정 내역이 없습니다. 표의 <strong>[조정]</strong> 버튼을 눌러 추가하세요.</span></div>}
              </section>

              <section className="forecast-workflow__adjustment-summary-box forecast-workflow__adjustment-span forecast-workflow__adjustment-node--sga-list" aria-labelledby="forecast-sga-summary-title">
                <div className="forecast-workflow__summary-box-header">
                  <div className="forecast-workflow__summary-box-title">
                    <FileText size={15} aria-hidden="true" />
                    <h3 id="forecast-sga-summary-title">판관비 조정 내역 ({sgaAdjustedList.length}건)</h3>
                  </div>
                  {sgaAdjustedList.length > 0 && <button
                    type="button"
                    className="forecast-workflow__btn-bulk-delete"
                    disabled={controlsDisabled || selectedSgaKeys.size === 0}
                    onClick={deleteSelectedSga}
                  >
                    <Trash2 size={13} aria-hidden="true" /> 선택 삭제 ({selectedSgaKeys.size})
                  </button>}
                </div>
                {sgaAccountSummaries.length > 0 && <div className="forecast-workflow__account-summary-bar" aria-label="판관비 계정 합계">
                  {sgaAccountSummaries.map((summary) => <div className="forecast-workflow__account-summary-pill" key={`${summary.month}:${summary.adjustmentKey}`}>
                    <span className="forecast-workflow__account-summary-badge">계정 합계</span>
                    <span className="forecast-workflow__month-badge">{monthLabel(summary.month)}</span>
                    <strong className="forecast-workflow__account-summary-name">{summary.metadata.display_name}</strong>
                    <span className="forecast-workflow__account-summary-amount">조정액 합계: <strong>{summary.total > 0 ? '+' : ''}{summary.total.toLocaleString('ko-KR')}원</strong></span>
                    <span className="forecast-workflow__account-summary-expected">최종 예상금액: <strong>{summary.baseline === undefined ? '—' : `${(summary.baseline + summary.total).toLocaleString('ko-KR')}원`}</strong></span>
                  </div>)}
                </div>}
                {sgaAdjustedList.length > 0 ? <div className="forecast-workflow__summary-table-wrap">
                  <table className="forecast-workflow__summary-table">
                    <thead><tr className="forecast-workflow__header-row--center">
                      <th scope="col" className="forecast-workflow__summary-check"><input
                        type="checkbox"
                        aria-label="판관비 조정 전체 선택"
                        disabled={controlsDisabled}
                        checked={selectedSgaKeys.size === sgaAdjustedList.length}
                        onChange={(event) => setSelectedSgaKeys(event.target.checked ? new Set(sgaAdjustedList.map((item) => item.selectionKey)) : new Set())}
                      /></th>
                      <th scope="col" className="forecast-workflow__cell--center">적용월</th><th scope="col" className="forecast-workflow__cell--center">구분</th><th scope="col" className="forecast-workflow__cell--center">계정명</th><th scope="col" className="forecast-workflow__cell--number">계획</th><th scope="col" className="forecast-workflow__cell--number">예상금액</th><th scope="col" className="forecast-workflow__cell--number">조정액</th><th scope="col" className="forecast-workflow__cell--reason">사유</th><th scope="col" className="forecast-workflow__cell--action">수정</th>
                    </tr></thead>
                    <tbody>{sgaAdjustedList.map((item) => {
                      const baseline = item.metadata.monthly_baseline_amounts?.[String(item.month)];
                      const amount = Number(item.amount.replace(/,/g, '').trim()) || 0;
                      const accountAggregateAmount = monthInput(item.month).sgaAdjustments[item.adjustmentKey]?.amount ?? item.amount;
                      const reasonKey = `sga-${item.selectionKey}`;
                      const reasonExpanded = expandedReasons.has(reasonKey);
                      return <React.Fragment key={`sga-summary-${item.selectionKey}`}>
                        <tr className={selectedSgaKeys.has(item.selectionKey) ? 'is-selected' : ''}>
                          <td className="forecast-workflow__summary-check"><input
                            type="checkbox"
                            aria-label={`${item.month}월 ${item.metadata.display_name} ${item.sourceLabel} 판관비 조정 선택`}
                            disabled={controlsDisabled}
                            checked={selectedSgaKeys.has(item.selectionKey)}
                            onChange={(event) => setSelectedSgaKeys((current) => {
                              const next = new Set(current);
                              if (event.target.checked) next.add(item.selectionKey); else next.delete(item.selectionKey);
                              return next;
                            })}
                          /></td>
                          <td className="forecast-workflow__cell--center"><span className="forecast-workflow__month-badge">{monthLabel(item.month)}</span></td>
                          <td className="forecast-workflow__cell--center"><span className={`forecast-workflow__section-badge forecast-workflow__section-badge--${item.metadata.section === 'selling' ? 'selling' : 'admin'}`}>{sgaSectionLabel(item.metadata.section)}</span></td>
                          <th scope="row" className="forecast-workflow__cell--center"><span className="forecast-workflow__summary-account">{item.metadata.display_name}</span><small className="forecast-workflow__summary-source">({item.sourceLabel})</small></th>
                          <td className="forecast-workflow__cell--number">{typeof baseline === 'number' && Number.isFinite(baseline) ? baseline.toLocaleString('ko-KR') : '—'}</td>
                          <td className="forecast-workflow__cell--number">{typeof baseline === 'number' && Number.isFinite(baseline) ? calculateAdjustmentExpectedAmount(baseline, accountAggregateAmount).toLocaleString('ko-KR') : '—'}</td>
                          <td className={`forecast-workflow__cell--number ${amount > 0 ? 'is-positive' : amount < 0 ? 'is-negative' : ''}`}>{amount > 0 ? `+${amount.toLocaleString('ko-KR')}` : amount.toLocaleString('ko-KR')}</td>
                          <td className="forecast-workflow__cell--reason"><div className="forecast-workflow__reason-cell">
                            <span className="forecast-workflow__reason-text" title={item.reason}>{item.reason || '(사유 미입력)'}</span>
                            {item.reason.length > 20 && <button type="button" className="forecast-workflow__btn-expand-reason" onClick={() => toggleExpandedReason(reasonKey)}>{reasonExpanded ? '접기' : '자세히'}</button>}
                          </div></td>
                          <td className="forecast-workflow__cell--action"><button type="button" className="forecast-workflow__btn-mini" disabled={controlsDisabled} onClick={() => { setSgaTab(item.metadata.section === 'general_admin' ? 'general_admin' : 'selling'); setSgaInputMonths((current) => ({ ...current, [item.adjustmentKey]: item.month })); openSgaEditor(item.adjustmentKey, item.month, item.amount, item.reason, { entry: item }); }}>수정</button></td>
                        </tr>
                        {reasonExpanded && <tr className="forecast-workflow__expanded-reason-row"><td colSpan={9}><div className="forecast-workflow__expanded-reason-box"><strong>상세 사유</strong><span>{item.reason}</span></div></td></tr>}
                      </React.Fragment>;
                    })}</tbody>
                  </table>
                </div> : <div className="forecast-workflow__summary-empty"><Info size={14} aria-hidden="true" /><span>등록된 판관비 조정 내역이 없습니다. 표의 <strong>[조정]</strong> 버튼을 눌러 추가하세요.</span></div>}
              </section>
              <section className="forecast-workflow__input-section forecast-workflow__adjustment-span forecast-workflow__adjustment-node--cogs-table" aria-labelledby="forecast-cogs-adjustments-title">
                <div className="forecast-workflow__input-heading">
                  <div><h3 id="forecast-cogs-adjustments-title">매출원가 조정액</h3><p>계획 기준값은 Backend 계약에 제공되지 않아 표시하지 않으며, 등록된 조정액만 산출 요청에 반영합니다.</p></div>
                  <span className="forecast-workflow__unit-badge">(단위: 원)</span>
                </div>
                <div className="forecast-workflow__table-scroll">
                  <table className="forecast-workflow__input-table forecast-workflow__cost-table">
                    <thead><tr className="forecast-workflow__header-row--center"><th scope="col" className="forecast-workflow__cell--center">적용월</th><th scope="col" className="forecast-workflow__cell--center">계정명</th><th scope="col" className="forecast-workflow__cell--number">계획</th><th scope="col" className="forecast-workflow__cell--number">예상금액(자동)</th><th scope="col" className="forecast-workflow__cell--number">조정액</th><th scope="col" className="forecast-workflow__cell--action">조정</th></tr></thead>
                    <tbody>{COGS_ADJUSTMENT_ROWS.map((item) => {
                      const rowMonth = cogsInputMonths[item.key] ?? (months[0] ?? adjustmentInputMonth);
                      const rowInput = monthInput(rowMonth);
                      const amount = String(rowInput[item.amountField]);
                      const reason = String(rowInput[item.reasonField]);
                      const numericAmount = Number(amount.replace(/,/g, '').trim()) || 0;
                      const hasAdjustment = hasForecastAdjustmentValue({ amount, reason });
                      const isEditing = editingCogsKey === item.key && editingCogsMonth === rowMonth;
                      return <React.Fragment key={item.key}>
                        <tr>
                          <td className="forecast-workflow__cell--center"><ForecastMonthSelect ariaLabel={`${item.displayName} 매출원가 적용월`} disabled={advancedControlsDisabled} months={months} modelYear={selectedBaseModel?.model_year} preservedMonths={outOfRangeAdjustmentMonths} value={rowMonth} onChange={(month) => { if (editingCogsKey === item.key) cancelCogsEditor(); setCogsInputMonths((current) => ({ ...current, [item.key]: month })); }} /></td>
                          <th scope="row" className="forecast-workflow__cell--center">{item.displayName}</th>
                          <td className="forecast-workflow__cell--number" data-contract-missing="cogs-baseline">—</td>
                          <td className="forecast-workflow__cell--number" data-contract-missing="cogs-baseline">—</td>
                          <td className={`forecast-workflow__cell--number ${numericAmount > 0 ? 'is-positive' : numericAmount < 0 ? 'is-negative' : ''}`}>{hasAdjustment ? (numericAmount > 0 ? `+${numericAmount.toLocaleString('ko-KR')}` : numericAmount.toLocaleString('ko-KR')) : '0'}</td>
                          <td className="forecast-workflow__cell--action"><button
                            type="button"
                            className={`forecast-workflow__btn-adjust ${hasAdjustment ? 'is-active' : ''}`}
                            disabled={advancedControlsDisabled}
                            aria-label={`${rowMonth}월 ${item.displayName} ${hasAdjustment ? '수정' : '조정'}`}
                            onClick={() => isEditing ? cancelCogsEditor() : openCogsEditor(item.key, rowMonth, amount, reason)}
                          >{hasAdjustment ? '수정' : '조정'}</button></td>
                        </tr>
                        {isEditing && <tr className="forecast-workflow__drawer-row"><td colSpan={6}>
                          <div className="forecast-workflow__inline-drawer">
                            <div className="forecast-workflow__inline-drawer-header"><strong>📝 [{item.displayName}] 비용 조정 입력</strong></div>
                            <div className="forecast-workflow__inline-drawer-body">
                              <div className="forecast-workflow__drawer-readonly-grid">
                                <label>계획<output data-readonly="true" data-contract-missing="cogs-baseline">—</output></label>
                                <label>예상금액(자동)<output data-readonly="true" data-contract-missing="cogs-baseline">—</output></label>
                              </div>
                              <label className="forecast-workflow__drawer-field"><span>조정액 (KRW)</span><FormattedNumericInput
                                disabled={advancedControlsDisabled}
                                ariaLabel={`${rowMonth}월 ${item.displayName} 매출원가 조정액`}
                                value={cogsDraftAmount}
                                onChange={setCogsDraftAmount}
                              /></label>
                              <label className="forecast-workflow__drawer-field forecast-workflow__drawer-field--reason"><span>조정 사유 (최대 500자)</span><input
                                className="forecast-workflow__reason-placeholder-centered"
                                style={{ textAlign: 'left' }}
                                disabled={advancedControlsDisabled}
                                aria-label={`${rowMonth}월 ${item.displayName} 매출원가 조정 사유`}
                                value={cogsDraftReason}
                                maxLength={500}
                                placeholder="조정 사유를 입력하세요"
                                onChange={(event) => setCogsDraftReason(event.target.value)}
                              /></label>
                              <div className="forecast-workflow__drawer-actions">
                                <button type="button" className="forecast-workflow__drawer-btn-save" disabled={advancedControlsDisabled} onClick={() => saveCogsEditor(item.key)}>등록</button>
                                <button type="button" className="forecast-workflow__drawer-btn-cancel" disabled={advancedControlsDisabled} onClick={cancelCogsEditor}>취소</button>
                              </div>
                            </div>
                          </div>
                        </td></tr>}
                      </React.Fragment>;
                    })}</tbody>
                  </table>
                </div>
              </section>

              <section className="forecast-workflow__adjustment-summary-box forecast-workflow__adjustment-span forecast-workflow__adjustment-node--cogs-list" aria-labelledby="forecast-cogs-summary-title">
                <div className="forecast-workflow__summary-box-header">
                  <div className="forecast-workflow__summary-box-title"><FileText size={15} aria-hidden="true" /><h3 id="forecast-cogs-summary-title">매출원가 조정 내역 ({cogsAdjustedList.length}건)</h3></div>
                  {cogsAdjustedList.length > 0 && <button type="button" className="forecast-workflow__btn-bulk-delete" disabled={controlsDisabled || selectedCogsKeys.size === 0} onClick={deleteSelectedCogs}><Trash2 size={13} aria-hidden="true" /> 선택 삭제 ({selectedCogsKeys.size})</button>}
                </div>
                {cogsAdjustedList.length > 0 ? <div className="forecast-workflow__summary-table-wrap">
                  <table className="forecast-workflow__summary-table">
                    <thead><tr className="forecast-workflow__header-row--center">
                      <th scope="col" className="forecast-workflow__summary-check"><input type="checkbox" aria-label="매출원가 조정 전체 선택" disabled={controlsDisabled} checked={selectedCogsKeys.size === cogsAdjustedList.length} onChange={(event) => setSelectedCogsKeys(event.target.checked ? new Set(cogsAdjustedList.map((item) => item.selectionKey)) : new Set())} /></th>
                      <th scope="col" className="forecast-workflow__cell--center">적용월</th><th scope="col" className="forecast-workflow__cell--center">계정명</th><th scope="col" className="forecast-workflow__cell--number">조정액</th><th scope="col" className="forecast-workflow__cell--number">예상금액</th><th scope="col" className="forecast-workflow__cell--reason">사유</th><th scope="col" className="forecast-workflow__cell--action">수정</th>
                    </tr></thead>
                    <tbody>{cogsAdjustedList.map((item) => {
                      const amount = item.amount;
                      const reason = item.reason;
                      const numericAmount = Number(amount.replace(/,/g, '').trim()) || 0;
                      const reasonKey = `cogs-${item.selectionKey}`;
                      const reasonExpanded = expandedReasons.has(reasonKey);
                      return <React.Fragment key={`cogs-summary-${item.selectionKey}`}>
                        <tr className={selectedCogsKeys.has(item.selectionKey) ? 'is-selected' : ''}>
                          <td className="forecast-workflow__summary-check"><input type="checkbox" aria-label={`${item.month}월 ${item.displayName} 매출원가 조정 선택`} disabled={controlsDisabled} checked={selectedCogsKeys.has(item.selectionKey)} onChange={(event) => setSelectedCogsKeys((current) => { const next = new Set(current); if (event.target.checked) next.add(item.selectionKey); else next.delete(item.selectionKey); return next; })} /></td>
                          <td className="forecast-workflow__cell--center"><span className="forecast-workflow__month-badge">{monthLabel(item.month)}</span></td>
                          <th scope="row" className="forecast-workflow__cell--center">{item.displayName}</th>
                          <td className={`forecast-workflow__cell--number ${numericAmount > 0 ? 'is-positive' : numericAmount < 0 ? 'is-negative' : ''}`}>{numericAmount > 0 ? `+${numericAmount.toLocaleString('ko-KR')}` : numericAmount.toLocaleString('ko-KR')}</td>
                          <td className="forecast-workflow__cell--number" data-contract-missing="cogs-baseline">—</td>
                          <td className="forecast-workflow__cell--reason"><div className="forecast-workflow__reason-cell"><span className="forecast-workflow__reason-text" title={reason}>{reason || '(사유 미입력)'}</span>{reason.length > 20 && <button type="button" className="forecast-workflow__btn-expand-reason" onClick={() => toggleExpandedReason(reasonKey)}>{reasonExpanded ? '접기' : '자세히'}</button>}</div></td>
                          <td className="forecast-workflow__cell--action"><button type="button" className="forecast-workflow__btn-mini" disabled={controlsDisabled} onClick={() => { setCogsInputMonths((current) => ({ ...current, [item.key]: item.month })); openCogsEditor(item.key, item.month, amount, reason); }}>수정</button></td>
                        </tr>
                        {reasonExpanded && <tr className="forecast-workflow__expanded-reason-row"><td colSpan={7}><div className="forecast-workflow__expanded-reason-box"><strong>상세 사유</strong><span>{reason}</span></div></td></tr>}
                      </React.Fragment>;
                    })}</tbody>
                  </table>
                </div> : <div className="forecast-workflow__summary-empty"><Info size={14} aria-hidden="true" /><span>등록된 매출원가 조정 내역이 없습니다. 표의 <strong>[조정]</strong> 버튼을 눌러 추가하세요.</span></div>}
              </section>
              <section className="forecast-workflow__advanced-block forecast-workflow__adjustment-node--tariff" aria-labelledby="forecast-tariff-title">
                <div className="forecast-workflow__block-heading-row"><h3 id="forecast-tariff-title">북미·남미 매출 관세</h3><ForecastMonthSelect ariaLabel="북미·남미 매출 관세 적용월" disabled={advancedControlsDisabled} months={months} modelYear={selectedBaseModel?.model_year} preservedMonths={outOfRangeAdjustmentMonths} value={tariffInputMonth} onChange={setTariffInputMonth} /></div>
                <p className="forecast-workflow__advanced-block-help">적용월의 계획·추정 북미/남미 매출을 입력합니다. 관세는 Backend의 v1.1 정책으로 월별 계산되며 별도 판관비 조정을 자동 생성하지 않습니다.</p>
                <div className="forecast-workflow__advanced-fields">
                  <div className="forecast-workflow__field-group-row">
                    <div className="forecast-workflow__field-subgrid">
                      <label>계획 북미·남미 매출 (원)<FormattedNumericInput disabled={advancedControlsDisabled} ariaLabel={`${tariffInputMonth}월 계획 북미·남미 매출`} value={tariffMonthInput.planNaSaSales} onChange={(value) => updateAdvanced(tariffInputMonth, 'planNaSaSales', value)} /></label>
                      <label>추정 북미·남미 매출 (원)<FormattedNumericInput disabled={advancedControlsDisabled} ariaLabel={`${tariffInputMonth}월 추정 북미·남미 매출`} value={tariffMonthInput.naSaSales} onChange={(value) => updateAdvanced(tariffInputMonth, 'naSaSales', value)} /></label>
                    </div>
                  </div>
                </div>
              </section>
              <section className="forecast-workflow__advanced-block forecast-workflow__adjustment-node--new-business" aria-labelledby="forecast-new-business-title">
                <div className="forecast-workflow__block-heading-row"><h3 id="forecast-new-business-title">신사업 입력 및 참고 기준값</h3><ForecastMonthSelect ariaLabel="신사업 상품원가 및 포장 적용월" disabled={advancedControlsDisabled} months={months} modelYear={selectedBaseModel?.model_year} preservedMonths={outOfRangeAdjustmentMonths} value={newBusinessInputMonth} onChange={setNewBusinessInputMonth} /></div>
                <p className="forecast-workflow__advanced-block-help">신사업 상품원가와 운반비는 Backend 정책으로 월별 반영됩니다. 포장 기준값만 해당 적용월의 Backend 계산 입력으로 전달합니다.</p>
                <div className="forecast-workflow__advanced-fields">
                  <div className="forecast-workflow__field-group-row forecast-workflow__field-group-row--stacked" data-reference-action="new-business-merchandise-cogs">
                    <fieldset className="forecast-workflow__radio-group"><legend>상품원가 입력방식</legend>
                      <label><input type="radio" name={`new-business-goods-cogs-${newBusinessInputMonth}`} disabled={advancedControlsDisabled} checked={newBusinessMonthInput.newBusinessGoodsCogsMode === 'ACTUAL_YTD_DEFAULT'} onChange={() => updateNewBusinessGoodsCogsMode(newBusinessInputMonth, 'ACTUAL_YTD_DEFAULT')} />Actual YTD 자동</label>
                      <label><input type="radio" name={`new-business-goods-cogs-${newBusinessInputMonth}`} disabled={advancedControlsDisabled} checked={newBusinessMonthInput.newBusinessGoodsCogsMode === 'MANUAL_OVERRIDE'} onChange={() => updateNewBusinessGoodsCogsMode(newBusinessInputMonth, 'MANUAL_OVERRIDE')} />최종 원가 직접 지정</label>
                    </fieldset>
                    {newBusinessMonthInput.newBusinessGoodsCogsMode === 'MANUAL_OVERRIDE' && <div className="forecast-workflow__field-subgrid">
                      <label>최종 적용 상품원가 직접 지정값 (원)<FormattedNumericInput disabled={advancedControlsDisabled} ariaLabel={`${newBusinessInputMonth}월 최종 적용 상품원가 직접 지정값`} value={newBusinessMonthInput.newBusinessGoodsCogs} onChange={(value) => updateAdvanced(newBusinessInputMonth, 'newBusinessGoodsCogs', value)} /></label>
                      <label>직접 지정 사유<input disabled={advancedControlsDisabled} aria-label={`${newBusinessInputMonth}월 상품원가 직접 지정 사유`} maxLength={500} value={newBusinessMonthInput.newBusinessGoodsCogsReason} onChange={(event) => updateAdvanced(newBusinessInputMonth, 'newBusinessGoodsCogsReason', event.target.value)} /></label>
                    </div>}
                  </div>
                  <div className="forecast-workflow__field-group-row" data-reference-action="ix-packaging">
                    <div className="forecast-workflow__field-subgrid">
                      <label>IX 포장 기준량 (L)<FormattedNumericInput disabled={advancedControlsDisabled} ariaLabel={`${newBusinessInputMonth}월 IX 포장 기준량`} value={newBusinessMonthInput.ixPackLiters} onChange={(value) => updateAdvanced(newBusinessInputMonth, 'ixPackLiters', value)} /></label>
                      <label>IX 포장 단가 (원)<FormattedNumericInput disabled={advancedControlsDisabled} ariaLabel={`${newBusinessInputMonth}월 IX 포장 단가`} value={newBusinessMonthInput.ixPackCost} onChange={(value) => updateAdvanced(newBusinessInputMonth, 'ixPackCost', value)} /></label>
                    </div>
                  </div>
                </div>
              </section>
              <section className="forecast-workflow__advanced-block forecast-workflow__adjustment-node--raw-material" aria-labelledby="forecast-raw-material-title">
                <div className="forecast-workflow__block-heading-row"><h3 id="forecast-raw-material-title">원재료 관세 환급</h3><ForecastMonthSelect ariaLabel="원재료 관세 환급 적용월" disabled={advancedControlsDisabled} months={months} modelYear={selectedBaseModel?.model_year} preservedMonths={outOfRangeAdjustmentMonths} value={rawMaterialInputMonth} onChange={setRawMaterialInputMonth} /></div>
                <p className="forecast-workflow__advanced-block-help">모형 산출값 기준에서는 조정액을, 구매팀 예상 금액 기준에서는 직접 입력액을 사용합니다. 환급액은 서버에서 계산합니다.</p>
                <div className="forecast-workflow__advanced-fields forecast-workflow__raw-material-fields">
                  <fieldset className="forecast-workflow__radio-group forecast-workflow__raw-material-basis"><legend className="forecast-workflow__visually-hidden">환급 기준</legend><label><input type="radio" name={`raw-material-basis-${rawMaterialInputMonth}`} disabled={advancedControlsDisabled} checked={rawMaterialMonthInput.rawMaterialBasis === 'model'} onChange={() => updateAdvanced(rawMaterialInputMonth, 'rawMaterialBasis', 'model')} />모형 산출값</label><label><input type="radio" name={`raw-material-basis-${rawMaterialInputMonth}`} disabled={advancedControlsDisabled} checked={rawMaterialMonthInput.rawMaterialBasis === 'direct'} onChange={() => updateAdvanced(rawMaterialInputMonth, 'rawMaterialBasis', 'direct')} />구매비 예상 금액</label></fieldset>
                  <div className="forecast-workflow__raw-material-row" data-raw-material-row="amounts">
                    <label>원재료 조정액 (모형 기준)<FormattedNumericInput disabled={advancedControlsDisabled || rawMaterialMonthInput.rawMaterialBasis !== 'model'} ariaLabel={`${rawMaterialInputMonth}월 원재료 조정액`} value={rawMaterialMonthInput.rawMaterialAdjustment} onChange={(value) => updateAdvanced(rawMaterialInputMonth, 'rawMaterialAdjustment', value)} /></label>
                    <label>원재료 직접 입력액 (구매비 기준)<FormattedNumericInput disabled={advancedControlsDisabled || rawMaterialMonthInput.rawMaterialBasis !== 'direct'} ariaLabel={`${rawMaterialInputMonth}월 원재료 직접 입력액`} value={rawMaterialMonthInput.rawMaterialDirect} onChange={(value) => updateAdvanced(rawMaterialInputMonth, 'rawMaterialDirect', value)} /></label>
                  </div>
                  <div className="forecast-workflow__raw-material-row" data-raw-material-row="reason-rate">
                    <label>원재료 사유<input disabled={advancedControlsDisabled} aria-label={`${rawMaterialInputMonth}월 원재료 사유`} maxLength={500} value={rawMaterialMonthInput.rawMaterialReason} onChange={(event) => updateAdvanced(rawMaterialInputMonth, 'rawMaterialReason', event.target.value)} /></label>
                    <label>원재료 관세 환급률 (%)<PercentageInput disabled={advancedControlsDisabled} ariaLabel={`${rawMaterialInputMonth}월 원재료 관세 환급률`} value={rawMaterialMonthInput.refundRate} onChange={(value) => updateAdvanced(rawMaterialInputMonth, 'refundRate', value)} /></label>
                  </div>
                </div>
              </section>
              <section className="forecast-workflow__advanced-block forecast-workflow__execution-card forecast-workflow__adjustment-node--execution" aria-labelledby="forecast-execute-title">
                <div className="forecast-workflow__block-heading-row">
                  <h3 id="forecast-execute-title">추정 모형 생성 실행</h3>
                </div>
                <p className="forecast-workflow__advanced-block-help">설정된 판매·생산 계획 및 비용 조정값을 반영하여 손익 추정 모형을 최종 산출합니다.</p>
                <div className="forecast-workflow__execution-summary-list">
                  <div className="forecast-workflow__execution-summary-item"><span className="forecast-workflow__execution-label">추정 기간</span><strong className="forecast-workflow__execution-value">{rangeValid ? `${startMonth}월 ~ ${endMonth}월 (${selectedMonthCount}개월)` : '기간 확인 필요'}</strong></div>
                  <div className="forecast-workflow__execution-summary-item"><span className="forecast-workflow__execution-label">모형명</span><strong className="forecast-workflow__execution-value" title={name}>{name || selectedBaseModel?.display_name || '-'}</strong></div>
                  <div className="forecast-workflow__execution-summary-item"><span className="forecast-workflow__execution-label">버전 정보</span><strong className="forecast-workflow__execution-value">{version || 'V1'}</strong></div>
                </div>
                {state === 'SUBMITTING' && <div className="forecast-workflow__execution-submitting-alert" role="status"><span className="forecast-workflow__spinner" aria-hidden="true" /><span>{startMonth}~{endMonth}월 추정 산출을 접수하고 계산 중입니다.</span></div>}
                <div className="forecast-workflow__execution-card-actions">
                  <button type="button" className="forecast-workflow__primary forecast-workflow__execution-submit-btn" disabled={submitDisabled} onClick={() => void submit()}>
                    {state === 'SUBMITTING' ? '추정 산출 연산 중…' : '추정 모형 생성'}
                  </button>
                </div>
              </section>
            </div>
          </details>
        </> : <p className="forecast-workflow__empty-input">유효한 기간을 선택하면 판매·생산 입력표가 표시됩니다.</p>}
      </section>
      </>}
    </div>

    {message && <p className={`forecast-workflow__message ${state === 'VALIDATION_ERROR' ? 'is-validation' : ''}`} role="alert">{message}</p>}

    {result && state === 'SUCCESS' && <section className="forecast-workflow__success" aria-live="polite">
      <div className="forecast-workflow__success-heading"><CheckCircle2 size={20} aria-hidden="true" /><div><h2>추정 모형 생성 완료</h2></div><span className="forecast-workflow__status-pill">{result.is_published ? '공개 상태' : '비공개 상태'}</span></div>
      <p><strong>{result.display_name}</strong> · {result.model_year}년 {result.start_month}~{result.end_month}월 (추정 모형)</p>
      <p className="forecast-workflow__success-meta"><ShieldCheck size={14} aria-hidden="true" /> {result.is_default ? '기본 모형' : '일반 모형'} · {result.is_published ? '공개 상태' : '비공개 상태 (관리자 전용)'}</p>
      <p className="forecast-workflow__success-help">공개 전까지는 분석 화면의 모형 목록에 나타나지 않습니다.</p>
      <p className="forecast-workflow__success-help">다운로드한 모형의 ‘입력반영내역’ 시트에서 입력값의 적용 위치와 이동 링크를 확인할 수 있습니다.</p>
      <div className="forecast-workflow__cta-row">
        <button
          type="button"
          className="forecast-workflow__secondary forecast-workflow__download"
          disabled={downloadState === 'DOWNLOADING'}
          onClick={() => void downloadWorkbook()}
        >
          <Download size={14} aria-hidden="true" />
          {downloadState === 'DOWNLOADING' ? '다운로드 준비 중…' : '생성 모형 내려받기 (.xlsx)'}
        </button>
        {onNavigateToPnl && <button type="button" className="forecast-workflow__secondary" onClick={onNavigateToPnl}>손익 현황 보기</button>}
        {onNavigateToAnalysis && <button type="button" className="forecast-workflow__secondary" onClick={onNavigateToAnalysis}>손익분석 보기</button>}
        {onNavigateToManagement && <button type="button" className="forecast-workflow__link" onClick={onNavigateToManagement}>모형 관리로 이동</button>}
      </div>
      {downloadState === 'FAILED' && downloadMessage && <p className="forecast-workflow__download-error" role="alert">{downloadMessage}</p>}
    </section>}

  </section>;
};

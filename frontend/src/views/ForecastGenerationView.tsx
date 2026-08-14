import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Calculator, CheckCircle2, Database, Download, LockKeyhole, RotateCcw, ShieldCheck } from 'lucide-react';
import { bffClient } from '../integration/client';
import {
  AnalysisModelDto,
  ApiClientError,
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
  BUSINESS_PRODUCTION_ROWS,
  createForecastMonthFormState,
  ensureForecastMonths,
  MCM_PRODUCTS,
  SALES_PRODUCTS,
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

const V1_FORECAST_SYNC_MAX_MONTHS = 6;
const MONTH_MIN = 1;
const MONTH_MAX = 12;

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

function sectionLabel(value: string | null): string {
  switch (value) {
    case 'selling': return '판매';
    case 'general_admin': return '일반';
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
  const [state, setState] = useState<ViewState>('LOADING');
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<ForecastGenerateResponseDto | null>(null);
  const [downloadState, setDownloadState] = useState<DownloadState>('IDLE');
  const [downloadMessage, setDownloadMessage] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [inputMetadata, setInputMetadata] = useState<ForecastInputMetadataDto | null>(null);
  const [metadataState, setMetadataState] = useState<'LOADING' | 'READY' | 'ERROR'>('LOADING');
  const [metadataMessage, setMetadataMessage] = useState('');
  const idempotencyKey = useRef(crypto.randomUUID());
  const submittingRef = useRef(false);
  const downloadPendingRef = useRef(false);
  const mountedRef = useRef(true);
  const metadataRequestSequence = useRef(0);

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

  const updateAdjustment = (
    month: number,
    section: 'manufacturingAdjustments' | 'sgaAdjustments',
    adjustmentKey: string,
    field: 'amount' | 'reason',
    value: string,
  ) => {
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
      const rows = current[section];
      const row = rows[adjustmentKey] ?? { amount: '0', reason: '' };
      return {
        ...old,
        [month]: {
          ...current,
          [section]: { ...rows, [adjustmentKey]: { ...row, [field]: value } },
        },
      };
    });
    markDraftChanged();
  };

  const updateAdvanced = (
    month: number,
    field: keyof Omit<ForecastMonthFormState, 'month' | 'sales' | 'production' | 'mcm' | 'manufacturingAdjustments' | 'sgaAdjustments'>,
    value: string,
  ) => {
    setInputs((old) => {
      const current = old[month] ?? createForecastMonthFormState(month, inputMetadata ?? undefined);
      return { ...old, [month]: { ...current, [field]: value } };
    });
    markDraftChanged();
  };

  const resetMonthInputs = (month: number) => {
    setInputs((old) => ({ ...old, [month]: createForecastMonthFormState(month, inputMetadata ?? undefined) }));
    markDraftChanged();
  };

  const updateBaseModel = (value: string) => {
    setBaseModelId(value);
    setInputMetadata(null);
    setMetadataState('LOADING');
    setMetadataMessage('');
    setInputs(Object.fromEntries(months.map((month) => [month, createForecastMonthFormState(month)])));
    setResult(null);
    setMessage('');
    setDownloadState('IDLE');
    setDownloadMessage('');
    setState('READY');
    idempotencyKey.current = crypto.randomUUID();
  };

  const updateStartMonth = (value: string) => {
    setStartMonth(value);
    markDraftChanged();
  };

  const updateEndMonth = (value: string) => {
    setEndMonth(value);
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

  const controlsDisabled = state === 'SUBMITTING' || state === 'LOADING';
  const advancedControlsDisabled = controlsDisabled || metadataState !== 'READY';
  const submitDisabled = controlsDisabled || !baseModelId || !rangeValid || !models.length
    || metadataState !== 'READY' || !inputMetadata;
  const selectedBaseModel = models.find((model) => model.model_id === baseModelId) || null;
  const activeMonthInput = inputs[activeInputMonth] ?? createForecastMonthFormState(activeInputMonth, inputMetadata ?? undefined);
  const advancedEnteredCount = useMemo(() => {
    const adjustmentCount = [
      ...Object.values(activeMonthInput.manufacturingAdjustments),
      ...Object.values(activeMonthInput.sgaAdjustments),
    ].filter((entry) => entry.amount.trim() !== '' && entry.amount.trim() !== '0' || entry.reason.trim() !== '').length;
    const scalarDefaults: Record<string, string> = {
      disposalAdjustment: '0', obsolescenceAdjustment: '0', newBusinessGoodsCogs: '0',
      ufMbrCogsRate: '0.85', ixCogsRate: '0.85', ufMbrTransportRate: '0.05', ixTransportRate: '0.05',
      ixPackLiters: '25', ixPackCost: '380', planNaSaSales: '0', naSaSales: '0',
      tariffApplicableRate: '0.1', tariffRate: '0.13', refundRate: '0.013',
    };
    const scalarCount = Object.entries(scalarDefaults).filter(([field, defaultValue]) => {
      const current = String(activeMonthInput[field as keyof typeof activeMonthInput]).trim();
      return current !== '' && current !== defaultValue;
    }).length;
    const reasonCount = [activeMonthInput.disposalReason, activeMonthInput.obsolescenceReason, activeMonthInput.newBusinessGoodsCogsReason, activeMonthInput.rawMaterialReason]
      .filter((value) => value.trim() !== '').length;
    const rawMaterialCount = activeMonthInput.rawMaterialBasis === 'direct'
      ? 1
      : Number(activeMonthInput.rawMaterialAdjustment.trim() !== '' && activeMonthInput.rawMaterialAdjustment.trim() !== '0');
    return adjustmentCount + scalarCount + reasonCount + rawMaterialCount;
  }, [activeMonthInput]);

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
      <div><p className="forecast-workflow__eyebrow">ADMIN WORKFLOW</p><h1 id="forecast-workflow-title">추정 산출</h1>
        <p>공개된 기준 모형과 월별 입력을 사용해 비공개 추정 모형을 생성합니다.</p></div>
      <span className="forecast-workflow__contract-badge">한 번에 최대 6개월</span>
    </header>

    <div className="forecast-workflow__notice"><ShieldCheck size={16} aria-hidden="true" /><span>선택한 기준 모형과 월별 입력으로 추정 모형을 생성합니다. 산출 중에는 입력이 잠깁니다.</span></div>

    <div className="forecast-workflow__grid">
      <section className="forecast-workflow__card forecast-workflow__card--setup" aria-labelledby="forecast-setup-title">
        <div className="forecast-workflow__card-heading"><div><p className="forecast-workflow__eyebrow">01 · SETUP</p><h2 id="forecast-setup-title">모형과 산출 기간</h2></div><span className="forecast-workflow__step-state">필수</span></div>
        <div className="forecast-workflow__form-grid">
          <label className="forecast-workflow__field forecast-workflow__field--wide">기준 모형
            <select disabled={controlsDisabled} value={baseModelId} onChange={(event) => updateBaseModel(event.target.value)}>
              {models.map((model) => <option key={model.model_id} value={model.model_id}>{model.display_name} · {model.model_year}년</option>)}
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
        </div>
        <div className={`forecast-workflow__range-note ${rangeValid ? '' : 'is-invalid'}`} role={!rangeValid ? 'alert' : undefined}>
          <span>{rangeValid ? `선택 기간 ${startMonth}~${endMonth}월 · ${selectedMonthCount}개월` : rangeMessage}</span>
          {!rangeValid && <strong>기간을 수정하면 실행할 수 있습니다.</strong>}
        </div>
      </section>

      <section className="forecast-workflow__card forecast-workflow__card--inputs" aria-labelledby="forecast-inputs-title">
        <div className="forecast-workflow__card-heading"><div><p className="forecast-workflow__eyebrow">02 · DIRECT INPUT</p><h2 id="forecast-inputs-title">판매·생산 계획 직접입력</h2></div><span className="forecast-workflow__step-state">월별 입력</span></div>
        <p className="forecast-workflow__helper">제품코드는 정해진 입력 순서를 따릅니다. LC는 4인치/PCS, FS는 LENGTH/m이며 서로 다른 수량 단위를 합산하지 않습니다.</p>
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
              <RotateCcw size={13} aria-hidden="true" /> 선택 월 0으로 초기화
            </button>
          </div>

          <section className="forecast-workflow__input-section" aria-labelledby="forecast-sales-title">
            <div className="forecast-workflow__input-heading"><div><h3 id="forecast-sales-title">판매계획</h3><p>제품별 판매수량과 예상 매출액을 입력합니다.</p></div><span>{SALES_PRODUCTS.length}개 품목</span></div>
            <div className="forecast-workflow__table-scroll">
              <table className="forecast-workflow__input-table">
                <thead><tr><th scope="col">제품코드</th><th scope="col">구분</th><th scope="col">단위</th><th scope="col">판매수량</th><th scope="col">매출액(원)</th></tr></thead>
                <tbody>{SALES_PRODUCTS.map((product) => <tr key={product.code}>
                  <th scope="row">{product.code}</th><td>{product.label}</td><td><span className={`forecast-workflow__unit forecast-workflow__unit--${product.unit === 'm' ? 'length' : 'quantity'}`}>{product.unit}</span></td>
                  <td><EditableNumericInput mode="decimal" disabled={controlsDisabled} aria-label={`${activeInputMonth}월 ${product.code} 판매수량`} value={activeMonthInput.sales[product.code]?.quantity ?? ''} onChange={(value) => updateInput(activeInputMonth, 'sales', product.code, 'quantity', value)} /></td>
                  <td><EditableNumericInput mode="decimal" disabled={controlsDisabled} aria-label={`${activeInputMonth}월 ${product.code} 매출액`} value={activeMonthInput.sales[product.code]?.amount ?? ''} onChange={(value) => updateInput(activeInputMonth, 'sales', product.code, 'amount', value)} /></td>
                </tr>)}</tbody>
              </table>
            </div>
          </section>

          <div className="forecast-workflow__production-grid">
            <section className="forecast-workflow__input-section" aria-labelledby="forecast-production-title">
              <div className="forecast-workflow__input-heading"><div><h3 id="forecast-production-title">생산계획</h3><p>공정과 제품군별 예상 생산수량을 입력합니다.</p></div><span>{BUSINESS_PRODUCTION_ROWS.length}개 업무행</span></div>
              <div className="forecast-workflow__table-scroll">
                <table className="forecast-workflow__input-table forecast-workflow__input-table--compact">
                  <thead><tr><th scope="col">공정</th><th scope="col">제품군</th><th scope="col">생산수량</th><th scope="col">단위</th></tr></thead>
                  <tbody>{BUSINESS_PRODUCTION_ROWS.map((row) => <tr key={row.key}>
                    <th scope="row">{row.process}</th><td>{row.label}</td>
                    <td><EditableNumericInput mode="decimal" disabled={controlsDisabled} aria-label={`${activeInputMonth}월 ${row.process} ${row.productGroup} 생산수량`} value={activeMonthInput.production[row.key]?.quantity ?? ''} onChange={(value) => updateInput(activeInputMonth, 'production', row.key, 'quantity', value)} /></td>
                    <td><span className={`forecast-workflow__unit forecast-workflow__unit--${row.unit === 'm' ? 'length' : 'quantity'}`}>{row.unit}</span></td>
                  </tr>)}</tbody>
                </table>
              </div>
              <p className="forecast-workflow__boundary-note">후공정 SW/BW 생산량은 기준모형의 동일 월 400/440 생산구성비로 서버에서 자동 배부됩니다.</p>
            </section>

            <section className="forecast-workflow__input-section" aria-labelledby="forecast-mcm-title">
              <div className="forecast-workflow__input-heading"><div><h3 id="forecast-mcm-title">MCM 유상사급</h3><p>유상사급 대상 제품의 월별 수량을 입력합니다.</p></div><span>{MCM_PRODUCTS.length}개 품목</span></div>
              <div className="forecast-workflow__table-scroll">
                <table className="forecast-workflow__input-table forecast-workflow__input-table--compact">
                  <thead><tr><th scope="col">제품코드</th><th scope="col">단위</th><th scope="col">MCM 수량</th></tr></thead>
                  <tbody>{MCM_PRODUCTS.map((product) => <tr key={product.code}>
                    <th scope="row">{product.code}</th><td><span className="forecast-workflow__unit forecast-workflow__unit--quantity">{product.unit}</span></td>
                    <td><EditableNumericInput mode="decimal" disabled={controlsDisabled} aria-label={`${activeInputMonth}월 ${product.code} MCM 수량`} value={activeMonthInput.mcm[product.code]?.quantity ?? ''} onChange={(value) => updateInput(activeInputMonth, 'mcm', product.code, 'quantity', value)} /></td>
                  </tr>)}</tbody>
                </table>
              </div>
              <p className="forecast-workflow__boundary-note">입력한 400/440 수량은 별도로 유지되며 화면에서 자동 배부하지 않습니다.</p>
            </section>
          </div>

          <details className="forecast-workflow__advanced">
            <summary>고급 입력 및 조정 · {advancedEnteredCount ? `${advancedEnteredCount}개 변경` : '변경 없음'}</summary>
            <p className="forecast-workflow__advanced-help">조정액·사유와 원시 가정값만 서버에 직접 전달합니다. 계획 대비 차이, 관세·운송·포장·환급 기준값은 화면에서 계산하지 않습니다.</p>
            <div className="forecast-workflow__adjustment-grid">
              <section className="forecast-workflow__input-section" aria-labelledby="forecast-manufacturing-adjustments-title">
                <div className="forecast-workflow__input-heading"><div><h3 id="forecast-manufacturing-adjustments-title">제조경비 조정액</h3><p>선택 월의 제조 계정별 조정액과 사유입니다.</p></div><span>{inputMetadata?.manufacturing.length ?? 0}개 항목</span></div>
                <div className="forecast-workflow__table-scroll">
                  <table className="forecast-workflow__input-table forecast-workflow__input-table--advanced">
                    <thead><tr><th scope="col">항목</th><th scope="col">단위</th><th scope="col">조정액</th><th scope="col">사유</th></tr></thead>
                    <tbody>{(inputMetadata?.manufacturing ?? []).map((item) => {
                      const row = activeMonthInput.manufacturingAdjustments[item.adjustment_key] ?? { amount: '0', reason: '' };
                      return <tr key={item.adjustment_key}>
                        <th scope="row">{item.display_name}</th><td>{item.unit || '금액'}</td>
                        <td><EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 ${item.display_name} 제조경비 조정액`} value={row.amount} onChange={(value) => updateAdjustment(activeInputMonth, 'manufacturingAdjustments', item.adjustment_key, 'amount', value)} /></td>
                        <td><input disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 ${item.display_name} 제조경비 조정 사유`} value={row.reason} maxLength={500} onChange={(event) => updateAdjustment(activeInputMonth, 'manufacturingAdjustments', item.adjustment_key, 'reason', event.target.value)} /></td>
                      </tr>;
                    })}</tbody>
                  </table>
                </div>
              </section>
              <section className="forecast-workflow__input-section" aria-labelledby="forecast-sga-adjustments-title">
                <div className="forecast-workflow__input-heading"><div><h3 id="forecast-sga-adjustments-title">판관비 조정액</h3><p>구분과 계정명은 기준 모형 정보에서 제공합니다.</p></div><span>{inputMetadata?.sga.length ?? 0}개 항목</span></div>
                <div className="forecast-workflow__table-scroll">
                  <table className="forecast-workflow__input-table forecast-workflow__input-table--advanced">
                    <thead><tr><th scope="col">항목</th><th scope="col">구분</th><th scope="col">단위</th><th scope="col">조정액</th><th scope="col">사유</th></tr></thead>
                    <tbody>{(inputMetadata?.sga ?? []).map((item) => {
                      const row = activeMonthInput.sgaAdjustments[item.adjustment_key] ?? { amount: '0', reason: '' };
                      return <tr key={item.adjustment_key}>
                        <th scope="row">{item.display_name}</th><td>{sectionLabel(item.section)}</td><td>{item.unit || '금액'}</td>
                        <td><EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 ${item.display_name} 판관비 조정액`} value={row.amount} onChange={(value) => updateAdjustment(activeInputMonth, 'sgaAdjustments', item.adjustment_key, 'amount', value)} /></td>
                        <td><input disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 ${item.display_name} 판관비 조정 사유`} value={row.reason} maxLength={500} onChange={(event) => updateAdjustment(activeInputMonth, 'sgaAdjustments', item.adjustment_key, 'reason', event.target.value)} /></td>
                      </tr>;
                    })}</tbody>
                  </table>
                </div>
              </section>
            </div>

            <div className="forecast-workflow__advanced-grid">
              <section className="forecast-workflow__advanced-block" aria-labelledby="forecast-cogs-adjustments-title">
                <h3 id="forecast-cogs-adjustments-title">매출원가 조정</h3>
                <div className="forecast-workflow__advanced-fields">
                  <label>제품 폐기손실 조정액<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 제품 폐기손실 조정액`} value={activeMonthInput.disposalAdjustment} onChange={(value) => updateAdvanced(activeInputMonth, 'disposalAdjustment', value)} /></label>
                  <label>제품 폐기손실 사유<input disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 제품 폐기손실 사유`} maxLength={500} value={activeMonthInput.disposalReason} onChange={(event) => updateAdvanced(activeInputMonth, 'disposalReason', event.target.value)} /></label>
                  <label>제품 진부화 평가손실 조정액<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 제품 진부화 평가손실 조정액`} value={activeMonthInput.obsolescenceAdjustment} onChange={(value) => updateAdvanced(activeInputMonth, 'obsolescenceAdjustment', value)} /></label>
                  <label>제품 진부화 평가손실 사유<input disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 제품 진부화 평가손실 사유`} maxLength={500} value={activeMonthInput.obsolescenceReason} onChange={(event) => updateAdvanced(activeInputMonth, 'obsolescenceReason', event.target.value)} /></label>
                </div>
              </section>
              <section className="forecast-workflow__advanced-block" aria-labelledby="forecast-new-business-title">
                <h3 id="forecast-new-business-title">신사업 입력 및 참고 기준값</h3>
                <p className="forecast-workflow__advanced-block-help">신사업 매출원가는 서버에 직접 반영합니다. 비율·운송·포장 기준값은 참고용으로 전달되며 자동으로 비용을 반영하지 않습니다.</p>
                <div className="forecast-workflow__advanced-fields">
                  <label>신사업 매출원가 직접 반영액<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 신사업 매출원가 직접 반영액`} value={activeMonthInput.newBusinessGoodsCogs} onChange={(value) => updateAdvanced(activeInputMonth, 'newBusinessGoodsCogs', value)} /></label>
                  <label>신사업 매출원가 사유<input disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 신사업 매출원가 사유`} maxLength={500} value={activeMonthInput.newBusinessGoodsCogsReason} onChange={(event) => updateAdvanced(activeInputMonth, 'newBusinessGoodsCogsReason', event.target.value)} /></label>
                  <label>UF/MBR 매출원가 비율 (0~1)<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 UF/MBR 매출원가 비율`} value={activeMonthInput.ufMbrCogsRate} onChange={(value) => updateAdvanced(activeInputMonth, 'ufMbrCogsRate', value)} /></label>
                  <label>IX 매출원가 비율 (0~1)<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 IX 매출원가 비율`} value={activeMonthInput.ixCogsRate} onChange={(value) => updateAdvanced(activeInputMonth, 'ixCogsRate', value)} /></label>
                  <label>UF/MBR 운송비 비율 (0~1)<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 UF/MBR 운송비 비율`} value={activeMonthInput.ufMbrTransportRate} onChange={(value) => updateAdvanced(activeInputMonth, 'ufMbrTransportRate', value)} /></label>
                  <label>IX 운송비 비율 (0~1)<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 IX 운송비 비율`} value={activeMonthInput.ixTransportRate} onChange={(value) => updateAdvanced(activeInputMonth, 'ixTransportRate', value)} /></label>
                  <label>IX 포장 기준량<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 IX 포장 기준량`} value={activeMonthInput.ixPackLiters} onChange={(value) => updateAdvanced(activeInputMonth, 'ixPackLiters', value)} /></label>
                  <label>IX 포장 단가<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 IX 포장 단가`} value={activeMonthInput.ixPackCost} onChange={(value) => updateAdvanced(activeInputMonth, 'ixPackCost', value)} /></label>
                </div>
              </section>
              <section className="forecast-workflow__advanced-block" aria-labelledby="forecast-tariff-title">
                <h3 id="forecast-tariff-title">북미·남미 관세 참고 기준값</h3>
                <p className="forecast-workflow__advanced-block-help">관세 원시 입력은 참고 기준값으로 전달합니다. 판관비에 자동 반영하지 않으며, 실제 반영은 판관비 조정액으로 입력합니다.</p>
                <div className="forecast-workflow__advanced-fields">
                  <label>기준 북미·남미 매출<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 기준 북미·남미 매출`} value={activeMonthInput.planNaSaSales} onChange={(value) => updateAdvanced(activeInputMonth, 'planNaSaSales', value)} /></label>
                  <label>추정 북미·남미 매출<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 추정 북미·남미 매출`} value={activeMonthInput.naSaSales} onChange={(value) => updateAdvanced(activeInputMonth, 'naSaSales', value)} /></label>
                  <label>관세 적용 비율 (0~1)<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 관세 적용 비율`} value={activeMonthInput.tariffApplicableRate} onChange={(value) => updateAdvanced(activeInputMonth, 'tariffApplicableRate', value)} /></label>
                  <label>관세율 (0~1)<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 관세율`} value={activeMonthInput.tariffRate} onChange={(value) => updateAdvanced(activeInputMonth, 'tariffRate', value)} /></label>
                </div>
              </section>
              <section className="forecast-workflow__advanced-block" aria-labelledby="forecast-raw-material-title">
                <h3 id="forecast-raw-material-title">원재료 관세 환급</h3>
                <p className="forecast-workflow__advanced-block-help">모형 산출값 기준에서는 조정액을, 구매팀 예상 금액 기준에서는 직접 입력액을 사용합니다. 환급액은 서버에서 계산합니다.</p>
                <div className="forecast-workflow__advanced-fields">
                  <fieldset className="forecast-workflow__radio-group"><legend>원재료 기준</legend><label><input type="radio" name={`raw-material-basis-${activeInputMonth}`} disabled={advancedControlsDisabled} checked={activeMonthInput.rawMaterialBasis === 'model'} onChange={() => updateAdvanced(activeInputMonth, 'rawMaterialBasis', 'model')} />모형 산출값</label><label><input type="radio" name={`raw-material-basis-${activeInputMonth}`} disabled={advancedControlsDisabled} checked={activeMonthInput.rawMaterialBasis === 'direct'} onChange={() => updateAdvanced(activeInputMonth, 'rawMaterialBasis', 'direct')} />구매팀 예상 금액</label></fieldset>
                  <label>원재료 직접 입력액{activeMonthInput.rawMaterialBasis === 'direct' && <span className="forecast-workflow__required">필수</span>}<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled || activeMonthInput.rawMaterialBasis !== 'direct'} aria-label={`${activeInputMonth}월 원재료 직접 입력액`} value={activeMonthInput.rawMaterialDirect} onChange={(value) => updateAdvanced(activeInputMonth, 'rawMaterialDirect', value)} /></label>
                  <label>원재료 조정액 (모형 기준)<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled || activeMonthInput.rawMaterialBasis !== 'model'} aria-label={`${activeInputMonth}월 원재료 조정액`} value={activeMonthInput.rawMaterialAdjustment} onChange={(value) => updateAdvanced(activeInputMonth, 'rawMaterialAdjustment', value)} /></label>
                  <label>원재료 사유<input disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 원재료 사유`} maxLength={500} value={activeMonthInput.rawMaterialReason} onChange={(event) => updateAdvanced(activeInputMonth, 'rawMaterialReason', event.target.value)} /></label>
                  <label>환급률 (0~1)<EditableNumericInput mode="decimal" disabled={advancedControlsDisabled} aria-label={`${activeInputMonth}월 환급률`} value={activeMonthInput.refundRate} onChange={(value) => updateAdvanced(activeInputMonth, 'refundRate', value)} /></label>
                </div>
              </section>
            </div>
          </details>
        </> : <p className="forecast-workflow__empty-input">유효한 기간을 선택하면 판매·생산 입력표가 표시됩니다.</p>}
      </section>
    </div>

    <section className="forecast-workflow__selection-summary" aria-label="추정 산출 요약">
      <div><span>산출 기간</span><strong>{hasOrderedRange ? `${startMonth}~${endMonth}월 · ${selectedMonthCount}개월` : '기간을 선택하세요'}</strong></div>
      <div><span>기준 모형</span><strong>{selectedBaseModel ? `${selectedBaseModel.display_name} · ${selectedBaseModel.model_year}년` : '모형을 선택하세요'}</strong></div>
      <div><span>직접입력 범위</span><strong>판매 {SALES_PRODUCTS.length} · 생산 전공정 3 / 후공정 3 · MCM {MCM_PRODUCTS.length}</strong></div>
      <div><span>{String(activeInputMonth).padStart(2, '0')}월 고급 입력</span><strong>{advancedEnteredCount ? `${advancedEnteredCount}개 변경` : '변경 없음'}</strong></div>
      <div><span>결과 유형</span><strong>추정 모형</strong></div>
    </section>
    <div className="forecast-workflow__actions">
      <div className="forecast-workflow__action-copy" aria-live="polite">
        {state === 'SUBMITTING' ? <><span className="forecast-workflow__spinner" aria-hidden="true" />{startMonth}~{endMonth}월 추정 산출을 접수하고 계산 중입니다. 입력은 잠겨 있습니다.</> : <>입력값과 기간을 확인한 뒤 추정 모형 생성을 실행하세요.</>}
      </div>
      <button type="button" className="forecast-workflow__primary" disabled={submitDisabled} onClick={submit}>{state === 'SUBMITTING' ? '추정 산출 중…' : '추정 모형 생성'}</button>
    </div>
    {message && <p className={`forecast-workflow__message ${state === 'VALIDATION_ERROR' ? 'is-validation' : ''}`} role="alert">{message}</p>}

    {result && state === 'SUCCESS' && <section className="forecast-workflow__success" aria-live="polite">
      <div className="forecast-workflow__success-heading"><CheckCircle2 size={20} aria-hidden="true" /><div><p className="forecast-workflow__eyebrow">COMPLETE</p><h2>추정 모형 생성 완료</h2></div><span className="forecast-workflow__status-pill">{result.is_published ? '공개' : '비공개'}</span></div>
      <p><strong>{result.display_name}</strong> · {result.model_year}년 {result.start_month}~{result.end_month}월</p>
      <p className="forecast-workflow__success-meta"><ShieldCheck size={14} aria-hidden="true" /> {result.is_default ? '기본 모형' : '일반 모형'} · {result.is_published ? '공개 상태' : '비공개 상태'}</p>
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
          {downloadState === 'DOWNLOADING' ? '다운로드 준비 중…' : '모형 내려받기'}
        </button>
        {onNavigateToPnl && <button type="button" className="forecast-workflow__secondary" onClick={onNavigateToPnl}>손익 현황 보기</button>}
        {onNavigateToAnalysis && <button type="button" className="forecast-workflow__secondary" onClick={onNavigateToAnalysis}>손익분석 보기</button>}
        {onNavigateToManagement && <button type="button" className="forecast-workflow__link" onClick={onNavigateToManagement}>모형 관리로 이동</button>}
      </div>
      {downloadState === 'FAILED' && downloadMessage && <p className="forecast-workflow__download-error" role="alert">{downloadMessage}</p>}
    </section>}

  </section>;
};

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Calculator, CheckCircle2, ChevronDown, Database, LockKeyhole, ShieldCheck } from 'lucide-react';
import { bffClient } from '../integration/client';
import {
  AnalysisModelDto,
  ApiClientError,
  ForecastGenerateResponseDto,
  ForecastMonthInputDto,
} from '../integration/types';

type ViewState =
  | 'LOADING'
  | 'READY'
  | 'SUBMITTING'
  | 'VALIDATION_ERROR'
  | 'SUCCESS'
  | 'EMPTY'
  | 'ERROR'
  | 'FORBIDDEN';

const V1_FORECAST_SYNC_MAX_MONTHS = 6;
const MONTH_MIN = 1;
const MONTH_MAX = 12;

export interface ForecastGenerationViewProps {
  onNavigateToPnl?: () => void;
  onNavigateToAnalysis?: () => void;
  onNavigateToManagement?: () => void;
}

const blankMonth = (month: number): ForecastMonthInputDto => ({
  month,
  sales: ['SW400', 'SW440', 'BW400', 'BW440', 'LC', 'FS_SW', 'FS_BW', 'FS_TW', 'UF_MBR', 'IX', 'OTHER']
    .map((product_code) => ({ product_code, quantity: 0, amount: 0 })),
  production: ['SW400', 'SW440', 'BW400', 'BW440', 'LC', 'FS_SW', 'FS_BW', 'FS_TW']
    .map((product_code) => ({ product_code, quantity: 0 })),
  mcm: ['SW400', 'SW440', 'BW400', 'BW440'].map((product_code) => ({ product_code, quantity: 0 })),
  manufacturing_adjustments: [],
  sga_adjustments: [],
});

const monthInput = (month: number) => JSON.stringify(blankMonth(month), null, 2);

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

function parseMonth(value: string): number {
  if (value.trim() === '') return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : 0;
}

export const ForecastGenerationView: React.FC<ForecastGenerationViewProps> = ({
  onNavigateToPnl,
  onNavigateToAnalysis,
  onNavigateToManagement,
}) => {
  const [models, setModels] = useState<AnalysisModelDto[]>([]);
  const [baseModelId, setBaseModelId] = useState('');
  const [startMonth, setStartMonth] = useState(7);
  const [endMonth, setEndMonth] = useState(7);
  const [name, setName] = useState('Forecast Model');
  const [version, setVersion] = useState('V1');
  const [inputs, setInputs] = useState<Record<number, string>>({ 7: monthInput(7) });
  const [state, setState] = useState<ViewState>('LOADING');
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<ForecastGenerateResponseDto | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const idempotencyKey = useRef(crypto.randomUUID());
  const requestSequence = useRef(0);
  const submittingRef = useRef(false);

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
      requestSequence.current += 1;
    };
  }, [loadAttempt]);

  const hasOrderedRange = Number.isInteger(startMonth) && Number.isInteger(endMonth)
    && MONTH_MIN <= startMonth && startMonth <= MONTH_MAX
    && MONTH_MIN <= endMonth && endMonth <= MONTH_MAX
    && startMonth <= endMonth;
  const selectedMonthCount = hasOrderedRange ? endMonth - startMonth + 1 : 0;
  const rangeValid = hasOrderedRange && selectedMonthCount <= V1_FORECAST_SYNC_MAX_MONTHS;
  const rangeMessage = !hasOrderedRange
    ? '시작 월과 종료 월은 1~12월 범위에서 순서대로 선택하세요.'
    : selectedMonthCount > V1_FORECAST_SYNC_MAX_MONTHS
      ? `선택한 기간은 ${selectedMonthCount}개월입니다. 한 번에 최대 6개월까지 추정할 수 있습니다.`
      : '';
  const months = useMemo(
    () => hasOrderedRange
      ? Array.from({ length: selectedMonthCount }, (_, index) => startMonth + index)
      : [],
    [hasOrderedRange, selectedMonthCount, startMonth],
  );

  useEffect(() => {
    setInputs((old) => {
      const next = { ...old };
      months.forEach((month) => {
        if (!next[month]) next[month] = monthInput(month);
      });
      return next;
    });
    requestSequence.current += 1;
    setResult(null);
    setMessage('');
    idempotencyKey.current = crypto.randomUUID();
    if (models.length && !submittingRef.current) setState('READY');
  }, [startMonth, endMonth, models.length, months]);

  const updateInput = (month: number, value: string) => {
    requestSequence.current += 1;
    setInputs((old) => ({ ...old, [month]: value }));
    setResult(null);
    setMessage('');
    setState(models.length ? 'READY' : state);
    idempotencyKey.current = crypto.randomUUID();
  };

  const updateBaseModel = (value: string) => {
    requestSequence.current += 1;
    setBaseModelId(value);
    setResult(null);
    setMessage('');
    setState('READY');
    idempotencyKey.current = crypto.randomUUID();
  };

  const submit = async () => {
    if (submittingRef.current || state === 'SUBMITTING') return;
    setMessage('');
    setResult(null);
    if (!rangeValid) {
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
    let parsed: ForecastMonthInputDto[];
    try {
      parsed = months.map((month) => {
        const value: unknown = JSON.parse(inputs[month] || '');
        if (!value || typeof value !== 'object' || Array.isArray(value)
          || (value as { month?: unknown }).month !== month) throw new Error('month');
        return value as ForecastMonthInputDto;
      });
    } catch {
      setState('VALIDATION_ERROR');
      setMessage('월별 입력 JSON과 선택 기간을 확인하세요.');
      return;
    }
    submittingRef.current = true;
    setState('SUBMITTING');
    const sequence = ++requestSequence.current;
    try {
      const saved = await bffClient.generateForecast({
        base_model_id: baseModelId,
        name,
        model_year: base.model_year,
        version,
        start_month: startMonth,
        end_month: endMonth,
        months: parsed,
        idempotency_key: idempotencyKey.current,
      });
      if (sequence !== requestSequence.current) return;
      setResult(saved);
      setState('SUCCESS');
    } catch (error: unknown) {
      if (sequence !== requestSequence.current) return;
      const mapped = safeErrorMessage(error);
      setState(mapped.state);
      setMessage(mapped.message);
    } finally {
      submittingRef.current = false;
    }
  };

  const controlsDisabled = state === 'SUBMITTING' || state === 'LOADING';
  const submitDisabled = controlsDisabled || !baseModelId || !rangeValid || !models.length;
  const selectedBaseModel = models.find((model) => model.model_id === baseModelId) || null;

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
            <input disabled={controlsDisabled} type="number" min={MONTH_MIN} max={MONTH_MAX} value={startMonth} onChange={(event) => setStartMonth(parseMonth(event.target.value))} />
          </label>
          <label className="forecast-workflow__field">종료 월
            <input disabled={controlsDisabled} type="number" min={MONTH_MIN} max={MONTH_MAX} value={endMonth} onChange={(event) => setEndMonth(parseMonth(event.target.value))} />
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
        <div className="forecast-workflow__card-heading"><div><p className="forecast-workflow__eyebrow">02 · INPUT</p><h2 id="forecast-inputs-title">월별 입력 JSON</h2></div><span className="forecast-workflow__step-state">정해진 입력 형식</span></div>
        <p className="forecast-workflow__helper">월별 입력 형식과 제품코드는 정해진 기준을 따릅니다. LC는 4인치/PCS, FS는 LENGTH/m이며 금액이나 수량을 화면에서 계산하지 않습니다.</p>
        <div className="forecast-workflow__month-list">
          {months.length ? months.map((month, index) => <details key={month} className="forecast-workflow__month" open={index === 0}>
            <summary><span>{month}월 입력</span><span className="forecast-workflow__month-meta">JSON · 입력 형식 <ChevronDown size={16} aria-hidden="true" /></span></summary>
            <label className="forecast-workflow__json-label" htmlFor={`forecast-month-${month}`}>월별 Forecast 입력
              <textarea id={`forecast-month-${month}`} disabled={controlsDisabled} aria-label={`${month}월 Forecast 입력`} value={inputs[month] || ''} onChange={(event) => updateInput(month, event.target.value)} rows={10} spellCheck={false} />
            </label>
          </details>) : <p className="forecast-workflow__empty-input">유효한 기간을 선택하면 월별 입력이 표시됩니다.</p>}
        </div>
      </section>
    </div>

    <section className="forecast-workflow__selection-summary" aria-label="추정 산출 요약">
      <div><span>산출 기간</span><strong>{hasOrderedRange ? `${startMonth}~${endMonth}월 · ${selectedMonthCount}개월` : '기간을 선택하세요'}</strong></div>
      <div><span>기준 모형</span><strong>{selectedBaseModel ? `${selectedBaseModel.display_name} · ${selectedBaseModel.model_year}년` : '모형을 선택하세요'}</strong></div>
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
      <div className="forecast-workflow__cta-row">
        {onNavigateToPnl && <button type="button" className="forecast-workflow__secondary" onClick={onNavigateToPnl}>손익 현황 보기</button>}
        {onNavigateToAnalysis && <button type="button" className="forecast-workflow__secondary" onClick={onNavigateToAnalysis}>손익분석 보기</button>}
        {onNavigateToManagement && <button type="button" className="forecast-workflow__link" onClick={onNavigateToManagement}>모형 관리로 이동</button>}
      </div>
    </section>}

  </section>;
};

import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Play, RefreshCw } from 'lucide-react';
import { EmptyState } from '../components/common/EmptyState';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { bffClient } from './client';
import {
  AnalysisModelDto,
  AnalysisPresentationDto,
  ApiClientError,
  JobStatusDto,
  Role,
  SubmitRequest,
  ViewerAnalysisResultOptionDto,
  ViewerState,
} from './types';
import { AnalysisPresentationPanel } from './AnalysisPresentationPanel';
import {
  EditableNumericInput,
  normalizeMonthInput,
  parseDecimalInput,
  parseMonthInput,
} from './EditableNumericInput';
import '../styles/variance-analysis-shell.css';

type FormState = Omit<SubmitRequest, 'idempotency_key' | 'start_month' | 'end_month' | 'baseline_sales_fx' | 'comparison_sales_fx' | 'baseline_sales_fx_monthly' | 'comparison_sales_fx_monthly'> & {
  start_month: string;
  end_month: string;
};

type ParsedFormState = Omit<SubmitRequest, 'idempotency_key'>;
type MonthlyFxInput = Record<string, { baseline: string; comparison: string }>;

const INITIAL_FORM: FormState = {
  baseline_model_id: '',
  comparison_model_id: '',
  start_month: '01',
  end_month: '12',
};

const ACTIVE_JOB_STORAGE_KEY = 'pnl.active-analysis-job-id';

const EXECUTION_STATE_LABELS: Record<JobStatusDto['execution_state'], string> = {
  QUEUED: '분석 요청 접수',
  STARTING_WORKER: '분석 엔진 준비 중',
  PROCESSING: '손익 분석 중',
  COMPLETED: '분석 완료',
  FAILED: '분석 실패',
};

export function CoreAnalysisView({ role, modelRefreshKey = 0, initialResultId }: { role: Role; modelRefreshKey?: number; initialResultId?: string }) {
  const [models, setModels] = useState<AnalysisModelDto[]>([]);
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [monthlyFx, setMonthlyFx] = useState<MonthlyFxInput>({});
  const [job, setJob] = useState<JobStatusDto | null>(null);
  const [result, setResult] = useState<AnalysisPresentationDto | null>(null);
  const [viewerState, setViewerState] = useState<ViewerState>('EMPTY');
  const [error, setError] = useState<string | null>(null);
  const [resultId, setResultId] = useState('');
  const [viewerOptions, setViewerOptions] = useState<ViewerAnalysisResultOptionDto[]>([]);
  const [viewerListState, setViewerListState] = useState<'LOADING' | 'READY' | 'EMPTY' | 'ERROR'>('LOADING');
  const [viewerListError, setViewerListError] = useState<string | null>(null);
  const logicalRequest = useRef<{ fingerprint: string; key: string } | null>(null);
  const viewerRequestSequence = useRef(0);
  const viewerListRequestSequence = useRef(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (role !== 'admin' || initialResultId) return;
    const activeJobId = window.sessionStorage.getItem(ACTIVE_JOB_STORAGE_KEY);
    if (!activeJobId) return;
    let active = true;
    bffClient.job(activeJobId).then((storedJob) => {
      if (!active) return;
      setJob(storedJob);
      if (storedJob.status === 'FAILED') {
        setViewerState('JOB_FAILED');
        setError(storedJob.error_message || '분석 Job이 실패했습니다.');
      } else {
        setViewerState('LOADING');
      }
    }).catch((value) => {
      if (!active) return;
      setViewerState(errorState(value));
      setError(safeMessage(value));
    });
    return () => { active = false; };
  }, [role, initialResultId]);

  useEffect(() => {
    if (role !== 'admin' || !initialResultId) return;
    let active = true;
    setJob(null);
    setResult(null);
    setResultId(initialResultId);
    setViewerState('LOADING');
    setError(null);
    bffClient.adminPresentation(initialResultId).then((stored) => {
      if (!active) return;
      setResult(stored);
      setResultId(stored.identity.result_id);
      setViewerState('READY');
    }).catch((value) => {
      if (!active) return;
      setResult(null);
      setViewerState(errorState(value));
      setError(safeMessage(value));
    });
    return () => { active = false; };
  }, [role, initialResultId]);

  useEffect(() => {
    if (role !== 'admin') return;
    let active = true;
    setError(null);
    bffClient.models().then((rows) => {
      if (!active) return;
      setModels(rows);
      if (rows.length >= 2) {
        setForm((value) => ({
          ...value,
          baseline_model_id: value.baseline_model_id || rows[0].model_id,
          comparison_model_id: value.comparison_model_id || rows[1].model_id,
        }));
      }
    }).catch((value) => {
      if (active && !initialResultId) {
        setViewerState(errorState(value));
        setError(safeMessage(value));
      }
    });
    return () => { active = false; };
  }, [role, modelRefreshKey, initialResultId]);

  useEffect(() => {
    if (role !== 'viewer') return;
    const requestSequence = ++viewerListRequestSequence.current;
    setJob(null);
    setResult(null);
    setResultId('');
    setViewerOptions([]);
    setViewerState('EMPTY');
    setError(null);
    setViewerListState('LOADING');
    setViewerListError(null);

    bffClient.viewerAnalysisResults().then((rows) => {
      if (requestSequence !== viewerListRequestSequence.current) return;
      setViewerOptions(rows);
      if (rows.length === 0) {
        setViewerListState('EMPTY');
        setViewerState('EMPTY');
        return;
      }
      setViewerListState('READY');
      void loadViewerResult(rows[0].result_id);
    }).catch((value) => {
      if (requestSequence !== viewerListRequestSequence.current) return;
      setViewerOptions([]);
      setViewerListState('ERROR');
      setViewerListError(safeMessage(value));
    });

    return () => {
      if (viewerListRequestSequence.current === requestSequence) {
        viewerListRequestSequence.current += 1;
      }
      viewerRequestSequence.current += 1;
    };
  }, [role]);

  useEffect(() => {
    if (initialResultId || !job || !['PENDING', 'PROCESSING'].includes(job.status)) return;
    let active = true;
    let timeoutId: number | undefined;
    let delay = 1000;
    let polls = 0;
    let controller: AbortController | null = null;

    const poll = async () => {
      polls += 1;
      if (polls > 120) {
        setViewerState('ERROR'); setError('Job 상태 확인 시간이 초과되었습니다.'); return;
      }
      controller = new AbortController();
      try {
        const next = await bffClient.job(job.job_id, controller.signal);
        if (!active) return;
        setJob(next);
        if (next.status === 'COMPLETED') {
          return;
        }
        if (next.status === 'FAILED') {
          setViewerState('JOB_FAILED');
          setError(next.error_message || '분석 Job이 실패했습니다.');
          return;
        }
        delay = Math.min(Math.round(delay * 1.5), 5000);
        timeoutId = window.setTimeout(poll, delay);
      } catch (value) {
        if (!active || (value instanceof DOMException && value.name === 'AbortError')) return;
        if (value instanceof ApiClientError && value.code === 'INPUT_INTEGRITY_MISMATCH') {
          setResult(null); setViewerState('INVALID_PAYLOAD'); setError(value.message); return;
        }
        if (value instanceof ApiClientError && value.code !== 'TRANSIENT_SYSTEM_ERROR') {
          setResult(null); setViewerState(errorState(value)); setError(value.message); return;
        }
        setError(safeMessage(value));
        delay = Math.min(Math.round(delay * 2), 5000);
        timeoutId = window.setTimeout(poll, delay);
      }
    };
    timeoutId = window.setTimeout(poll, delay);
    return () => {
      active = false;
      if (timeoutId) window.clearTimeout(timeoutId);
      controller?.abort();
    };
  }, [initialResultId, job?.job_id, job?.status]);

  useEffect(() => {
    if (initialResultId || job?.status !== 'COMPLETED') return;
    if (!job.result_id) {
      setResult(null); setViewerState('INVALID_PAYLOAD'); setError('완료 Job에 Result 식별자가 없습니다.');
      return;
    }
    let active = true;
    setResult(null); setViewerState('LOADING'); setError(null);
    bffClient.adminPresentation(job.result_id).then((stored) => {
      if (!active) return;
      setResult(stored); setResultId(stored.identity.result_id); setViewerState('READY');
    }).catch((value) => {
      if (!active) return;
      setViewerState(errorState(value));
      setError(safeMessage(value));
    });
    return () => { active = false; };
  }, [initialResultId, job?.status, job?.result_id]);

  useEffect(() => {
    if (role !== 'admin' || initialResultId) return;
    setJob(null);
    setResult(null);
    setResultId('');
    setViewerState('EMPTY');
    setError(null);
  }, [role, initialResultId]);

  const parsedStartMonth = parseMonthInput(form.start_month);
  const parsedEndMonth = parseMonthInput(form.end_month);
  const baseModelObj = models.find((model) => model.model_id === form.baseline_model_id);
  const compModelObj = models.find((model) => model.model_id === form.comparison_model_id);
  const analysisYear = baseModelObj?.model_year;
  const monthlyFxKeys = useMemo(() => (
    analysisYear !== undefined
    && parsedStartMonth !== null
    && parsedEndMonth !== null
    && parsedStartMonth <= parsedEndMonth
      ? Array.from(
        { length: parsedEndMonth - parsedStartMonth + 1 },
        (_, index) => `${analysisYear}-${String(parsedStartMonth + index).padStart(2, '0')}`,
      )
      : []
  ), [analysisYear, parsedStartMonth, parsedEndMonth]);

  useEffect(() => {
    setMonthlyFx((previous) => Object.fromEntries(
      monthlyFxKeys.map((key) => [key, previous[key] ?? { baseline: '', comparison: '' }]),
    ));
  }, [monthlyFxKeys.join('|')]);

  const fingerprint = useMemo(() => JSON.stringify({ form, monthlyFx }), [form, monthlyFx]);
  const parsedBaselineSalesFxMonthly: Record<string, number> = {};
  const parsedComparisonSalesFxMonthly: Record<string, number> = {};
  let monthlyFxValid = monthlyFxKeys.length > 0;
  for (const key of monthlyFxKeys) {
    const baseline = parseDecimalInput(monthlyFx[key]?.baseline ?? '');
    const comparison = parseDecimalInput(monthlyFx[key]?.comparison ?? '');
    if (baseline === null || comparison === null || baseline <= 0 || comparison <= 0) {
      monthlyFxValid = false;
      continue;
    }
    parsedBaselineSalesFxMonthly[key] = baseline;
    parsedComparisonSalesFxMonthly[key] = comparison;
  }
  const parsedForm: ParsedFormState | null = parsedStartMonth !== null
    && parsedEndMonth !== null
    && parsedStartMonth <= parsedEndMonth
    && monthlyFxValid
    ? {
      baseline_model_id: form.baseline_model_id,
      comparison_model_id: form.comparison_model_id,
      start_month: parsedStartMonth,
      end_month: parsedEndMonth,
      baseline_sales_fx_monthly: parsedBaselineSalesFxMonthly,
      comparison_sales_fx_monthly: parsedComparisonSalesFxMonthly,
    }
    : null;
  const formValid = Boolean(
    parsedForm
    && form.baseline_model_id
    && form.comparison_model_id
    && form.baseline_model_id !== form.comparison_model_id,
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!formValid || !parsedForm || isSubmitting || isJobActive(job)) return;
    setIsSubmitting(true);
    setError(null);
    setResult(null);
    setViewerState('LOADING');
    if (!logicalRequest.current || logicalRequest.current.fingerprint !== fingerprint) {
      logicalRequest.current = { fingerprint, key: crypto.randomUUID() };
    }
    try {
      const response = await bffClient.submit({ ...parsedForm, idempotency_key: logicalRequest.current.key });
      window.sessionStorage.setItem(ACTIVE_JOB_STORAGE_KEY, response.job_id);
      setJob({
        job_id: response.job_id,
        status: response.status,
        baseline_model_id: form.baseline_model_id,
        comparison_model_id: form.comparison_model_id,
        start_month: parsedForm.start_month,
        end_month: parsedForm.end_month,
        attempt: 0,
        max_attempts: 0,
        created_at: '', heartbeat_at: null, completed_at: null, result_id: null,
        error_code: null, error_message: null, execution_state: response.execution_state, dto_version: '1',
      });
    } catch (value) {
      setViewerState(errorState(value));
      setError(safeMessage(value));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function loadViewerResult(nextResultId: string) {
    const requestSequence = ++viewerRequestSequence.current;
    setResultId(nextResultId);
    setResult(null); // never keep a stale published Result while revalidating
    setError(null);
    if (!nextResultId) {
      setViewerState('EMPTY');
      return;
    }
    setViewerState('LOADING');
    try {
      const stored = await bffClient.viewerPresentation(nextResultId);
      if (requestSequence !== viewerRequestSequence.current) return;
      setResult(stored);
      setViewerState('READY');
    } catch (value) {
      if (requestSequence !== viewerRequestSequence.current) return;
      setResult(null);
      if (value instanceof ApiClientError && value.code === 'RESULT_NOT_AVAILABLE') {
        setViewerState('EMPTY');
        setError(null);
      } else {
        setViewerState(errorState(value));
        setError(safeMessage(value));
      }
    }
  }

  if (role === 'viewer') {
    return (
      <section className="variance-analysis-page">
        <div className="variance-query-card" data-testid="analysis-condition-card">
          <div className="variance-query-card__heading">
            <strong>공개 분석 결과 조회</strong>
            <span>공개 완료된 손익 변동 요인과 근거를 확인합니다.</span>
          </div>
          <label className="variance-result-query">
            <span className="filter-label">분석 결과 선택</span>
            <select
              aria-label="분석 결과 선택"
              className="filter-select"
              value={resultId}
              disabled={viewerListState !== 'READY'}
              onChange={(event) => void loadViewerResult(event.target.value)}
            >
              {viewerListState === 'LOADING' && <option value="">목록을 불러오는 중…</option>}
              {viewerListState === 'EMPTY' && <option value="">조회 가능한 결과 없음</option>}
              {viewerListState === 'ERROR' && <option value="">목록 조회 실패</option>}
              {viewerOptions.map((option) => (
                <option key={option.result_id} value={option.result_id}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>
        {viewerListState === 'LOADING' && <div className="variance-state-card"><LoadingSpinner message="공개 분석 결과 목록을 불러오는 중입니다…" /></div>}
        {viewerListState === 'ERROR' && <StateMessage kind="error" title="분석 결과 목록을 불러오지 못했습니다." description={viewerListError || '잠시 후 다시 시도하거나 관리자에게 문의하세요.'} />}
        {viewerListState === 'EMPTY' && <ResultState state="EMPTY" error={null} result={null} role={role} />}
        {viewerListState === 'READY' && <ResultState state={viewerState} error={error} result={result} role={role}
          onUnavailable={() => { setResult(null); setViewerState('EMPTY'); setError(null); }} />}
      </section>
    );
  }

  let analysisTypeLabel = '';
  if (baseModelObj && compModelObj) {
    if (baseModelObj.model_type === 'PLAN' && compModelObj.model_type === 'ACTUAL') {
      analysisTypeLabel = '계획 대비 실적';
    } else if (baseModelObj.model_type === 'PLAN' && compModelObj.model_type === 'FORECAST') {
      analysisTypeLabel = '계획 대비 추정';
    } else if (baseModelObj.model_type === 'ACTUAL' && compModelObj.model_type === 'ACTUAL') {
      analysisTypeLabel = '실적 간 비교';
    } else {
      analysisTypeLabel = '모형 비교';
    }
  }

  return (
    <section className="variance-analysis-page">
      <form onSubmit={submit} className="variance-analysis-controls" data-testid="analysis-condition-card">
        <div className="variance-control-heading">
          <div>
            <strong>분석 조건 설정</strong>
            <span>기준 모형과 비교 모형의 손익 변동 요인을 분석합니다.</span>
          </div>
          {analysisTypeLabel ? (
            <span style={{
              fontSize: '12px',
              fontWeight: 700,
              backgroundColor: '#eff6ff',
              color: '#1d4ed8',
              padding: '4px 12px',
              borderRadius: '4px',
              border: '1px solid #bfdbfe',
            }}>
              {analysisTypeLabel}
            </span>
          ) : (
            <span className="unit-tag">실제 Job 상태만 표시</span>
          )}
        </div>
        <div className="variance-control-grid">
          <ModelSelect label="기준 모형" value={form.baseline_model_id} models={models} disabled={isSubmitting || isJobActive(job)}
            onChange={(value) => setForm({ ...form, baseline_model_id: value })} />
          <ModelSelect label="비교 모형" value={form.comparison_model_id} models={models} disabled={isSubmitting || isJobActive(job)}
            onChange={(value) => setForm({ ...form, comparison_model_id: value })} />
          <NumberInput mode="month" label="시작 월" value={form.start_month} disabled={isSubmitting || isJobActive(job)} onChange={(value) => setForm({ ...form, start_month: value })} />
          <NumberInput mode="month" label="종료 월" value={form.end_month} disabled={isSubmitting || isJobActive(job)} onChange={(value) => setForm({ ...form, end_month: value })} />
          <div className="variance-monthly-fx" aria-label="월별 매출환율 입력">
            <div className="variance-monthly-fx__heading">
              <strong>월별 매출환율 (KRW/USD)</strong>
              <span>선택기간의 각 월 환율을 개별 입력합니다.</span>
            </div>
            <div className="variance-monthly-fx__table">
              <div className="variance-monthly-fx__row is-header" aria-hidden="true">
                <span>월</span><span>기준 매출환율</span><span>비교 매출환율</span>
              </div>
              {monthlyFxKeys.map((key) => (
                <div className="variance-monthly-fx__row" key={key}>
                  <span className="variance-monthly-fx__month">{key}</span>
                  <EditableNumericInput
                    className="filter-select variance-monthly-fx__input"
                    mode="decimal"
                    value={monthlyFx[key]?.baseline ?? ''}
                    disabled={isSubmitting || isJobActive(job)}
                    aria-label={`${key} 기준 매출환율 (KRW/USD)`}
                    aria-invalid={parseDecimalInput(monthlyFx[key]?.baseline ?? '') === null}
                    onChange={(value) => setMonthlyFx((current) => ({
                      ...current,
                      [key]: { ...(current[key] ?? { baseline: '', comparison: '' }), baseline: value },
                    }))}
                  />
                  <EditableNumericInput
                    className="filter-select variance-monthly-fx__input"
                    mode="decimal"
                    value={monthlyFx[key]?.comparison ?? ''}
                    disabled={isSubmitting || isJobActive(job)}
                    aria-label={`${key} 비교 매출환율 (KRW/USD)`}
                    aria-invalid={parseDecimalInput(monthlyFx[key]?.comparison ?? '') === null}
                    onChange={(value) => setMonthlyFx((current) => ({
                      ...current,
                      [key]: { ...(current[key] ?? { baseline: '', comparison: '' }), comparison: value },
                    }))}
                  />
                </div>
              ))}
            </div>
          </div>
          <div className="variance-control-actions">
            <button className="btn btn-primary variance-control-run" disabled={!formValid || isSubmitting || isJobActive(job)}>
              <Play size={14} fill="currentColor" />{isSubmitting ? '요청 중…' : '분석 실행'}
            </button>
            <button type="button" className="btn btn-secondary" disabled={isSubmitting || isJobActive(job)} onClick={() => {
              window.sessionStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
              logicalRequest.current = null; setJob(null); setResult(null); setViewerState('EMPTY'); setError(null);
            }}>
              <RefreshCw size={14} />새 분석
            </button>
          </div>
        </div>
      </form>
      {error && !['ERROR', 'JOB_FAILED', 'FORBIDDEN', 'INVALID_PAYLOAD'].includes(viewerState) && <div role="alert" style={{ color: '#b91c1c', marginTop: 10 }}>{error}</div>}
      {job && <div className={`variance-job-status variance-job-status-${job.status.toLowerCase()}`} data-testid="job-status">
        <div>
          <span className="variance-job-eyebrow">분석 진행상태</span>
          <strong>{EXECUTION_STATE_LABELS[job.execution_state]}</strong>
        </div>
        <div className="variance-job-meta tabular-nums">시도 {job.attempt}/{job.max_attempts || '-'} · Job {job.job_id}</div>
      </div>}
      <ResultState state={viewerState} error={error} result={result} role={role} />
    </section>
  );
}

function ModelSelect({ label, value, models, disabled, onChange }: { label: string; value: string; models: AnalysisModelDto[]; disabled: boolean; onChange: (value: string) => void }) {
  return (
    <div className="variance-control-field">
      <label>
        <span className="filter-label">{label}</span>
        <select className="filter-select" style={{ width: '100%' }} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
          <option value="">선택</option>
          {models.map((model) => <option key={model.model_id} value={model.model_id}>[{model.model_type}] {model.display_name} ({model.model_year})</option>)}
        </select>
      </label>
    </div>
  );
}

function NumberInput({ mode, label, value, disabled, onChange }: { mode: 'month' | 'decimal'; label: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  return (
    <div className="variance-control-field">
      <label>
        <span className="filter-label">{label}</span>
        <EditableNumericInput
          className="filter-select"
          style={{ width: '100%' }}
          mode={mode}
          value={value}
          disabled={disabled}
          onChange={onChange}
          onValueBlur={mode === 'month' ? (nextValue) => onChange(normalizeMonthInput(nextValue)) : undefined}
        />
      </label>
    </div>
  );
}

function ResultState({ state, error, result, role, onUnavailable }: {
  state: ViewerState; error: string | null; result: AnalysisPresentationDto | null; role: Role; onUnavailable?: () => void;
}) {
  if (state === 'LOADING') return <div className="variance-state-card"><LoadingSpinner message="손익 분석 결과를 불러오는 중입니다…" /></div>;
  if (state === 'JOB_FAILED') return <StateMessage kind="error" title="분석 계산에 실패했습니다." description={error || '잠시 후 다시 시도하거나 관리자에게 문의하세요.'} />;
  if (state === 'ERROR') return <StateMessage kind="error" title="분석 결과를 불러오지 못했습니다." description={error || '잠시 후 다시 시도하거나 관리자에게 문의하세요.'} />;
  if (state === 'FORBIDDEN') return <StateMessage kind="forbidden" title="이 분석 결과를 볼 권한이 없습니다." description="현재 계정의 Viewer/Admin 권한을 확인해 주세요." />;
  if (state === 'INVALID_PAYLOAD') return <StateMessage kind="integrity" title="분석 결과의 무결성을 확인할 수 없습니다." description={error || '서버가 제공한 결과 계약이 올바르지 않습니다.'} />;
  if (state === 'EMPTY' || !result) return <div className="variance-state-card" data-testid="viewer-empty"><EmptyState
    title={role === 'viewer' ? '조회 가능한 공개 분석 결과가 없습니다.' : '아직 생성된 분석 결과가 없습니다.'}
    description={role === 'viewer' ? '비교할 수 있는 분석 결과가 공개되면 이 화면에서 확인할 수 있습니다.' : '분석 조건을 선택하고 실행하면 결과가 이 화면에 표시됩니다.'}
  /></div>;
  return <div data-testid="stored-result">
    <AnalysisPresentationPanel value={result} role={role} onUnavailable={onUnavailable} />
  </div>;
}

function StateMessage({ kind, title, description }: { kind: 'error' | 'forbidden' | 'integrity'; title: string; description: string }) {
  return <div role="alert" className={`variance-state-message variance-state-message-${kind}`}>
    <strong>{title}</strong><span>{description}</span>
  </div>;
}

function isJobActive(job: JobStatusDto | null): boolean {
  return job?.status === 'PENDING' || job?.status === 'PROCESSING';
}

function errorState(value: unknown): ViewerState {
  if (value instanceof ApiClientError && (value.status === 403 || value.code === 'FORBIDDEN')) return 'FORBIDDEN';
  if (value instanceof ApiClientError && value.code === 'INPUT_INTEGRITY_MISMATCH') return 'INVALID_PAYLOAD';
  return 'ERROR';
}

function safeMessage(value: unknown): string {
  return value instanceof ApiClientError ? value.message : '요청을 처리할 수 없습니다.';
}

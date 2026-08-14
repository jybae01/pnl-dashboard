import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Play, RefreshCw, Search } from 'lucide-react';
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

type FormState = Omit<SubmitRequest, 'idempotency_key' | 'start_month' | 'end_month' | 'baseline_sales_fx' | 'comparison_sales_fx'> & {
  start_month: string;
  end_month: string;
  baseline_sales_fx: string;
  comparison_sales_fx: string;
};

type ParsedFormState = Omit<SubmitRequest, 'idempotency_key'>;

const INITIAL_FORM: FormState = {
  baseline_model_id: '',
  comparison_model_id: '',
  start_month: '01',
  end_month: '12',
  baseline_sales_fx: '1450',
  comparison_sales_fx: '1450',
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
  const [job, setJob] = useState<JobStatusDto | null>(null);
  const [result, setResult] = useState<AnalysisPresentationDto | null>(null);
  const [viewerState, setViewerState] = useState<ViewerState>('EMPTY');
  const [error, setError] = useState<string | null>(null);
  const [resultId, setResultId] = useState('');
  const logicalRequest = useRef<{ fingerprint: string; key: string } | null>(null);
  const viewerRequestSequence = useRef(0);
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
        setViewerState('ERROR');
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
          setViewerState('ERROR');
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
    if (initialResultId) return;
    setJob(null);
    setResult(null);
    setResultId('');
    setViewerState('EMPTY');
    setError(null);
  }, [initialResultId]);

  const fingerprint = useMemo(() => JSON.stringify(form), [form]);
  const parsedStartMonth = parseMonthInput(form.start_month);
  const parsedEndMonth = parseMonthInput(form.end_month);
  const parsedBaselineSalesFx = parseDecimalInput(form.baseline_sales_fx);
  const parsedComparisonSalesFx = parseDecimalInput(form.comparison_sales_fx);
  const parsedForm: ParsedFormState | null = parsedStartMonth !== null
    && parsedEndMonth !== null
    && parsedStartMonth <= parsedEndMonth
    && parsedBaselineSalesFx !== null
    && parsedComparisonSalesFx !== null
    ? {
      baseline_model_id: form.baseline_model_id,
      comparison_model_id: form.comparison_model_id,
      start_month: parsedStartMonth,
      end_month: parsedEndMonth,
      baseline_sales_fx: parsedBaselineSalesFx,
      comparison_sales_fx: parsedComparisonSalesFx,
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

  async function readViewerResult(event: FormEvent) {
    event.preventDefault();
    const requestSequence = ++viewerRequestSequence.current;
    setResult(null); // never keep a stale published Result while revalidating
    setError(null);
    if (!resultId.trim()) {
      setViewerState('EMPTY');
      return;
    }
    setViewerState('LOADING');
    try {
      const stored = await bffClient.viewerPresentation(resultId.trim());
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
        <AnalysisPageHeading role={role} />
        <form onSubmit={readViewerResult} className="variance-query-card">
          <label className="variance-result-query">
            <span className="filter-label">공개 결과 ID</span>
            <input aria-label="Result ID" className="filter-select" value={resultId}
              onChange={(event) => setResultId(event.target.value)} placeholder="Result ID를 입력하세요" />
          </label>
          <button className="btn btn-primary"><Search size={14} />조회</button>
        </form>
        <ResultState state={viewerState} error={error} result={result} role={role}
          onUnavailable={() => { setResult(null); setViewerState('EMPTY'); setError(null); }} />
      </section>
    );
  }

  return (
    <section className="variance-analysis-page">
      <AnalysisPageHeading role={role} />
      <form onSubmit={submit} className="variance-analysis-controls">
        <div className="variance-control-heading">
          <div><strong>분석 조건</strong><span>기준 모형과 비교 모형의 저장 결과를 생성합니다.</span></div>
          <span className="unit-tag">실제 Job 상태만 표시</span>
        </div>
        <div className="variance-control-grid">
          <ModelSelect label="기준 모형" value={form.baseline_model_id} models={models} disabled={isSubmitting || isJobActive(job)}
            onChange={(value) => setForm({ ...form, baseline_model_id: value })} />
          <ModelSelect label="비교 모형" value={form.comparison_model_id} models={models} disabled={isSubmitting || isJobActive(job)}
            onChange={(value) => setForm({ ...form, comparison_model_id: value })} />
          <NumberInput mode="month" label="시작 월" value={form.start_month} disabled={isSubmitting || isJobActive(job)} onChange={(value) => setForm({ ...form, start_month: value })} />
          <NumberInput mode="month" label="종료 월" value={form.end_month} disabled={isSubmitting || isJobActive(job)} onChange={(value) => setForm({ ...form, end_month: value })} />
          <NumberInput mode="decimal" label="기준 매출환율 (KRW/USD)" value={form.baseline_sales_fx} disabled={isSubmitting || isJobActive(job)} onChange={(value) => setForm({ ...form, baseline_sales_fx: value })} />
          <NumberInput mode="decimal" label="비교 매출환율 (KRW/USD)" value={form.comparison_sales_fx} disabled={isSubmitting || isJobActive(job)} onChange={(value) => setForm({ ...form, comparison_sales_fx: value })} />
        </div>
        <div className="variance-control-actions">
          <button className="btn btn-primary" disabled={!formValid || isSubmitting || isJobActive(job)}><Play size={14} />{isSubmitting ? '요청 중…' : '분석 실행'}</button>
          <button type="button" className="btn btn-secondary" disabled={isSubmitting || isJobActive(job)} onClick={() => {
            window.sessionStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
            logicalRequest.current = null; setJob(null); setResult(null); setViewerState('EMPTY'); setError(null);
          }}><RefreshCw size={14} />새 분석</button>
        </div>
      </form>
      {error && !['ERROR', 'FORBIDDEN', 'INVALID_PAYLOAD'].includes(viewerState) && <div role="alert" style={{ color: '#b91c1c', marginTop: 10 }}>{error}</div>}
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

function AnalysisPageHeading({ role }: { role: Role }) {
  return <header className="variance-page-heading">
    <div><span className="variance-page-kicker">PROFIT ANALYSIS</span><h1>손익 분석</h1>
      <p>기준 모형과 비교 모형의 영업이익 변동을 Effect와 근거 항목으로 확인합니다.</p></div>
    <span className="variance-access-badge">{role === 'admin' ? 'ADMIN · 분석 실행 및 결과 조회' : 'VIEWER · 결과 조회 전용'}</span>
  </header>;
}

function ModelSelect({ label, value, models, disabled, onChange }: { label: string; value: string; models: AnalysisModelDto[]; disabled: boolean; onChange: (value: string) => void }) {
  return <label><span className="filter-label">{label}</span><select className="filter-select" style={{ width: '100%' }} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
    <option value="">선택</option>{models.map((model) => <option key={model.model_id} value={model.model_id}>[{model.model_type}] {model.display_name} ({model.model_year})</option>)}
  </select></label>;
}

function NumberInput({ mode, label, value, disabled, onChange }: { mode: 'month' | 'decimal'; label: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  return <label><span className="filter-label">{label}</span><EditableNumericInput
    className="filter-select"
    style={{ width: '100%' }}
    mode={mode}
    value={value}
    disabled={disabled}
    onChange={onChange}
    onValueBlur={mode === 'month' ? (nextValue) => onChange(normalizeMonthInput(nextValue)) : undefined}
  /></label>;
}

function ResultState({ state, error, result, role, onUnavailable }: {
  state: ViewerState; error: string | null; result: AnalysisPresentationDto | null; role: Role; onUnavailable?: () => void;
}) {
  if (state === 'LOADING') return <div className="variance-state-card"><LoadingSpinner message="손익 분석 결과를 불러오는 중입니다…" /></div>;
  if (state === 'ERROR') return <StateMessage kind="error" title="분석 결과를 불러오지 못했습니다." description={error || '잠시 후 다시 시도하거나 관리자에게 문의하세요.'} />;
  if (state === 'FORBIDDEN') return <StateMessage kind="forbidden" title="이 분석 결과를 볼 권한이 없습니다." description="현재 계정의 Viewer/Admin 권한을 확인해 주세요." />;
  if (state === 'INVALID_PAYLOAD') return <StateMessage kind="integrity" title="분석 결과의 무결성을 확인할 수 없습니다." description={error || '서버가 제공한 결과 계약이 올바르지 않습니다.'} />;
  if (state === 'EMPTY' || !result) return <div className="variance-state-card" data-testid="viewer-empty"><EmptyState
    title={role === 'viewer' ? '아직 공개된 분석 결과가 없습니다.' : '아직 생성된 분석 결과가 없습니다.'}
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

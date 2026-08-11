import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { bffClient } from './client';
import {
  AnalysisModelDto,
  ApiClientError,
  JobStatusDto,
  Role,
  StoredResultDto,
  SubmitRequest,
  ViewerState,
} from './types';
import { EvidenceDownloadButton } from './EvidenceDownloadButton';

type FormState = Omit<SubmitRequest, 'idempotency_key'>;

const INITIAL_FORM: FormState = {
  baseline_model_id: '',
  comparison_model_id: '',
  start_month: 1,
  end_month: 12,
  baseline_sales_fx: 1450,
  comparison_sales_fx: 1450,
};

export function CoreAnalysisView({ role, modelRefreshKey = 0 }: { role: Role; modelRefreshKey?: number }) {
  const [models, setModels] = useState<AnalysisModelDto[]>([]);
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [job, setJob] = useState<JobStatusDto | null>(null);
  const [result, setResult] = useState<StoredResultDto | null>(null);
  const [viewerState, setViewerState] = useState<ViewerState>('EMPTY');
  const [error, setError] = useState<string | null>(null);
  const [resultId, setResultId] = useState('');
  const logicalRequest = useRef<{ fingerprint: string; key: string } | null>(null);

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
      if (active) setError(safeMessage(value));
    });
    return () => { active = false; };
  }, [role, modelRefreshKey]);

  useEffect(() => {
    if (!job || !['PENDING', 'PROCESSING'].includes(job.status)) return;
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
          setResult(null); setViewerState('ERROR'); setError(value.message); return;
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
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    if (job?.status !== 'COMPLETED') return;
    if (!job.result_id) {
      setResult(null); setViewerState('INVALID_PAYLOAD'); setError('완료 Job에 Result 식별자가 없습니다.');
      return;
    }
    let active = true;
    setResult(null); setViewerState('LOADING'); setError(null);
    bffClient.adminResult(job.result_id).then((stored) => {
      if (!active) return;
      setResult(stored); setResultId(stored.result_id); setViewerState('READY');
    }).catch((value) => {
      if (!active) return;
      setViewerState(value instanceof ApiClientError && value.code === 'INPUT_INTEGRITY_MISMATCH' ? 'INVALID_PAYLOAD' : 'ERROR');
      setError(safeMessage(value));
    });
    return () => { active = false; };
  }, [job?.status, job?.result_id]);

  const fingerprint = useMemo(() => JSON.stringify(form), [form]);
  const formValid = form.baseline_model_id && form.comparison_model_id &&
    form.baseline_model_id !== form.comparison_model_id &&
    form.start_month >= 1 && form.start_month <= form.end_month && form.end_month <= 12 &&
    form.baseline_sales_fx > 0 && form.comparison_sales_fx > 0;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!formValid) return;
    setError(null);
    setResult(null);
    setViewerState('LOADING');
    if (!logicalRequest.current || logicalRequest.current.fingerprint !== fingerprint) {
      logicalRequest.current = { fingerprint, key: crypto.randomUUID() };
    }
    try {
      const response = await bffClient.submit({ ...form, idempotency_key: logicalRequest.current.key });
      setJob({
        job_id: response.job_id,
        status: response.status,
        baseline_model_id: form.baseline_model_id,
        comparison_model_id: form.comparison_model_id,
        start_month: form.start_month,
        end_month: form.end_month,
        attempt: 0,
        max_attempts: 0,
        created_at: '', heartbeat_at: null, completed_at: null, result_id: null,
        error_code: null, error_message: null, dto_version: '1',
      });
    } catch (value) {
      setViewerState('ERROR');
      setError(safeMessage(value));
    }
  }

  async function readViewerResult(event: FormEvent) {
    event.preventDefault();
    setResult(null); // never keep a stale published Result while revalidating
    setError(null);
    if (!resultId.trim()) {
      setViewerState('EMPTY');
      return;
    }
    setViewerState('LOADING');
    try {
      const stored = await bffClient.viewerResult(resultId.trim());
      setResult(stored);
      setViewerState('READY');
    } catch (value) {
      setResult(null);
      if (value instanceof ApiClientError && value.code === 'RESULT_NOT_AVAILABLE') {
        setViewerState('EMPTY');
        setError(null);
      } else if (value instanceof ApiClientError && value.code === 'INPUT_INTEGRITY_MISMATCH') {
        setViewerState('INVALID_PAYLOAD');
        setError(value.message);
      } else {
        setViewerState('ERROR');
        setError(safeMessage(value));
      }
    }
  }

  if (role === 'viewer') {
    return (
      <section>
        <div className="view-header-bar"><strong>게시된 손익 분석 결과</strong></div>
        <form onSubmit={readViewerResult} className="card" style={{ padding: 16, display: 'flex', gap: 8 }}>
          <input aria-label="Result ID" className="filter-select" style={{ flex: 1 }} value={resultId}
            onChange={(event) => setResultId(event.target.value)} placeholder="Result ID" />
          <button className="btn btn-primary">조회</button>
        </form>
        <ResultState state={viewerState} error={error} result={result} role={role}
          onUnavailable={() => { setResult(null); setViewerState('EMPTY'); setError(null); }} />
      </section>
    );
  }

  return (
    <section>
      <div className="view-header-bar"><strong>Base / Comparison 분석 실행</strong><span className="unit-tag">실제 Job 상태만 표시</span></div>
      <form onSubmit={submit} className="card" style={{ padding: 18 }}>
        <div className="grid-2col" style={{ gap: 12 }}>
          <ModelSelect label="Base Model" value={form.baseline_model_id} models={models}
            onChange={(value) => setForm({ ...form, baseline_model_id: value })} />
          <ModelSelect label="Comparison Model" value={form.comparison_model_id} models={models}
            onChange={(value) => setForm({ ...form, comparison_model_id: value })} />
          <NumberInput label="시작 월" value={form.start_month} onChange={(value) => setForm({ ...form, start_month: value })} />
          <NumberInput label="종료 월" value={form.end_month} onChange={(value) => setForm({ ...form, end_month: value })} />
          <NumberInput label="Base 매출환율" value={form.baseline_sales_fx} onChange={(value) => setForm({ ...form, baseline_sales_fx: value })} />
          <NumberInput label="Comparison 매출환율" value={form.comparison_sales_fx} onChange={(value) => setForm({ ...form, comparison_sales_fx: value })} />
        </div>
        <button className="btn btn-primary" disabled={!formValid || job?.status === 'PENDING' || job?.status === 'PROCESSING'} style={{ marginTop: 14 }}>
          분석 실행
        </button>
        <button type="button" className="btn btn-secondary" style={{ marginTop: 14, marginLeft: 8 }} onClick={() => {
          logicalRequest.current = null; setJob(null); setResult(null); setViewerState('EMPTY'); setError(null);
        }}>새 분석</button>
      </form>
      {error && viewerState !== 'ERROR' && viewerState !== 'INVALID_PAYLOAD' && <div role="alert" style={{ color: '#b91c1c', marginTop: 10 }}>{error}</div>}
      {job && <div className="card" data-testid="job-status" style={{ padding: 14, marginTop: 12 }}>
        <strong>{job.status}</strong> · attempt {job.attempt}/{job.max_attempts || '-'} · Job {job.job_id}
        {job.status === 'COMPLETED' && job.result_id && viewerState === 'READY' && result?.result_id === job.result_id && <div style={{ marginTop: 10 }}>
          <EvidenceDownloadButton resultId={job.result_id} role="admin" />
        </div>}
      </div>}
      <ResultState state={viewerState} error={error} result={result} role={role} />
    </section>
  );
}

function ModelSelect({ label, value, models, onChange }: { label: string; value: string; models: AnalysisModelDto[]; onChange: (value: string) => void }) {
  return <label><span className="filter-label">{label}</span><select className="filter-select" style={{ width: '100%' }} value={value} onChange={(event) => onChange(event.target.value)}>
    <option value="">선택</option>{models.map((model) => <option key={model.model_id} value={model.model_id}>[{model.model_type}] {model.display_name} ({model.model_year})</option>)}
  </select></label>;
}

function NumberInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return <label><span className="filter-label">{label}</span><input className="filter-select" style={{ width: '100%' }} type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}

function ResultState({ state, error, result, role, onUnavailable }: {
  state: ViewerState; error: string | null; result: StoredResultDto | null; role: Role; onUnavailable?: () => void;
}) {
  if (state === 'LOADING') return <div role="status" className="card" style={{ padding: 18, marginTop: 12 }}>불러오는 중…</div>;
  if (state === 'ERROR') return <div role="alert" className="card" style={{ padding: 18, marginTop: 12, color: '#b91c1c' }}>{error || '결과 조회 오류'}</div>;
  if (state === 'INVALID_PAYLOAD') return <div role="alert" className="card" style={{ padding: 18, marginTop: 12, color: '#b45309' }}>{error || '결과 계약이 올바르지 않습니다.'}</div>;
  if (state === 'EMPTY' || !result) return <div className="card" data-testid="viewer-empty" style={{ padding: 18, marginTop: 12 }}>표시할 Result가 없습니다.</div>;
  return <article className="card" data-testid="stored-result" style={{ padding: 18, marginTop: 12 }}>
    <h2 style={{ fontSize: 16 }}>Stored Result</h2>
    <div>Result {result.result_id} · Job {result.job_id}</div>
    <div style={{ marginTop: 10 }}><EvidenceDownloadButton resultId={result.result_id} role={role} onUnavailable={onUnavailable} /></div>
    <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', background: '#f8fafc', padding: 12 }}>{JSON.stringify(result.analysis_view, null, 2)}</pre>
  </article>;
}

function safeMessage(value: unknown): string {
  return value instanceof ApiClientError ? value.message : '요청을 처리할 수 없습니다.';
}

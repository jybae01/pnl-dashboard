import { useCallback, useEffect, useState } from 'react';
import { bffClient } from './client';
import { EvidenceDownloadButton } from './EvidenceDownloadButton';
import { ApiClientError, CalculationHistoryDto } from './types';

export function CalculationHistoryView() {
  const [page, setPage] = useState<CalculationHistoryDto | null>(null);
  const [state, setState] = useState<'LOADING' | 'READY' | 'EMPTY' | 'ERROR'>('LOADING');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (beforeCreatedAt?: string, beforeJobId?: string) => {
    setState('LOADING'); setError(null);
    try {
      const next = await bffClient.history(20, beforeCreatedAt, beforeJobId);
      setPage(next); setState(next.items.length ? 'READY' : 'EMPTY');
    } catch (value) {
      setPage(null); setState('ERROR');
      setError(value instanceof ApiClientError ? value.message : '계산 이력을 불러올 수 없습니다.');
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return <section className="content-card" aria-labelledby="history-heading" style={{ marginTop: 16 }}>
    <div className="section-header"><h2 id="history-heading" className="section-title">Calculation History</h2></div>
    {state === 'LOADING' && <p role="status">계산 이력 확인 중…</p>}
    {state === 'EMPTY' && <p>계산 이력이 없습니다.</p>}
    {state === 'ERROR' && <p role="alert">{error}</p>}
    {state === 'READY' && page && <>
      <table className="data-table"><thead><tr><th>상태</th><th>Base / Comparison</th><th>기간</th><th>생성</th><th>Result</th><th>Action</th></tr></thead>
        <tbody>{page.items.map((item) => <tr key={item.job_id}>
          <td>{item.status}{item.error_message ? <div className="text-muted">{item.error_message}</div> : null}</td>
          <td>{item.baseline_model_name}<br />→ {item.comparison_model_name}</td>
          <td>{item.start_month !== null && item.end_month !== null ? `${item.start_month}–${item.end_month}월` : '—'}</td>
          <td>{new Date(item.created_at).toLocaleString('ko-KR')}</td>
          <td>{item.result_id || '—'}</td>
          <td>{item.status === 'COMPLETED' && item.result_id
            ? <EvidenceDownloadButton resultId={item.result_id} role="admin" /> : null}</td>
        </tr>)}</tbody></table>
      {page.next_before_created_at && page.next_before_job_id && <button type="button" className="btn btn-secondary" onClick={() => void load(page.next_before_created_at!, page.next_before_job_id!)}>다음 페이지</button>}
    </>}
  </section>;
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, Clock3, ExternalLink, Settings2, XCircle } from 'lucide-react';
import { bffClient } from './client';
import { EvidenceDownloadButton } from './EvidenceDownloadButton';
import { ApiClientError, CalculationHistoryItemDto } from './types';
import '../styles/calculation-history.css';

type HistoryState = 'LOADING' | 'READY' | 'EMPTY' | 'FILTER_EMPTY' | 'ERROR' | 'FORBIDDEN';
type StatusFilter = 'ALL' | CalculationHistoryItemDto['status'];
type Cursor = { beforeCreatedAt: string; beforeJobId: string } | null;
type PublicationChoice = 'PRIVATE' | 'PUBLISHED' | 'DASHBOARD_DEFAULT';

const STATUS_LABELS: Record<CalculationHistoryItemDto['status'], string> = {
  PENDING: '분석 대기',
  PROCESSING: '분석 중',
  COMPLETED: '완료',
  FAILED: '분석 실패',
};

function statusLabel(status: CalculationHistoryItemDto['status']): string {
  return STATUS_LABELS[status];
}

function statusClass(status: CalculationHistoryItemDto['status']): string {
  return status.toLowerCase();
}

function periodLabel(item: Pick<CalculationHistoryItemDto, 'start_month' | 'end_month'>): string {
  return item.start_month !== null && item.end_month !== null
    ? `${item.start_month}~${item.end_month}월`
    : '기간 미제공';
}

function dateLabel(value: string | null): string {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? '—'
    : parsed.toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' });
}

function errorLabel(code: string | null): string | null {
  switch (code) {
    case 'VALIDATION_ERROR': return '입력값을 확인할 수 없습니다.';
    case 'MODEL_NOT_FOUND': return '분석 모형을 찾을 수 없습니다.';
    case 'RESULT_NOT_AVAILABLE': return '공개할 수 있는 결과가 없습니다.';
    case 'INPUT_INTEGRITY_MISMATCH': return '결과 무결성을 확인할 수 없습니다.';
    case 'INPUT_PROVENANCE_UNRESOLVED': return '분석 입력 근거를 확인할 수 없습니다.';
    case 'preflight_failed': return '워크북 사전 검증을 통과하지 못했습니다.';
    case 'upload_timeout': return '워크북 업로드 시간이 초과되었습니다.';
    case 'attempts_exhausted': return '분석 재시도 한도에 도달했습니다.';
    case 'IDEMPOTENCY_CONFLICT': return '중복 요청으로 처리되지 않았습니다.';
    case 'WORKER_BUSY': return '분석 엔진이 다른 요청을 처리 중입니다.';
    case 'TRANSIENT_SYSTEM_ERROR': return '일시적인 오류가 발생했습니다.';
    case 'FORBIDDEN': return '이 이력을 볼 권한이 없습니다.';
    default: return null;
  }
}

function safeRequestError(value: unknown): { forbidden: boolean; message: string } {
  if (!(value instanceof ApiClientError)) {
    return { forbidden: false, message: '계산 이력을 불러오지 못했습니다. 잠시 후 다시 시도하세요.' };
  }
  const forbidden = value.status === 403 || value.code === 'FORBIDDEN';
  return {
    forbidden,
    message: forbidden
      ? '계산 이력에 접근할 권한이 없습니다.'
      : errorLabel(value.code) || '계산 이력을 불러오지 못했습니다. 잠시 후 다시 시도하세요.',
  };
}

function safePublicationError(value: unknown): string {
  if (!(value instanceof ApiClientError)) return '결과 공개 설정을 변경하지 못했습니다. 잠시 후 다시 시도하세요.';
  if (value.status === 403 || value.code === 'FORBIDDEN') return '결과 공개 설정을 변경할 권한이 없습니다.';
  switch (value.code) {
    case 'VALIDATION_ERROR': return '선택한 공개 설정을 적용할 수 없습니다.';
    case 'RESULT_NOT_AVAILABLE':
    case 'RESULT_NOT_FOUND': return '공개할 계산 결과를 찾을 수 없습니다.';
    case 'INPUT_INTEGRITY_MISMATCH': return '결과 무결성을 확인할 수 없어 공개하지 않았습니다.';
    case 'TRANSIENT_SYSTEM_ERROR': return '일시적인 오류로 공개 설정을 변경하지 못했습니다.';
    default: return '결과 공개 설정을 변경하지 못했습니다. 잠시 후 다시 시도하세요.';
  }
}

function publicationChoice(item: CalculationHistoryItemDto): PublicationChoice {
  if (item.is_default) return 'DASHBOARD_DEFAULT';
  return item.is_published ? 'PUBLISHED' : 'PRIVATE';
}

function rowFailureMessage(item: CalculationHistoryItemDto): string | null {
  if (item.status !== 'FAILED') return null;
  // Prefer a presentation mapping so internal error codes and backend diagnostics never leak.
  return errorLabel(item.error_code) || '분석 요청을 완료하지 못했습니다.';
}

export interface CalculationHistoryViewProps {
  onOpenResult?: (resultId: string) => void;
}

export function CalculationHistoryView({ onOpenResult }: CalculationHistoryViewProps) {
  const [items, setItems] = useState<CalculationHistoryItemDto[]>([]);
  const [nextCursor, setNextCursor] = useState<Cursor>(null);
  const [state, setState] = useState<HistoryState>('LOADING');
  const [error, setError] = useState<string | null>(null);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [selectedItem, setSelectedItem] = useState<CalculationHistoryItemDto | null>(null);
  const [publicationTarget, setPublicationTarget] = useState<CalculationHistoryItemDto | null>(null);
  const [publicationSelection, setPublicationSelection] = useState<PublicationChoice>('PRIVATE');
  const [publicationPending, setPublicationPending] = useState(false);
  const [publicationError, setPublicationError] = useState<string | null>(null);
  const [publicationNotice, setPublicationNotice] = useState<string | null>(null);
  const publicationPendingRef = useRef(false);

  const load = useCallback(async (cursor: Cursor = null, append = false) => {
    if (append) {
      setLoadingMore(true);
      setLoadMoreError(null);
    } else {
      setState('LOADING');
      setError(null);
      setLoadMoreError(null);
      setSelectedItem(null);
    }
    try {
      const page = await bffClient.history(20, cursor?.beforeCreatedAt, cursor?.beforeJobId);
      setItems((previous) => append ? [...previous, ...page.items] : page.items);
      setNextCursor(page.next_before_created_at && page.next_before_job_id
        ? { beforeCreatedAt: page.next_before_created_at, beforeJobId: page.next_before_job_id }
        : null);
      if (!append) setState(page.items.length ? 'READY' : 'EMPTY');
    } catch (value) {
      const mapped = safeRequestError(value);
      if (append) {
        setLoadMoreError(mapped.message);
      } else {
        setItems([]);
        setNextCursor(null);
        setState(mapped.forbidden ? 'FORBIDDEN' : 'ERROR');
        setError(mapped.message);
      }
    } finally {
      if (append) setLoadingMore(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const openPublication = (item: CalculationHistoryItemDto) => {
    setPublicationTarget(item);
    setPublicationSelection(publicationChoice(item));
    setPublicationError(null);
    setPublicationNotice(null);
  };

  const confirmPublication = async () => {
    if (!publicationTarget?.result_id || publicationPendingRef.current) return;
    publicationPendingRef.current = true;
    setPublicationPending(true);
    setPublicationError(null);
    const payload = publicationSelection === 'PRIVATE'
      ? { is_published: false, is_default: false }
      : { is_published: true, is_default: publicationSelection === 'DASHBOARD_DEFAULT' };
    try {
      await bffClient.publishResult(publicationTarget.result_id, payload);
      const notice = publicationSelection === 'PRIVATE'
        ? '결과를 비공개로 변경했습니다.'
        : publicationSelection === 'DASHBOARD_DEFAULT'
          ? '결과를 공개하고 Dashboard 기본 결과로 지정했습니다.'
          : '결과를 공개했습니다.';
      setPublicationTarget(null);
      setPublicationNotice(notice);
      await load();
    } catch (value) {
      setPublicationError(safePublicationError(value));
    } finally {
      publicationPendingRef.current = false;
      setPublicationPending(false);
    }
  };

  const filteredItems = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('ko-KR');
    return items.filter((item) => {
      if (statusFilter !== 'ALL' && item.status !== statusFilter) return false;
      if (!needle) return true;
      return [item.baseline_model_name, item.comparison_model_name, periodLabel(item)]
        .some((value) => value.toLocaleLowerCase('ko-KR').includes(needle));
    });
  }, [items, search, statusFilter]);

  const visibleState: HistoryState = state === 'READY' && filteredItems.length === 0
    ? 'FILTER_EMPTY'
    : state;

  return (
    <section className="content-card calculation-history" aria-labelledby="history-heading">
      <header className="calculation-history__header">
        <div>
          <p className="calculation-history__eyebrow">RESULT LIBRARY</p>
          <h2 id="history-heading">계산 이력</h2>
          <p className="calculation-history__description">기준 모형과 비교 모형으로 생성된 분석 결과를 확인합니다.</p>
        </div>
        <span className="calculation-history__count tabular-nums">현재 불러온 {items.length}건</span>
      </header>

      {publicationNotice && <p className="calculation-history__notice" role="status"><CheckCircle2 size={15} />{publicationNotice}</p>}

      {state !== 'LOADING' && state !== 'ERROR' && state !== 'FORBIDDEN' && (
        <div className="calculation-history__filters">
          <label className="calculation-history__search">
            <span>이력 검색</span>
            <input aria-label="계산 이력 검색" placeholder="모형명·기간 검색" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <label>
            <span>상태</span>
            <select aria-label="계산 이력 상태 필터" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
              <option value="ALL">전체 상태</option>
              <option value="PENDING">분석 대기</option>
              <option value="PROCESSING">분석 중</option>
              <option value="COMPLETED">완료</option>
              <option value="FAILED">분석 실패</option>
            </select>
          </label>
          <span className="calculation-history__filter-note">검색과 상태 필터는 현재 불러온 이력에 적용됩니다.</span>
        </div>
      )}

      {visibleState === 'LOADING' && <div className="calculation-history__state" role="status">계산 이력을 확인하고 있습니다…</div>}
      {visibleState === 'EMPTY' && <div className="calculation-history__state"><Clock3 size={24} /><h3>계산 이력이 없습니다.</h3><p>분석을 실행하면 생성된 결과가 이곳에 표시됩니다.</p></div>}
      {visibleState === 'FORBIDDEN' && <div className="calculation-history__state"><AlertTriangle size={24} /><h3>계산 이력에 접근할 수 없습니다.</h3><p role="alert">{error}</p></div>}
      {visibleState === 'ERROR' && <div className="calculation-history__state"><XCircle size={24} /><h3>계산 이력을 불러오지 못했습니다.</h3><p role="alert">{error}</p><button type="button" className="calculation-history__secondary" onClick={() => void load()}>다시 시도</button></div>}
      {visibleState === 'FILTER_EMPTY' && <div className="calculation-history__filter-empty"><AlertTriangle size={20} /><strong>조건에 맞는 계산 이력이 없습니다.</strong><span>검색어나 상태를 조정해 보세요.</span></div>}

      {(visibleState === 'READY' || visibleState === 'FILTER_EMPTY') && items.length > 0 && (
        <>
          {filteredItems.length > 0 && <div className="calculation-history__table-wrap">
            <table className="calculation-history__table">
              <thead><tr><th>상태</th><th>기준 모형 / 비교 모형</th><th>기간</th><th>생성</th><th>완료</th><th>공개 상태</th><th>Dashboard 기본</th><th>작업</th></tr></thead>
              <tbody>{filteredItems.map((item) => {
                const failure = rowFailureMessage(item);
                const completed = item.status === 'COMPLETED' && Boolean(item.result_id);
                const selected = selectedItem?.job_id === item.job_id;
                return <tr key={item.job_id} className={selected ? 'is-selected' : ''}>
                  <td>
                    <span className={`calculation-history__status calculation-history__status--${statusClass(item.status)}`}>
                      {item.status === 'COMPLETED' && <CheckCircle2 size={13} aria-hidden="true" />}
                      {item.status === 'PROCESSING' && <Clock3 size={13} aria-hidden="true" />}
                      {item.status === 'FAILED' && <XCircle size={13} aria-hidden="true" />}
                      {statusLabel(item.status)}
                    </span>
                    {failure && <span className="calculation-history__failure">{failure}</span>}
                  </td>
                  <td><strong>{item.baseline_model_name}</strong><span className="calculation-history__arrow">→</span><strong>{item.comparison_model_name}</strong></td>
                  <td className="tabular-nums">{periodLabel(item)}</td>
                  <td className="tabular-nums">{dateLabel(item.created_at)}</td>
                  <td className="tabular-nums">{dateLabel(item.completed_at)}</td>
                  <td><span className={`calculation-history__publication ${item.is_published ? 'is-published' : ''}`}>{item.is_published ? '공개' : '비공개'}</span></td>
                  <td><span className={`calculation-history__default ${item.is_default ? 'is-default' : ''}`}>{item.is_default ? '기본 결과' : item.is_published ? '일반 결과' : '해당 없음'}</span></td>
                  <td>
                    <div className="calculation-history__actions">
                      {completed && onOpenResult && <button type="button" className="calculation-history__action" onClick={() => onOpenResult(item.result_id!)}><ExternalLink size={13} />결과 보기</button>}
                      {completed && <EvidenceDownloadButton resultId={item.result_id!} role="admin" />}
                      {completed && <button type="button" className="calculation-history__publication-button" onClick={() => openPublication(item)}><Settings2 size={13} />공개 설정</button>}
                      <button type="button" className="calculation-history__detail-button" aria-expanded={selected} onClick={() => setSelectedItem(selected ? null : item)}>상세</button>
                    </div>
                  </td>
                </tr>;
              })}</tbody>
            </table>
          </div>}

          {nextCursor && <div className="calculation-history__pagination">
            {loadMoreError && <span role="alert" className="calculation-history__load-error">{loadMoreError}</span>}
            <button type="button" className="calculation-history__secondary" disabled={loadingMore} onClick={() => void load(nextCursor, true)}>{loadingMore ? '불러오는 중…' : '다음 이력 보기'}</button>
          </div>}
        </>
      )}

      {selectedItem && <HistoryDetail item={selectedItem} />}
      {publicationTarget && <div className="calculation-history__modal-backdrop" role="presentation">
        <section className="calculation-history__modal" role="dialog" aria-modal="true" aria-labelledby="result-publication-heading">
          <p className="calculation-history__eyebrow">RESULT PUBLICATION</p>
          <h3 id="result-publication-heading">공개 설정</h3>
          <p className="calculation-history__modal-target"><strong>{publicationTarget.baseline_model_name} → {publicationTarget.comparison_model_name}</strong><span>{periodLabel(publicationTarget)}</span></p>
          <fieldset disabled={publicationPending}>
            <legend>결과 사용 범위</legend>
            <label><input type="radio" name="result-publication" value="PRIVATE" checked={publicationSelection === 'PRIVATE'} onChange={() => setPublicationSelection('PRIVATE')} /><span><strong>비공개</strong><small>Admin만 결과를 확인할 수 있습니다.</small></span></label>
            <label><input type="radio" name="result-publication" value="PUBLISHED" checked={publicationSelection === 'PUBLISHED'} onChange={() => setPublicationSelection('PUBLISHED')} /><span><strong>공개</strong><small>Viewer가 이 결과와 근거 자료를 확인할 수 있습니다.</small></span></label>
            <label><input type="radio" name="result-publication" value="DASHBOARD_DEFAULT" checked={publicationSelection === 'DASHBOARD_DEFAULT'} onChange={() => setPublicationSelection('DASHBOARD_DEFAULT')} /><span><strong>공개 + Dashboard 기본 결과</strong><small>서버 검증을 통과하면 이 비교 모형의 Dashboard 기본 결과로 사용합니다.</small></span></label>
          </fieldset>
          {publicationSelection === 'DASHBOARD_DEFAULT' && <p className="calculation-history__modal-warning"><AlertTriangle size={15} />기존 Dashboard 기본 결과가 있다면 해당 지정이 해제됩니다. Backend가 모형 공개와 결과 근거를 최종 검증합니다.</p>}
          {publicationError && <p className="calculation-history__modal-error" role="alert">{publicationError}</p>}
          <div className="calculation-history__modal-actions">
            <button type="button" className="calculation-history__secondary" disabled={publicationPending} onClick={() => setPublicationTarget(null)}>취소</button>
            <button type="button" className={publicationSelection === 'PRIVATE' ? 'calculation-history__unpublish' : 'calculation-history__confirm'} disabled={publicationPending} onClick={() => void confirmPublication()}>{publicationPending ? '적용 중…' : '설정 적용'}</button>
          </div>
        </section>
      </div>}
    </section>
  );
}

function HistoryDetail({ item }: { item: CalculationHistoryItemDto }) {
  const failure = rowFailureMessage(item);
  return <section className="calculation-history__detail" aria-labelledby="history-detail-heading">
    <div className="calculation-history__detail-heading"><div><p className="calculation-history__eyebrow">SELECTED ENTRY</p><h3 id="history-detail-heading">{item.baseline_model_name} → {item.comparison_model_name}</h3></div><span className={`calculation-history__status calculation-history__status--${statusClass(item.status)}`}>{statusLabel(item.status)}</span></div>
    <dl className="calculation-history__summary">
      <div><dt>적용 기간</dt><dd>{periodLabel(item)}</dd></div>
      <div><dt>생성 시각</dt><dd>{dateLabel(item.created_at)}</dd></div>
      <div><dt>완료 시각</dt><dd>{dateLabel(item.completed_at)}</dd></div>
      <div><dt>공개 상태</dt><dd>{item.is_published ? '공개' : '비공개'}</dd></div>
      <div><dt>Dashboard 기본 결과</dt><dd>{item.is_default ? '기본 결과' : '아님'}</dd></div>
      <div><dt>공개 시각</dt><dd>{dateLabel(item.published_at)}</dd></div>
    </dl>
    {failure && <p className="calculation-history__detail-error" role="status">{failure}</p>}
    <details className="calculation-history__technical">
      <summary>관리자 기술 정보 <ChevronDown size={15} /></summary>
      <dl>
        <div><dt>Job ID</dt><dd>{item.job_id}</dd></div>
        <div><dt>Result ID</dt><dd>{item.result_id || '제공되지 않음'}</dd></div>
        <div><dt>시도 횟수</dt><dd>{item.attempt} / {item.max_attempts}</dd></div>
      </dl>
    </details>
  </section>;
}

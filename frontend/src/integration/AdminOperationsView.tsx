import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, Clock3, Power, RefreshCw, ServerCog, Square } from 'lucide-react';
import { bffClient } from './client';
import { ApiClientError, WorkerStatusDto } from './types';
import '../styles/admin-operations.css';

type OperationsState = 'LOADING' | 'READY' | 'ERROR' | 'FORBIDDEN';
type OperationAction = 'WAKE' | 'STOP';
type WorkerPresentationState = 'IDLE' | 'STARTING' | 'ACTIVE' | 'STOPPING' | 'ATTENTION';

const STATUS_LABELS: Record<WorkerPresentationState, string> = {
  IDLE: '대기 상태',
  STARTING: '분석 엔진 시작 중',
  ACTIVE: '분석 엔진 가동 중',
  STOPPING: '분석 엔진 종료 중',
  ATTENTION: '운영 상태 확인 필요',
};

function workerPresentation(value: WorkerStatusDto): WorkerPresentationState {
  if (value.desired_instance_count === 0 && value.actual_instance_count === 0 && !value.platform_reconciling) return 'IDLE';
  if (value.desired_instance_count === 1 && (value.platform_reconciling || value.actual_instance_count !== 1)) return 'STARTING';
  if (value.desired_instance_count === 0 && (value.platform_reconciling || value.actual_instance_count === 1)) return 'STOPPING';
  if (value.desired_instance_count === 1 && value.actual_instance_count === 1 && value.platform_ready) return 'ACTIVE';
  return 'ATTENTION';
}

function statusClass(value: WorkerPresentationState): string {
  return value.toLowerCase();
}

function policyLabel(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `약 ${minutes}분 기준`;
}

function safeError(value: unknown, operation: 'load' | 'action'): { forbidden: boolean; message: string } {
  if (value instanceof ApiClientError && (value.status === 403 || value.code === 'FORBIDDEN')) {
    return { forbidden: true, message: '분석 엔진 운영 화면에 접근할 권한이 없습니다.' };
  }
  if (value instanceof ApiClientError && value.code === 'WORKER_BUSY') {
    return { forbidden: false, message: '현재 진행 중인 작업이 있어 분석 엔진 긴급 종료를 완료하지 못했습니다.' };
  }
  return {
    forbidden: false,
    message: operation === 'load'
      ? '분석 엔진 상태를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.'
      : '분석 엔진 작업을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.',
  };
}

export interface AdminOperationsViewProps {
  onNavigateToHistory?: () => void;
}

export function AdminOperationsView({ onNavigateToHistory }: AdminOperationsViewProps) {
  const [state, setState] = useState<OperationsState>('LOADING');
  const [worker, setWorker] = useState<WorkerStatusDto | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState(false);
  const [pendingAction, setPendingAction] = useState<OperationAction | null>(null);
  const [mutationPending, setMutationPending] = useState(false);
  const mutationGuard = useRef(false);

  const refresh = useCallback(async () => {
    setState('LOADING');
    setMessage(null);
    try {
      const next = await bffClient.workerStatus();
      setWorker(next);
      setState('READY');
    } catch (value) {
      const mapped = safeError(value, 'load');
      setWorker(null);
      setState(mapped.forbidden ? 'FORBIDDEN' : 'ERROR');
      setMessage(mapped.message);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const presentation = useMemo(() => (worker ? workerPresentation(worker) : null), [worker]);

  function requestAction(action: OperationAction) {
    if (mutationGuard.current || mutationPending) return;
    setActionError(false);
    setActionMessage(null);
    setPendingAction(action);
  }

  async function confirmAction() {
    if (!pendingAction || mutationGuard.current || mutationPending) return;
    const action = pendingAction;
    mutationGuard.current = true;
    setMutationPending(true);
    setActionError(false);
    setActionMessage(null);
    try {
      const next = action === 'WAKE'
        ? await bffClient.emergencyWorkerWake()
        : await bffClient.safeWorkerStop();
      setWorker(next);
      setState('READY');
      setActionMessage(action === 'WAKE' ? '분석 엔진 긴급 가동 요청을 접수했습니다.' : '분석 엔진 긴급 종료 요청을 접수했습니다.');
      setPendingAction(null);
    } catch (value) {
      const mapped = safeError(value, 'action');
      setActionError(true);
      setActionMessage(mapped.message);
      if (mapped.forbidden) setState('FORBIDDEN');
    } finally {
      mutationGuard.current = false;
      setMutationPending(false);
    }
  }

  if (state === 'LOADING' && !worker) {
    return <section className="admin-operations" aria-labelledby="operations-heading">
      <OperationsHeading />
      <div className="admin-operations__state" role="status">분석 엔진 상태를 확인하고 있습니다…</div>
    </section>;
  }

  if (state === 'FORBIDDEN') {
    return <section className="admin-operations" aria-labelledby="operations-heading">
      <OperationsHeading />
      <div className="admin-operations__state admin-operations__state--error" role="alert">
        <AlertTriangle size={25} aria-hidden="true" />
        <h2>운영 화면에 접근할 수 없습니다.</h2>
        <p>{message}</p>
      </div>
    </section>;
  }

  if (state === 'ERROR' && !worker) {
    return <section className="admin-operations" aria-labelledby="operations-heading">
      <OperationsHeading />
      <div className="admin-operations__state admin-operations__state--error" role="alert">
        <AlertTriangle size={25} aria-hidden="true" />
        <h2>분석 엔진 상태를 확인하지 못했습니다.</h2>
        <p>{message}</p>
        <button type="button" className="admin-operations__secondary" onClick={() => void refresh()}>다시 시도</button>
      </div>
    </section>;
  }

  return <section className="admin-operations" aria-labelledby="operations-heading">
    <OperationsHeading />
    <div className="admin-operations__toolbar">
      <div>
        <p className="admin-operations__eyebrow">CURRENT STATUS</p>
        <h2 id="operations-heading">분석 엔진 상태</h2>
      </div>
      <button type="button" className="admin-operations__secondary" disabled={state === 'LOADING' || mutationPending} onClick={() => void refresh()}>
        <RefreshCw size={15} aria-hidden="true" />상태 새로고침
      </button>
    </div>

    {worker && presentation && <>
      <div className={`admin-operations__status-card admin-operations__status-card--${statusClass(presentation)}`} data-testid="operations-status">
        <div className="admin-operations__status-icon" aria-hidden="true">
          {presentation === 'ACTIVE' && <CheckCircle2 size={24} />}
          {presentation === 'IDLE' && <Square size={22} />}
          {presentation === 'STARTING' && <Clock3 size={24} />}
          {presentation === 'STOPPING' && <Power size={23} />}
          {presentation === 'ATTENTION' && <AlertTriangle size={24} />}
        </div>
        <div className="admin-operations__status-copy">
          <span className="admin-operations__status-kicker">현재 운영 상태</span>
          <strong>{STATUS_LABELS[presentation]}</strong>
          <p>{worker.work_exists ? '현재 처리할 작업이 있습니다.' : '현재 처리할 작업이 없습니다.'}</p>
        </div>
        <dl className="admin-operations__status-facts">
          <div><dt>현재 작업</dt><dd>{worker.work_exists ? '있음' : '없음'}</dd></div>
          <div><dt>자동 시작</dt><dd>분석 요청 시</dd></div>
          <div><dt>자동 종료</dt><dd>{policyLabel(worker.idle_policy_seconds)}</dd></div>
        </dl>
      </div>

      <div className="admin-operations__actions" aria-label="분석 엔진 제어">
        <button type="button" className="admin-operations__secondary admin-operations__warning" disabled={mutationPending} onClick={() => requestAction('WAKE')}>
          <ServerCog size={16} aria-hidden="true" />분석 엔진 긴급 가동
        </button>
        <button type="button" className="admin-operations__danger" disabled={mutationPending} onClick={() => requestAction('STOP')}>
          <Power size={16} aria-hidden="true" />분석 엔진 긴급 종료
        </button>
        <p className="admin-operations__action-note">일반 분석 요청은 자동으로 시작됩니다. 두 작업은 긴급 상황에서만 사용하세요.</p>
      </div>

      {actionMessage && (!pendingAction || !actionError) && <p className={`admin-operations__message ${actionError ? 'is-error' : 'is-success'}`} role={actionError ? 'alert' : 'status'}>{actionMessage}</p>}

      <div className="admin-operations__notes">
        <p><strong>수요 발생 시 운영</strong> 일반 분석 요청이 있을 때 자동으로 시작되며, 유휴 시간이 지나면 정리될 수 있습니다.</p>
        <p>현재 서버 정책 기준: <strong>{policyLabel(worker.idle_policy_seconds)}</strong>. 추정 모형 생성은 별도 실행 흐름에서 진행됩니다.</p>
      </div>

      <details className="admin-operations__technical">
        <summary>운영 상세 정보 <ChevronDown size={15} aria-hidden="true" /></summary>
        <dl>
          <div><dt>목표 인스턴스</dt><dd>{worker.desired_instance_count}</dd></div>
          <div><dt>실제 인스턴스</dt><dd>{worker.actual_instance_count === null ? '확인 중' : worker.actual_instance_count}</dd></div>
          <div><dt>플랫폼 상태</dt><dd>{worker.platform_ready ? '준비됨' : '확인 필요'}</dd></div>
          <div><dt>대기열</dt><dd>{worker.queue_depth}</dd></div>
          <div><dt>처리 대기</dt><dd>{worker.pending_count}</dd></div>
          <div><dt>처리 중</dt><dd>{worker.processing_count}</dd></div>
          <div><dt>최근 활동</dt><dd>{new Date(worker.last_worker_activity_at).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' })}</dd></div>
        </dl>
      </details>

      {onNavigateToHistory && <div className="admin-operations__history-cta">
        <div><span className="admin-operations__eyebrow">RESULTS</span><strong>계산 이력에서 실행 결과를 확인하세요.</strong><p>이전 요청의 상태와 공개 결과를 확인할 수 있습니다.</p></div>
        <button type="button" className="admin-operations__secondary" onClick={onNavigateToHistory}>계산 이력 보기</button>
      </div>}
    </>}

    {pendingAction && <div className="admin-operations__modal-backdrop" role="presentation">
      <section className={`admin-operations__modal ${pendingAction === 'STOP' ? 'is-danger' : ''}`} role="dialog" aria-modal="true" aria-labelledby="operations-confirm-heading">
        <p className="admin-operations__eyebrow">CONFIRM OPERATION</p>
        <h2 id="operations-confirm-heading">{pendingAction === 'WAKE' ? '분석 엔진을 긴급 가동할까요?' : '분석 엔진을 긴급 종료할까요?'}</h2>
        <p>{pendingAction === 'WAKE' ? '일반 분석 요청은 자동으로 시작되며, 지금은 긴급 가동이 필요한 경우에만 사용합니다.' : '새 작업을 받지 않도록 긴급 종료를 서버에 요청합니다. 진행 중인 작업이 있으면 서버가 거부할 수 있습니다.'}</p>
        {actionMessage && actionError && <p className="admin-operations__modal-error" role="alert">{actionMessage}</p>}
        <div className="admin-operations__modal-actions">
          <button type="button" className="admin-operations__secondary" disabled={mutationPending} onClick={() => setPendingAction(null)}>취소</button>
          <button type="button" className={pendingAction === 'STOP' ? 'admin-operations__danger' : 'admin-operations__primary'} disabled={mutationPending} onClick={() => void confirmAction()}>{mutationPending ? '처리 중…' : '확인'}</button>
        </div>
      </section>
    </div>}
  </section>;
}

function OperationsHeading() {
  return <header className="admin-operations__heading">
    <div><span className="admin-operations__eyebrow">ADMIN OPERATIONS</span><h1>분석 엔진 운영</h1><p>분석 엔진의 상태를 확인하고 필요한 작업을 요청합니다.</p></div>
    <span className="admin-operations__access-badge">ADMIN ONLY</span>
  </header>;
}

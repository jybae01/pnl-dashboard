import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { bffClient } from '../integration/client';
import { PnlDashboardPanel } from '../integration/PnlDashboardPanel';
import { ApiClientError, PnlDashboardDto } from '../integration/types';

type DashboardState = 'LOADING' | 'READY' | 'EMPTY' | 'ERROR' | 'FORBIDDEN' | 'INVALID_PAYLOAD';

export interface PnlStatusViewProps {
  onNavigateToVariance?: () => void;
}

function StateMessage({ state, onRetry }: { state: Exclude<DashboardState, 'LOADING' | 'READY'>; onRetry: () => void }) {
  const content = {
    EMPTY: { title: '아직 확인할 수 있는 손익 데이터가 없습니다.', description: '공개된 손익 현황이 생성되면 이 화면에서 확인할 수 있습니다.' },
    ERROR: { title: '손익 현황을 불러오지 못했습니다.', description: '잠시 후 다시 시도하거나 관리자에게 문의하세요.' },
    FORBIDDEN: { title: '손익 현황을 조회할 권한이 없습니다.', description: '현재 계정의 Viewer/Admin 권한과 공개 범위를 확인하세요.' },
    INVALID_PAYLOAD: { title: '손익 현황 데이터 형식을 확인할 수 없습니다.', description: '서버 응답 무결성 검증에 실패했습니다. 잠시 후 다시 시도하세요.' },
  }[state];
  const role = state === 'ERROR' || state === 'INVALID_PAYLOAD' ? 'alert' : 'status';
  return <section className={`pnl-dashboard-state pnl-dashboard-state--${state.toLowerCase()}`} role={role} aria-live="polite">
    <div className="pnl-dashboard-state__title">{content.title}</div>
    <div className="pnl-dashboard-state__description">{content.description}</div>
    {state !== 'FORBIDDEN' && <button type="button" className="pnl-dashboard-state__retry" onClick={onRetry}>다시 조회</button>}
  </section>;
}

export function PnlStatusView({ onNavigateToVariance }: PnlStatusViewProps) {
  const [state, setState] = useState<DashboardState>('LOADING');
  const [dashboard, setDashboard] = useState<PnlDashboardDto | null>(null);
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    const requestId = ++sequence.current;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setState('LOADING');
    setDashboard(null);
    try {
      const next = await bffClient.pnlDashboard(nextController.signal);
      if (requestId !== sequence.current) return;
      setDashboard(next);
      setState('READY');
    } catch (error) {
      if (requestId !== sequence.current || nextController.signal.aborted) return;
      setDashboard(null);
      if (error instanceof ApiClientError && (error.status === 403 || error.code === 'FORBIDDEN')) {
        setState('FORBIDDEN');
      } else if (error instanceof ApiClientError && error.code === 'RESULT_NOT_AVAILABLE') {
        setState('EMPTY');
      } else if (error instanceof ApiClientError && ['INVALID_PAYLOAD', 'INPUT_INTEGRITY_MISMATCH'].includes(error.code)) {
        setState('INVALID_PAYLOAD');
      } else {
        setState('ERROR');
      }
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      sequence.current += 1;
      controller.current?.abort();
    };
  }, [load]);

  return <div className="pnl-dashboard-page">
    {state === 'LOADING' && <section className="pnl-dashboard-state" role="status" aria-live="polite"><span className="pnl-dashboard__loading-spinner" aria-hidden="true" /><div className="pnl-dashboard-state__title">손익 현황을 불러오는 중…</div></section>}
    {state !== 'LOADING' && state !== 'READY' && <StateMessage state={state} onRetry={() => void load()} />}
    {state === 'READY' && dashboard && <>
      <div className="pnl-dashboard__toolbar"><div><span className="pnl-dashboard__toolbar-kicker">P&amp;L STATUS</span><span className="pnl-dashboard__toolbar-copy">게시된 결과 기준</span></div><button type="button" className="pnl-dashboard__toolbar-refresh" onClick={() => void load()}><RefreshCw size={13} /> 새로고침</button></div>
      <PnlDashboardPanel dashboard={dashboard} onNavigateToVariance={onNavigateToVariance} />
    </>}
  </div>;
}

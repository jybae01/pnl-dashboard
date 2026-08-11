import { useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { bffClient } from '../integration/client';
import { PnlDashboardPanel } from '../integration/PnlDashboardPanel';
import { ApiClientError, PnlDashboardDto } from '../integration/types';

type State = 'LOADING' | 'READY' | 'EMPTY' | 'ERROR' | 'INVALID_PAYLOAD';

export function PnlStatusView() {
  const [state, setState] = useState<State>('LOADING');
  const [dashboard, setDashboard] = useState<PnlDashboardDto | null>(null);
  const [message, setMessage] = useState('');
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);

  async function load() {
    const requestId = ++sequence.current;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setState('LOADING'); setDashboard(null); setMessage('');
    try {
      const next = await bffClient.pnlDashboard(nextController.signal);
      if (requestId !== sequence.current) return;
      setDashboard(next); setState('READY');
    } catch (error) {
      if (requestId !== sequence.current || nextController.signal.aborted) return;
      setDashboard(null);
      if (error instanceof ApiClientError && error.code === 'RESULT_NOT_AVAILABLE') {
        setState('EMPTY'); return;
      }
      if (error instanceof ApiClientError && ['INVALID_PAYLOAD', 'INPUT_INTEGRITY_MISMATCH'].includes(error.code)) {
        setState('INVALID_PAYLOAD'); setMessage('손익 현황 데이터 계약을 확인할 수 없습니다.'); return;
      }
      setState('ERROR'); setMessage(error instanceof Error ? error.message : '손익 현황을 조회할 수 없습니다.');
    }
  }

  useEffect(() => {
    void load();
    return () => { sequence.current += 1; controller.current?.abort(); };
  }, []);
  if (state === 'LOADING') return <div className="view-container" role="status">손익 현황을 불러오는 중…</div>;
  if (state === 'EMPTY') return <div className="view-container empty-state-box"><div className="empty-state-title">공개된 손익 현황이 없습니다</div><button className="btn btn-secondary" onClick={load}>다시 조회</button></div>;
  if (state === 'ERROR' || state === 'INVALID_PAYLOAD') return <div className="view-container" role="alert"><div className="empty-state-title">{message}</div><button className="btn btn-secondary" onClick={load}>다시 조회</button></div>;
  return <div className="view-container"><button className="btn btn-secondary btn-sm" onClick={load}><RefreshCw size={13} /> 새로고침</button>{dashboard && <PnlDashboardPanel dashboard={dashboard} />}</div>;
}

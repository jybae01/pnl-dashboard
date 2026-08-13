import { useEffect, useState } from 'react';
import { Header } from './components/common/Header';
import { PnlStatusView } from './views/PnlStatusView';
import { ForecastGenerationView } from './views/ForecastGenerationView';
import { bffClient } from './integration/client';
import { CoreAnalysisView } from './integration/CoreAnalysisView';
import { LoginView } from './integration/LoginView';
import { ModelManagementView } from './integration/ModelManagementView';
import { ApiClientError, Role, SessionDto } from './integration/types';
import './styles/global.css';
import './styles/tables.css';
import './styles/charts.css';
import './styles/components.css';
import './styles/pnl-dashboard.css';
import './styles/forecast-workflow.css';
import './styles/data-management.css';

type CoreRoute = 'pnl' | 'forecast' | 'variance' | 'management';

function routeFromHash(role?: Role): CoreRoute {
  const route = window.location.hash.replace('#', '').split('?')[0] as CoreRoute;
  if (!['pnl', 'forecast', 'variance', 'management'].includes(route)) {
    return role === 'admin' ? 'management' : 'variance';
  }
  if (role === 'viewer' && !['pnl', 'variance'].includes(route)) return 'variance';
  return route;
}

export function App() {
  const [session, setSession] = useState<SessionDto | null>(null);
  const [sessionState, setSessionState] = useState<'LOADING' | 'READY' | 'ANONYMOUS' | 'ERROR'>('LOADING');
  const [route, setRoute] = useState<CoreRoute>('variance');
  const [analysisResultId, setAnalysisResultId] = useState<string | null>(null);

  useEffect(() => {
    bffClient.session().then((value) => {
      setSession(value); setSessionState('READY'); setRoute(routeFromHash(value.role));
    }).catch((value) => {
      setSession(null);
      setSessionState(value instanceof ApiClientError && value.status === 401 ? 'ANONYMOUS' : 'ERROR');
    });
  }, []);

  useEffect(() => {
    const listener = () => {
      const next = routeFromHash(session?.role);
      setRoute(next);
      if (next !== 'variance') setAnalysisResultId(null);
    };
    window.addEventListener('hashchange', listener);
    return () => window.removeEventListener('hashchange', listener);
  }, [session?.role]);

  function navigate(next: CoreRoute) {
    if (session?.role === 'viewer' && !['pnl', 'variance'].includes(next)) return;
    setAnalysisResultId(null);
    window.location.hash = next;
    setRoute(next);
  }

  function navigateToAnalysisResult(resultId: string) {
    if (session?.role !== 'admin' || !resultId) return;
    setAnalysisResultId(resultId);
    window.location.hash = 'variance';
    setRoute('variance');
  }

  if (sessionState === 'LOADING') return <main role="status" className="app-content">세션 확인 중…</main>;
  if (sessionState === 'ERROR') return <main role="alert" className="app-content">서버 세션을 확인할 수 없습니다.</main>;
  if (!session) return <LoginView onAuthenticated={(value) => { setSession(value); setSessionState('READY'); navigate(value.role === 'admin' ? 'management' : 'variance'); }} />;

  return <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
    <Header />
    <nav className="app-nav" aria-label="주요 화면">
      <div className="nav-tabs">
        <button className={`nav-tab-btn ${route === 'pnl' ? 'active' : ''}`} onClick={() => navigate('pnl')}>1. 손익 현황</button>
        {session.role === 'admin' && <>
          <button className={`nav-tab-btn ${route === 'forecast' ? 'active' : ''}`} onClick={() => navigate('forecast')}>2. Forecast</button>
          <button className={`nav-tab-btn ${route === 'management' ? 'active' : ''}`} onClick={() => navigate('management')}>3. 데이터 관리 / 분석 실행</button>
        </>}
        <button className={`nav-tab-btn ${route === 'variance' ? 'active' : ''}`} onClick={() => navigate('variance')}>4. 손익 분석 결과</button>
        <button className="nav-tab-btn" onClick={async () => {
          try {
            await bffClient.logout();
            setSession(null);
            setSessionState('ANONYMOUS');
          } catch {
            setSessionState('ERROR');
          }
        }}>로그아웃</button>
      </div>
      <div className="nav-right-actions" aria-label="현재 권한">
        <span className="env-tag">{session.role === 'admin' ? 'ADMIN · 업로드/공개/분석' : 'VIEWER · 공개 결과 조회'}</span>
      </div>
    </nav>
    <main className="app-content">
      {route === 'pnl' && <PnlStatusView onNavigateToVariance={() => navigate('variance')} />}
      {route === 'forecast' && session.role === 'admin' && <ForecastGenerationView
        onNavigateToPnl={() => navigate('pnl')}
        onNavigateToAnalysis={() => navigate('variance')}
        onNavigateToManagement={() => navigate('management')}
      />}
      {route === 'management' && session.role === 'admin' && <ModelManagementView
        onNavigateToForecast={() => navigate('forecast')}
        onNavigateToAnalysis={() => navigate('variance')}
        onNavigateToAnalysisResult={navigateToAnalysisResult}
      />}
      {route === 'variance' && <CoreAnalysisView role={session.role} initialResultId={analysisResultId || undefined} />}
    </main>
  </div>;
}

export default App;

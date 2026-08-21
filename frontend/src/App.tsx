import { useEffect, useRef, useState } from 'react';
import { Calculator, Database, GitCompare, LayoutDashboard, Sliders } from 'lucide-react';
import { Header } from './components/common/Header';
import { PnlStatusView } from './views/PnlStatusView';
import { ForecastGenerationView } from './views/ForecastGenerationView';
import { bffClient } from './integration/client';
import { pnlReportingSource } from './integration/pnlReportingSource';
import { CoreAnalysisView } from './integration/CoreAnalysisView';
import { LoginBrandLogo, LoginView } from './integration/LoginView';
import { ModelManagementView } from './integration/ModelManagementView';
import { AdminOperationsView } from './integration/AdminOperationsView';
import { ApiClientError, Role, SessionDto } from './integration/types';
import './styles/global.css';
import './styles/tables.css';
import './styles/charts.css';
import './styles/components.css';
import './styles/pnl-dashboard.css';
import './styles/forecast-workflow.css';
import './styles/data-management.css';
import './styles/admin-operations.css';

type CoreRoute = 'pnl' | 'forecast' | 'variance' | 'management' | 'operations';

function routeFromHash(role?: Role): CoreRoute {
  const route = window.location.hash.replace('#', '').split('?')[0] as CoreRoute;
  if (!['pnl', 'forecast', 'variance', 'management', 'operations'].includes(route)) {
    return role === 'admin' ? 'management' : 'variance';
  }
  if (role !== 'admin' && !['pnl', 'variance'].includes(route)) return 'variance';
  return route;
}

export function App() {
  const [session, setSession] = useState<SessionDto | null>(null);
  const [sessionState, setSessionState] = useState<'LOADING' | 'READY' | 'ANONYMOUS' | 'ERROR'>('LOADING');
  const [route, setRoute] = useState<CoreRoute>('variance');
  const [analysisResultId, setAnalysisResultId] = useState<string | null>(null);
  const [pnlReportingRefreshToken, setPnlReportingRefreshToken] = useState(0);
  const navigationRef = useRef<HTMLElement>(null);
  const activeTabRef = useRef<HTMLButtonElement>(null);

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
      if (!session) return;
      const next = routeFromHash(session?.role);
      setRoute(next);
      if (next !== 'variance') setAnalysisResultId(null);
    };
    window.addEventListener('hashchange', listener);
    return () => window.removeEventListener('hashchange', listener);
  }, [session?.role]);

  useEffect(() => {
    const navigation = navigationRef.current;
    const activeTab = activeTabRef.current;
    if (!navigation || !activeTab || typeof navigation.scrollBy !== 'function') return;
    const navigationBounds = navigation.getBoundingClientRect();
    const activeBounds = activeTab.getBoundingClientRect();
    let horizontalDelta = 0;
    if (activeBounds.left < navigationBounds.left) horizontalDelta = activeBounds.left - navigationBounds.left;
    if (activeBounds.right > navigationBounds.right) horizontalDelta = activeBounds.right - navigationBounds.right;
    if (horizontalDelta !== 0) navigation.scrollBy({ left: horizontalDelta, top: 0, behavior: 'auto' });
  }, [route, session?.role]);

  function navigate(next: CoreRoute) {
    if (session?.role === 'viewer' && !['pnl', 'variance'].includes(next)) return;
    setAnalysisResultId(null);
    window.location.hash = next;
    setRoute(next);
  }

  function navigateToAnalysisResult(resultId: string) {
    setAnalysisResultId(resultId);
    window.location.hash = 'variance';
    setRoute('variance');
  }

  function navigateToHistory() {
    setAnalysisResultId(null);
    window.location.hash = 'management?section=history';
    setRoute('management');
  }

  if (sessionState === 'LOADING') {
    return (
      <main className="login-shell" role="status" aria-live="polite">
        <section className="login-card login-card--status">
          <LoginBrandLogo />
          <h1>세션 확인 중…</h1>
          <p>사용자 권한 및 세션 상태를 확인하고 있습니다.</p>
        </section>
      </main>
    );
  }

  if (sessionState === 'ERROR') {
    return (
      <main className="login-shell" role="alert">
        <section className="login-card login-card--status">
          <LoginBrandLogo />
          <h1>서버 세션을 확인할 수 없습니다</h1>
          <p>네트워크 상태를 확인하고 잠시 후 다시 시도해 주세요.</p>
          <button className="login-submit" onClick={() => window.location.reload()}>다시 시도</button>
        </section>
      </main>
    );
  }

  if (!session) return <LoginView onAuthenticated={(value) => { setSession(value); setSessionState('READY'); navigate(value.role === 'admin' ? 'management' : 'variance'); }} />;

  return <div className="app-shell">
    <Header
      session={session}
      onLogout={async () => {
        try {
          await bffClient.logout();
          setSession(null);
          setSessionState('ANONYMOUS');
        } catch {
          setSessionState('ERROR');
        }
      }}
    />
    <nav ref={navigationRef} className="app-nav" aria-label="주요 화면">
      <div className="nav-tabs">
        <button
          className={`nav-tab-btn ${route === 'pnl' ? 'active' : ''}`}
          onClick={() => navigate('pnl')}
          aria-current={route === 'pnl' ? 'page' : undefined}
          ref={route === 'pnl' ? activeTabRef : undefined}
        >
          <LayoutDashboard size={14} aria-hidden="true" />
          <span>손익현황</span>
          <span className="nav-tab-badge">KPI & Trend</span>
        </button>
        {session.role === 'admin' && (
          <button
            className={`nav-tab-btn ${route === 'forecast' ? 'active' : ''}`}
            onClick={() => navigate('forecast')}
            aria-current={route === 'forecast' ? 'page' : undefined}
            ref={route === 'forecast' ? activeTabRef : undefined}
          >
            <Calculator size={14} aria-hidden="true" />
            <span>추정 산출</span>
            <span className="nav-tab-badge" style={{ backgroundColor: '#f5f3ff', color: '#7c3aed', borderColor: '#ddd6fe' }}>Forecast</span>
          </button>
        )}
        <button
          className={`nav-tab-btn ${route === 'variance' ? 'active' : ''}`}
          onClick={() => navigate('variance')}
          aria-current={route === 'variance' ? 'page' : undefined}
          ref={route === 'variance' ? activeTabRef : undefined}
        >
          <GitCompare size={14} aria-hidden="true" />
          <span>손익 분석</span>
          <span className="nav-tab-badge">Waterfall &amp; Effect</span>
        </button>
        {session.role === 'admin' && (
          <button
            className={`nav-tab-btn ${route === 'management' ? 'active' : ''}`}
            onClick={() => navigate('management')}
            aria-current={route === 'management' ? 'page' : undefined}
            ref={route === 'management' ? activeTabRef : undefined}
          >
            <Database size={14} aria-hidden="true" />
            <span>데이터 관리</span>
            <span className="nav-tab-badge">Model & Calc</span>
          </button>
        )}
        {session.role === 'admin' && (
          <button
            className={`nav-tab-btn ${route === 'operations' ? 'active' : ''}`}
            onClick={() => navigate('operations')}
            aria-current={route === 'operations' ? 'page' : undefined}
            ref={route === 'operations' ? activeTabRef : undefined}
          >
            <Sliders size={14} aria-hidden="true" />
            <span>운영 관리</span>
            <span className="nav-tab-badge">Operations</span>
          </button>
        )}
      </div>
    </nav>
    <main className="app-content">
      {route === 'pnl' && <PnlStatusView reportingSource={pnlReportingSource} refreshToken={pnlReportingRefreshToken} onNavigateToVariance={() => navigate('variance')} />}
      {route === 'forecast' && session.role === 'admin' && <ForecastGenerationView
        onNavigateToPnl={() => navigate('pnl')}
        onNavigateToAnalysis={() => navigate('variance')}
        onNavigateToManagement={() => navigate('management')}
      />}
      {route === 'management' && session.role === 'admin' && <ModelManagementView
        onNavigateToForecast={() => navigate('forecast')}
        onNavigateToAnalysis={() => navigate('variance')}
        onNavigateToAnalysisResult={navigateToAnalysisResult}
        onPnlReportingChanged={() => setPnlReportingRefreshToken((value) => value + 1)}
        initialHistoryOpen={route === 'management' && window.location.hash.includes('section=history')}
      />}
      {route === 'operations' && session.role === 'admin' && <AdminOperationsView onNavigateToHistory={navigateToHistory} />}
      {route === 'variance' && <CoreAnalysisView role={session.role} initialResultId={analysisResultId || undefined} />}
    </main>
  </div>;
}

export default App;

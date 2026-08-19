import { ArrowRightCircle, Calendar, Factory, FileSpreadsheet, Landmark, Package, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { KpiOverview } from '../components/pnl/KpiOverview';
import { MfgCostTable } from '../components/pnl/MfgCostTable';
import { MonthlyTrendChart } from '../components/pnl/MonthlyTrendChart';
import { PnlTable } from '../components/pnl/PnlTable';
import { ProductSegmentPnlTable } from '../components/pnl/ProductSegmentPnlTable';
import { SgaTable } from '../components/pnl/SgaTable';
import {
  parsePnlReportingLoadResult,
  PnlReportingSourceError,
  type PnlDetailTab,
  type PnlReportingMetadata,
  type PnlReportingReadModel,
  type PnlReportingState,
  type PnlReportingSource,
} from '../types/pnlReporting';

type DashboardState = 'LOADING' | PnlReportingState | 'ERROR';
type ErrorPresentation = 'ERROR' | 'FORBIDDEN' | 'INVALID_PAYLOAD';

export interface PnlStatusViewProps {
  onNavigateToVariance?: () => void;
  reportingSource: PnlReportingSource;
  initialYear?: number | null;
  refreshToken?: number;
}

const STATE_COPY: Record<Exclude<DashboardState, 'LOADING' | 'READY' | 'ERROR'> | ErrorPresentation, { title: string; description: string }> = {
  MISSING_BOTH: { title: 'PLAN과 ACTUAL 데이터가 아직 등록되지 않았습니다.', description: '데이터 관리에서 선택한 기준년도의 PLAN과 ACTUAL을 등록하세요.' },
  MISSING_PLAN: { title: 'PLAN 데이터가 아직 등록되지 않았습니다.', description: '데이터 관리에서 선택한 기준년도의 PLAN을 등록하세요.' },
  MISSING_ACTUAL: { title: 'ACTUAL 데이터가 아직 등록되지 않았습니다.', description: '데이터 관리에서 선택한 기준년도의 ACTUAL을 등록하세요.' },
  ERROR: { title: '손익 현황을 불러오지 못했습니다.', description: '잠시 후 다시 시도하거나 관리자에게 문의하세요.' },
  FORBIDDEN: { title: '손익 현황을 조회할 권한이 없습니다.', description: '현재 계정의 Viewer/Admin 권한과 공개 범위를 확인하세요.' },
  INVALID_PAYLOAD: { title: '손익 현황 데이터 형식을 확인할 수 없습니다.', description: 'Reporting read model 무결성 검증에 실패했습니다.' },
};

function StateMessage({ state, presentation, onRetry }: { state: Exclude<DashboardState, 'LOADING' | 'READY'>; presentation: ErrorPresentation; onRetry: () => void }) {
  const key = state === 'ERROR' ? presentation : state;
  const content = STATE_COPY[key];
  return <section className={`pnl-report__state pnl-report__state--${key.toLowerCase()}`} role={state === 'ERROR' ? 'alert' : 'status'} aria-live="polite">
    <div className="pnl-report__state-title">{content.title}</div>
    <div className="pnl-report__state-description">{content.description}</div>
    {state === 'ERROR' && <button type="button" className="pnl-report__state-retry" onClick={onRetry}>다시 조회</button>}
  </section>;
}

export function PnlStatusView({ onNavigateToVariance, reportingSource, initialYear = null, refreshToken = 0 }: PnlStatusViewProps) {
  const [year, setYear] = useState<number | null>(initialYear);
  const [state, setState] = useState<DashboardState>('LOADING');
  const [errorPresentation, setErrorPresentation] = useState<ErrorPresentation>('ERROR');
  const [report, setReport] = useState<PnlReportingReadModel | null>(null);
  const [metadata, setMetadata] = useState<PnlReportingMetadata | null>(null);
  const [activeTab, setActiveTab] = useState<PnlDetailTab>('pnl_statement');
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const selectedYear = useRef<number | null>(initialYear);

  const load = useCallback(async (requestedYear: number | null = selectedYear.current) => {
    const requestId = ++sequence.current;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setReport(null);
    setState('LOADING');
    setErrorPresentation('ERROR');
    try {
      const parsed = parsePnlReportingLoadResult(await reportingSource.load(requestedYear, nextController.signal));
      if (requestId !== sequence.current) return;
      if (!parsed) {
        setErrorPresentation('INVALID_PAYLOAD');
        setState('ERROR');
        return;
      }
      setMetadata(parsed.metadata);
      selectedYear.current = parsed.metadata.selectedYear;
      setYear(parsed.metadata.selectedYear);
      if (parsed.reportingState === 'READY') {
        setReport(parsed.report);
        setState('READY');
        return;
      }
      setState(parsed.reportingState);
    } catch (error) {
      if (requestId !== sequence.current || nextController.signal.aborted) return;
      setReport(null);
      if (error instanceof PnlReportingSourceError && error.code === 'FORBIDDEN') setErrorPresentation('FORBIDDEN');
      else if (error instanceof PnlReportingSourceError && error.code === 'INVALID_PAYLOAD') setErrorPresentation('INVALID_PAYLOAD');
      else setErrorPresentation('ERROR');
      setState('ERROR');
    }
  }, [reportingSource]);

  useEffect(() => {
    selectedYear.current = initialYear;
    void load(initialYear);
    return () => {
      sequence.current += 1;
      controller.current?.abort();
    };
  }, [initialYear, load, refreshToken]);

  const availableYears = metadata
    ? metadata.availableYears.includes(metadata.selectedYear)
      ? metadata.availableYears
      : [metadata.selectedYear, ...metadata.availableYears]
    : [];

  return <div className="pnl-report" data-state={state} data-testid="pnl-report">
    <div className="pnl-report__view-container">
      <div className="pnl-report__filter-bar">
        <div className="pnl-report__filter-item">
          <span className="pnl-report__filter-label"><Calendar size={13} color="#2563eb" />기준년도</span>
          <select className="pnl-report__filter-select" aria-label="기준년도" value={year ?? ''} disabled={!metadata} onChange={(event) => {
            const nextYear = Number(event.target.value);
            selectedYear.current = nextYear;
            setYear(nextYear);
            void load(nextYear);
          }}>{availableYears.map((option) => <option key={option} value={option}>{option}년</option>)}</select>
        </div>
        <button type="button" className="pnl-report__refresh" title="새로고침" aria-label="손익 현황 새로고침" onClick={() => void load()}><RefreshCw size={13} className={state === 'LOADING' ? 'spin' : ''} /></button>
      </div>

      {state === 'LOADING' && <section className="pnl-report__state" role="status" aria-live="polite"><span className="pnl-report__spinner" aria-hidden="true" /><div className="pnl-report__state-title">손익 현황을 불러오는 중…</div></section>}
      {state !== 'LOADING' && state !== 'READY' && <StateMessage state={state} presentation={errorPresentation} onRetry={() => void load()} />}

      {state === 'READY' && report && <div className="pnl-report__ready" key={report.reportKey}>
        <KpiOverview kpis={report.kpis} />
        <MonthlyTrendChart data={report.monthlyTrends} dataRows={report.monthlyDataRows} />

        <nav className="pnl-report__detail-nav" aria-label="손익 상세">
          <div className="pnl-report__detail-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={activeTab === 'pnl_statement'} className={activeTab === 'pnl_statement' ? 'active' : ''} onClick={() => setActiveTab('pnl_statement')}><FileSpreadsheet size={14} />1. 손익계산서 (P&amp;L)</button>
            <button type="button" role="tab" aria-selected={activeTab === 'mfg_cost_breakdown'} className={activeTab === 'mfg_cost_breakdown' ? 'active' : ''} onClick={() => setActiveTab('mfg_cost_breakdown')}><Factory size={14} />2. 제품/반제품 매출원가 내역</button>
            <button type="button" role="tab" aria-selected={activeTab === 'sga_breakdown'} className={activeTab === 'sga_breakdown' ? 'active' : ''} onClick={() => setActiveTab('sga_breakdown')}><Landmark size={14} />3. 판매관리비 내역</button>
            <button type="button" role="tab" aria-selected={activeTab === 'item_segment_pnl'} className={activeTab === 'item_segment_pnl' ? 'active' : ''} onClick={() => setActiveTab('item_segment_pnl')}><Package size={14} />4. Item별 구분손익</button>
          </div>
          {onNavigateToVariance && <button type="button" className="pnl-report__analysis-link" onClick={onNavigateToVariance}>손익 요인 Waterfall 분석 바로가기 <ArrowRightCircle size={13} /></button>}
        </nav>

        <div className="pnl-report__detail-panel">
          {activeTab === 'pnl_statement' && <PnlTable rows={report.pnlRows} periods={report.periods} actualPeriodKeys={report.actualPeriodKeys} initialPeriodKey={report.selectedPeriodKey} defaultCustomRangeKey={report.defaultCustomRangeKey} />}
          {activeTab === 'mfg_cost_breakdown' && <MfgCostTable rows={report.cogsRows} periods={report.periods} actualPeriodKeys={report.actualPeriodKeys} />}
          {activeTab === 'sga_breakdown' && <SgaTable rows={report.sgaRows} periods={report.periods} actualPeriodKeys={report.actualPeriodKeys} initialPeriodKey={report.selectedPeriodKey} defaultCustomRangeKey={report.defaultCustomRangeKey} />}
          {activeTab === 'item_segment_pnl' && <ProductSegmentPnlTable segments={report.productSegments} periods={report.periods} actualPeriodKeys={report.actualPeriodKeys} initialPeriodKey={report.selectedPeriodKey} defaultCustomRangeKey={report.defaultCustomRangeKey} />}
        </div>
      </div>}
    </div>
  </div>;
}

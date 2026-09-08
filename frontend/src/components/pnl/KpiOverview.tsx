import type { PnlKpiSlot } from '../../types/pnlReporting';
import { formatReportingDisplayText } from './ReportingTableControls';

interface KpiOverviewProps {
  kpis: PnlKpiSlot[];
}

export function KpiOverview({ kpis }: KpiOverviewProps) {
  return <section className="pnl-report__kpi-grid" aria-label="핵심 손익 지표">
    {kpis.map((kpi) => <article className="pnl-report__kpi-card" data-kpi-key={kpi.key} key={kpi.key}>
      <div className="pnl-report__kpi-label">{kpi.label}</div>
      <div className="pnl-report__kpi-value">
        <span className="pnl-report__tabular">{kpi.amountText === null ? '—' : formatReportingDisplayText(kpi.amountText)}</span>
        <span className="pnl-report__kpi-unit">{kpi.unitText}</span>
      </div>
      <div>
        {(kpi.progressText || kpi.achievementText) ? <span className="pnl-report__kpi-secondary">
          <span>진도율 {kpi.progressText ? formatReportingDisplayText(kpi.progressText) : '—'} | 계획 대비 달성률 {kpi.achievementText ? formatReportingDisplayText(kpi.achievementText) : '—'}</span>
        </span> : <span className="pnl-report__kpi-secondary">지표 미등록</span>}
      </div>
    </article>)}
  </section>;
}

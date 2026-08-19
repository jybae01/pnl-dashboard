import type { PnlKpiSlot } from '../../types/pnlReporting';

interface KpiOverviewProps {
  kpis: PnlKpiSlot[];
}

export function KpiOverview({ kpis }: KpiOverviewProps) {
  return <section className="pnl-report__kpi-grid" aria-label="핵심 손익 지표">
    {kpis.map((kpi) => <article className="pnl-report__kpi-card" data-kpi-key={kpi.key} key={kpi.key}>
      <div className="pnl-report__kpi-label">{kpi.label}</div>
      <div className="pnl-report__kpi-value">
        <span className="pnl-report__tabular">{kpi.amountText ?? '—'}</span>
        <span className="pnl-report__kpi-unit">{kpi.unitText}</span>
      </div>
      <div>
        {(kpi.progressText || kpi.achievementText) ? <span className={`pnl-report__kpi-pill pnl-report__value--${kpi.tone}`}>
          <span aria-hidden="true">{kpi.tone === 'favorable' ? '↑' : kpi.tone === 'unfavorable' ? '↓' : '–'}</span>
          <span>진도율 {kpi.progressText ?? '—'} | 계획 대비 달성률 {kpi.achievementText ?? '—'}</span>
        </span> : <span className="pnl-report__kpi-pill pnl-report__value--neutral">지표 미등록</span>}
      </div>
    </article>)}
  </section>;
}

import React from 'react';
import { PnlDashboardDto } from './types';

const money = (value: number) => `${(value / 1_000_000).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}백만원`;
const nullableMoney = (value: number | null) => value === null ? '미산출' : money(value);
const percent = (value: number | null) => value === null ? '미산출' : `${value.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`;

function Delta({ value }: { value: number }) {
  return <span style={{ color: value > 0 ? '#dc2626' : value < 0 ? '#2563eb' : '#64748b' }}>{money(value)}</span>;
}

export function PnlDashboardPanel({ dashboard }: { dashboard: PnlDashboardDto }) {
  const [tab, setTab] = React.useState<'pnl' | 'manufacturing' | 'sga' | 'groups'>('pnl');
  const { identity, kpis } = dashboard;
  return <>
    <section className="filter-bar" aria-label="Dashboard identity">
      <strong>{identity.model_year}년 손익 현황</strong>
      <span>{identity.baseline_model_name} → {identity.comparison_model_name}</span>
      <span>{identity.start_month}~{identity.end_month}월 · 실적 확정 {identity.actual_through_month === null ? '없음' : `${identity.actual_through_month}월`}</span>
    </section>

    <section className="kpi-grid" aria-label="핵심 KPI">
      {(['revenue', 'gross_profit', 'operating_profit'] as const).map((code) => {
        const metric = kpis[code].period;
        return <article className="kpi-card" key={code}>
          <div className="kpi-title">{metric.label}</div>
          <div className="kpi-value">{money(metric.comparison)}</div>
          <div className="kpi-sub">기간 Base {money(metric.baseline)} · 증감 <Delta value={metric.delta} /></div>
          <div className="kpi-sub">{kpis.latest_month}월 Comparison {money(kpis[code].latest.comparison)}</div>
        </article>;
      })}
      <article className="kpi-card">
        <div className="kpi-title">영업이익률</div>
        <div className="kpi-value">{percent(kpis.period_operating_margin.comparison)}</div>
        <div className="kpi-sub">Base {percent(kpis.period_operating_margin.baseline)} · 증감 {percent(kpis.period_operating_margin.delta_percentage_points)}</div>
      </article>
    </section>

    <section className="card" aria-label="월별 추이">
      <div className="card-header"><h3>월별 손익 추이</h3></div>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>월</th><th>구분</th><th>매출 Base / Comparison / 증감</th><th>GP Base / Comparison / 증감</th><th>OP Base / Comparison / 증감</th><th>영업이익률</th></tr></thead><tbody>
        {dashboard.monthly_series.map((row) => <tr key={row.month}><td>{row.month}월</td><td>{row.comparison_period_type ?? '미분류'}</td><td>{money(row.revenue.baseline)} / {money(row.revenue.comparison)} / {money(row.revenue.delta)}</td><td>{money(row.gross_profit.baseline)} / {money(row.gross_profit.comparison)} / {money(row.gross_profit.delta)}</td><td>{money(row.operating_profit.baseline)} / {money(row.operating_profit.comparison)} / {money(row.operating_profit.delta)}</td><td>{percent(row.comparison_operating_margin)}</td></tr>)}
      </tbody></table></div>
    </section>

    <div className="tab-row" role="tablist">
      {([['pnl', '손익계산서'], ['manufacturing', '제조원가'], ['sga', '판매관리비'], ['groups', '제품군 손익']] as const).map(([key, label]) => <button className={`tab-pill-btn ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)} key={key}>{label}</button>)}
    </div>
    {tab === 'pnl' && <FinancialTable title="손익계산서" rows={dashboard.pnl_statement} />}
    {tab === 'manufacturing' && <section className="card"><FinancialTable title="제조원가 구성" rows={dashboard.manufacturing.cost_lines} nested /><AccountTable rows={dashboard.manufacturing.accounts} /><p className="text-muted">JPY 환율 단위: {dashboard.manufacturing.material_components.jpy_fx_unit} · MCM 별도 원재료 효과 없음</p></section>}
    {tab === 'sga' && <section className="card"><h3>판매관리비 명세</h3><AccountTable rows={dashboard.sga.accounts} /><p className="text-muted">{dashboard.sga.fixed_scope}</p></section>}
    {tab === 'groups' && <section className="card"><h3>제품군 손익</h3><div className="table-scroll"><table className="data-table"><thead><tr><th>제품군</th><th>수량 단위</th><th>Base / Comparison 수량</th><th>Base / Comparison 매출</th><th>Base / Comparison 원가</th><th>Base / Comparison GP</th></tr></thead><tbody>{dashboard.product_groups.map((row) => <tr key={row.code}><td>{row.display_name}</td><td>{row.quantity_unit}</td><td>{row.baseline_quantity.toLocaleString()} / {row.comparison_quantity.toLocaleString()}</td><td>{money(row.baseline_revenue)} / {money(row.comparison_revenue)}</td><td>{money(row.baseline_cogs)} / {money(row.comparison_cogs)}</td><td>{money(row.baseline_gross_profit)} / {money(row.comparison_gross_profit)}</td></tr>)}</tbody></table></div></section>}

    <section className="card" aria-label="주요 변동"><h3>주요 손익 변동</h3>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>Effect</th><th>영업이익 영향</th></tr></thead><tbody>{dashboard.key_facts.effects.map((effect) => <tr key={effect.code}><td>{effect.label}</td><td><Delta value={effect.profit_effect} /></td></tr>)}<tr><td>Residual</td><td><Delta value={dashboard.key_facts.residual} /></td></tr></tbody></table></div>
    </section>
  </>;
}

function FinancialTable({ title, rows, nested = false }: { title: string; rows: PnlDashboardDto['pnl_statement']; nested?: boolean }) {
  const table = <div className="table-scroll"><table className="data-table"><thead><tr><th>항목</th><th>Base</th><th>Comparison</th><th>증감</th><th>매출 대비</th></tr></thead><tbody>{rows.map((row) => <tr key={row.code}><td>{row.label}</td><td>{money(row.baseline)}</td><td>{money(row.comparison)}</td><td><Delta value={row.delta} /></td><td>{percent(row.comparison_ratio_to_revenue)}</td></tr>)}</tbody></table></div>;
  return nested ? table : <section className="card"><h3>{title}</h3>{table}</section>;
}

function AccountTable({ rows }: { rows: PnlDashboardDto['manufacturing']['accounts'] }) {
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>계정</th><th>분류</th><th>Base</th><th>Comparison</th><th>증감</th><th>손익효과</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.account}-${index}`}><td>{row.account}</td><td>{row.classification}</td><td>{money(row.baseline)}</td><td>{money(row.comparison)}</td><td><Delta value={row.delta} /></td><td>{nullableMoney(row.profit_effect)}</td></tr>)}</tbody></table></div>;
}

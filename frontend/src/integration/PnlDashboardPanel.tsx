import React, { useMemo, useState } from 'react';
import { ArrowRight, Factory, FileSpreadsheet, Landmark, Package } from 'lucide-react';
import { PnlDashboardDto, DashboardFinancialLineDto, DashboardAccountDto } from './types';

type DashboardTab = 'pnl' | 'manufacturing' | 'sga' | 'groups';

const moneyFormatter = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 });
const compactMoneyFormatter = new Intl.NumberFormat('ko-KR', { notation: 'compact', maximumFractionDigits: 1 });
const decimalFormatter = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 });

function money(value: number): string {
  return `${value < 0 ? '-' : ''}₩${moneyFormatter.format(Math.abs(value))}`;
}

function nullableMoney(value: number | null): string {
  return value === null ? '미산출' : money(value);
}

function signedMoney(value: number): string {
  return `${value > 0 ? '+' : ''}${money(value)}`;
}

function percent(value: number | null): string {
  return value === null ? '미산출' : `${decimalFormatter.format(value)}%`;
}

function signedPercent(value: number | null): string {
  return value === null ? '미산출' : `${value > 0 ? '+' : ''}${decimalFormatter.format(value)}%p`;
}

function tone(value: number): 'positive' | 'negative' | 'neutral' {
  return value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral';
}

function ToneValue({ value, format = 'money', signed = false }: {
  value: number | null;
  format?: 'money' | 'percent';
  signed?: boolean;
}) {
  const label = value === null
    ? '미산출'
    : format === 'percent'
      ? signedPercent(value)
      : signed ? signedMoney(value) : money(value);
  return <span className={`pnl-dashboard__tone pnl-dashboard__tone--${value === null ? 'neutral' : tone(value)}`}>{label}</span>;
}

function NeutralAmount({ value }: { value: number }) {
  return <span className="pnl-dashboard__amount">{signedMoney(value)}</span>;
}

function ScenarioBadge({ scenario }: { scenario: '기준 모형' | '비교 모형' | '실적' | '추정' | '계획' }) {
  const scenarioClass = scenario === '실적'
    ? 'actual'
    : scenario === '추정'
      ? 'forecast'
      : scenario === '계획' || scenario === '기준 모형'
        ? 'plan'
        : 'neutral';
  return <span className={`pnl-dashboard__scenario pnl-dashboard__scenario--${scenarioClass}`}>{scenario}</span>;
}

function metricValue(row: PnlDashboardDto['monthly_series'][number], metric: TrendMetric['key'], side: 'baseline' | 'comparison'): number | null {
  if (metric === 'revenue') return row.revenue[side];
  if (metric === 'operating_profit') return row.operating_profit[side];
  return side === 'baseline' ? row.baseline_operating_margin : row.comparison_operating_margin;
}

type TrendMetric = {
  key: 'revenue' | 'operating_profit' | 'operating_margin';
  label: string;
  format: 'money' | 'percent';
};

const trendMetrics: TrendMetric[] = [
  { key: 'revenue', label: '매출액', format: 'money' },
  { key: 'operating_profit', label: '영업이익', format: 'money' },
  { key: 'operating_margin', label: '영업이익률', format: 'percent' },
];

function chartValueLabel(value: number | null, format: TrendMetric['format']): string {
  if (value === null) return '미산출';
  return format === 'money' ? money(value) : percent(value);
}

function chartAxisLabel(value: number, format: TrendMetric['format']): string {
  return format === 'money'
    ? `${value < 0 ? '-' : ''}₩${compactMoneyFormatter.format(Math.abs(value))}`
    : percent(value);
}

function TrendChart({ rows, metric, baselineName, comparisonName }: {
  rows: PnlDashboardDto['monthly_series'];
  metric: TrendMetric;
  baselineName: string;
  comparisonName: string;
}) {
  const width = 760;
  const height = 214;
  const plot = { left: 48, right: 16, top: 18, bottom: 34 };
  const values = rows.flatMap((row) => [metricValue(row, metric.key, 'baseline'), metricValue(row, metric.key, 'comparison')])
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const rawMin = values.length ? Math.min(...values) : 0;
  const rawMax = values.length ? Math.max(...values) : 1;
  const range = rawMax - rawMin || Math.max(Math.abs(rawMax), 1);
  const min = rawMin - range * 0.12;
  const max = rawMax + range * 0.12;
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const x = (index: number) => rows.length <= 1 ? plot.left + innerWidth / 2 : plot.left + (index / (rows.length - 1)) * innerWidth;
  const y = (value: number) => plot.top + ((max - value) / (max - min)) * innerHeight;
  const points = (side: 'baseline' | 'comparison') => rows.map((row, index) => {
    const value = metricValue(row, metric.key, side);
    return value === null ? null : { x: x(index), y: y(value), value, row, index };
  });
  const baselinePoints = points('baseline');
  const comparisonPoints = points('comparison');
  const pathSegments = (series: Array<{ x: number; y: number } | null>) => {
    const paths: string[] = [];
    let current: Array<{ x: number; y: number }> = [];
    const flush = () => {
      if (current.length > 0) {
        paths.push(current.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' '));
      }
      current = [];
    };
    series.forEach((point) => {
      if (point === null) flush();
      else current.push(point);
    });
    flush();
    return paths;
  };
  const baselinePaths = pathSegments(baselinePoints);
  const scenarioColor = (period: PnlDashboardDto['monthly_series'][number]['comparison_period_type']) => (
    period === '추정' ? 'var(--pnl-forecast)' : period === '계획' ? 'var(--pnl-plan)' : period === '실적' ? 'var(--pnl-actual)' : 'var(--pnl-neutral)'
  );

  return <article className="pnl-dashboard__trend-card">
    <div className="pnl-dashboard__trend-card-header">
      <div>
        <h3>{metric.label}</h3>
        <p>월별 기준 모형과 비교 모형 추이</p>
      </div>
      <span className="pnl-dashboard__trend-range">{rows[0]?.month}월–{rows[rows.length - 1]?.month}월</span>
    </div>
    <div className="pnl-dashboard__trend-chart-scroll">
      <svg className="pnl-dashboard__trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${metric.label} 월별 추이`}>
        {[0, 0.5, 1].map((fraction) => {
          const gridY = plot.top + innerHeight * fraction;
          const gridValue = max - (max - min) * fraction;
          return <g key={fraction}>
            <line x1={plot.left} x2={width - plot.right} y1={gridY} y2={gridY} className="pnl-dashboard__trend-grid" />
            <text x={plot.left - 8} y={gridY + 4} textAnchor="end" className="pnl-dashboard__trend-axis">{chartAxisLabel(gridValue, metric.format)}</text>
          </g>;
        })}
        {baselinePaths.map((path, index) => <path key={`baseline-path-${index}`} d={path} className="pnl-dashboard__trend-line pnl-dashboard__trend-line--baseline" />)}
        {comparisonPoints.map((point, index) => {
          const previous = comparisonPoints[index - 1];
          if (!point) return null;
          const color = scenarioColor(point.row.comparison_period_type);
          return <g key={`comparison-${point.row.month}`}>
            {previous && <line x1={previous.x} y1={previous.y} x2={point.x} y2={point.y} className="pnl-dashboard__trend-line" style={{ stroke: color }} />}
            <circle cx={point.x} cy={point.y} r="4" className="pnl-dashboard__trend-point" style={{ fill: color }}>
              <title>{`${point.row.month}월 ${comparisonName}: ${chartValueLabel(point.value, metric.format)}`}</title>
            </circle>
          </g>;
        })}
        {baselinePoints.map((point) => point && <circle key={`baseline-${point.row.month}`} cx={point.x} cy={point.y} r="3" className="pnl-dashboard__trend-point pnl-dashboard__trend-point--baseline">
          <title>{`${point.row.month}월 ${baselineName}: ${chartValueLabel(point.value, metric.format)}`}</title>
        </circle>)}
        {rows.map((row, index) => <text key={row.month} x={x(index)} y={height - 10} textAnchor="middle" className="pnl-dashboard__trend-axis">{row.month}월</text>)}
      </svg>
    </div>
  </article>;
}

function FinancialLinesTable({ title, rows, baselineName, comparisonName, embedded = false }: {
  title: string;
  rows: DashboardFinancialLineDto[];
  baselineName: string;
  comparisonName: string;
  embedded?: boolean;
}) {
  const content = <>
    <div className="pnl-dashboard__section-header"><h3>{title}</h3><span>금액 단위: KRW</span></div>
    <div className="pnl-dashboard__table-scroll">
      <table className="pnl-dashboard__table">
        <thead><tr><th scope="col">항목</th><th scope="col" className="is-number">{baselineName}</th><th scope="col" className="is-number">{comparisonName}</th><th scope="col" className="is-number">증감</th><th scope="col" className="is-number">비교 매출 대비</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.code}>
          <th scope="row">{row.label}</th>
          <td className="is-number">{money(row.baseline)}</td>
          <td className="is-number">{money(row.comparison)}</td>
          <td className="is-number"><NeutralAmount value={row.delta} /></td>
          <td className="is-number">{percent(row.comparison_ratio_to_revenue)}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </>;
  return embedded ? <div className="pnl-dashboard__table-block">{content}</div> : <section className="pnl-dashboard__section-card">{content}</section>;
}

function accountClassification(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'fixed' || normalized === 'fixed_cost' || normalized === 'fixed manufacturing') return '고정';
  if (normalized === 'variable' || normalized === 'variable_cost' || normalized === 'variable manufacturing') return '변동';
  if (value === '고정' || value === '변동') return value;
  return '미분류';
}

function AccountTable({ rows, baselineName, comparisonName }: { rows: DashboardAccountDto[]; baselineName: string; comparisonName: string }) {
  if (rows.length === 0) return <p className="pnl-dashboard__muted">표시할 계정 내역이 없습니다.</p>;
  return <div className="pnl-dashboard__table-scroll">
    <table className="pnl-dashboard__table">
      <thead><tr><th scope="col">계정</th><th scope="col">분류</th><th scope="col" className="is-number">{baselineName}</th><th scope="col" className="is-number">{comparisonName}</th><th scope="col" className="is-number">증감</th><th scope="col" className="is-number">손익 영향</th></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={`${row.account}-${index}`}>
        <th scope="row">{row.account}</th><td>{accountClassification(row.classification)}</td><td className="is-number">{money(row.baseline)}</td><td className="is-number">{money(row.comparison)}</td><td className="is-number"><NeutralAmount value={row.delta} /></td><td className="is-number">{row.profit_effect === null ? '미산출' : <ToneValue value={row.profit_effect} signed />}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}

function ProductGroupTable({ dashboard }: { dashboard: PnlDashboardDto }) {
  const { identity, product_groups: groups } = dashboard;
  return <section className="pnl-dashboard__section-card">
    <div className="pnl-dashboard__section-header"><h3>제품군 손익</h3><span>단위가 다른 수량은 별도 표시</span></div>
    <div className="pnl-dashboard__table-scroll">
      <table className="pnl-dashboard__table">
        <thead><tr><th scope="col">제품군</th><th scope="col">수량 단위</th><th scope="col" className="is-number">{identity.baseline_model_name} 수량</th><th scope="col" className="is-number">{identity.comparison_model_name} 수량</th><th scope="col" className="is-number">기준 매출</th><th scope="col" className="is-number">비교 매출</th><th scope="col" className="is-number">기준 원가</th><th scope="col" className="is-number">비교 원가</th><th scope="col" className="is-number">기준 GP</th><th scope="col" className="is-number">비교 GP</th></tr></thead>
        <tbody>{groups.map((row) => <tr key={row.code}>
          <th scope="row">{row.display_name}</th><td><span className="pnl-dashboard__unit-badge">{row.quantity_unit}</span></td><td className="is-number">{row.baseline_quantity.toLocaleString('ko-KR')}</td><td className="is-number">{row.comparison_quantity.toLocaleString('ko-KR')}</td><td className="is-number">{money(row.baseline_revenue)}</td><td className="is-number">{money(row.comparison_revenue)}</td><td className="is-number">{money(row.baseline_cogs)}</td><td className="is-number">{money(row.comparison_cogs)}</td><td className="is-number">{money(row.baseline_gross_profit)}</td><td className="is-number">{money(row.comparison_gross_profit)}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}

export interface PnlDashboardPanelProps {
  dashboard: PnlDashboardDto;
  onNavigateToVariance?: () => void;
}

export function PnlDashboardPanel({ dashboard, onNavigateToVariance }: PnlDashboardPanelProps) {
  const [tab, setTab] = useState<DashboardTab>('pnl');
  const { identity, kpis } = dashboard;
  const scenarioTypes = useMemo(() => Array.from(new Set(dashboard.monthly_series.map((row) => row.comparison_period_type).filter((value): value is '실적' | '추정' | '계획' => value !== null))), [dashboard.monthly_series]);
  const hasUnclassifiedScenario = dashboard.monthly_series.some((row) => row.comparison_period_type === null);
  const tabs: Array<{ key: DashboardTab; label: string; icon: React.ReactNode }> = [
    { key: 'pnl', label: '손익계산서', icon: <FileSpreadsheet size={14} /> },
    { key: 'manufacturing', label: '제조원가', icon: <Factory size={14} /> },
    { key: 'sga', label: '판매관리비', icon: <Landmark size={14} /> },
    { key: 'groups', label: '제품군 손익', icon: <Package size={14} /> },
  ];

  return <div className="pnl-dashboard" data-testid="pnl-dashboard">
    <section className="pnl-dashboard__identity" aria-label="손익 현황 조건">
      <div className="pnl-dashboard__identity-heading">
        <div><p className="pnl-dashboard__eyebrow">P&amp;L STATUS</p><h1>손익 현황</h1></div>
        <span className="pnl-dashboard__identity-year">{identity.model_year}년</span>
      </div>
      <div className="pnl-dashboard__identity-meta">
        <span className="pnl-dashboard__model-pair"><ScenarioBadge scenario="기준 모형" /> <strong>{identity.baseline_model_name}</strong><span aria-hidden="true">↔</span><ScenarioBadge scenario="비교 모형" /> <strong>{identity.comparison_model_name}</strong></span>
        <span>{identity.start_month}월–{identity.end_month}월</span>
        <span>실적 확정 {identity.actual_through_month === null ? '없음' : `${identity.actual_through_month}월`}</span>
      </div>
    </section>

    <section className="pnl-dashboard__summary" aria-labelledby="pnl-summary-title">
      <div className="pnl-dashboard__section-heading"><div><p className="pnl-dashboard__eyebrow">AT A GLANCE</p><h2 id="pnl-summary-title">핵심 손익 요약</h2></div><span className="pnl-dashboard__unit-note">금액 단위: KRW</span></div>
      <div className="pnl-dashboard__kpi-grid">
        <article className="pnl-dashboard__kpi"><p>매출액</p><strong>{money(kpis.revenue.period.comparison)}</strong><span>{identity.comparison_model_name} · 기준 {money(kpis.revenue.period.baseline)}</span><small>기준 대비 <NeutralAmount value={kpis.revenue.period.delta} /></small></article>
        <article className="pnl-dashboard__kpi pnl-dashboard__kpi--primary"><p>영업이익</p><strong>{money(kpis.operating_profit.period.comparison)}</strong><span>{identity.comparison_model_name} · 기준 {money(kpis.operating_profit.period.baseline)}</span><small>기준 대비 <ToneValue value={kpis.operating_profit.period.delta} signed /></small></article>
        <article className="pnl-dashboard__kpi"><p>영업이익률</p><strong>{percent(kpis.period_operating_margin.comparison)}</strong><span>{identity.comparison_model_name} · 기준 {percent(kpis.period_operating_margin.baseline)}</span><small>차이 <ToneValue value={kpis.period_operating_margin.delta_percentage_points} format="percent" signed /></small></article>
        <article className="pnl-dashboard__kpi"><p>기준 대비 영업이익 증감</p><strong className={`pnl-dashboard__tone pnl-dashboard__tone--${tone(kpis.operating_profit.period.delta)}`}>{signedMoney(kpis.operating_profit.period.delta)}</strong><span>{identity.baseline_model_name} → {identity.comparison_model_name}</span><small>영업이익 영향 기준</small></article>
      </div>
    </section>

    <section className="pnl-dashboard__trend-section" aria-labelledby="pnl-trend-title">
      <div className="pnl-dashboard__section-heading"><div><p className="pnl-dashboard__eyebrow">MONTHLY TREND</p><h2 id="pnl-trend-title">월별 추세</h2></div><div className="pnl-dashboard__legend"><span><i className="pnl-dashboard__legend-dot pnl-dashboard__legend-dot--plan" />기준 모형</span>{scenarioTypes.map((scenario) => <span key={scenario}><i className={`pnl-dashboard__legend-dot pnl-dashboard__legend-dot--${scenario === '실적' ? 'actual' : scenario === '추정' ? 'forecast' : 'plan'}`} />{scenario}</span>)}{hasUnclassifiedScenario && <span><i className="pnl-dashboard__legend-dot pnl-dashboard__legend-dot--neutral" />미지정</span>}</div></div>
      <div className="pnl-dashboard__trend-grid">{trendMetrics.map((metric) => <TrendChart key={metric.key} rows={dashboard.monthly_series} metric={metric} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} />)}</div>
    </section>

    <section className="pnl-dashboard__details" aria-labelledby="pnl-detail-title">
      <div className="pnl-dashboard__section-heading"><div><p className="pnl-dashboard__eyebrow">DETAILS</p><h2 id="pnl-detail-title">상세 손익</h2></div><span className="pnl-dashboard__unit-note">업무용 고밀도 표 · 금액 단위: KRW</span></div>
      <div className="pnl-dashboard__tabs-row" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-default)', marginBottom: 9, flexWrap: 'wrap', gap: 8 }}>
        <div className="pnl-dashboard__tabs" role="tablist" aria-label="손익 상세 영역" style={{ borderBottom: 'none', marginBottom: 0 }}>
          {tabs.map((item) => <button key={item.key} type="button" role="tab" aria-selected={tab === item.key} aria-controls={`pnl-dashboard-tabpanel-${item.key}`} className={`pnl-dashboard__tab ${tab === item.key ? 'is-active' : ''}`} onClick={() => setTab(item.key)}>{item.icon}{item.label}</button>)}
        </div>
        {onNavigateToVariance && (
          <button
            type="button"
            className="pnl-dashboard__quick-variance-link"
            onClick={onNavigateToVariance}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', fontSize: '11.5px', fontWeight: 700, color: '#1d4ed8', backgroundColor: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '4px', cursor: 'pointer', marginBottom: 4 }}
          >
            <span>손익 요인 Waterfall 분석 바로가기</span>
            <ArrowRight size={13} aria-hidden="true" />
          </button>
        )}
      </div>
      <div id="pnl-dashboard-tabpanel-pnl" role="tabpanel" hidden={tab !== 'pnl'}>{tab === 'pnl' && <FinancialLinesTable title="손익계산서" rows={dashboard.pnl_statement} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} />}</div>
      <div id="pnl-dashboard-tabpanel-manufacturing" role="tabpanel" hidden={tab !== 'manufacturing'}>{tab === 'manufacturing' && <section className="pnl-dashboard__section-card"><div className="pnl-dashboard__section-header"><h3>제조원가</h3><span>환율 단위: {dashboard.manufacturing.material_components.jpy_fx_unit}</span></div><FinancialLinesTable title="제조원가 구성" rows={dashboard.manufacturing.cost_lines} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} embedded /><div className="pnl-dashboard__subsection"><h4>원재료 구성</h4><div className="pnl-dashboard__material-grid"><span>비직물 가격 (환율 제외)<strong>{nullableMoney(dashboard.manufacturing.material_components.nonwoven_price_ex_fx)}</strong></span><span>비직물 JPY<strong>{nullableMoney(dashboard.manufacturing.material_components.nonwoven_jpy)}</strong></span><span>비직물 외 재료<strong>{nullableMoney(dashboard.manufacturing.material_components.materials_ex_nonwoven)}</strong></span><span>합계<strong>{nullableMoney(dashboard.manufacturing.material_components.total)}</strong></span></div></div><div className="pnl-dashboard__subsection"><h4>제조원가 계정</h4><AccountTable rows={dashboard.manufacturing.accounts} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} /></div></section>}</div>
      <div id="pnl-dashboard-tabpanel-sga" role="tabpanel" hidden={tab !== 'sga'}>{tab === 'sga' && <section className="pnl-dashboard__section-card"><div className="pnl-dashboard__section-header"><h3>판매관리비</h3><span>계정별 비교</span></div><AccountTable rows={dashboard.sga.accounts} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} /></section>}</div>
      <div id="pnl-dashboard-tabpanel-groups" role="tabpanel" hidden={tab !== 'groups'}>{tab === 'groups' && <ProductGroupTable dashboard={dashboard} />}</div>
    </section>

    <section className="pnl-dashboard__factors" aria-labelledby="pnl-factors-title">
      <div className="pnl-dashboard__section-heading"><div><p className="pnl-dashboard__eyebrow">KEY VARIANCES</p><h2 id="pnl-factors-title">주요 손익 변동요인</h2></div><span className="pnl-dashboard__unit-note">결과 제공 순서</span></div>
      <div className="pnl-dashboard__factor-grid">{dashboard.key_facts.effects.map((effect) => <div className="pnl-dashboard__factor" key={effect.code}><span>{effect.label}</span><ToneValue value={effect.profit_effect} signed /></div>)}<div className="pnl-dashboard__factor pnl-dashboard__factor--residual"><span>기타 요인</span><ToneValue value={dashboard.key_facts.residual} signed /></div></div>
      <div className="pnl-dashboard__cta"><div><h3>기준 대비 변동원인을 더 확인해야 하나요?</h3><p>손익분석에서 변동요인과 세부 근거를 확인할 수 있습니다.</p></div>{onNavigateToVariance && <button type="button" className="pnl-dashboard__cta-button" onClick={onNavigateToVariance}>손익분석 상세 보기 <ArrowRight size={15} /></button>}</div>
    </section>
  </div>;
}

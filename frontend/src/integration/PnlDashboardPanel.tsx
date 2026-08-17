import React, { useMemo, useState } from 'react';
import { ArrowRight, DollarSign, Factory, FileSpreadsheet, Landmark, Package, TrendingUp } from 'lucide-react';
import { PnlDashboardDto, DashboardFinancialLineDto, DashboardAccountDto } from './types';

type DashboardTab = 'pnl' | 'manufacturing' | 'sga' | 'groups';

const moneyFormatter = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 });
const decimalFormatter = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 });

function money(value: number): string {
  const millions = value / 1_000_000;
  return `${millions < 0 ? '-' : ''}${moneyFormatter.format(Math.abs(millions))} 백만원`;
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

function tone(value: number | null): 'positive' | 'negative' | 'neutral' {
  if (value === null || Number.isNaN(value) || value === 0) return 'neutral';
  return value > 0 ? 'positive' : 'negative';
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
  return <span className={`pnl-dashboard__tone pnl-dashboard__tone--${tone(value)}`}>{label}</span>;
}

function NeutralAmount({ value }: { value: number }) {
  return <span className="pnl-dashboard__amount">{signedMoney(value)}</span>;
}

function chartValueLabel(value: number | null, format: 'money' | 'percent'): string {
  if (value === null) return '미산출';
  return format === 'money' ? money(value) : percent(value);
}

function chartAxisLabel(value: number, format: 'money' | 'percent'): string {
  return format === 'money'
    ? `${value < 0 ? '-' : ''}${decimalFormatter.format(Math.abs(value) / 1_000_000)}`
    : percent(value);
}

function RevenueTrendCard({ rows, baselineName, comparisonName }: {
  rows: PnlDashboardDto['monthly_series'];
  baselineName: string;
  comparisonName: string;
}) {
  const width = 760;
  const height = 214;
  const plot = { left: 52, right: 16, top: 18, bottom: 34 };
  const values = rows.flatMap((row) => [row.revenue.baseline, row.revenue.comparison])
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const rawMin = values.length ? Math.min(...values) : 0;
  const rawMax = values.length ? Math.max(...values) : 1;
  const range = rawMax - rawMin || Math.max(Math.abs(rawMax), 1);
  const min = Math.min(0, rawMin - range * 0.08);
  const max = rawMax + range * 0.12;
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const x = (index: number) => rows.length <= 1 ? plot.left + innerWidth / 2 : plot.left + (index / (rows.length - 1)) * innerWidth;
  const y = (value: number) => plot.top + ((max - value) / (max - min)) * innerHeight;

  const baselinePoints = rows.map((row, index) => {
    const value = row.revenue.baseline;
    return value === null ? null : { x: x(index), y: y(value), value, row, index };
  });
  const comparisonPoints = rows.map((row, index) => {
    const value = row.revenue.comparison;
    return value === null ? null : { x: x(index), y: y(value), value, row, index };
  });

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

  return <article className="pnl-dashboard__trend-card" data-testid="revenue-trend-card">
    <div className="pnl-dashboard__trend-card-header">
      <div>
        <h3><DollarSign size={14} aria-hidden="true" style={{ color: '#2563eb', verticalAlign: 'middle', marginRight: 4 }} />월별 매출액 추이</h3>
        <p>월별 기준 모형과 비교 모형 매출 추이</p>
      </div>
      <span className="pnl-dashboard__trend-range">{rows[0]?.month}월–{rows[rows.length - 1]?.month}월</span>
    </div>
    <div className="pnl-dashboard__trend-chart-scroll">
      <svg className="pnl-dashboard__trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="월별 매출액 추이">
        {[0, 0.5, 1].map((fraction) => {
          const gridY = plot.top + innerHeight * fraction;
          const gridValue = max - (max - min) * fraction;
          return <g key={fraction}>
            <line x1={plot.left} x2={width - plot.right} y1={gridY} y2={gridY} className="pnl-dashboard__trend-grid" />
            <text x={plot.left - 8} y={gridY + 4} textAnchor="end" className="pnl-dashboard__trend-axis">{chartAxisLabel(gridValue, 'money')}</text>
          </g>;
        })}
        {baselinePaths.map((path, index) => <path key={`baseline-rev-path-${index}`} d={path} className="pnl-dashboard__trend-line pnl-dashboard__trend-line--baseline" />)}
        {comparisonPoints.map((point, index) => {
          const previous = comparisonPoints[index - 1];
          if (!point) return null;
          const color = scenarioColor(point.row.comparison_period_type);
          return <g key={`comparison-rev-${point.row.month}`}>
            {previous && <line x1={previous.x} y1={previous.y} x2={point.x} y2={point.y} className="pnl-dashboard__trend-line" style={{ stroke: color }} />}
            <circle cx={point.x} cy={point.y} r="4" className="pnl-dashboard__trend-point" style={{ fill: color }}>
              <title>{`${point.row.month}월 ${comparisonName} 매출: ${chartValueLabel(point.value, 'money')}`}</title>
            </circle>
          </g>;
        })}
        {baselinePoints.map((point) => point && <circle key={`baseline-rev-${point.row.month}`} cx={point.x} cy={point.y} r="3" className="pnl-dashboard__trend-point pnl-dashboard__trend-point--baseline">
          <title>{`${point.row.month}월 ${baselineName} 매출: ${chartValueLabel(point.value, 'money')}`}</title>
        </circle>)}
        {rows.map((row, index) => <text key={row.month} x={x(index)} y={height - 10} textAnchor="middle" className="pnl-dashboard__trend-axis">{row.month}월</text>)}
      </svg>
    </div>
  </article>;
}

function CompositeProfitMarginTrendCard({ rows, baselineName, comparisonName }: {
  rows: PnlDashboardDto['monthly_series'];
  baselineName: string;
  comparisonName: string;
}) {
  const [mode, setMode] = useState<'operating-profit' | 'table'>('operating-profit');
  const width = 760;
  const height = 214;
  const plot = { left: 52, right: 48, top: 18, bottom: 34 };

  const opValues = rows.flatMap((row) => [row.operating_profit.baseline, row.operating_profit.comparison])
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const rawOpMin = opValues.length ? Math.min(...opValues) : 0;
  const rawOpMax = opValues.length ? Math.max(...opValues) : 1;
  const opRange = rawOpMax - rawOpMin || Math.max(Math.abs(rawOpMax), 1);
  const minOp = rawOpMin - opRange * 0.12;
  const maxOp = rawOpMax + opRange * 0.12;

  const marginValues = rows.flatMap((row) => [row.baseline_operating_margin, row.comparison_operating_margin])
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const rawMarginMin = marginValues.length ? Math.min(...marginValues) : 0;
  const rawMarginMax = marginValues.length ? Math.max(...marginValues) : 10;
  const marginRange = rawMarginMax - rawMarginMin || 10;
  const minMargin = Math.min(0, rawMarginMin - marginRange * 0.1);
  const maxMargin = rawMarginMax + marginRange * 0.15;

  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const x = (index: number) => rows.length <= 1 ? plot.left + innerWidth / 2 : plot.left + (index / (rows.length - 1)) * innerWidth;
  const yOp = (value: number) => plot.top + ((maxOp - value) / (maxOp - minOp)) * innerHeight;
  const yMargin = (value: number) => plot.top + ((maxMargin - value) / (maxMargin - minMargin)) * innerHeight;

  const opBaselinePoints = rows.map((row, index) => {
    const value = row.operating_profit.baseline;
    return value === null ? null : { x: x(index), y: yOp(value), value, row, index };
  });
  const opComparisonPoints = rows.map((row, index) => {
    const value = row.operating_profit.comparison;
    return value === null ? null : { x: x(index), y: yOp(value), value, row, index };
  });
  const marginComparisonPoints = rows.map((row, index) => {
    const value = row.comparison_operating_margin;
    return value === null ? null : { x: x(index), y: yMargin(value), value, row, index };
  });

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
  const opBaselinePaths = pathSegments(opBaselinePoints);
  const scenarioColor = (period: PnlDashboardDto['monthly_series'][number]['comparison_period_type']) => (
    period === '추정' ? 'var(--pnl-forecast)' : period === '계획' ? 'var(--pnl-plan)' : period === '실적' ? 'var(--pnl-actual)' : 'var(--pnl-neutral)'
  );

  return <article className="pnl-dashboard__trend-card" data-testid="composite-trend-card">
    <div className="pnl-dashboard__trend-card-header">
      <div>
        <h3><TrendingUp size={14} aria-hidden="true" style={{ color: '#ff5f1f', verticalAlign: 'middle', marginRight: 4 }} />월별 손익 추이</h3>
        <p>영업이익과 월별 데이터표를 전환하여 확인합니다.</p>
      </div>
      <div className="pnl-dashboard__trend-modes" role="tablist" aria-label="월별 손익 추이 표시 방식">
        <button type="button" role="tab" aria-selected={mode === 'operating-profit'} className={mode === 'operating-profit' ? 'is-active' : ''} onClick={() => setMode('operating-profit')}>영업이익</button>
        <button type="button" role="tab" aria-selected="false" disabled title="Reporting Backend Contract에서 조정 영업이익이 제공되면 사용할 수 있습니다.">조정 영업이익</button>
        <button type="button" role="tab" aria-selected={mode === 'table'} className={mode === 'table' ? 'is-active' : ''} onClick={() => setMode('table')}>월별 데이터표</button>
      </div>
    </div>
    {mode === 'table' ? <div className="pnl-dashboard__table-scroll">
      <table className="pnl-dashboard__table pnl-dashboard__monthly-table">
        <thead><tr><th>월</th><th className="is-number">기준 영업이익</th><th className="is-number">비교 영업이익</th><th className="is-number">증감</th><th className="is-number">비교 영업이익률</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.month}><th scope="row">{row.month}월</th><td className="is-number">{money(row.operating_profit.baseline)}</td><td className="is-number">{money(row.operating_profit.comparison)}</td><td className="is-number"><NeutralAmount value={row.operating_profit.delta} /></td><td className="is-number">{percent(row.comparison_operating_margin)}</td></tr>)}</tbody>
      </table>
    </div> : <div className="pnl-dashboard__trend-chart-scroll">
      <svg className="pnl-dashboard__trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="월별 영업이익 및 영업이익률 복합 추이">
        {[0, 0.5, 1].map((fraction) => {
          const gridY = plot.top + innerHeight * fraction;
          const gridOpValue = maxOp - (maxOp - minOp) * fraction;
          const gridMarginValue = maxMargin - (maxMargin - minMargin) * fraction;
          return <g key={fraction}>
            <line x1={plot.left} x2={width - plot.right} y1={gridY} y2={gridY} className="pnl-dashboard__trend-grid" />
            <text x={plot.left - 8} y={gridY + 4} textAnchor="end" className="pnl-dashboard__trend-axis">{chartAxisLabel(gridOpValue, 'money')}</text>
            <text x={width - plot.right + 8} y={gridY + 4} textAnchor="start" className="pnl-dashboard__trend-axis" style={{ fill: '#6366f1' }}>{percent(gridMarginValue)}</text>
          </g>;
        })}
        {opBaselinePaths.map((path, index) => <path key={`baseline-op-path-${index}`} d={path} className="pnl-dashboard__trend-line pnl-dashboard__trend-line--baseline" />)}
        {opComparisonPoints.map((point, index) => {
          const previous = opComparisonPoints[index - 1];
          if (!point) return null;
          const color = scenarioColor(point.row.comparison_period_type);
          return <g key={`comparison-op-${point.row.month}`}>
            {previous && <line x1={previous.x} y1={previous.y} x2={point.x} y2={point.y} className="pnl-dashboard__trend-line" style={{ stroke: color, strokeWidth: 2.2 }} />}
            <circle cx={point.x} cy={point.y} r="4" className="pnl-dashboard__trend-point" style={{ fill: color }}>
              <title>{`${point.row.month}월 ${comparisonName} 영업이익: ${chartValueLabel(point.value, 'money')}`}</title>
            </circle>
          </g>;
        })}
        {opBaselinePoints.map((point) => point && <circle key={`baseline-op-${point.row.month}`} cx={point.x} cy={point.y} r="3" className="pnl-dashboard__trend-point pnl-dashboard__trend-point--baseline">
          <title>{`${point.row.month}월 ${baselineName} 영업이익: ${chartValueLabel(point.value, 'money')}`}</title>
        </circle>)}
        {marginComparisonPoints.map((point, index) => {
          const previous = marginComparisonPoints[index - 1];
          if (!point) return null;
          return <g key={`comparison-margin-${point.row.month}`}>
            {previous && <line x1={previous.x} y1={previous.y} x2={point.x} y2={point.y} stroke="#6366f1" strokeWidth="1.8" strokeDasharray="3 2" />}
            <polygon
              points={`${point.x},${point.y - 4} ${point.x + 4},${point.y} ${point.x},${point.y + 4} ${point.x - 4},${point.y}`}
              fill="#6366f1"
            >
              <title>{`${point.row.month}월 ${comparisonName} 영업이익률: ${chartValueLabel(point.value, 'percent')}`}</title>
            </polygon>
          </g>;
        })}
        {rows.map((row, index) => <text key={row.month} x={x(index)} y={height - 10} textAnchor="middle" className="pnl-dashboard__trend-axis">{row.month}월</text>)}
      </svg>
    </div>}
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
    <div className="pnl-dashboard__section-header"><h3>{title}</h3><span>금액 단위: 백만원</span></div>
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
    <section className="pnl-dashboard__summary" aria-labelledby="pnl-summary-title">
      <div className="pnl-dashboard__section-heading"><h2 id="pnl-summary-title">핵심 손익 요약</h2><span className="pnl-dashboard__unit-note">금액 단위: 백만원</span></div>
      <div className="pnl-dashboard__kpi-grid">
        <article className="pnl-dashboard__kpi">
          <p>매출액</p>
          <strong>{money(kpis.revenue.period.comparison)}</strong>
          <span>{identity.comparison_model_name} · 기준 {money(kpis.revenue.period.baseline)}</span>
          <small className="pnl-dashboard__kpi-pill">
            <span>기준 대비</span> <NeutralAmount value={kpis.revenue.period.delta} />
          </small>
        </article>
        <article className="pnl-dashboard__kpi pnl-dashboard__kpi--primary">
          <p>영업이익</p>
          <strong>{money(kpis.operating_profit.period.comparison)}</strong>
          <span>{identity.comparison_model_name} · 기준 {money(kpis.operating_profit.period.baseline)}</span>
          <small className={`pnl-dashboard__kpi-pill pnl-dashboard__kpi-pill--${tone(kpis.operating_profit.period.delta)}`}>
            <span>{kpis.operating_profit.period.delta > 0 ? '↑' : kpis.operating_profit.period.delta < 0 ? '↓' : '—'}</span>
            <span>기준 대비</span> <ToneValue value={kpis.operating_profit.period.delta} signed />
          </small>
        </article>
        <article className="pnl-dashboard__kpi pnl-dashboard__kpi--unavailable">
          <p>조정 영업이익</p>
          <strong>미제공</strong>
          <span>Reporting Backend Contract 필요</span>
          <small className="pnl-dashboard__kpi-pill">
            Production fallback 없음
          </small>
        </article>
      </div>
    </section>

    <section className="pnl-dashboard__trend-section" aria-labelledby="pnl-trend-title">
      <div className="pnl-dashboard__section-heading">
        <div>
          <p className="pnl-dashboard__eyebrow">MONTHLY TREND</p>
          <h2 id="pnl-trend-title">월별 추세</h2>
        </div>
        <div className="pnl-dashboard__legend">
          <span><i className="pnl-dashboard__legend-dot pnl-dashboard__legend-dot--plan" />기준 모형</span>
          {scenarioTypes.map((scenario) => <span key={scenario}><i className={`pnl-dashboard__legend-dot pnl-dashboard__legend-dot--${scenario === '실적' ? 'actual' : scenario === '추정' ? 'forecast' : 'plan'}`} />{scenario}</span>)}
          {hasUnclassifiedScenario && <span><i className="pnl-dashboard__legend-dot pnl-dashboard__legend-dot--neutral" />미지정</span>}
        </div>
      </div>
      <div className="pnl-dashboard__trend-grid">
        <RevenueTrendCard rows={dashboard.monthly_series} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} />
        <CompositeProfitMarginTrendCard rows={dashboard.monthly_series} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} />
      </div>
    </section>

    <section className="pnl-dashboard__details" aria-labelledby="pnl-detail-title">
      <div className="pnl-dashboard__section-heading"><h2 id="pnl-detail-title">상세 손익</h2><span className="pnl-dashboard__unit-note">금액 단위: 백만원</span></div>
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
      <div id="pnl-dashboard-tabpanel-pnl" role="tabpanel" hidden={tab !== 'pnl'}>{tab === 'pnl' && <>
        <FinancialLinesTable title="손익계산서" rows={dashboard.pnl_statement} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} />
        <section className="pnl-dashboard__factors" aria-labelledby="pnl-factors-title">
          <div className="pnl-dashboard__section-heading"><h3 id="pnl-factors-title">주요 손익 변동요인</h3><span className="pnl-dashboard__unit-note">Backend 제공 순서</span></div>
          <div className="pnl-dashboard__factor-grid">{dashboard.key_facts.effects.map((effect) => <div className="pnl-dashboard__factor" key={effect.code}><span>{effect.label}</span><ToneValue value={effect.profit_effect} signed /></div>)}<div className="pnl-dashboard__factor pnl-dashboard__factor--residual"><span>기타 요인</span><ToneValue value={dashboard.key_facts.residual} signed /></div></div>
        </section>
      </>}</div>
      <div id="pnl-dashboard-tabpanel-manufacturing" role="tabpanel" hidden={tab !== 'manufacturing'}>{tab === 'manufacturing' && <section className="pnl-dashboard__section-card"><div className="pnl-dashboard__section-header"><h3>제조원가</h3><span>환율 단위: {dashboard.manufacturing.material_components.jpy_fx_unit}</span></div><FinancialLinesTable title="제조원가 구성" rows={dashboard.manufacturing.cost_lines} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} embedded /><div className="pnl-dashboard__subsection"><h4>원재료 구성</h4><div className="pnl-dashboard__material-grid"><span>비직물 가격 (환율 제외)<strong>{nullableMoney(dashboard.manufacturing.material_components.nonwoven_price_ex_fx)}</strong></span><span>비직물 JPY<strong>{nullableMoney(dashboard.manufacturing.material_components.nonwoven_jpy)}</strong></span><span>비직물 외 재료<strong>{nullableMoney(dashboard.manufacturing.material_components.materials_ex_nonwoven)}</strong></span><span>합계<strong>{nullableMoney(dashboard.manufacturing.material_components.total)}</strong></span></div></div><div className="pnl-dashboard__subsection"><h4>제조원가 계정</h4><AccountTable rows={dashboard.manufacturing.accounts} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} /></div></section>}</div>
      <div id="pnl-dashboard-tabpanel-sga" role="tabpanel" hidden={tab !== 'sga'}>{tab === 'sga' && <section className="pnl-dashboard__section-card"><div className="pnl-dashboard__section-header"><h3>판매관리비</h3><span>계정별 비교</span></div><AccountTable rows={dashboard.sga.accounts} baselineName={identity.baseline_model_name} comparisonName={identity.comparison_model_name} /></section>}</div>
      <div id="pnl-dashboard-tabpanel-groups" role="tabpanel" hidden={tab !== 'groups'}>{tab === 'groups' && <ProductGroupTable dashboard={dashboard} />}</div>
    </section>

  </div>;
}

import { Award, BarChart2, DollarSign, Table, TrendingUp } from 'lucide-react';
import { useState } from 'react';
import type { PnlMonthlyDataRow, PnlMonthlyTrendSlot } from '../../types/pnlReporting';

type ProfitMode = 'OP_PROFIT' | 'ADJ_OP_PROFIT' | 'DATA_TABLE';

interface MonthlyTrendChartProps {
  data: PnlMonthlyTrendSlot[];
  dataRows: PnlMonthlyDataRow[];
}

const SVG_WIDTH = 920;
const LEFT = 58;
const RIGHT = 40;
const BAR_WIDTH = 18;
const BAR_GAP = 4;
const GROUP_WIDTH = BAR_WIDTH * 2 + BAR_GAP;
const WON_PER_MILLION = 1_000_000;

function hasGeometryValue(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function maxGeometryValue(values: Array<number | null>): number {
  const available = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  return available.length ? Math.max(...available.map((value) => Math.abs(value)), 1) : 1;
}

function barGeometry(value: number, maximum: number, tierBottom: number, tierHeight: number) {
  const height = Math.max((Math.abs(value) / maximum) * tierHeight, 2);
  return { height, y: tierBottom - height };
}

export function MonthlyTrendChart({ data, dataRows }: MonthlyTrendChartProps) {
  const [profitMode, setProfitMode] = useState<ProfitMode>('OP_PROFIT');
  const columnWidth = (SVG_WIDTH - LEFT - RIGHT) / Math.max(data.length, 1);
  const revenueMaximum = Math.max(maxGeometryValue(data.flatMap((slot) => [slot.planRevenue, slot.actualRevenue])), 12500 * WON_PER_MILLION) * 1.22;
  const profitMaximum = Math.max(maxGeometryValue(data.flatMap((slot) => profitMode === 'ADJ_OP_PROFIT'
    ? [slot.planAdjustedOperatingProfit, slot.actualAdjustedOperatingProfit]
    : [slot.planOperatingProfit, slot.actualOperatingProfit])), (profitMode === 'ADJ_OP_PROFIT' ? 1430 : 1250) * WON_PER_MILLION) * 1.25;

  const revenueTop = 24;
  const revenueHeight = 135;
  const revenueBottom = 159;
  const profitTop = 95;
  const profitHeight = 135;
  const profitBottom = 230;
  const marginTop = 18;
  const marginHeight = 52;
  const marginMaximum = 18;

  const marginPoint = (value: number) => marginTop + marginHeight * (1 - Math.max(0, Math.min(value, marginMaximum)) / marginMaximum);
  const actualMarginPoints = data.flatMap((slot, index) => {
    if (!slot.actualAvailable) return [];
    const value = profitMode === 'ADJ_OP_PROFIT' ? slot.actualAdjustedOperatingMargin : slot.actualOperatingMargin;
    if (!hasGeometryValue(value)) return [];
    return [{ slot, value, x: LEFT + index * columnWidth + columnWidth / 2, y: marginPoint(value) }];
  });
  const marginPath = actualMarginPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
  const lastActualMarginPeriod = actualMarginPoints[actualMarginPoints.length - 1]?.slot.periodKey;

  return <section className="pnl-report__trends" aria-label="월별 손익 추이">
    <article className="pnl-report__chart-card" data-testid="revenue-trend-card">
      <header className="pnl-report__chart-header">
        <div className="pnl-report__chart-title-wrap">
          <h2 className="pnl-report__chart-title"><DollarSign size={16} color="#2563eb" />월별 매출액 추이</h2>
          <span className="pnl-report__unit-tag">단위: 금액 (백만원)</span>
        </div>
        <div className="pnl-report__legend" aria-label="매출액 범례">
          <span><i className="pnl-report__legend-box pnl-report__legend-box--plan" />계획</span>
          <span><i className="pnl-report__legend-box pnl-report__legend-box--revenue" />실적</span>
        </div>
      </header>
      <div className="pnl-report__chart-scroll">
        <svg className="pnl-report__trend-svg" viewBox="0 0 920 195" role="img" aria-label="월별 매출액 계획 실적 막대 차트">
          <defs>
            <linearGradient id="pnl-revenue-actual" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" /><stop offset="100%" stopColor="#1d4ed8" /></linearGradient>
            <linearGradient id="pnl-revenue-plan" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#e2e8f0" /><stop offset="100%" stopColor="#cbd5e1" /></linearGradient>
          </defs>
          {[0, .33, .66, 1].map((ratio) => {
            const y = revenueTop + revenueHeight * (1 - ratio);
            const label = Math.round((revenueMaximum * ratio) / WON_PER_MILLION / 1000) * 1000;
            return <g key={ratio}><line x1={LEFT} y1={y} x2={SVG_WIDTH - RIGHT} y2={y} stroke="#f1f5f9" strokeWidth="1" /><text data-axis-label="amount" x={LEFT - 8} y={y + 3.5} textAnchor="end" fontSize="11" fill="#94a3b8">{label.toLocaleString()}</text></g>;
          })}
          <line x1={LEFT} y1={revenueBottom} x2={SVG_WIDTH - RIGHT} y2={revenueBottom} stroke="#cbd5e1" strokeWidth="1" />
          {data.map((slot, index) => {
            const x = LEFT + index * columnWidth;
            const groupStart = x + (columnWidth - GROUP_WIDTH) / 2;
            const plan = hasGeometryValue(slot.planRevenue) ? barGeometry(slot.planRevenue, revenueMaximum, revenueBottom, revenueHeight) : null;
            const actual = slot.actualAvailable && hasGeometryValue(slot.actualRevenue) ? barGeometry(slot.actualRevenue, revenueMaximum, revenueBottom, revenueHeight) : null;
            return <g key={slot.periodKey} data-period-key={slot.periodKey} data-actual-available={slot.actualAvailable ? 'true' : 'false'}>
              {plan && <rect data-series="plan" x={groupStart} y={plan.y} width={BAR_WIDTH} height={plan.height} fill="url(#pnl-revenue-plan)" stroke="#94a3b8" strokeWidth=".6" rx="2" />}
              {actual && <>
                <rect data-series="actual" x={groupStart + BAR_WIDTH + BAR_GAP} y={actual.y} width={BAR_WIDTH} height={actual.height} fill="url(#pnl-revenue-actual)" stroke="#1d4ed8" strokeWidth=".6" rx="2" />
                {slot.actualRevenueText && <text x={groupStart + BAR_WIDTH + BAR_GAP + BAR_WIDTH / 2} y={actual.y - 5} textAnchor="middle" fontSize="11" fontWeight="700" fill="#1d4ed8">{slot.actualRevenueText}</text>}
              </>}
              <text data-axis-label="month" x={x + columnWidth / 2} y={revenueBottom + 17} textAnchor="middle" fontSize="11.5" fontWeight="600" fill="#475569">{slot.label}</text>
            </g>;
          })}
        </svg>
      </div>
    </article>

    <article className="pnl-report__chart-card" data-testid="profit-trend-card">
      <header className="pnl-report__chart-header">
        <div className="pnl-report__chart-title-wrap">
          <h2 className="pnl-report__chart-title"><TrendingUp size={16} color="#ea580c" />월별 영업이익 추이</h2>
          <span className="pnl-report__unit-tag">단위: 금액 (백만원), 비율 (%)</span>
        </div>
        <div className="pnl-report__chart-actions">
          {profitMode !== 'DATA_TABLE' && <div className="pnl-report__legend" aria-label="영업이익 범례">
            <span><i className="pnl-report__legend-box pnl-report__legend-box--plan" />계획</span>
            <span><i className={`pnl-report__legend-box ${profitMode === 'ADJ_OP_PROFIT' ? 'pnl-report__legend-box--adjusted' : 'pnl-report__legend-box--profit'}`} />실적</span>
            <span><i className={`pnl-report__legend-line ${profitMode === 'ADJ_OP_PROFIT' ? 'pnl-report__legend-line--adjusted' : ''}`} />이익률</span>
          </div>}
          <div className="pnl-report__segmented" role="group" aria-label="영업이익 추이 보기 방식">
            <button type="button" className={profitMode === 'OP_PROFIT' ? 'active' : ''} onClick={() => setProfitMode('OP_PROFIT')}><BarChart2 size={12} />영업이익</button>
            <button type="button" className={profitMode === 'ADJ_OP_PROFIT' ? 'active' : ''} onClick={() => setProfitMode('ADJ_OP_PROFIT')}><Award size={12} />조정 영업이익</button>
            <button type="button" className={profitMode === 'DATA_TABLE' ? 'active' : ''} onClick={() => setProfitMode('DATA_TABLE')}><Table size={12} />월별 데이터표</button>
          </div>
        </div>
      </header>
      {profitMode === 'DATA_TABLE' ? <div className="pnl-report__chart-scroll">
        <table className="pnl-report__financial-table pnl-report__monthly-table" data-column-count={data.length + 1}>
          <thead><tr><th>손익 지표</th>{data.map((slot) => <th key={slot.periodKey}>{slot.label}</th>)}</tr></thead>
          <tbody>{dataRows.map((row) => <tr key={row.key} data-tone={row.tone}><td>{row.label}</td>{data.map((slot, index) => <td className="pnl-report__tabular" key={slot.periodKey}>{row.cells[index]?.text ?? '—'}</td>)}</tr>)}</tbody>
        </table>
      </div> : <div className="pnl-report__chart-scroll">
        <svg className="pnl-report__trend-svg" viewBox="0 0 920 275" role="img" aria-label="월별 영업이익 계획 실적 막대와 실적 이익률 복합 차트">
          <defs>
            <linearGradient id="pnl-profit-plan" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#e2e8f0" /><stop offset="100%" stopColor="#cbd5e1" /></linearGradient>
            <linearGradient id="pnl-profit-actual" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#fb923c" /><stop offset="100%" stopColor="#ea580c" /></linearGradient>
            <linearGradient id="pnl-profit-adjusted" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2dd4bf" /><stop offset="100%" stopColor="#0d9488" /></linearGradient>
          </defs>
          {marginPath && <path data-series="actual-margin" data-last-period-key={lastActualMarginPeriod} d={marginPath} fill="none" stroke={profitMode === 'ADJ_OP_PROFIT' ? '#0d9488' : '#ea580c'} strokeWidth="2.2" />}
          {actualMarginPoints.map((point) => <g key={point.slot.periodKey}>
            <circle data-series="actual-margin-point" data-period-key={point.slot.periodKey} cx={point.x} cy={point.y} r="3.5" fill="#fff" stroke={profitMode === 'ADJ_OP_PROFIT' ? '#0d9488' : '#ea580c'} strokeWidth="2" />
            <text x={point.x} y={point.y - 5.5} textAnchor="middle" fontSize="11" fontWeight="800" fill={profitMode === 'ADJ_OP_PROFIT' ? '#0f766e' : '#c2410c'}>{profitMode === 'ADJ_OP_PROFIT' ? point.slot.actualAdjustedOperatingMarginText : point.slot.actualOperatingMarginText}</text>
          </g>)}
          {[0, .33, .66, 1].map((ratio) => {
            const y = profitTop + profitHeight * (1 - ratio);
            const label = Math.round((profitMaximum * ratio) / WON_PER_MILLION / 100) * 100;
            return <g key={ratio}><line x1={LEFT} y1={y} x2={SVG_WIDTH - RIGHT} y2={y} stroke="#f1f5f9" strokeWidth="1" /><text data-axis-label="amount" x={LEFT - 8} y={y + 3.5} textAnchor="end" fontSize="11" fill="#94a3b8">{label.toLocaleString()}</text></g>;
          })}
          <line x1={LEFT} y1={profitBottom} x2={SVG_WIDTH - RIGHT} y2={profitBottom} stroke="#cbd5e1" strokeWidth="1" />
          {data.map((slot, index) => {
            const x = LEFT + index * columnWidth;
            const planValue = profitMode === 'ADJ_OP_PROFIT' ? slot.planAdjustedOperatingProfit : slot.planOperatingProfit;
            const actualValue = profitMode === 'ADJ_OP_PROFIT' ? slot.actualAdjustedOperatingProfit : slot.actualOperatingProfit;
            const actualText = profitMode === 'ADJ_OP_PROFIT' ? slot.actualAdjustedOperatingProfitText : slot.actualOperatingProfitText;
            const groupStart = x + (columnWidth - GROUP_WIDTH) / 2;
            const plan = hasGeometryValue(planValue) ? barGeometry(planValue, profitMaximum, profitBottom, profitHeight) : null;
            const actual = slot.actualAvailable && hasGeometryValue(actualValue) ? barGeometry(actualValue, profitMaximum, profitBottom, profitHeight) : null;
            return <g key={slot.periodKey} data-period-key={slot.periodKey} data-actual-available={slot.actualAvailable ? 'true' : 'false'}>
              {plan && <rect data-series="plan" x={groupStart} y={plan.y} width={BAR_WIDTH} height={plan.height} fill="url(#pnl-profit-plan)" stroke="#94a3b8" strokeWidth=".6" rx="2" />}
              {actual && <>
                <rect data-series="actual" x={groupStart + BAR_WIDTH + BAR_GAP} y={actual.y} width={BAR_WIDTH} height={actual.height} fill={profitMode === 'ADJ_OP_PROFIT' ? 'url(#pnl-profit-adjusted)' : 'url(#pnl-profit-actual)'} stroke={profitMode === 'ADJ_OP_PROFIT' ? '#0f766e' : '#c2410c'} strokeWidth=".6" rx="2" />
                {actualText && <text x={groupStart + BAR_WIDTH + BAR_GAP + BAR_WIDTH / 2} y={actual.y - 5} textAnchor="middle" fontSize="11" fontWeight="700" fill={profitMode === 'ADJ_OP_PROFIT' ? '#0f766e' : '#c2410c'}>{actualText}</text>}
              </>}
              <text data-axis-label="month" x={x + columnWidth / 2} y={profitBottom + 17} textAnchor="middle" fontSize="11.5" fontWeight="600" fill="#475569">{slot.label}</text>
            </g>;
          })}
        </svg>
      </div>}
    </article>
  </section>;
}

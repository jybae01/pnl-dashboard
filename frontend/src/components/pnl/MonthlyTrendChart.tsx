import React, { useState } from 'react';
import { MonthlyTrendItem } from '../../types/pnl';
import { TrendingUp, BarChart2, DollarSign, Award, Table } from 'lucide-react';

interface MonthlyTrendChartProps {
  data: MonthlyTrendItem[];
  selectedMonth?: string;
  onSelectMonth?: (month: string) => void;
}

type ProfitViewMode = 'OP_PROFIT' | 'ADJ_OP_PROFIT' | 'DATA_TABLE';

export const MonthlyTrendChart: React.FC<MonthlyTrendChartProps> = ({
  data,
  selectedMonth,
  onSelectMonth,
}) => {
  const [profitMode, setProfitMode] = useState<ProfitViewMode>('OP_PROFIT');

  // Calculate maximum values with generous headroom (+25%) so bar top labels never touch top boundaries
  const rawMaxRevenue = Math.max(...data.map(d => Math.max(d.planRevenue, d.actualRevenue || 0, d.forecastRevenue || 0)), 12500);
  const maxRevenue = rawMaxRevenue * 1.22;

  const rawMaxOp = Math.max(...data.map(d => Math.max(d.planOpProfit, d.actualOpProfit || 0, d.forecastOpProfit || 0)), 1250);
  const maxOpProfit = rawMaxOp * 1.25;

  const rawMaxAdjOp = Math.max(...data.map(d => Math.max(d.planAdjOpProfit, d.actualAdjOpProfit || 0, d.forecastAdjOpProfit || 0)), 1430);
  const maxAdjOpProfit = rawMaxAdjOp * 1.25;

  const svgWidth = 920;
  const paddingLeft = 58;
  const paddingRight = 40;
  const chartWidth = svgWidth - paddingLeft - paddingRight;
  const colWidth = chartWidth / data.length;

  // 1. Revenue Chart Dimensions (Generous headroom)
  const revSvgHeight = 195;
  const revTierTop = 24;
  const revTierHeight = 135;
  const revTierBottom = revTierTop + revTierHeight; // 159

  // 2. Profit Chart Dimensions (4 Distinct Layers / Generous Headroom)
  // Layer 1: Section Header (y: 6 ~ 22)
  // Layer 2: Margin Line Chart (% scale 0% ~ 18%) (y: 30 ~ 95)
  // Layer 3: Divider & Sub-Title (y: 104 ~ 124)
  // Layer 4: Amount Bar Chart & Labels (y: 140 ~ 275)
  const profitSvgHeight = 310;

  const marginTierTop = 36;
  const marginTierHeight = 56;
  const maxMarginScale = 18; // 0% ~ 18% scale gives ample top headroom for ~13.5% numbers

  const dividerY = 106;
  const amountSubtitleY = 122;

  const bottomTierTop = 138;
  const bottomTierHeight = 130;
  const bottomTierBottom = bottomTierTop + bottomTierHeight; // 268

  const getYMargin = (margin: number) => {
    const clamped = Math.max(0, Math.min(margin, maxMarginScale));
    return marginTierTop + marginTierHeight * (1 - clamped / maxMarginScale);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 16 }}>
      {/* ========================================================================= */}
      {/* [첫 번째 영역] 월별 매출액 추이 (항상 표시)                                  */}
      {/* ========================================================================= */}
      <div className="chart-card" style={{ padding: '12px 14px' }}>
        <div className="chart-header" style={{ marginBottom: 6 }}>
          <div className="chart-title-wrap">
            <span className="chart-title" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '13px' }}>
              <DollarSign size={15} color="#2563eb" />
              월별 매출액 추이
            </span>
            <span className="unit-tag">단위: 금액 (백만원)</span>
          </div>

          <div className="chart-legend">
            <div className="legend-item">
              <span className="legend-color-box" style={{ backgroundColor: '#cbd5e1', border: '1px solid #94a3b8' }} />
              <span>계획 매출</span>
            </div>
            <div className="legend-item">
              <span className="legend-color-box" style={{ backgroundColor: '#2563eb', border: '1px solid #1d4ed8' }} />
              <span>실적/추정 매출</span>
            </div>
          </div>
        </div>

        <div style={{ overflowX: 'auto', width: '100%' }}>
          <svg viewBox={`0 0 ${svgWidth} ${revSvgHeight}`} style={{ width: '100%', minWidth: '760px', height: '195px' }}>
            <defs>
              <linearGradient id="rev-blue-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" />
                <stop offset="100%" stopColor="#1d4ed8" />
              </linearGradient>
              <linearGradient id="rev-plan-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#e2e8f0" />
                <stop offset="100%" stopColor="#cbd5e1" />
              </linearGradient>
            </defs>

            {/* Y-Axis Gridlines */}
            {[0, 0.33, 0.66, 1.0].map((ratio, i) => {
              const y = revTierTop + revTierHeight * (1 - ratio);
              const stepVal = Math.round((maxRevenue * ratio) / 1000) * 1000;
              return (
                <g key={`rev-grid-${i}`}>
                  <line x1={paddingLeft} y1={y} x2={svgWidth - paddingRight} y2={y} stroke="#f1f5f9" strokeWidth="1" />
                  <text x={paddingLeft - 8} y={y + 3.5} textAnchor="end" fontSize="9" fill="#94a3b8" className="tabular-nums">
                    {stepVal.toLocaleString()}
                  </text>
                </g>
              );
            })}

            {/* Zero Baseline */}
            <line
              x1={paddingLeft}
              y1={revTierBottom}
              x2={svgWidth - paddingRight}
              y2={revTierBottom}
              stroke="#cbd5e1"
              strokeWidth="1"
            />

            {/* Revenue Bars */}
            {data.map((item, idx) => {
              const x = paddingLeft + idx * colWidth;
              const barW = Math.max(colWidth * 0.34, 10);

              const planH = Math.max((item.planRevenue / maxRevenue) * revTierHeight, 2);
              const planY = revTierBottom - planH;

              const actualVal = item.isActual ? item.actualRevenue || 0 : item.forecastRevenue || 0;
              const actualH = Math.max((actualVal / maxRevenue) * revTierHeight, 2);
              const actualY = revTierBottom - actualH;

              return (
                <g
                  key={`rev-${item.month}`}
                  style={{ cursor: onSelectMonth ? 'pointer' : 'default' }}
                  onClick={() => onSelectMonth && onSelectMonth(item.month)}
                >
                  {/* Plan Bar */}
                  <rect
                    x={x + colWidth * 0.14}
                    y={planY}
                    width={barW}
                    height={planH}
                    fill="url(#rev-plan-grad)"
                    stroke="#94a3b8"
                    strokeWidth="0.6"
                    rx="2"
                  />

                  {/* Actual Bar */}
                  <rect
                    x={x + colWidth * 0.14 + barW + 2}
                    y={actualY}
                    width={barW}
                    height={actualH}
                    fill="url(#rev-blue-grad)"
                    stroke="#1d4ed8"
                    strokeWidth="0.6"
                    rx="2"
                  />

                  {/* Amount Label with plenty of headroom */}
                  <text
                    x={x + colWidth * 0.14 + barW + 2 + barW / 2}
                    y={actualY - 5}
                    textAnchor="middle"
                    fontSize="9.5"
                    fontWeight="700"
                    fill="#1e3a8a"
                    className="tabular-nums"
                  >
                    {actualVal.toLocaleString()}
                  </text>

                  {/* Month Label */}
                  <text
                    x={x + colWidth / 2}
                    y={revTierBottom + 17}
                    textAnchor="middle"
                    fontSize="9.5"
                    fontWeight="600"
                    fill="#475569"
                  >
                    {item.monthLabel}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* [두 번째 영역] 월별 손익 추이 (4구역 분리 및 넉넉한 텍스트 여백 확보)             */}
      {/* ========================================================================= */}
      <div className="chart-card" style={{ padding: '12px 14px' }}>
        {/* Header Toolbar: Fixed Left Title & Fixed Submenu */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          marginBottom: 10,
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: 8,
        }}>
          {/* Top Row: Title & Legend/Unit */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
              <TrendingUp size={15} color="#2563eb" />
              월별 손익 추이
            </div>

            {profitMode !== 'DATA_TABLE' ? (
              <div className="chart-legend">
                <div className="legend-item">
                  <span className="legend-color-box" style={{ backgroundColor: '#cbd5e1', border: '1px solid #94a3b8' }} />
                  <span>계획</span>
                </div>
                <div className="legend-item">
                  <span
                    className="legend-color-box"
                    style={{
                      backgroundColor: profitMode === 'ADJ_OP_PROFIT' ? '#ea580c' : '#2563eb',
                      border: `1px solid ${profitMode === 'ADJ_OP_PROFIT' ? '#c2410c' : '#1d4ed8'}`
                    }}
                  />
                  <span>실적/추정</span>
                </div>
                {profitMode === 'OP_PROFIT' && (
                  <div className="legend-item">
                    <span style={{ width: 14, height: 3, backgroundColor: '#2563eb', borderRadius: 2, display: 'inline-block' }} />
                    <span style={{ fontWeight: 700, color: '#1e40af' }}>영업이익률 (%)</span>
                  </div>
                )}
                {profitMode === 'ADJ_OP_PROFIT' && (
                  <div className="legend-item">
                    <span style={{ width: 14, height: 3, backgroundColor: '#ea580c', borderRadius: 2, display: 'inline-block' }} />
                    <span style={{ fontWeight: 700, color: '#c2410c' }}>조정 이익률 (%)</span>
                  </div>
                )}
              </div>
            ) : (
              <span className="unit-tag" style={{ fontWeight: 600, color: '#475569' }}>
                (단위: 백만원, %)
              </span>
            )}
          </div>

          {/* Submenu Buttons: Always Fixed on the Left right below title */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-start' }}>
            <div className="segmented-control">
              <button
                type="button"
                className={`segmented-btn ${profitMode === 'OP_PROFIT' ? 'active' : ''}`}
                onClick={() => setProfitMode('OP_PROFIT')}
              >
                <BarChart2 size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
                영업이익
              </button>
              <button
                type="button"
                className={`segmented-btn ${profitMode === 'ADJ_OP_PROFIT' ? 'active' : ''}`}
                onClick={() => setProfitMode('ADJ_OP_PROFIT')}
              >
                <Award size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
                조정 영업이익
              </button>
              <button
                type="button"
                className={`segmented-btn ${profitMode === 'DATA_TABLE' ? 'active' : ''}`}
                onClick={() => setProfitMode('DATA_TABLE')}
              >
                <Table size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
                월별 데이터표
              </button>
            </div>
          </div>
        </div>

        {profitMode !== 'DATA_TABLE' ? (
          /* 4-Layer Split Chart with Dedicated Headroom */
          <div style={{ overflowX: 'auto', width: '100%' }}>
            <svg viewBox={`0 0 ${svgWidth} ${profitSvgHeight}`} style={{ width: '100%', minWidth: '760px', height: '310px' }}>
              <defs>
                <linearGradient id="profit-blue-grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" />
                  <stop offset="100%" stopColor="#1d4ed8" />
                </linearGradient>
                <linearGradient id="profit-orange-grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#fb923c" />
                  <stop offset="100%" stopColor="#ea580c" />
                </linearGradient>
                <linearGradient id="profit-plan-grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#e2e8f0" />
                  <stop offset="100%" stopColor="#cbd5e1" />
                </linearGradient>
              </defs>

              {/* ------------------------------------------------------------- */}
              {/* LAYER 1 & 2: Top Margin Area (Title & Line Chart)             */}
              {/* ------------------------------------------------------------- */}
              {/* Background card for margin section */}
              <rect
                x={paddingLeft}
                y={6}
                width={chartWidth}
                height={88}
                fill="#f8fafc"
                rx="4"
              />

              {/* Layer 1: Dedicated Section Header (y: 18px) */}
              <text
                x={paddingLeft + 8}
                y={20}
                fontSize="10.5"
                fontWeight="700"
                fill={profitMode === 'ADJ_OP_PROFIT' ? '#c2410c' : '#1e40af'}
              >
                {profitMode === 'ADJ_OP_PROFIT' ? '▲ 월별 조정 영업이익률 (%)' : '▲ 월별 영업이익률 (%)'}
              </text>

              {/* Layer 2: % Scale Gridlines (5%, 10%, 15%) */}
              {[5, 10, 15].map(pct => {
                const y = getYMargin(pct);
                return (
                  <g key={`margin-grid-${pct}`}>
                    <line x1={paddingLeft} y1={y} x2={svgWidth - paddingRight} y2={y} stroke="#e2e8f0" strokeWidth="0.8" />
                    <text x={paddingLeft - 6} y={y + 3} textAnchor="end" fontSize="8.5" fill="#94a3b8" className="tabular-nums">
                      {pct}%
                    </text>
                  </g>
                );
              })}

              {/* Margin Path Line */}
              <path
                d={data.map((item, idx) => {
                  const x = paddingLeft + idx * colWidth + colWidth / 2;
                  const margin = item.isActual
                    ? (profitMode === 'OP_PROFIT' ? item.actualOpMargin || 0 : item.actualAdjOpMargin || 0)
                    : (profitMode === 'OP_PROFIT' ? item.forecastOpMargin || 0 : item.forecastAdjOpMargin || 0);
                  const y = getYMargin(margin);
                  return `${idx === 0 ? 'M' : 'L'} ${x} ${y}`;
                }).join(' ')}
                fill="none"
                stroke={profitMode === 'ADJ_OP_PROFIT' ? '#ea580c' : '#2563eb'}
                strokeWidth="2.2"
              />

              {/* Margin Points & Labels (% labels have safe headroom below header y:20) */}
              {data.map((item, idx) => {
                const x = paddingLeft + idx * colWidth + colWidth / 2;
                const margin = item.isActual
                  ? (profitMode === 'OP_PROFIT' ? item.actualOpMargin || 0 : item.actualAdjOpMargin || 0)
                  : (profitMode === 'OP_PROFIT' ? item.forecastOpMargin || 0 : item.forecastAdjOpMargin || 0);
                const y = getYMargin(margin);

                return (
                  <g key={`profit-pt-${item.month}`}>
                    <circle
                      cx={x}
                      cy={y}
                      r="3.5"
                      fill="#ffffff"
                      stroke={profitMode === 'ADJ_OP_PROFIT' ? '#ea580c' : '#2563eb'}
                      strokeWidth="2"
                    />
                    <text
                      x={x}
                      y={y - 5.5}
                      textAnchor="middle"
                      fontSize="9.5"
                      fontWeight="800"
                      fill={profitMode === 'ADJ_OP_PROFIT' ? '#c2410c' : '#1e40af'}
                      className="tabular-nums"
                    >
                      {margin.toFixed(1)}%
                    </text>
                  </g>
                );
              })}

              {/* ------------------------------------------------------------- */}
              {/* LAYER 3: Middle Divider & Subtitle                            */}
              {/* ------------------------------------------------------------- */}
              <line
                x1={paddingLeft}
                y1={dividerY}
                x2={svgWidth - paddingRight}
                y2={dividerY}
                stroke="#cbd5e1"
                strokeWidth="1.2"
                strokeDasharray="4 4"
              />
              <text
                x={paddingLeft + 6}
                y={amountSubtitleY}
                fontSize="10"
                fontWeight="700"
                fill="#475569"
              >
                ▼ 월별 금액 (단위: 백만원)
              </text>

              {/* ------------------------------------------------------------- */}
              {/* LAYER 4: Bottom Bar Chart & Amount Labels                     */}
              {/* ------------------------------------------------------------- */}
              {[0, 0.33, 0.66, 1.0].map((ratio, i) => {
                const currentMax = profitMode === 'OP_PROFIT' ? maxOpProfit : maxAdjOpProfit;
                const stepVal = Math.round((currentMax * ratio) / 100) * 100;
                const y = bottomTierTop + bottomTierHeight * (1 - ratio);
                return (
                  <g key={`profit-grid-${i}`}>
                    <line x1={paddingLeft} y1={y} x2={svgWidth - paddingRight} y2={y} stroke="#f1f5f9" strokeWidth="1" />
                    <text x={paddingLeft - 6} y={y + 3.5} textAnchor="end" fontSize="9" fill="#94a3b8" className="tabular-nums">
                      {stepVal.toLocaleString()}
                    </text>
                  </g>
                );
              })}

              {/* Zero Baseline */}
              <line
                x1={paddingLeft}
                y1={bottomTierBottom}
                x2={svgWidth - paddingRight}
                y2={bottomTierBottom}
                stroke="#cbd5e1"
                strokeWidth="1"
              />

              {/* Bars */}
              {data.map((item, idx) => {
                const x = paddingLeft + idx * colWidth;
                const barW = Math.max(colWidth * 0.33, 9);
                const currentMax = profitMode === 'OP_PROFIT' ? maxOpProfit : maxAdjOpProfit;

                const planVal = profitMode === 'OP_PROFIT' ? item.planOpProfit : item.planAdjOpProfit;
                const planH = Math.max((planVal / currentMax) * bottomTierHeight, 2);
                const planY = bottomTierBottom - planH;

                const actualVal = item.isActual
                  ? (profitMode === 'OP_PROFIT' ? item.actualOpProfit || 0 : item.actualAdjOpProfit || 0)
                  : (profitMode === 'OP_PROFIT' ? item.forecastOpProfit || 0 : item.forecastAdjOpProfit || 0);
                const actualH = Math.max((actualVal / currentMax) * bottomTierHeight, 2);
                const actualY = bottomTierBottom - actualH;

                return (
                  <g
                    key={`profit-bar-${item.month}`}
                    style={{ cursor: onSelectMonth ? 'pointer' : 'default' }}
                    onClick={() => onSelectMonth && onSelectMonth(item.month)}
                  >
                    {/* Plan Bar */}
                    <rect
                      x={x + colWidth * 0.14}
                      y={planY}
                      width={barW}
                      height={planH}
                      fill="url(#profit-plan-grad)"
                      stroke="#94a3b8"
                      strokeWidth="0.6"
                      rx="2"
                    />

                    {/* Actual / Forecast Bar */}
                    <rect
                      x={x + colWidth * 0.14 + barW + 2}
                      y={actualY}
                      width={barW}
                      height={actualH}
                      fill={profitMode === 'ADJ_OP_PROFIT' ? 'url(#profit-orange-grad)' : 'url(#profit-blue-grad)'}
                      stroke={profitMode === 'ADJ_OP_PROFIT' ? '#c2410c' : '#1d4ed8'}
                      strokeWidth="0.6"
                      rx="2"
                    />

                    {/* Amount Label - with plenty of headroom below subtitle/divider */}
                    <text
                      x={x + colWidth * 0.14 + barW + 2 + barW / 2}
                      y={actualY - 5}
                      textAnchor="middle"
                      fontSize="9.5"
                      fontWeight="700"
                      fill={profitMode === 'ADJ_OP_PROFIT' ? '#c2410c' : '#1e3a8a'}
                      className="tabular-nums"
                    >
                      {actualVal.toLocaleString()}
                    </text>

                    {/* Month Label */}
                    <text
                      x={x + colWidth / 2}
                      y={bottomTierBottom + 17}
                      textAnchor="middle"
                      fontSize="10"
                      fontWeight="600"
                      fill="#475569"
                    >
                      {item.monthLabel}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        ) : (
          /* Monthly Numeric Matrix Table with Right-aligned Unit */
          <div style={{ overflowX: 'auto', maxHeight: '260px' }}>
            <table className="financial-table" style={{ fontSize: '11px' }}>
              <thead>
                <tr>
                  <th style={{ width: '16%' }}>손익 지표</th>
                  {data.map(d => (
                    <th key={d.month} className="text-right" style={{ width: '7%' }}>{d.monthLabel}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600 }}>매출액 계획</td>
                  {data.map(d => (
                    <td key={d.month} className="text-right tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      {d.planRevenue.toLocaleString()}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: 700, color: '#1e3a8a' }}>매출액 실적</td>
                  {data.map(d => (
                    <td key={d.month} className="text-right tabular-nums" style={{ fontWeight: 700, color: '#1e3a8a' }}>
                      {(d.actualRevenue || d.forecastRevenue || 0).toLocaleString()}
                    </td>
                  ))}
                </tr>
                <tr style={{ backgroundColor: '#f0fdf4' }}>
                  <td style={{ fontWeight: 600 }}>영업이익 계획</td>
                  {data.map(d => (
                    <td key={d.month} className="text-right tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      {d.planOpProfit.toLocaleString()}
                    </td>
                  ))}
                </tr>
                <tr style={{ backgroundColor: '#f0fdf4' }}>
                  <td style={{ fontWeight: 700, color: '#047857' }}>영업이익 실적</td>
                  {data.map(d => (
                    <td key={d.month} className="text-right tabular-nums" style={{ fontWeight: 700, color: '#047857' }}>
                      {(d.actualOpProfit || d.forecastOpProfit || 0).toLocaleString()}
                    </td>
                  ))}
                </tr>
                <tr style={{ backgroundColor: '#f0fdf4' }}>
                  <td style={{ color: '#047857', fontWeight: 600 }}>영업이익률</td>
                  {data.map(d => (
                    <td key={d.month} className="text-right tabular-nums" style={{ color: '#047857', fontWeight: 600 }}>
                      {(d.actualOpMargin || d.forecastOpMargin || 0).toFixed(1)}%
                    </td>
                  ))}
                </tr>
                <tr style={{ backgroundColor: '#fff7ed' }}>
                  <td style={{ fontWeight: 600 }}>조정 영업이익 계획</td>
                  {data.map(d => (
                    <td key={d.month} className="text-right tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      {d.planAdjOpProfit.toLocaleString()}
                    </td>
                  ))}
                </tr>
                <tr style={{ backgroundColor: '#fff7ed' }}>
                  <td style={{ fontWeight: 700, color: '#c2410c' }}>조정 영업이익 실적</td>
                  {data.map(d => (
                    <td key={d.month} className="text-right tabular-nums" style={{ fontWeight: 700, color: '#c2410c' }}>
                      {(d.actualAdjOpProfit || d.forecastAdjOpProfit || 0).toLocaleString()}
                    </td>
                  ))}
                </tr>
                <tr style={{ backgroundColor: '#fff7ed' }}>
                  <td style={{ color: '#c2410c', fontWeight: 600 }}>조정 영업이익률</td>
                  {data.map(d => (
                    <td key={d.month} className="text-right tabular-nums" style={{ color: '#c2410c', fontWeight: 600 }}>
                      {(d.actualAdjOpMargin || d.forecastAdjOpMargin || 0).toFixed(1)}%
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

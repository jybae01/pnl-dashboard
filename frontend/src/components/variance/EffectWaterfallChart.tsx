import React, { useState } from 'react';
import { WaterfallBarData } from '../../types/variance';
import { BarChart3 } from 'lucide-react';

interface EffectWaterfallChartProps {
  bars: WaterfallBarData[];
  selectedEffectId?: string;
  onSelectEffect?: (id: string) => void;
}

export const EffectWaterfallChart: React.FC<EffectWaterfallChartProps> = ({
  bars,
  selectedEffectId,
  onSelectEffect,
}) => {
  const [hoveredBar, setHoveredBar] = useState<WaterfallBarData | null>(null);

  // Dynamic scale with graceful padding
  const allValues = bars.flatMap(b => [b.startValue, b.endValue]);
  const minValue = Math.min(0, ...allValues);
  const maxValue = Math.max(...allValues) * 1.18;

  const svgWidth = 940;
  const svgHeight = 295;
  const paddingLeft = 65;
  const paddingRight = 35;
  const paddingTop = 38;
  const paddingBottom = 65;

  const chartWidth = svgWidth - paddingLeft - paddingRight;
  const chartHeight = svgHeight - paddingTop - paddingBottom;
  const colWidth = chartWidth / bars.length;
  const barWidth = Math.min(colWidth * 0.70, 44);

  const getY = (val: number) => {
    const range = maxValue - minValue;
    const ratio = (val - minValue) / range;
    return paddingTop + chartHeight * (1 - ratio);
  };

  return (
    <div className="chart-card" style={{ marginBottom: 16 }}>
      {/* Header */}
      <div className="chart-header">
        <div className="chart-title-wrap">
          <span className="chart-title" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '13px' }}>
            <BarChart3 size={15} color="#2563eb" />
            손익영향 Waterfall 분석
          </span>
          <span className="unit-tag">단위: 금액 (백만원) · 막대 클릭 시 하단 세부 내역 연동</span>
        </div>

        <div className="chart-legend">
          <div className="legend-item">
            <span className="legend-color-box" style={{ backgroundColor: '#1e3a8a', border: '1px solid #1e293b' }} />
            <span>기준(계획)</span>
          </div>
          <div className="legend-item">
            <span className="legend-color-box" style={{ backgroundColor: '#059669', border: '1px solid #047857' }} />
            <span>이익증가 (+)</span>
          </div>
          <div className="legend-item">
            <span className="legend-color-box" style={{ backgroundColor: '#e11d48', border: '1px solid #be123c' }} />
            <span>이익감소 (-)</span>
          </div>
          <div className="legend-item">
            <span className="legend-color-box" style={{ backgroundColor: '#0f172a', border: '1px solid #000000' }} />
            <span>결과(실적)</span>
          </div>
        </div>
      </div>

      {/* SVG Container */}
      <div className="waterfall-svg-container">
        <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="waterfall-svg" style={{ minWidth: '780px' }}>
          <defs>
            {/* Modern Financial Gradients */}
            <linearGradient id="grad-plan" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2563eb" />
              <stop offset="100%" stopColor="#1e3a8a" />
            </linearGradient>

            <linearGradient id="grad-actual" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1e293b" />
              <stop offset="100%" stopColor="#0f172a" />
            </linearGradient>

            <linearGradient id="grad-favorable" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" />
              <stop offset="100%" stopColor="#059669" />
            </linearGradient>

            <linearGradient id="grad-unfavorable" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f43f5e" />
              <stop offset="100%" stopColor="#e11d48" />
            </linearGradient>

            {/* Subtle Drop Shadow for Bar Highlights */}
            <filter id="bar-shadow" x="-8%" y="-8%" width="116%" height="116%">
              <feDropShadow dx="0" dy="2" stdDeviation="2" floodOpacity="0.12" />
            </filter>
          </defs>

          {/* Y Axis Gridlines */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((ratio, i) => {
            const val = minValue + (maxValue - minValue) * ratio;
            const y = getY(val);
            return (
              <g key={i}>
                <line x1={paddingLeft} y1={y} x2={svgWidth - paddingRight} y2={y} stroke="#f1f5f9" strokeWidth="1" />
                <text x={paddingLeft - 10} y={y + 3.5} textAnchor="end" fontSize="10" fontWeight="500" fill="#94a3b8" className="tabular-nums">
                  {Math.round(val).toLocaleString()}
                </text>
              </g>
            );
          })}

          {/* Zero baseline */}
          <line
            x1={paddingLeft}
            y1={getY(0)}
            x2={svgWidth - paddingRight}
            y2={getY(0)}
            stroke="#cbd5e1"
            strokeWidth="1.2"
          />

          {/* Waterfall Bars & Connectors */}
          {bars.map((bar, idx) => {
            const xCenter = paddingLeft + idx * colWidth + colWidth / 2;
            const x = xCenter - barWidth / 2;

            const yTop = getY(Math.max(bar.startValue, bar.endValue));
            const yBottom = getY(Math.min(bar.startValue, bar.endValue));
            const height = Math.max(yBottom - yTop, 3.5);

            const isSelected = selectedEffectId === bar.id;
            const isHovered = hoveredBar?.id === bar.id;

            // Connector line to next bar
            const nextBar = bars[idx + 1];
            let connectorLine = null;
            if (nextBar) {
              const nextXCenter = paddingLeft + (idx + 1) * colWidth + colWidth / 2;
              const nextX = nextXCenter - barWidth / 2;
              const connectorY = getY(bar.endValue);
              connectorLine = (
                <line
                  x1={x + barWidth}
                  y1={connectorY}
                  x2={nextX}
                  y2={connectorY}
                  stroke="#94a3b8"
                  strokeWidth="1.2"
                  strokeDasharray="3 3"
                />
              );
            }

            let barFill = 'url(#grad-plan)';
            let barStroke = '#1e3a8a';
            if (bar.isStart) {
              barFill = 'url(#grad-plan)';
              barStroke = '#1d4ed8';
            } else if (bar.isEnd) {
              barFill = 'url(#grad-actual)';
              barStroke = '#0f172a';
            } else if (bar.delta >= 0) {
              barFill = 'url(#grad-favorable)';
              barStroke = '#047857';
            } else {
              barFill = 'url(#grad-unfavorable)';
              barStroke = '#be123c';
            }

            return (
              <g
                key={bar.id}
                onMouseEnter={() => setHoveredBar(bar)}
                onMouseLeave={() => setHoveredBar(null)}
                onClick={() => onSelectEffect && onSelectEffect(bar.id)}
                style={{ cursor: 'pointer' }}
              >
                {connectorLine}

                {/* Bar Selection Highlight Ring */}
                {(isSelected || isHovered) && (
                  <rect
                    x={x - 3}
                    y={yTop - 3}
                    width={barWidth + 6}
                    height={height + 6}
                    fill="none"
                    stroke="#ff5f1f"
                    strokeWidth="2.5"
                    rx="4"
                  />
                )}

                {/* Main Bar with Rounded Corners & Subtle Stroke */}
                <rect
                  x={x}
                  y={yTop}
                  width={barWidth}
                  height={height}
                  fill={barFill}
                  stroke={barStroke}
                  strokeWidth="0.8"
                  rx="3"
                  filter={isHovered ? 'url(#bar-shadow)' : undefined}
                  opacity={isHovered ? 0.95 : 1}
                />

                {/* Top/Bottom Amount Label */}
                <text
                  x={xCenter}
                  y={bar.delta >= 0 ? yTop - 7 : yBottom + 14}
                  textAnchor="middle"
                  className="chart-text-val"
                  fontSize="11"
                  fontWeight="700"
                  fill={
                    bar.isTotal
                      ? '#0f172a'
                      : bar.delta >= 0
                      ? '#047857'
                      : '#be123c'
                  }
                >
                  {bar.isTotal
                    ? Math.round(bar.delta).toLocaleString()
                    : bar.delta > 0
                    ? `+${Math.round(bar.delta)}`
                    : Math.round(bar.delta)}
                </text>

                {/* X Axis Label */}
                <text
                  x={xCenter}
                  y={paddingTop + chartHeight + 19}
                  className="chart-text-label"
                  style={{
                    fontSize: '11px',
                    fontWeight: bar.isTotal || isSelected ? '700' : '600',
                    fill: isSelected ? '#ff5f1f' : '#334155'
                  }}
                >
                  {bar.name}
                </text>

                {/* Category Sublabel */}
                <text
                  x={xCenter}
                  y={paddingTop + chartHeight + 33}
                  className="chart-text-sublabel"
                  style={{ fontSize: '9.5px', fill: '#64748b' }}
                >
                  {bar.category === 'INTERNAL' ? '내부' : bar.category === 'EXTERNAL' ? '외부' : bar.category === 'COST' ? '비용' : ''}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Hover Info Tip */}
      {hoveredBar && (
        <div style={{
          marginTop: 6,
          padding: '6px 12px',
          backgroundColor: '#f8fafc',
          border: '1px solid #cbd5e1',
          borderLeft: '4px solid #ff5f1f',
          borderRadius: 'var(--radius-sm)',
          fontSize: '11.5px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div>
            <strong style={{ color: '#0f172a' }}>{hoveredBar.name}</strong>: {hoveredBar.isTotal ? `영업이익 ${hoveredBar.delta.toLocaleString()} 백만원` : `손익 영향 ${hoveredBar.delta > 0 ? '+' : ''}${hoveredBar.delta.toLocaleString()} 백만원`}
          </div>
          <span style={{ color: '#64748b' }}>클릭 시 하단 상세표 포커스</span>
        </div>
      )}
    </div>
  );
};

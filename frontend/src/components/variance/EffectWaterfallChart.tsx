import { useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { AnalysisWaterfallBar } from '../../integration/analysisPresentation';

interface EffectWaterfallChartProps {
  bars: AnalysisWaterfallBar[];
  selectedEffectId?: string;
  onSelectEffect?: (id: string) => void;
}

type BarTone = 'baseline' | 'comparison' | 'positive' | 'negative' | 'zero';

const BAR_COLORS: Record<BarTone, string> = {
  baseline: '#2563eb',
  comparison: '#334155',
  positive: '#047857',
  negative: '#b91c1c',
  zero: '#64748b',
};

function toneForBar(bar: AnalysisWaterfallBar): BarTone {
  if (bar.isStart) return 'baseline';
  if (bar.isEnd) return 'comparison';
  if (bar.delta > 0) return 'positive';
  if (bar.delta < 0) return 'negative';
  return 'zero';
}

function formatEokWon(krwValue: number, signed = false): string {
  const eok = krwValue / 100_000_000;
  const formatted = eok.toLocaleString('ko-KR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  return `${signed && eok > 0 ? '+' : ''}${formatted}억원`;
}

function categoryLabel(category: AnalysisWaterfallBar['category']): string {
  switch (category) {
    case 'INTERNAL': return '내부';
    case 'EXTERNAL': return '외부';
    case 'COST': return '비용';
    case 'LAG': return '';
    default: return '';
  }
}

export function EffectWaterfallChart({
  bars,
  selectedEffectId,
  onSelectEffect,
}: EffectWaterfallChartProps) {
  const [hoveredBar, setHoveredBar] = useState<AnalysisWaterfallBar | null>(null);

  const allValues = bars.length ? bars.flatMap((bar) => [bar.startValue, bar.endValue]) : [0];
  const domainMin = Math.min(0, ...allValues);
  const domainMax = Math.max(0, ...allValues);
  const domainSpan = Math.max(domainMax - domainMin, 1);
  const minValue = domainMin - domainSpan * 0.08;
  const maxValue = domainMax + domainSpan * 0.12;

  const svgWidth = 1_020;
  const svgHeight = 320;
  const paddingLeft = 70;
  const paddingRight = 28;
  const paddingTop = 36;
  const paddingBottom = 78;
  const chartWidth = svgWidth - paddingLeft - paddingRight;
  const chartHeight = svgHeight - paddingTop - paddingBottom;
  const colWidth = chartWidth / Math.max(bars.length, 1);
  const barWidth = Math.min(colWidth * 0.64, 48);

  const getY = (value: number) => {
    const ratio = (value - minValue) / (maxValue - minValue);
    return paddingTop + chartHeight * (1 - ratio);
  };

  const selectBar = (bar: AnalysisWaterfallBar) => {
    if (!bar.isTotal) onSelectEffect?.(bar.id);
  };

  const handleBarKeyDown = (bar: AnalysisWaterfallBar, event: React.KeyboardEvent<SVGGElement>) => {
    if (bar.isTotal || !onSelectEffect) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelectEffect(bar.id);
    }
  };

  return (
    <section className="variance-analysis__waterfall-card" aria-labelledby="variance-waterfall-title">
      <div className="variance-analysis__chart-header">
        <div>
          <h3 id="variance-waterfall-title" className="variance-analysis__chart-title">
            <BarChart3 size={16} aria-hidden="true" />
            영업이익 변동 Waterfall
          </h3>
          <p className="variance-analysis__chart-subtitle">단위: 억원 · 막대를 선택하면 Effect 상세가 강조됩니다.</p>
        </div>
        <div className="variance-analysis__chart-legend" aria-label="Waterfall 범례">
          <Legend color={BAR_COLORS.baseline} label="기준" />
          <Legend color={BAR_COLORS.positive} label="이익 증가" />
          <Legend color={BAR_COLORS.negative} label="이익 감소" />
          <Legend color={BAR_COLORS.zero} label="변동 없음" />
          <Legend color={BAR_COLORS.comparison} label="비교" />
        </div>
      </div>

      <div className="variance-analysis__waterfall-scroll" role="region" aria-label="영업이익 변동 Waterfall 차트" tabIndex={0}>
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="variance-analysis__waterfall-svg"
          role="img"
          aria-labelledby="variance-waterfall-title"
        >
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const value = minValue + (maxValue - minValue) * ratio;
            const y = getY(value);
            return (
              <g key={ratio} aria-hidden="true">
                <line x1={paddingLeft} y1={y} x2={svgWidth - paddingRight} y2={y} className="variance-analysis__waterfall-gridline" />
                <text x={paddingLeft - 10} y={y + 3.5} textAnchor="end" className="variance-analysis__waterfall-axis-label">
                  {formatEokWon(value)}
                </text>
              </g>
            );
          })}

          <line x1={paddingLeft} y1={getY(0)} x2={svgWidth - paddingRight} y2={getY(0)} className="variance-analysis__waterfall-zero-line" aria-hidden="true" />

          {bars.map((bar, index) => {
            const xCenter = paddingLeft + index * colWidth + colWidth / 2;
            const x = xCenter - barWidth / 2;
            const yTop = getY(Math.max(bar.startValue, bar.endValue));
            const yBottom = getY(Math.min(bar.startValue, bar.endValue));
            const height = Math.max(yBottom - yTop, 3.5);
            const selected = !bar.isTotal && selectedEffectId === bar.id;
            const hovered = hoveredBar?.id === bar.id;
            const selectable = !bar.isTotal && Boolean(onSelectEffect);
            const tone = toneForBar(bar);
            const nextBar = bars[index + 1];
            const connectorY = getY(bar.endValue);
            const nextX = nextBar ? paddingLeft + (index + 1) * colWidth + colWidth / 2 - barWidth / 2 : null;

            return (
              <g
                key={bar.id}
                data-testid={`waterfall-bar-${bar.id}`}
                className={`variance-analysis__waterfall-bar variance-analysis__waterfall-bar--${tone}`}
                role={selectable ? 'button' : 'img'}
                aria-label={`${bar.name}: ${formatEokWon(bar.delta, !bar.isTotal)}`}
                aria-pressed={selectable ? selected : undefined}
                tabIndex={selectable ? 0 : -1}
                onClick={() => selectBar(bar)}
                onKeyDown={(event) => handleBarKeyDown(bar, event)}
                onMouseEnter={() => setHoveredBar(bar)}
                onMouseLeave={() => setHoveredBar(null)}
                onFocus={() => setHoveredBar(bar)}
                onBlur={() => setHoveredBar(null)}
              >
                {nextX !== null && (
                  <line x1={x + barWidth} y1={connectorY} x2={nextX} y2={connectorY} className="variance-analysis__waterfall-connector" aria-hidden="true" />
                )}
                {(selected || hovered) && (
                  <rect
                    x={x - 4}
                    y={yTop - 4}
                    width={barWidth + 8}
                    height={height + 8}
                    className={`variance-analysis__waterfall-selection-ring ${selected ? 'is-selected' : ''}`}
                    rx="3"
                    aria-hidden="true"
                  />
                )}
                <rect
                  x={x}
                  y={yTop}
                  width={barWidth}
                  height={height}
                  fill={BAR_COLORS[tone]}
                  className="variance-analysis__waterfall-rect"
                  rx="2"
                />
                <text
                  x={xCenter}
                  y={bar.delta >= 0 ? yTop - 8 : yBottom + 15}
                  textAnchor="middle"
                  className={`variance-analysis__waterfall-value variance-analysis__waterfall-value--${tone}`}
                >
                  {formatEokWon(bar.delta, !bar.isTotal)}
                </text>
                <text x={xCenter} y={paddingTop + chartHeight + 20} textAnchor="middle" className={`variance-analysis__waterfall-name ${selected ? 'is-selected' : ''}`}>
                  {bar.name}
                </text>
                <text x={xCenter} y={paddingTop + chartHeight + 36} textAnchor="middle" className="variance-analysis__waterfall-category">
                  {categoryLabel(bar.category)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {hoveredBar && (
        <div className="variance-analysis__waterfall-hover" role="status" aria-live="polite">
          <strong>{hoveredBar.name}</strong>
          <span>{formatEokWon(hoveredBar.delta, !hoveredBar.isTotal)}</span>
          {!hoveredBar.isTotal && <span className="variance-analysis__waterfall-hover-hint">Enter/Space 또는 클릭으로 선택</span>}
        </div>
      )}
    </section>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return <span className="variance-analysis__legend-item"><span className="variance-analysis__legend-color" style={{ backgroundColor: color }} aria-hidden="true" />{label}</span>;
}

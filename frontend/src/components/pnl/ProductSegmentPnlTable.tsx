import { Package } from 'lucide-react';
import { useState } from 'react';
import type { PnlPeriodSlot, PnlProductSegmentSlot, PnlReportingViewMode } from '../../types/pnlReporting';
import { displayCells, ReportingMonthSelector, ReportingTableControls, ReportingValueCell } from './ReportingTableControls';

interface ProductSegmentPnlTableProps {
  segments: PnlProductSegmentSlot[];
  periods: PnlPeriodSlot[];
  actualPeriodKeys: string[];
  initialPeriodKey: string;
  defaultCustomRangeKey: string;
}

export function ProductSegmentPnlTable({ segments, periods, actualPeriodKeys, initialPeriodKey, defaultCustomRangeKey }: ProductSegmentPnlTableProps) {
  const [mode, setMode] = useState<PnlReportingViewMode>('PLAN_ACTUAL_COMPARE');
  const [segmentKey, setSegmentKey] = useState(segments[0]?.key ?? '');
  const [periodKey, setPeriodKey] = useState(initialPeriodKey);
  const [rangeKey, setRangeKey] = useState(defaultCustomRangeKey);
  const segment = segments.find((item) => item.key === segmentKey) ?? segments[0];
  const selectedLabel = periods.find((period) => period.key === periodKey)?.label ?? periodKey;
  const isLatestActualPeriod = periodKey === initialPeriodKey;
  const actualOnlyWidth = Math.max(860, 359 + actualPeriodKeys.length * 82);
  const tableWidth = mode === 'PLAN_ACTUAL_COMPARE' ? '1150px' : mode === 'ACTUAL_ONLY' ? `${actualOnlyWidth}px` : '760px';
  const columnCount = mode === 'PLAN_ACTUAL_COMPARE' ? 10 : mode === 'ACTUAL_ONLY' ? actualPeriodKeys.length + 3 : 5;

  return <section className="pnl-report__table-container" data-testid="product-table-shell">
    <header className="pnl-report__table-toolbar">
      <div className="pnl-report__table-toolbar-primary">
        <div className="pnl-report__table-title"><Package size={16} color="#2563eb" />Item별 구분손익</div>
        <div className="pnl-report__segmented pnl-report__segment-selector" role="group" aria-label="제품군 선택">{segments.map((item) => <button type="button" key={item.key} className={item.key === segment?.key ? 'active' : ''} data-unit={item.businessUnit ?? undefined} data-dimension={item.dimensionLabel ?? undefined} onClick={() => setSegmentKey(item.key)}>{item.label}</button>)}</div>
        {mode === 'PLAN_ACTUAL_COMPARE' && <ReportingMonthSelector periods={periods} actualPeriodKeys={actualPeriodKeys} selectedKey={periodKey} latestKey={initialPeriodKey} onSelect={setPeriodKey} />}
      </div>
      <ReportingTableControls mode={mode} defaultRangeKey={defaultCustomRangeKey} onModeChange={setMode} onRangeApply={(start, end) => setRangeKey(`${start}:${end}`)} />
    </header>
    {segment ? <div className="pnl-report__table-wrap">
      <div className="pnl-report__table-unit" style={{ width: tableWidth }}>{segment.businessUnit ? `(단위: 백만원, ${segment.businessUnit}, 원, %)` : '(단위: 백만원, 원, %)'}</div>
      <table className="pnl-report__financial-table" style={{ width: tableWidth }} data-table-kind="product" data-mode={mode} data-column-count={columnCount}>
        <thead>
          {mode === 'PLAN_ACTUAL_COMPARE' && <><tr><th rowSpan={2} style={{ width: 220 }}>손익 항목</th><th rowSpan={2} style={{ width: 50 }}>단위</th><th colSpan={4} style={{ width: 440 }}>{`${selectedLabel}${isLatestActualPeriod ? ' 당월' : ''} 실적 비교`}</th><th colSpan={4} className="pnl-report__cumulative" style={{ width: 440 }}>누계 실적 비교 (1월 ~ {selectedLabel})</th></tr><tr><th style={{ width: 110 }}>{isLatestActualPeriod ? '당월 계획' : `${selectedLabel} 계획`}</th><th style={{ width: 110 }}>{isLatestActualPeriod ? '당월 실적' : `${selectedLabel} 실적`}</th><th style={{ width: 105 }}>차이</th><th style={{ width: 115 }}>증감률</th><th className="pnl-report__cumulative" style={{ width: 110 }}>누계 계획</th><th className="pnl-report__cumulative" style={{ width: 110 }}>누계 실적</th><th className="pnl-report__cumulative" style={{ width: 105 }}>누계 차이</th><th className="pnl-report__cumulative" style={{ width: 115 }}>증감률</th></tr></>}
          {mode === 'ACTUAL_ONLY' && <tr><th style={{ width: 210 }}>손익 항목</th><th style={{ width: 54 }}>단위</th>{actualPeriodKeys.map((key) => <th key={key} style={{ width: 82 }}>{periods.find((period) => period.key === key)?.label ?? key}</th>)}<th className="pnl-report__cumulative" style={{ width: 95 }}>누계 실적</th></tr>}
          {mode === 'CUSTOM_PERIOD_COMPARE' && <tr><th style={{ width: 240 }}>손익 항목</th><th style={{ width: 60 }}>단위</th><th style={{ width: 160 }}>기간 계획 누계</th><th style={{ width: 160 }}>기간 실적 누계</th><th style={{ width: 140 }}>차이</th></tr>}
        </thead>
        <tbody>{segment.rows.map((row) => {
          const expected = mode === 'PLAN_ACTUAL_COMPARE' ? 8 : mode === 'ACTUAL_ONLY' ? actualPeriodKeys.length + 1 : 3;
          const cells = displayCells(mode === 'PLAN_ACTUAL_COMPARE' ? row.compareByPeriod[periodKey] : mode === 'ACTUAL_ONLY' ? row.actualOnly : row.customByRange[rangeKey], expected);
          return <tr key={row.key} data-row-key={row.key} className={`row-${row.kind} row-sublevel-${row.level}`}><td className="text-left">{row.label}</td><td className="text-center pnl-report__unit-cell">{row.unit}</td>{cells.map((cell, index) => <ReportingValueCell key={index} cell={cell} />)}</tr>;
        })}</tbody>
      </table>
    </div> : <div className="pnl-report__inline-empty">표시할 제품군이 없습니다.</div>}
  </section>;
}

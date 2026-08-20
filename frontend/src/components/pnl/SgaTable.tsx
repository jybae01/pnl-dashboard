import { ChevronDown, ChevronRight, Landmark } from 'lucide-react';
import { useState } from 'react';
import type { PnlPeriodSlot, PnlReportingViewMode, PnlSgaRowSlot } from '../../types/pnlReporting';
import { displayCells, ReportingMonthSelector, ReportingTableControls, ReportingValueCell } from './ReportingTableControls';

const SHOW_OTHER_DETAIL_CONTROLS = false;

interface SgaTableProps {
  rows: PnlSgaRowSlot[];
  periods: PnlPeriodSlot[];
  actualPeriodKeys: string[];
  initialPeriodKey: string;
  defaultCustomRangeKey: string;
}

export function SgaTable({ rows, periods, actualPeriodKeys, initialPeriodKey, defaultCustomRangeKey }: SgaTableProps) {
  const [mode, setMode] = useState<PnlReportingViewMode>('PLAN_ACTUAL_COMPARE');
  const [periodKey, setPeriodKey] = useState(initialPeriodKey);
  const [rangeKey, setRangeKey] = useState(defaultCustomRangeKey);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const selectedLabel = periods.find((period) => period.key === periodKey)?.label ?? periodKey;
  const isLatestActualPeriod = periodKey === initialPeriodKey;
  const visibleRows = rows.filter((row) => !row.parentKey || row.level === 1 || expanded[row.parentKey]);
  const actualOnlyWidth = Math.max(860, 359 + actualPeriodKeys.length * 82);
  const tableWidth = mode === 'PLAN_ACTUAL_COMPARE' ? '1150px' : mode === 'ACTUAL_ONLY' ? `${actualOnlyWidth}px` : '760px';
  const columnCount = mode === 'PLAN_ACTUAL_COMPARE' ? 9 : mode === 'ACTUAL_ONLY' ? actualPeriodKeys.length + 2 : 5;

  return <section className="pnl-report__table-container" data-testid="sga-table-shell">
    <header className="pnl-report__table-toolbar">
      <div className="pnl-report__table-toolbar-primary"><div className="pnl-report__table-title"><Landmark size={16} color="#7c3aed" />판매관리비 내역</div>{mode === 'PLAN_ACTUAL_COMPARE' && <ReportingMonthSelector periods={periods} actualPeriodKeys={actualPeriodKeys} selectedKey={periodKey} latestKey={initialPeriodKey} onSelect={setPeriodKey} />}</div>
      <ReportingTableControls mode={mode} defaultRangeKey={defaultCustomRangeKey} onModeChange={setMode} onRangeApply={(start, end) => setRangeKey(`${start}:${end}`)} />
    </header>
    <div className="pnl-report__table-wrap">
      <div className="pnl-report__table-unit" style={{ width: tableWidth }}>(단위: 백만원, %)</div>
      <table className="pnl-report__financial-table" style={{ width: tableWidth }} data-table-kind="sga" data-mode={mode} data-column-count={columnCount}>
        <thead>
          {mode === 'PLAN_ACTUAL_COMPARE' && <><tr><th rowSpan={2} style={{ width: 270 }}>판관비 항목</th><th colSpan={4} style={{ width: 440 }}>{`${selectedLabel}${isLatestActualPeriod ? ' 당월' : ''} 실적 비교`}</th><th colSpan={4} className="pnl-report__cumulative" style={{ width: 440 }}>누계 실적 비교 (1월 ~ {selectedLabel})</th></tr><tr><th style={{ width: 110 }}>{isLatestActualPeriod ? '당월 계획' : `${selectedLabel} 계획`}</th><th style={{ width: 110 }}>{isLatestActualPeriod ? '당월 실적' : `${selectedLabel} 실적`}</th><th style={{ width: 105 }}>차이</th><th style={{ width: 115 }}>증감률</th><th className="pnl-report__cumulative" style={{ width: 110 }}>누계 계획</th><th className="pnl-report__cumulative" style={{ width: 110 }}>누계 실적</th><th className="pnl-report__cumulative" style={{ width: 105 }}>누계 차이</th><th className="pnl-report__cumulative" style={{ width: 115 }}>증감률</th></tr></>}
          {mode === 'ACTUAL_ONLY' && <tr><th style={{ width: 264 }}>판관비 항목</th>{actualPeriodKeys.map((key) => <th key={key} style={{ width: 82 }}>{periods.find((period) => period.key === key)?.label ?? key}</th>)}<th className="pnl-report__cumulative" style={{ width: 95 }}>누계 실적</th></tr>}
          {mode === 'CUSTOM_PERIOD_COMPARE' && <tr><th style={{ width: 284 }}>판관비 항목</th><th style={{ width: 125 }}>기간 계획 누계</th><th style={{ width: 125 }}>기간 실적 누계</th><th style={{ width: 110 }}>차이</th><th style={{ width: 116 }}>증감률</th></tr>}
        </thead>
        <tbody>{visibleRows.map((row) => {
          const expected = mode === 'PLAN_ACTUAL_COMPARE' ? 8 : mode === 'ACTUAL_ONLY' ? actualPeriodKeys.length + 1 : 4;
          const cells = displayCells(mode === 'PLAN_ACTUAL_COMPARE' ? row.compareByPeriod[periodKey] : mode === 'ACTUAL_ONLY' ? row.actualOnly : row.customByRange[rangeKey], expected);
          return <tr key={row.key} data-row-key={row.key} className={`row-${row.kind} row-sublevel-${row.level}`}>
            <td className="text-left"><div className="pnl-report__sga-label"><span>{row.label}</span>{SHOW_OTHER_DETAIL_CONTROLS && row.level === 1 && row.collapsible && <button className={`pnl-report__sga-detail ${expanded[row.key] ? 'active' : ''}`} type="button" aria-label={expanded[row.key] ? `${row.label} 접기` : `${row.label} 세부보기`} onClick={() => setExpanded((current) => ({ ...current, [row.key]: !current[row.key] }))}>{expanded[row.key] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}<span>{expanded[row.key] ? '접기' : '세부보기'}</span></button>}</div></td>
            {cells.map((cell, index) => <ReportingValueCell key={index} cell={cell} />)}
          </tr>;
        })}</tbody>
      </table>
    </div>
  </section>;
}

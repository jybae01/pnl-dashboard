import { ChevronDown, ChevronRight, FileSpreadsheet } from 'lucide-react';
import { useState } from 'react';
import type { PnlPeriodSlot, PnlReportingViewMode, PnlStatementRowSlot } from '../../types/pnlReporting';
import { displayCells, ReportingMonthSelector, ReportingTableControls, ReportingValueCell } from './ReportingTableControls';

interface PnlTableProps {
  rows: PnlStatementRowSlot[];
  periods: PnlPeriodSlot[];
  actualPeriodKeys: string[];
  initialPeriodKey: string;
  defaultCustomRangeKey: string;
}

export function PnlTable({ rows, periods, actualPeriodKeys, initialPeriodKey, defaultCustomRangeKey }: PnlTableProps) {
  const [mode, setMode] = useState<PnlReportingViewMode>('PLAN_ACTUAL_COMPARE');
  const [periodKey, setPeriodKey] = useState(initialPeriodKey);
  const [rangeKey, setRangeKey] = useState(defaultCustomRangeKey);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const selectedLabel = periods.find((period) => period.key === periodKey)?.label ?? periodKey;
  const visibleRows = rows.filter((row) => !row.parentKey || !collapsed[row.parentKey]);
  const tableWidth = mode === 'PLAN_ACTUAL_COMPARE' ? '1150px' : mode === 'ACTUAL_ONLY' ? '860px' : '760px';
  const columnCount = mode === 'PLAN_ACTUAL_COMPARE' ? 10 : mode === 'ACTUAL_ONLY' ? 9 : 6;

  return <section className="pnl-report__table-container" data-testid="pnl-table-shell">
    <header className="pnl-report__table-toolbar">
      <div className="pnl-report__table-toolbar-primary"><div className="pnl-report__table-title"><FileSpreadsheet size={16} color="#2563eb" />손익계산서 (P&amp;L)</div>{mode === 'PLAN_ACTUAL_COMPARE' && <ReportingMonthSelector periods={periods} actualPeriodKeys={actualPeriodKeys} selectedKey={periodKey} latestKey={initialPeriodKey} onSelect={setPeriodKey} />}</div>
      <ReportingTableControls mode={mode} onModeChange={setMode} onRangeApply={(start, end) => setRangeKey(`${start}:${end}`)} />
    </header>
    <div className="pnl-report__table-wrap">
      <div className="pnl-report__table-unit" style={{ width: tableWidth }}>(단위: 백만원, % / %p)</div>
      <table className="pnl-report__financial-table" style={{ width: tableWidth }} data-table-kind="pnl" data-mode={mode} data-column-count={columnCount}>
        <thead>
          {mode === 'PLAN_ACTUAL_COMPARE' && <>
            <tr><th rowSpan={2} style={{ width: 220 }}>계정과목</th><th rowSpan={2} style={{ width: 50 }}>단위</th><th colSpan={4} style={{ width: 440 }}>{selectedLabel === '6월' ? '당월 실적 비교 (6월)' : `${selectedLabel} 실적 비교`}</th><th colSpan={4} className="pnl-report__cumulative" style={{ width: 440 }}>누계 실적 비교 (1월 ~ {selectedLabel})</th></tr>
            <tr><th style={{ width: 110 }}>{selectedLabel === '6월' ? '당월 계획' : `${selectedLabel} 계획`}</th><th style={{ width: 110 }}>{selectedLabel === '6월' ? '당월 실적' : `${selectedLabel} 실적`}</th><th style={{ width: 105 }}>차이</th><th style={{ width: 115 }}>증감률</th><th className="pnl-report__cumulative" style={{ width: 110 }}>누계 계획</th><th className="pnl-report__cumulative" style={{ width: 110 }}>누계 실적</th><th className="pnl-report__cumulative" style={{ width: 105 }}>누계 차이</th><th className="pnl-report__cumulative" style={{ width: 115 }}>증감률</th></tr>
          </>}
          {mode === 'ACTUAL_ONLY' && <tr><th style={{ width: 210 }}>계정과목</th><th style={{ width: 54 }}>단위</th>{actualPeriodKeys.map((key) => <th key={key} style={{ width: 82 }}>{periods.find((period) => period.key === key)?.label ?? key}</th>)}<th className="pnl-report__cumulative" style={{ width: 95 }}>누계 실적</th></tr>}
          {mode === 'CUSTOM_PERIOD_COMPARE' && <tr><th style={{ width: 230 }}>계정과목</th><th style={{ width: 54 }}>단위</th><th style={{ width: 125 }}>기간 계획 누계</th><th style={{ width: 125 }}>기간 실적 누계</th><th style={{ width: 110 }}>누계 차이</th><th style={{ width: 116 }}>누계 증감률</th></tr>}
        </thead>
        <tbody>{visibleRows.map((row) => {
          const expected = mode === 'PLAN_ACTUAL_COMPARE' ? 8 : mode === 'ACTUAL_ONLY' ? 7 : 4;
          const cells = displayCells(mode === 'PLAN_ACTUAL_COMPARE' ? row.compareByPeriod[periodKey] : mode === 'ACTUAL_ONLY' ? row.actualOnly : row.customByRange[rangeKey], expected);
          return <tr key={row.key} data-row-key={row.key} data-highlight={row.key === 'operating_profit' ? 'operating-profit' : undefined} className={`row-${row.kind} row-sublevel-${row.level}`}>
            <td className="text-left">{row.collapsible && <button className="pnl-report__expand" type="button" aria-label={collapsed[row.key] ? `${row.label} 펼치기` : `${row.label} 접기`} onClick={() => setCollapsed((current) => ({ ...current, [row.key]: !current[row.key] }))}>{collapsed[row.key] ? <ChevronRight size={13} /> : <ChevronDown size={13} />}</button>}<span>{row.label}</span></td>
            <td className="text-center pnl-report__unit-cell">{row.unit}</td>
            {cells.map((cell, index) => <ReportingValueCell key={index} cell={cell} />)}
          </tr>;
        })}</tbody>
      </table>
    </div>
  </section>;
}

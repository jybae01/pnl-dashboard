import { Factory } from 'lucide-react';
import { Fragment } from 'react';
import type { PnlCogsRowSlot, PnlPeriodSlot } from '../../types/pnlReporting';
import { displayCells, ReportingValueCell } from './ReportingTableControls';

interface MfgCostTableProps {
  rows: PnlCogsRowSlot[];
  periods: PnlPeriodSlot[];
  actualPeriodKeys: string[];
}

export function MfgCostTable({ rows, periods, actualPeriodKeys }: MfgCostTableProps) {
  const displayedPeriods = actualPeriodKeys;
  const monthCellCount = displayedPeriods.length * 2;
  const tableWidth = 140 + displayedPeriods.length * 120 + 90 + 95;
  const columnCount = monthCellCount + 3;
  return <section className="pnl-report__table-container" data-testid="cogs-table-shell">
    <header className="pnl-report__table-toolbar">
      <div className="pnl-report__table-title"><Factory size={16} color="#0f766e" />제품/반제품 매출원가 내역</div>
    </header>
    <div className="pnl-report__table-wrap">
      <div className="pnl-report__table-unit" style={{ width: tableWidth }}>(단위: 백만원, %)</div>
      <table className="pnl-report__financial-table" style={{ width: tableWidth }} data-table-kind="cogs" data-column-count={columnCount}>
        <thead>
          <tr><th rowSpan={2} style={{ width: 140 }}>매출원가 요소</th>{displayedPeriods.map((key) => <th key={key} colSpan={2} style={{ width: 120 }}>{periods.find((period) => period.key === key)?.label ?? key}</th>)}<th rowSpan={2} className="pnl-report__cumulative" style={{ width: 90 }}>누계 실적</th><th rowSpan={2} style={{ width: 95, lineHeight: 1.3 }}>매출액 대비<br />비중(%)</th></tr>
          <tr>{displayedPeriods.map((key) => <Fragment key={key}><th style={{ width: 64 }}>금액</th><th style={{ width: 56 }}>비중(%)</th></Fragment>)}</tr>
        </thead>
        <tbody>{rows.map((row) => <tr key={row.key} data-row-key={row.key} className={`row-${row.kind}`}>
          <td className="text-left">{row.label}</td>
          {displayCells([...row.cells.slice(0, monthCellCount), ...row.cells.slice(-2)], monthCellCount + 2).map((cell, index) => <ReportingValueCell key={index} cell={cell} />)}
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}

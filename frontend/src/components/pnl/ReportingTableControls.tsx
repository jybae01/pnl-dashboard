import { Search } from 'lucide-react';
import { useState } from 'react';
import { PnlReportingViewMode } from '../../types/pnlReporting';
import type { PnlDisplayCell } from '../../types/pnlReporting';
import type { PnlPeriodSlot } from '../../types/pnlReporting';

const MONTHS = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'];

interface ReportingTableControlsProps {
  mode: PnlReportingViewMode;
  onModeChange: (mode: PnlReportingViewMode) => void;
  onRangeApply: (start: string, end: string) => void;
}

export function ReportingTableControls({ mode, onModeChange, onRangeApply }: ReportingTableControlsProps) {
  const [start, setStart] = useState('1월');
  const [end, setEnd] = useState('6월');

  return <div className="pnl-report__table-controls">
    <div className="pnl-report__segmented" role="group" aria-label="표 보기 방식">
      <button type="button" className={mode === 'ACTUAL_ONLY' ? 'active' : ''} onClick={() => onModeChange('ACTUAL_ONLY')}>실적만 보기</button>
      <button type="button" className={mode === 'PLAN_ACTUAL_COMPARE' ? 'active' : ''} onClick={() => onModeChange('PLAN_ACTUAL_COMPARE')}>계획 / 실적 비교</button>
      <button type="button" className={mode === 'CUSTOM_PERIOD_COMPARE' ? 'active' : ''} onClick={() => onModeChange('CUSTOM_PERIOD_COMPARE')}>기간 설정 비교</button>
    </div>
    {mode === 'CUSTOM_PERIOD_COMPARE' && <div className="pnl-report__period-controls">
      <span>시작월</span>
      <select aria-label="시작월" value={start} onChange={(event) => setStart(event.target.value)}>{MONTHS.map((month) => <option key={`start-${month}`}>{month}</option>)}</select>
      <span>~ 종료월</span>
      <select aria-label="종료월" value={end} onChange={(event) => setEnd(event.target.value)}>{MONTHS.map((month) => <option key={`end-${month}`}>{month}</option>)}</select>
      <button type="button" onClick={() => onRangeApply(start, end)}><Search size={11} />조회</button>
    </div>}
  </div>;
}

export function ReportingMonthSelector({ periods, actualPeriodKeys, selectedKey, latestKey, onSelect }: {
  periods: PnlPeriodSlot[];
  actualPeriodKeys: string[];
  selectedKey: string;
  latestKey: string;
  onSelect: (key: string) => void;
}) {
  return <div className="pnl-report__segmented pnl-report__month-selector" aria-label="월 선택">
    <span>월 선택:</span>
    {periods.filter((period) => actualPeriodKeys.includes(period.key)).map((period) => <button type="button" key={period.key} className={selectedKey === period.key ? 'active' : ''} onClick={() => onSelect(period.key)}>{period.label}{period.key === latestKey ? '(당월)' : ''}</button>)}
  </div>;
}

export function displayCells(cells: PnlDisplayCell[] | undefined, expected: number): PnlDisplayCell[] {
  if (cells?.length === expected) return cells;
  return Array.from({ length: expected }, () => ({ text: '—', tone: 'neutral' as const }));
}

export function ReportingValueCell({ cell }: { cell: PnlDisplayCell }) {
  return <td className={`text-right pnl-report__tabular pnl-report__value--${cell.tone ?? 'neutral'}`} data-emphasis={cell.emphasis ?? 'normal'}>{cell.text}</td>;
}

import React from 'react';
import { Calendar } from 'lucide-react';

interface PeriodSelectorProps {
  value: string;
  onChange: (month: string) => void;
  availableMonths?: string[];
  disabled?: boolean;
}

export const PeriodSelector: React.FC<PeriodSelectorProps> = ({
  value,
  onChange,
  availableMonths = [
    '2026-06',
    '2026-05',
    '2026-04',
    '2026-03',
    '2026-02',
    '2026-01',
  ],
  disabled = false,
}) => {
  return (
    <div className="filter-item">
      <span className="filter-label">
        <Calendar size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
        기준월:
      </span>
      <select
        className="filter-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        {availableMonths.map((m) => {
          const [year, month] = m.split('-');
          return (
            <option key={m} value={m}>
              {year}년 {parseInt(month, 10)}월 {m === '2026-06' ? '(당월)' : ''}
            </option>
          );
        })}
      </select>
    </div>
  );
};

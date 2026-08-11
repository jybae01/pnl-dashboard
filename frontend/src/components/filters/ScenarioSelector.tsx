import React from 'react';
import { ScenarioType, ComparisonType } from '../../types/common';

interface ScenarioSelectorProps {
  value: ScenarioType;
  onChange: (scenario: ScenarioType) => void;
  disabled?: boolean;
}

export const ScenarioSelector: React.FC<ScenarioSelectorProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  return (
    <div className="filter-item">
      <span className="filter-label">구분:</span>
      <div className="segmented-control">
        <button
          type="button"
          className={`segmented-btn ${value === 'ACTUAL' ? 'active' : ''}`}
          onClick={() => !disabled && onChange('ACTUAL')}
          disabled={disabled}
        >
          실적 (Actual)
        </button>
        <button
          type="button"
          className={`segmented-btn ${value === 'FORECAST' ? 'active' : ''}`}
          onClick={() => !disabled && onChange('FORECAST')}
          disabled={disabled}
        >
          추정 (Forecast)
        </button>
      </div>
    </div>
  );
};

interface ComparisonSelectorProps {
  value: ComparisonType;
  onChange: (comp: ComparisonType) => void;
  disabled?: boolean;
}

export const ComparisonSelector: React.FC<ComparisonSelectorProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  return (
    <div className="filter-item">
      <span className="filter-label">비교 대상:</span>
      <div className="segmented-control">
        <button
          type="button"
          className={`segmented-btn ${value === 'PLAN_VS_ACTUAL' ? 'active' : ''}`}
          onClick={() => !disabled && onChange('PLAN_VS_ACTUAL')}
          disabled={disabled}
        >
          계획 대비 실적 (Plan vs Actual)
        </button>
        <button
          type="button"
          className={`segmented-btn ${value === 'PLAN_VS_FORECAST' ? 'active' : ''}`}
          onClick={() => !disabled && onChange('PLAN_VS_FORECAST')}
          disabled={disabled}
        >
          계획 대비 추정 (Plan vs Forecast)
        </button>
      </div>
    </div>
  );
};

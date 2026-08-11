import React from 'react';
import { ViewTab } from '../../types/common';
import { LayoutDashboard, Calculator, GitCompare, Database } from 'lucide-react';

interface NavigationProps {
  activeTab: ViewTab;
  onTabChange: (tab: ViewTab) => void;
}

export const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  onTabChange,
}) => {
  return (
    <nav className="app-nav">
      <div className="nav-tabs">
        <button
          className={`nav-tab-btn ${activeTab === 'pnl_status' ? 'active' : ''}`}
          onClick={() => onTabChange('pnl_status')}
        >
          <LayoutDashboard size={14} />
          1. 손익 현황
          <span className="nav-tab-badge">KPI & Trend</span>
        </button>

        <button
          className={`nav-tab-btn ${activeTab === 'forecast_generation' ? 'active' : ''}`}
          onClick={() => onTabChange('forecast_generation')}
        >
          <Calculator size={14} />
          2. 추정 산출
          <span className="nav-tab-badge" style={{ backgroundColor: '#f1f5f9', color: '#64748b' }}>Placeholder</span>
        </button>

        <button
          className={`nav-tab-btn ${activeTab === 'variance_analysis' ? 'active' : ''}`}
          onClick={() => onTabChange('variance_analysis')}
        >
          <GitCompare size={14} />
          3. 손익 분석
          <span className="nav-tab-badge">Waterfall & Effect</span>
        </button>

        <button
          className={`nav-tab-btn ${activeTab === 'data_management' ? 'active' : ''}`}
          onClick={() => onTabChange('data_management')}
        >
          <Database size={14} />
          4. 데이터 관리
          <span className="nav-tab-badge">Model & Calc</span>
        </button>
      </div>
    </nav>
  );
};

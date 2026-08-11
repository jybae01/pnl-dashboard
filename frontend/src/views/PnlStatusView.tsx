import React, { useState, useEffect } from 'react';
import {
  PnlFilterState,
  PnlKpiSummary,
  MonthlyTrendItem,
  PnlLineItem,
  MfgCostBreakdownItem,
  SgaBreakdownItem,
  ProductSegmentPnl,
  KeyVarianceNote,
  PnlSubTab
} from '../types/pnl';
import { ProductGroup } from '../types/common';
import { pnlService } from '../services/pnlService';
import { KpiOverview } from '../components/pnl/KpiOverview';
import { MonthlyTrendChart } from '../components/pnl/MonthlyTrendChart';
import { PnlTable } from '../components/pnl/PnlTable';
import { MfgCostTable } from '../components/pnl/MfgCostTable';
import { SgaTable } from '../components/pnl/SgaTable';
import { ProductSegmentPnlTable } from '../components/pnl/ProductSegmentPnlTable';
import { KeyVariancesCard } from '../components/pnl/KeyVariancesCard';
import {
  Calendar,
  FileSpreadsheet,
  Factory,
  Landmark,
  Package,
  ArrowRightCircle,
  RefreshCw
} from 'lucide-react';

interface PnlStatusViewProps {
  onNavigateToVariance?: (group: ProductGroup) => void;
  simulateEmpty?: boolean;
}

export const PnlStatusView: React.FC<PnlStatusViewProps> = ({
  onNavigateToVariance,
  simulateEmpty = false,
}) => {
  const [filter, setFilter] = useState<PnlFilterState>({
    baseYear: 2026,
    baseMonth: '2026-06',
    activeSubTab: 'pnl_statement',
  });

  const [loading, setLoading] = useState<boolean>(true);
  const [kpiSummary, setKpiSummary] = useState<PnlKpiSummary | null>(null);
  const [monthlyTrends, setMonthlyTrends] = useState<MonthlyTrendItem[]>([]);
  const [pnlItems, setPnlItems] = useState<PnlLineItem[]>([]);
  const [mfgCostItems, setMfgCostItems] = useState<MfgCostBreakdownItem[]>([]);
  const [sgaItems, setSgaItems] = useState<SgaBreakdownItem[]>([]);
  const [productSegments, setProductSegments] = useState<ProductSegmentPnl[]>([]);
  const [keyNotes, setKeyNotes] = useState<KeyVarianceNote[]>([]);

  const loadData = async () => {
    setLoading(true);
    try {
      if (simulateEmpty) {
        setKpiSummary(null);
        setMonthlyTrends([]);
        setPnlItems([]);
        setMfgCostItems([]);
        setSgaItems([]);
        setProductSegments([]);
        setKeyNotes([]);
      } else {
        const [kpi, trends, pnl, mfg, sga, segs, notes] = await Promise.all([
          pnlService.getKpiSummary(filter),
          pnlService.getMonthlyTrends(filter.baseYear, 'ALL'),
          pnlService.getPnlTable(filter),
          pnlService.getMfgCostBreakdown(filter),
          pnlService.getSgaBreakdown(filter),
          pnlService.getItemSegmentPnl(filter),
          pnlService.getKeyNotes(filter),
        ]);
        setKpiSummary(kpi);
        setMonthlyTrends(trends);
        setPnlItems(pnl);
        setMfgCostItems(mfg);
        setSgaItems(sga);
        setProductSegments(segs);
        setKeyNotes(notes);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [filter.baseYear, simulateEmpty]);

  const handleSubTabChange = (tab: PnlSubTab) => {
    setFilter(prev => ({ ...prev, activeSubTab: tab }));
  };

  return (
    <div className="view-container">
      {/* 1. Simplified Top Global Filter Bar: Base Year Only */}
      <div className="filter-bar" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="filter-item">
            <span className="filter-label" style={{ fontWeight: 700, color: '#0f172a' }}>
              <Calendar size={13} color="#2563eb" /> 기준년도
            </span>
            <select
              className="filter-select"
              style={{ fontWeight: 700, color: '#1e3a8a', backgroundColor: '#ffffff', minWidth: '100px' }}
              value={filter.baseYear}
              onChange={e => setFilter({ ...filter, baseYear: parseInt(e.target.value, 10) })}
            >
              <option value="2026">2026년</option>
              <option value="2025">2025년</option>
            </select>
          </div>

          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            · 전사 경영 손익 현황 (최근 마감: 2026년 06월 실적 확정)
          </span>
        </div>

        <button
          className="btn btn-secondary btn-sm"
          onClick={loadData}
          title="새로고침"
          style={{ padding: '4px 8px' }}
        >
          <RefreshCw size={13} className={loading ? 'spin' : ''} />
        </button>
      </div>

      {/* Empty State */}
      {simulateEmpty && (
        <div className="empty-state-box">
          <div className="empty-state-title">선택한 조건의 손익 데이터가 없습니다</div>
          <div className="empty-state-desc">기준년도를 변경하여 다시 조회하십시오.</div>
        </div>
      )}

      {!simulateEmpty && (
        <>
          {/* 2. Top 3 KPIs (영업이익 Primary Highlight) */}
          {kpiSummary && <KpiOverview kpi={kpiSummary} />}

          {/* 3. Monthly Trends Section (4 Independent Views: 매출액 / 영업이익 / 조정 영업이익 / 월별 데이터표) */}
          <MonthlyTrendChart data={monthlyTrends} />

          {/* 4. Sub-Navigation Tabs */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '2px solid var(--border-default)',
            marginBottom: 12,
            marginTop: 8,
            flexWrap: 'wrap',
            gap: 8
          }}>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                type="button"
                className={`tab-pill-btn ${filter.activeSubTab === 'pnl_statement' ? 'active' : ''}`}
                onClick={() => handleSubTabChange('pnl_statement')}
              >
                <FileSpreadsheet size={14} />
                1. 손익계산서 (P&L)
              </button>

              <button
                type="button"
                className={`tab-pill-btn ${filter.activeSubTab === 'mfg_cost_breakdown' ? 'active' : ''}`}
                onClick={() => handleSubTabChange('mfg_cost_breakdown')}
              >
                <Factory size={14} />
                2. 제품/반제품 매출원가 내역
              </button>

              <button
                type="button"
                className={`tab-pill-btn ${filter.activeSubTab === 'sga_breakdown' ? 'active' : ''}`}
                onClick={() => handleSubTabChange('sga_breakdown')}
              >
                <Landmark size={14} />
                3. 판매관리비 명세
              </button>

              <button
                type="button"
                className={`tab-pill-btn ${filter.activeSubTab === 'item_segment_pnl' ? 'active' : ''}`}
                onClick={() => handleSubTabChange('item_segment_pnl')}
              >
                <Package size={14} />
                4. Item별 구분손익
              </button>
            </div>

            {/* Quick Link to Tab 3 (손익 분석) */}
            {onNavigateToVariance && (
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onNavigateToVariance('ALL')}
                style={{ fontSize: '11.5px', color: '#1d4ed8', borderColor: '#bfdbfe', backgroundColor: '#eff6ff' }}
              >
                손익 요인 Waterfall 분석 바로가기 <ArrowRightCircle size={13} style={{ verticalAlign: -1, marginLeft: 3 }} />
              </button>
            )}
          </div>

          {/* 5. Sub-Tab Report Content (With local ViewMode in each component) */}
          {filter.activeSubTab === 'pnl_statement' && (
            <PnlTable items={pnlItems} />
          )}

          {filter.activeSubTab === 'mfg_cost_breakdown' && (
            <MfgCostTable items={mfgCostItems} />
          )}

          {filter.activeSubTab === 'sga_breakdown' && (
            <SgaTable items={sgaItems} />
          )}

          {filter.activeSubTab === 'item_segment_pnl' && (
            <ProductSegmentPnlTable segments={productSegments} />
          )}

          {/* 6. Key Variance Highlights Card */}
          <KeyVariancesCard notes={keyNotes} />
        </>
      )}
    </div>
  );
};

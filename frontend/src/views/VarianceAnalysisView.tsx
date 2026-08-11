import React, { useState, useEffect } from 'react';
import { varianceService, calculationService } from '../services';
import { VarianceAnalysisResult, VarianceFilterState } from '../types/variance';
import { PeriodSelector } from '../components/filters/PeriodSelector';
import { ProductGroupSelector } from '../components/filters/ProductGroupSelector';
import { ComparisonSelector } from '../components/filters/ScenarioSelector';
import { VarianceSummaryHeader } from '../components/variance/VarianceSummaryHeader';
import { EffectWaterfallChart } from '../components/variance/EffectWaterfallChart';
import { VarianceDetailTable } from '../components/variance/VarianceDetailTable';
import { ExecutiveNarrativeCard } from '../components/variance/ExecutiveNarrativeCard';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { EmptyState } from '../components/common/EmptyState';
import { ProductGroup } from '../types/common';
import { GitCompare, FileSpreadsheet } from 'lucide-react';

interface VarianceAnalysisViewProps {
  initialProductGroup?: ProductGroup;
  simulateEmpty?: boolean;
}

export const VarianceAnalysisView: React.FC<VarianceAnalysisViewProps> = ({
  initialProductGroup = 'ALL',
  simulateEmpty = false,
}) => {
  const [filter, setFilter] = useState<VarianceFilterState>({
    baseMonth: '2026-06',
    periodType: 'MONTHLY',
    comparisonType: 'PLAN_VS_ACTUAL',
    productGroup: initialProductGroup,
  });

  const [analysis, setAnalysis] = useState<VarianceAnalysisResult | null>(null);
  const [selectedEffectId, setSelectedEffectId] = useState<string | undefined>('eff_vol');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [downloadNotice, setDownloadNotice] = useState<string | null>(null);

  useEffect(() => {
    if (initialProductGroup) {
      setFilter(prev => ({ ...prev, productGroup: initialProductGroup }));
    }
  }, [initialProductGroup]);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);

    varianceService.getVarianceAnalysis(filter).then((res) => {
      if (isMounted) {
        setAnalysis(res);
        setIsLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [filter]);

  const handleSelectEffect = (id: string) => {
    setSelectedEffectId(id);
  };

  const handleDownloadExcel = () => {
    calculationService.downloadAnalysisWorkbook();
    setDownloadNotice('실제 분석 근거 Excel은 Backend 통합 후 내려받을 수 있습니다.');
    setTimeout(() => setDownloadNotice(null), 3500);
  };

  return (
    <div>
      {/* Top Header & Filter Bar */}
      <div className="view-header-bar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '13.5px', fontWeight: 800, color: '#0f172a' }}>
            <GitCompare size={16} color="#2563eb" />
            <span>손익 분석</span>
            <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>— 모형 비교</span>
          </div>

          <div className="filter-group">
            <PeriodSelector
              value={filter.baseMonth}
              onChange={(m) => setFilter(prev => ({ ...prev, baseMonth: m }))}
            />
            <ComparisonSelector
              value={filter.comparisonType}
              onChange={(c) => setFilter(prev => ({ ...prev, comparisonType: c }))}
            />
            <ProductGroupSelector
              value={filter.productGroup}
              onChange={(g) => setFilter(prev => ({ ...prev, productGroup: g }))}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className="unit-tag">
            손익 분해 엔진: Variance Decomposition V2 (8 Effects)
          </span>
        </div>
      </div>

      {/* Download Action Notice Toast */}
      {downloadNotice && (
        <div style={{
          marginBottom: 12,
          padding: '10px 14px',
          backgroundColor: '#f0fdf4',
          border: '1px solid #86efac',
          borderRadius: 'var(--radius-sm)',
          fontSize: '12px',
          color: '#15803d',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}>
          <FileSpreadsheet size={15} color="#16a34a" />
          <span>{downloadNotice}</span>
        </div>
      )}

      {isLoading ? (
        <LoadingSpinner message="손익 변동 Effect 분해 연산 결과를 계산 및 시각화하는 중..." />
      ) : simulateEmpty || !analysis ? (
        <EmptyState
          title="손익 분석 데이터가 없습니다"
          description="데이터 관리에서 비교할 모형 2개를 선택한 후 손익 분석을 실행해 주세요."
          actionText="데이터 관리로 이동"
          onAction={() => {
            window.location.hash = 'management';
          }}
        />
      ) : (
        <>
          {/* 1. Overall P&L Variance Hero Summary with Download Action */}
          <VarianceSummaryHeader
            data={analysis}
            onDownloadExcel={handleDownloadExcel}
          />

          {/* 2. Executive Generated Narrative Summary */}
          <ExecutiveNarrativeCard
            summary={analysis.executiveSummary}
            positiveFactors={analysis.keyPositiveFactors}
            negativeFactors={analysis.keyNegativeFactors}
          />

          {/* 3. Interactive Waterfall / Contribution Chart */}
          <EffectWaterfallChart
            bars={analysis.waterfallBars}
            selectedEffectId={selectedEffectId}
            onSelectEffect={handleSelectEffect}
          />

          {/* 4. Detailed Variance Effects Table */}
          <VarianceDetailTable
            effects={analysis.effects}
            highlightedEffectId={selectedEffectId}
            onSelectEffect={handleSelectEffect}
          />
        </>
      )}
    </div>
  );
};

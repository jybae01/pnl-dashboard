import React, { useState, useEffect } from 'react';
import { modelService } from '../services';
import { DataModelItem, ModelType, PublishedStatus } from '../types/model';
import { ModelTable } from '../components/management/ModelTable';
import { ModelUploadArea } from '../components/management/ModelUploadArea';
import { ModelDetailModal } from '../components/management/ModelDetailModal';
import { ModelDeleteConfirmModal } from '../components/management/ModelDeleteConfirmModal';
import { CalculationRunnerModal } from '../components/management/CalculationRunnerModal';
import { CalculationHistoryTable } from '../components/management/CalculationHistoryTable';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { EmptyState } from '../components/common/EmptyState';
import { Sparkles, Search, ArrowLeftRight, CheckCircle2, AlertCircle, Info, Check } from 'lucide-react';

interface DataManagementViewProps {
  onGoToVarianceView: () => void;
  isCalcModalOpen: boolean;
  onOpenCalcModal: () => void;
  onCloseCalcModal: () => void;
  simulateEmpty?: boolean;
}

export const DataManagementView: React.FC<DataManagementViewProps> = ({
  onGoToVarianceView,
  isCalcModalOpen,
  onOpenCalcModal,
  onCloseCalcModal,
  simulateEmpty = false,
}) => {
  const [models, setModels] = useState<DataModelItem[]>([]);
  const [selectedModel, setSelectedModel] = useState<DataModelItem | null>(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [toastNotice, setToastNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Filters
  const [typeFilter, setTypeFilter] = useState<ModelType | 'ALL'>('ALL');
  const [statusFilter, setStatusFilter] = useState<PublishedStatus | 'ALL'>('ALL');
  const [searchKeyword, setSearchKeyword] = useState<string>('');

  // 2-Model Selection States for Variance Analysis (Max 2 items)
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([]);
  const [baselineModelId, setBaselineModelId] = useState<string>('');
  const [comparisonModelId, setComparisonModelId] = useState<string>('');
  const [selectionWarning, setSelectionWarning] = useState<string | null>(null);

  // 0~N Independent Delete Selection State (No 2-item limit)
  const [deleteSelectedModelIds, setDeleteSelectedModelIds] = useState<string[]>([]);

  const fetchModels = () => {
    setIsLoading(true);
    modelService.getModels({
      modelType: typeFilter,
      publishedStatus: statusFilter,
      searchKeyword,
    }).then(res => {
      setModels(res);
      // Pre-select top 2 eligible models as initial selection if empty
      if (selectedModelIds.length === 0 && res.length >= 2) {
        const defaultBase = res.find(m => m.modelType === 'PLAN') || res[0];
        const defaultComp = res.find(m => m.id !== defaultBase.id) || res[1];
        if (defaultBase && defaultComp) {
          setSelectedModelIds([defaultBase.id, defaultComp.id]);
          setBaselineModelId(defaultBase.id);
          setComparisonModelId(defaultComp.id);
        }
      }
      setIsLoading(false);
    });
  };

  useEffect(() => {
    setDeleteSelectedModelIds([]);
    fetchModels();
  }, [typeFilter, statusFilter, searchKeyword]);

  // Checkbox toggle logic with strict 2-item limit and warning
  const handleToggleSelectModel = (modelId: string) => {
    setSelectionWarning(null);

    if (selectedModelIds.includes(modelId)) {
      // Uncheck
      const remaining = selectedModelIds.filter(id => id !== modelId);
      setSelectedModelIds(remaining);
      if (baselineModelId === modelId) {
        setBaselineModelId(remaining[0] || '');
      }
      if (comparisonModelId === modelId) {
        setComparisonModelId(remaining[0] || '');
      }
    } else {
      // Check attempt
      if (selectedModelIds.length >= 2) {
        setSelectionWarning('손익 분석은 두 개의 모형을 선택하여 실행합니다.');
        setTimeout(() => setSelectionWarning(null), 4000);
        return;
      }

      const nextSelected = [...selectedModelIds, modelId];
      setSelectedModelIds(nextSelected);

      if (nextSelected.length === 1) {
        setBaselineModelId(modelId);
      } else if (nextSelected.length === 2) {
        // Assign role intelligently: if one is PLAN, it makes a great baseline
        const first = models.find(m => m.id === nextSelected[0]);
        const second = models.find(m => m.id === modelId);
        if (second?.modelType === 'PLAN' && first?.modelType !== 'PLAN' && first) {
          setBaselineModelId(second.id);
          setComparisonModelId(first.id);
        } else {
          setBaselineModelId(nextSelected[0]);
          setComparisonModelId(modelId);
        }
      }
    }
  };

  // Independent Delete Selection Handlers (0~N items, no analysis limits)
  const handleToggleDeleteSelectModel = (modelId: string) => {
    setDeleteSelectedModelIds(prev =>
      prev.includes(modelId) ? prev.filter(id => id !== modelId) : [...prev, modelId]
    );
  };

  const handleToggleSelectAllDelete = () => {
    if (deleteSelectedModelIds.length === models.length && models.length > 0) {
      setDeleteSelectedModelIds([]);
    } else {
      setDeleteSelectedModelIds(models.map(m => m.id));
    }
  };

  // Swap baseline and comparison roles
  const handleSwapRoles = () => {
    const temp = baselineModelId;
    setBaselineModelId(comparisonModelId);
    setComparisonModelId(temp);
  };

  const handleSelectBaseline = (id: string) => {
    setBaselineModelId(id);
    // If selected baseline is the same as comparison, switch comparison to the other selected model
    if (id === comparisonModelId && selectedModelIds.length === 2) {
      const other = selectedModelIds.find(mId => mId !== id);
      if (other) setComparisonModelId(other);
    }
  };

  const handleSelectComparison = (id: string) => {
    setComparisonModelId(id);
    if (id === baselineModelId && selectedModelIds.length === 2) {
      const other = selectedModelIds.find(mId => mId !== id);
      if (other) setBaselineModelId(other);
    }
  };

  const handleSelectModelForDetail = (model: DataModelItem) => {
    setSelectedModel(model);
    setIsDetailModalOpen(true);
  };

  const handleRunAnalysisWithModel = (model: DataModelItem) => {
    if (model.modelType === 'PLAN') {
      setBaselineModelId(model.id);
      if (!selectedModelIds.includes(model.id)) {
        setSelectedModelIds(prev => [model.id, prev[0] || ''].filter(Boolean).slice(0, 2));
      }
    } else {
      setComparisonModelId(model.id);
      if (!selectedModelIds.includes(model.id)) {
        setSelectedModelIds(prev => [prev[0] || '', model.id].filter(Boolean).slice(0, 2));
      }
    }
    onOpenCalcModal();
  };

  // Delete Handlers (Triggered by delete selection)
  const handleRequestDeleteSelected = () => {
    if (deleteSelectedModelIds.length > 0) {
      setIsDeleteModalOpen(true);
    }
  };

  const handleConfirmDelete = async () => {
    const count = selectedModelIds.length;
    await modelService.deleteModels(selectedModelIds);

    // Clear selection states
    setSelectedModelIds([]);
    setBaselineModelId('');
    setComparisonModelId('');
    setSelectionWarning(null);
    setIsDeleteModalOpen(false);

    // Set brief toast notice
    const msg = count === 2 ? '선택한 모형 2개를 삭제했습니다.' : '선택한 모형을 삭제했습니다.';
    setToastNotice(msg);
    setTimeout(() => setToastNotice(null), 3500);

    fetchModels();
  };

  // Selected Model objects and derived analysis label
  const selectedModels = models.filter(m => selectedModelIds.includes(m.id));
  const baseModelObj = models.find(m => m.id === baselineModelId);
  const compModelObj = models.find(m => m.id === comparisonModelId);

  let analysisTypeLabel = '모형 간 비교';
  if (baseModelObj?.modelType === 'PLAN' && compModelObj?.modelType === 'ACTUAL') {
    analysisTypeLabel = '계획 대비 실적';
  } else if (baseModelObj?.modelType === 'PLAN' && compModelObj?.modelType === 'FORECAST') {
    analysisTypeLabel = '계획 대비 추정';
  } else if (baseModelObj?.modelType === 'ACTUAL' && compModelObj?.modelType === 'ACTUAL') {
    analysisTypeLabel = '실적 간 비교';
  }

  const isReadyToRun = selectedModelIds.length === 2 && baselineModelId && comparisonModelId && baselineModelId !== comparisonModelId;

  return (
    <div>
      {/* Top Filter Bar */}
      <div className="view-header-bar">
        <div className="filter-group">
          <div className="filter-item">
            <span className="filter-label">모형 구분:</span>
            <div className="segmented-control">
              {(['ALL', 'PLAN', 'ACTUAL', 'FORECAST'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`segmented-btn ${typeFilter === t ? 'active' : ''}`}
                  onClick={() => setTypeFilter(t)}
                >
                  {t === 'ALL' ? '전체' : t}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-item">
            <span className="filter-label">게시 상태:</span>
            <select
              className="filter-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as any)}
            >
              <option value="ALL">전체 상태</option>
              <option value="PUBLISHED">게시 완료</option>
              <option value="DRAFT">작성 중</option>
            </select>
          </div>

          <div className="filter-item" style={{ position: 'relative' }}>
            <input
              type="text"
              placeholder="모형명/등록자 검색..."
              className="filter-select"
              style={{ width: '180px', paddingLeft: '26px' }}
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
            />
            <Search size={13} color="#94a3b8" style={{ position: 'absolute', left: 8, top: 10 }} />
          </div>
        </div>
      </div>

      {/* 1. Upload Area Mock */}
      <ModelUploadArea
        onUploadSuccess={(payload) => {
          if (payload.modelType === 'PLAN') {
            modelService.createModel({
              modelName: `${payload.baseYear}년 경영계획 (${payload.fileName})`,
              modelType: 'PLAN',
              baseMonth: `${payload.baseYear}`,
              description: `${payload.baseYear}년 연간 경영계획 확정 데이터 (사용자 등록)`,
            }).then(() => fetchModels());
          } else if (payload.modelType === 'ACTUAL') {
            const mNum = parseInt(payload.actualLatestMonth || '06', 10);
            modelService.createModel({
              modelName: `${payload.baseYear}년 ${mNum}월 누계 실적 (${payload.fileName})`,
              modelType: 'ACTUAL',
              baseMonth: `${payload.baseYear}-${payload.actualLatestMonth || '06'}`,
              description: `${payload.baseYear}년 1~${mNum}월 전사 손익결산 마감 데이터 (사용자 등록)`,
            }).then(() => fetchModels());
          } else if (payload.modelType === 'FORECAST') {
            const sNum = parseInt(payload.forecastStartMonth || '07', 10);
            const eNum = parseInt(payload.forecastEndMonth || '12', 10);
            modelService.createModel({
              modelName: `${payload.baseYear}년 ${sNum}~${eNum}월 손익 추정 (${payload.fileName})`,
              modelType: 'FORECAST',
              baseMonth: `${payload.baseYear}-${payload.forecastStartMonth || '07'}~${payload.forecastEndMonth || '12'}`,
              description: `${payload.baseYear}년 ${sNum}~${eNum}월 적용 손익 추정 모형 (사용자 등록)`,
            }).then(() => fetchModels());
          }
        }}
      />

      {/* Toast Notice (Deletion / Action Success) */}
      {toastNotice && (
        <div style={{
          marginBottom: 12,
          padding: '10px 14px',
          backgroundColor: '#ecfdf5',
          border: '1px solid #6ee7b7',
          borderRadius: 'var(--radius-sm)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: '12px',
          color: '#047857',
          fontWeight: 700,
        }}>
          <Check size={16} color="#059669" />
          <span>{toastNotice}</span>
        </div>
      )}

      {/* 3-Model Selection Warning Notice */}
      {selectionWarning && (
        <div style={{
          marginBottom: 12,
          padding: '10px 14px',
          backgroundColor: '#fef2f2',
          border: '1px solid #fca5a5',
          borderRadius: 'var(--radius-sm)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: '12px',
          color: '#b91c1c',
          fontWeight: 700
        }}>
          <AlertCircle size={16} color="#dc2626" />
          <span>{selectionWarning}</span>
        </div>
      )}

      {/* 2. Model List Table with Checkboxes */}
      {isLoading ? (
        <LoadingSpinner message="손익 모형 목록을 불러오는 중..." />
      ) : simulateEmpty || models.length === 0 ? (
        <EmptyState
          title="등록된 데이터 모형이 없습니다"
          description="선택한 필터 조건에 일치하는 손익 모형이 없습니다. 필터를 초기화하거나 상단에서 신규 모형을 등록하십시오."
          actionText="필터 초기화"
          onAction={() => {
            setTypeFilter('ALL');
            setStatusFilter('ALL');
            setSearchKeyword('');
          }}
        />
      ) : (
        <ModelTable
          models={models}
          deleteSelectedModelIds={deleteSelectedModelIds}
          onToggleDeleteSelectModel={handleToggleDeleteSelectModel}
          onToggleSelectAllDelete={handleToggleSelectAllDelete}
          selectedModelIds={selectedModelIds}
          onToggleSelectModel={handleToggleSelectModel}
          onSelectModel={handleSelectModelForDetail}
          onRunAnalysisWithModel={handleRunAnalysisWithModel}
          onRequestDeleteSelected={handleRequestDeleteSelected}
        />
      )}

      {/* 3. Model Role Assignment & Execution Panel (Compact & Responsive for 1366px) */}
      {!isLoading && models.length > 0 && (
        <div style={{
          marginTop: 10,
          marginBottom: 16,
          padding: '12px 16px',
          backgroundColor: selectedModelIds.length === 2 ? '#f0fdf4' : '#f8fafc',
          border: `1px solid ${selectedModelIds.length === 2 ? '#86efac' : 'var(--border-default)'}`,
          borderRadius: 'var(--radius-md)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 10,
        }}>
          {/* Left: Selection Status & Guidance */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: '220px' }}>
            <div style={{
              width: 28,
              height: 28,
              borderRadius: 14,
              backgroundColor: selectedModelIds.length === 2 ? '#dcfce7' : '#e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}>
              {selectedModelIds.length === 2 ? (
                <CheckCircle2 size={16} color="#16a34a" />
              ) : (
                <Info size={16} color="#64748b" />
              )}
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a' }}>
                  {selectedModelIds.length === 2 ? '2개 모형 선택됨' : selectedModelIds.length === 1 ? '1개 모형 선택됨' : '선택된 모형: 0개'}
                </span>
                {selectedModelIds.length === 2 && (
                  <span style={{ fontSize: '10.5px', backgroundColor: '#dbeafe', color: '#1e40af', padding: '1px 6px', borderRadius: '4px', fontWeight: 700 }}>
                    {analysisTypeLabel}
                  </span>
                )}
              </div>
              <div style={{ fontSize: '11px', color: selectedModelIds.length === 2 ? '#15803d' : '#64748b' }}>
                {selectedModelIds.length === 2
                  ? '기준/비교 역할을 확인 후 실행하십시오.'
                  : selectedModelIds.length === 1
                  ? '비교할 모형을 하나 더 선택해 주세요.'
                  : '상단 목록에서 비교할 2개 모형을 선택하십시오.'}
              </div>
            </div>
          </div>

          {/* Center: Baseline & Comparison Role Selectors (Active when 2 selected) */}
          {selectedModelIds.length === 2 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#1e3a8a' }}>기준:</span>
                <select
                  className="filter-select"
                  style={{ minWidth: '150px', maxWidth: '210px', fontWeight: 600, fontSize: '11px', backgroundColor: '#ffffff', padding: '4px 8px' }}
                  value={baselineModelId}
                  onChange={(e) => handleSelectBaseline(e.target.value)}
                >
                  {selectedModels.map(m => (
                    <option key={`sel-base-${m.id}`} value={m.id}>
                      [{m.modelType}] {m.modelName}
                    </option>
                  ))}
                </select>
              </div>

              {/* Swap Button */}
              <button
                type="button"
                className="btn btn-secondary btn-icon"
                onClick={handleSwapRoles}
                title="기준 모형과 비교 모형 역할 전환 (Swap)"
                style={{ backgroundColor: '#ffffff', borderColor: '#cbd5e1', padding: '4px 6px' }}
              >
                <ArrowLeftRight size={12} color="#2563eb" />
              </button>

              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#047857' }}>비교:</span>
                <select
                  className="filter-select"
                  style={{ minWidth: '150px', maxWidth: '210px', fontWeight: 600, fontSize: '11px', backgroundColor: '#ffffff', padding: '4px 8px' }}
                  value={comparisonModelId}
                  onChange={(e) => handleSelectComparison(e.target.value)}
                >
                  {selectedModels.map(m => (
                    <option key={`sel-comp-${m.id}`} value={m.id}>
                      [{m.modelType}] {m.modelName}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* Right: Execution Button */}
          <div>
            <button
              className="btn btn-primary"
              onClick={onOpenCalcModal}
              disabled={!isReadyToRun}
              style={{
                opacity: isReadyToRun ? 1 : 0.5,
                cursor: isReadyToRun ? 'pointer' : 'not-allowed',
                padding: '6px 14px',
                fontSize: '12px',
                fontWeight: 700,
              }}
            >
              <Sparkles size={13} />
              손익 분석 실행
            </button>
          </div>
        </div>
      )}

      {/* 4. Past Calculation History Table */}
      <CalculationHistoryTable onGoToVariance={onGoToVarianceView} />

      {/* Detail Modal */}
      <ModelDetailModal
        model={selectedModel}
        isOpen={isDetailModalOpen}
        onClose={() => setIsDetailModalOpen(false)}
        onRunCalculation={handleRunAnalysisWithModel}
      />

      {/* Delete Confirmation Modal */}
      <ModelDeleteConfirmModal
        isOpen={isDeleteModalOpen}
        selectedModels={selectedModels}
        onConfirm={handleConfirmDelete}
        onCancel={() => setIsDeleteModalOpen(false)}
      />

      {/* Calculation Runner Simulation Modal (Receives dynamic user selections, no hardcoding) */}
      <CalculationRunnerModal
        isOpen={isCalcModalOpen}
        onClose={onCloseCalcModal}
        models={models}
        defaultBaselineId={baselineModelId}
        defaultComparisonId={comparisonModelId}
        onGoToVarianceView={onGoToVarianceView}
      />
    </div>
  );
};

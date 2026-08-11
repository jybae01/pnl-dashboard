import React from 'react';
import { DataModelItem } from '../../types/model';
import { ModelTypeBadge, PublishedBadge, CalcStatusBadge } from '../common/StatusBadge';
import { Eye, Filter, Trash2 } from 'lucide-react';

interface ModelTableProps {
  models: DataModelItem[];
  selectedModelIds: string[];
  onToggleSelectModel: (modelId: string) => void;
  onSelectModel: (model: DataModelItem) => void;
  onRunAnalysisWithModel?: (model: DataModelItem) => void;
  onRequestDeleteSelected?: () => void;
}

export const ModelTable: React.FC<ModelTableProps> = ({
  models,
  selectedModelIds,
  onToggleSelectModel,
  onSelectModel,
  onRequestDeleteSelected,
}) => {
  // Helper to extract year and applied period (적용기간)
  const getYearAndPeriod = (m: DataModelItem) => {
    let year = '2026';
    let period = '-';

    if (m.baseMonth) {
      if (m.baseMonth.includes('-')) {
        const parts = m.baseMonth.split('-');
        year = parts[0];
        const monthPart = parts[1];

        if (m.modelType === 'PLAN') {
          period = '-';
        } else if (m.modelType === 'ACTUAL') {
          const monthNum = parseInt(monthPart, 10);
          period = `1~${monthNum}월`;
        } else if (m.modelType === 'FORECAST') {
          if (monthPart.includes('~')) {
            const [s, e] = monthPart.split('~');
            period = `${parseInt(s, 10)}~${parseInt(e, 10)}월`;
          } else {
            const monthNum = parseInt(monthPart, 10);
            const startM = monthNum === 6 ? 7 : monthNum;
            period = `${startM}~12월`;
          }
        }
      } else if (m.baseMonth.length === 4) {
        year = m.baseMonth;
        period = '-';
      }
    }

    if (m.modelType === 'PLAN') {
      period = '-';
    }

    return { year, period };
  };

  return (
    <div className="financial-table-container">
      <div style={{
        padding: '10px 14px',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        backgroundColor: '#f8fafc',
        flexWrap: 'wrap',
        gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '13px' }}>
          <Filter size={15} color="#2563eb" />
          손익 데이터 모델 목록 (Data Models)
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 500 }}>
            총 {models.length}개 모델 등록됨
          </span>
        </div>

        {/* Selection Status & Delete Action */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="unit-tag" style={{ color: selectedModelIds.length > 0 ? '#2563eb' : '#64748b', fontWeight: selectedModelIds.length > 0 ? 700 : 500 }}>
            {selectedModelIds.length > 0 ? `${selectedModelIds.length}개 모형 선택됨` : '선택된 모형: 0개'}
          </span>

          {onRequestDeleteSelected && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onRequestDeleteSelected}
              disabled={selectedModelIds.length === 0}
              style={{
                padding: '3px 9px',
                fontSize: '11px',
                color: selectedModelIds.length > 0 ? '#b91c1c' : '#94a3b8',
                borderColor: selectedModelIds.length > 0 ? '#fca5a5' : '#e2e8f0',
                backgroundColor: selectedModelIds.length > 0 ? '#fef2f2' : '#f8fafc',
                cursor: selectedModelIds.length > 0 ? 'pointer' : 'not-allowed',
                opacity: selectedModelIds.length > 0 ? 1 : 0.6,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                fontWeight: 600,
              }}
              title={selectedModelIds.length === 0 ? '삭제할 모형을 목록에서 먼저 선택해 주세요' : '선택된 모형 삭제'}
            >
              <Trash2 size={12} />
              선택 삭제
            </button>
          )}
        </div>
      </div>

      <table className="financial-table">
        <thead>
          <tr>
            <th className="text-center" style={{ width: '4%', minWidth: '38px' }}>선택</th>
            <th style={{ width: '22%' }}>모델명 (Model Name)</th>
            <th className="text-center" style={{ width: '8%' }}>구분</th>
            <th className="text-center" style={{ width: '7%' }}>기준년도</th>
            <th className="text-center" style={{ width: '8%' }}>적용기간</th>
            <th className="text-center" style={{ width: '6%' }}>버전</th>
            <th style={{ width: '13%' }}>생성일시</th>
            <th style={{ width: '12%' }}>등록자</th>
            <th className="text-center" style={{ width: '8%' }}>게시 상태</th>
            <th className="text-center" style={{ width: '7%' }}>계산 상태</th>
            <th className="text-center" style={{ width: '5%' }}>상세</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => {
            const isSelected = selectedModelIds.includes(m.id);
            const { year, period } = getYearAndPeriod(m);

            return (
              <tr
                key={m.id}
                style={{
                  backgroundColor: isSelected ? 'rgba(37, 99, 235, 0.05)' : undefined,
                  transition: 'background-color 0.15s ease',
                }}
              >
                {/* Selection Checkbox */}
                <td className="text-center" style={{ verticalAlign: 'middle' }}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleSelectModel(m.id)}
                    style={{
                      cursor: 'pointer',
                      width: '15px',
                      height: '15px',
                      accentColor: '#2563eb',
                      verticalAlign: 'middle',
                    }}
                    title={isSelected ? '선택 해제' : '비교 분석 모형으로 선택'}
                  />
                </td>

                {/* Model Name */}
                <td className="text-left" style={{ fontWeight: 600 }}>
                  <div style={{ color: isSelected ? '#1e40af' : '#0f172a' }}>
                    {m.modelName}
                  </div>
                  <div style={{ fontSize: '10.5px', color: 'var(--text-muted)', marginTop: 2 }}>
                    {m.description}
                  </div>
                </td>

                <td className="text-center">
                  <ModelTypeBadge type={m.modelType} />
                </td>

                <td className="text-center font-mono" style={{ fontSize: '11.5px', fontWeight: 600 }}>
                  {year}
                </td>

                <td className="text-center font-mono" style={{ fontSize: '11.5px', color: period === '-' ? '#94a3b8' : '#0f172a', fontWeight: period === '-' ? 400 : 700 }}>
                  {period}
                </td>

                <td className="text-center">
                  <span style={{ fontWeight: 700, fontSize: '11px', color: '#1e293b' }}>
                    {m.version}
                  </span>
                </td>

                <td className="text-left font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  {m.createdDate}
                </td>

                <td className="text-left" style={{ fontSize: '11.5px' }}>
                  {m.createdBy}
                </td>

                <td className="text-center">
                  <PublishedBadge status={m.publishedStatus} />
                </td>

                <td className="text-center">
                  <CalcStatusBadge status={m.calculationStatus} />
                </td>

                {/* Actions */}
                <td className="text-center">
                  <button
                    className="btn btn-secondary btn-icon"
                    onClick={() => onSelectModel(m)}
                    title="상세 메타데이터 보기"
                  >
                    <Eye size={12} />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

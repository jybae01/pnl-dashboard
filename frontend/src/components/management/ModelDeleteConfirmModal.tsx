import React from 'react';
import { DataModelItem } from '../../types/model';
import { Trash2, AlertTriangle, X } from 'lucide-react';

interface ModelDeleteConfirmModalProps {
  isOpen: boolean;
  selectedModels: DataModelItem[];
  onConfirm: () => void;
  onCancel: () => void;
}

export const ModelDeleteConfirmModal: React.FC<ModelDeleteConfirmModalProps> = ({
  isOpen,
  selectedModels,
  onConfirm,
  onCancel,
}) => {
  if (!isOpen || selectedModels.length === 0) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal-card" style={{ maxWidth: '440px' }}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#dc2626', fontWeight: 700 }}>
            <Trash2 size={16} />
            <span>선택한 모형 삭제</span>
          </div>
          <button className="btn btn-secondary btn-icon" onClick={onCancel}>
            <X size={14} />
          </button>
        </div>

        <div className="modal-body" style={{ padding: '16px 20px' }}>
          <div style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>
            선택한 {selectedModels.length}개의 모형을 삭제하시겠습니까?
          </div>

          <div style={{
            margin: '10px 0 14px 0',
            padding: '10px 14px',
            backgroundColor: '#f8fafc',
            borderRadius: '6px',
            border: '1px solid #e2e8f0',
            maxHeight: '160px',
            overflowY: 'auto'
          }}>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: '12px', color: '#1e293b' }}>
              {selectedModels.map(m => (
                <li key={m.id} style={{ marginBottom: 4, lineHeight: 1.4 }}>
                  <span style={{ fontWeight: 700, color: m.modelType === 'PLAN' ? '#1e40af' : m.modelType === 'ACTUAL' ? '#15803d' : '#854d0e' }}>
                    [{m.modelType === 'PLAN' ? '계획' : m.modelType === 'ACTUAL' ? '실적' : '추정'}]
                  </span>{' '}
                  {m.modelName} <span style={{ color: '#64748b', fontSize: '11px' }}>({m.version})</span>
                </li>
              ))}
            </ul>
          </div>

          <div style={{
            padding: '8px 12px',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '4px',
            fontSize: '11.5px',
            color: '#b91c1c',
            display: 'flex',
            alignItems: 'center',
            gap: 6
          }}>
            <AlertTriangle size={13} color="#dc2626" />
            <span>삭제된 모형은 현재 모형 목록에서 제거됩니다.</span>
          </div>
        </div>

        <div className="modal-footer" style={{ justifyContent: 'flex-end', gap: 8, padding: '12px 20px' }}>
          <button type="button" className="btn btn-secondary" onClick={onCancel} style={{ padding: '6px 14px', fontSize: '12px' }}>
            취소
          </button>
          <button
            type="button"
            className="btn"
            onClick={onConfirm}
            style={{
              padding: '6px 16px',
              fontSize: '12px',
              fontWeight: 700,
              backgroundColor: '#dc2626',
              borderColor: '#b91c1c',
              color: '#ffffff'
            }}
          >
            삭제
          </button>
        </div>
      </div>
    </div>
  );
};

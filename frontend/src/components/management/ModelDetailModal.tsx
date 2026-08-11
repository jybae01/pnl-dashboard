import React from 'react';
import { Modal } from '../common/Modal';
import { DataModelItem } from '../../types/model';
import { ModelTypeBadge, PublishedBadge, CalcStatusBadge } from '../common/StatusBadge';
import { Database, ShieldCheck, FileSpreadsheet, KeyRound } from 'lucide-react';

interface ModelDetailModalProps {
  model: DataModelItem | null;
  isOpen: boolean;
  onClose: () => void;
  onRunCalculation?: (model: DataModelItem) => void;
}

export const ModelDetailModal: React.FC<ModelDetailModalProps> = ({
  model,
  isOpen,
  onClose,
  onRunCalculation,
}) => {
  if (!model) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Database size={16} color="#2563eb" />
          데이터 모델 상세 메타데이터 (Model Inspection)
        </div>
      }
      footer={
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn btn-secondary" onClick={onClose}>
            닫기
          </button>
          {onRunCalculation && (
            <button
              className="btn btn-primary"
              onClick={() => {
                onClose();
                onRunCalculation(model);
              }}
            >
              이 모델로 분석 계산 실행
            </button>
          )}
        </div>
      }
    >
      <div>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: '15px', fontWeight: 800, color: 'var(--text-primary)', marginBottom: 4 }}>
            {model.modelName}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            {model.description}
          </div>
        </div>

        <div className="grid-2col" style={{ gap: 12, marginBottom: 16 }}>
          <div style={{ padding: 12, backgroundColor: '#f8fafc', border: '1px solid var(--border-subtle)', borderRadius: 4 }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 2 }}>모델 구분</div>
            <ModelTypeBadge type={model.modelType} />
          </div>

          <div style={{ padding: 12, backgroundColor: '#f8fafc', border: '1px solid var(--border-subtle)', borderRadius: 4 }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 2 }}>기준월 / 버전</div>
            <div style={{ fontWeight: 700, fontSize: '13px' }}>{model.baseMonth} · {model.version}</div>
          </div>

          <div style={{ padding: 12, backgroundColor: '#f8fafc', border: '1px solid var(--border-subtle)', borderRadius: 4 }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 2 }}>게시 상태</div>
            <PublishedBadge status={model.publishedStatus} />
          </div>

          <div style={{ padding: 12, backgroundColor: '#f8fafc', border: '1px solid var(--border-subtle)', borderRadius: 4 }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: 2 }}>손익 계산 상태</div>
            <CalcStatusBadge status={model.calculationStatus} />
          </div>
        </div>

        {/* Technical Provenance / Checksum Information */}
        <div style={{ padding: 12, backgroundColor: '#f1f5f9', borderRadius: 4, border: '1px solid #cbd5e1' }}>
          <div style={{ fontSize: '11.5px', fontWeight: 700, color: '#334155', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <KeyRound size={13} color="#2563eb" />
            데이터 무결성 검증 해시 (Provenance Integrity Hash)
          </div>
          <div className="font-mono" style={{ fontSize: '11px', color: '#1e293b', wordBreak: 'break-all', backgroundColor: '#ffffff', padding: '6px 8px', borderRadius: 3, border: '1px solid #e2e8f0' }}>
            {model.checksum}
          </div>
          <div style={{ marginTop: 6, display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
            <span>적재 레코드 수: {model.rowCount.toLocaleString()} 건</span>
            <span>등록자: {model.createdBy} ({model.createdDate})</span>
          </div>
        </div>
      </div>
    </Modal>
  );
};

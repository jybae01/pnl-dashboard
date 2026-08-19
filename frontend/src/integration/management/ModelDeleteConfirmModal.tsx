import { AlertTriangle, Trash2, X } from 'lucide-react';
import { AdminModelDto } from '../types';

function modelTypeLabel(type: string): string {
  if (type === 'PLAN') return '계획';
  if (type === 'ACTUAL') return '실적';
  if (type === 'FORECAST') return '추정';
  return '미분류';
}

export function ModelDeleteConfirmModal({
  selectedModels,
  selectedCount,
  pending,
  onCancel,
  onConfirm,
}: {
  selectedModels: AdminModelDto[];
  selectedCount: number;
  pending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return <div className="data-management__modal-backdrop" role="presentation">
    <section className="data-management__modal data-management__modal--delete" role="dialog" aria-modal="true" aria-labelledby="model-delete-confirm-heading">
      <div className="data-management__modal-header">
        <div className="data-management__delete-title"><Trash2 size={16} /><h2 id="model-delete-confirm-heading">선택한 모형 {selectedCount}건 삭제</h2></div>
        <button type="button" className="data-management__icon-button" disabled={pending} aria-label="삭제 확인 닫기" onClick={onCancel}><X size={15} /></button>
      </div>
      <div className="data-management__modal-body">
        <p className="data-management__confirm-copy">선택한 {selectedCount}개의 모형을 영구 삭제하시겠습니까?</p>
        <ul className="data-management__selected-models">{selectedModels.map((model) => <li key={model.model_id}><strong>[{modelTypeLabel(model.model_type)}]</strong> {model.display_name} <span>({model.version})</span></li>)}</ul>
        <p className="data-management__delete-warning"><AlertTriangle size={14} />삭제 후 복구할 수 없습니다. 분석·Forecast 이력에서 참조 중인 모형은 삭제가 차단되며, 차단된 항목의 DB와 Storage는 유지됩니다.</p>
      </div>
      <div className="data-management__modal-footer">
        <button type="button" className="data-management__secondary" disabled={pending} onClick={onCancel}>취소</button>
        <button type="button" className="data-management__danger data-management__danger-solid" disabled={pending} onClick={onConfirm}>{pending ? '삭제 중…' : '영구 삭제'}</button>
      </div>
    </section>
  </div>;
}

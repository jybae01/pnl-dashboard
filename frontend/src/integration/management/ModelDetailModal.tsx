import { Check, Clipboard, Database, X } from 'lucide-react';
import { AdminModelDto } from '../types';
import { modelDateLabel, modelPeriodLabel } from './ModelTable';

function modelTypeLabel(type: string): string {
  if (type === 'PLAN') return '계획';
  if (type === 'ACTUAL') return '실적';
  if (type === 'FORECAST') return '추정';
  return '미분류';
}

export function ModelDetailModal({
  model,
  publicationPending,
  copiedSha,
  onClose,
  onRequestPublication,
  onCopySha,
}: {
  model: AdminModelDto;
  publicationPending: boolean;
  copiedSha: boolean;
  onClose: () => void;
  onRequestPublication: (model: AdminModelDto, isPublished: boolean, isDefault: boolean, label: string) => void;
  onCopySha: (value: string) => void;
}) {
  return <div className="data-management__modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="data-management__modal data-management__modal--detail" role="dialog" aria-modal="true" aria-labelledby="model-detail-heading">
      <div className="data-management__modal-header">
        <div className="data-management__section-title"><Database size={16} aria-hidden="true" /><h2 id="model-detail-heading">데이터 모형 상세 메타데이터</h2></div>
        <button type="button" className="data-management__icon-button" aria-label="모형 상세 닫기" onClick={onClose}><X size={15} /></button>
      </div>
      <div className="data-management__modal-body">
        <div className="data-management__detail-heading"><strong>{model.display_name}</strong><span>{model.file_name}</span></div>
        <dl className="data-management__detail-grid">
          <div><dt>모형 구분</dt><dd>{modelTypeLabel(model.model_type)}</dd></div>
          <div><dt>기준년도 / 적용기간</dt><dd>{model.model_year}년 · {modelPeriodLabel(model)}</dd></div>
          <div><dt>버전</dt><dd>{model.version}</dd></div>
          <div><dt>공개 상태</dt><dd>{model.is_published ? '공개' : '비공개'}{model.is_default ? ' · 기본 모형' : ''}</dd></div>
          <div><dt>등록일시</dt><dd>{modelDateLabel(model.uploaded_at)}</dd></div>
          <div><dt>모형 ID</dt><dd className="data-management__technical-value">{model.model_id}</dd></div>
        </dl>
        <div className="data-management__integrity-box">
          <span>데이터 무결성 검증 해시 (SHA-256)</span>
          {model.workbook_sha256 ? <div><code>{model.workbook_sha256}</code><button type="button" className="data-management__copy" onClick={() => onCopySha(model.workbook_sha256!)}>{copiedSha ? <Check size={13} /> : <Clipboard size={13} />}{copiedSha ? '복사됨' : '복사'}</button></div> : <strong>제공되지 않음</strong>}
        </div>
      </div>
      <div className="data-management__modal-footer">
        <button type="button" className="data-management__secondary" onClick={onClose}>닫기</button>
        {!model.is_published && <><button type="button" className="data-management__primary" disabled={publicationPending} onClick={() => onRequestPublication(model, true, false, '공개')}>공개</button><button type="button" className="data-management__secondary" disabled={publicationPending} onClick={() => onRequestPublication(model, true, true, '공개 및 기본 지정')}>공개 + 기본</button></>}
        {model.is_published && !model.is_default && <button type="button" className="data-management__secondary" disabled={publicationPending} onClick={() => onRequestPublication(model, true, true, '기본 모형 지정')}>기본 모형 지정</button>}
        {model.is_published && <button type="button" className="data-management__danger" disabled={publicationPending} onClick={() => onRequestPublication(model, false, false, '공개 해제')}>공개 해제</button>}
      </div>
    </section>
  </div>;
}

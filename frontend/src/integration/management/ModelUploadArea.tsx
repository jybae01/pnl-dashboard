import { FormEvent, useRef, useState } from 'react';
import { FileSpreadsheet, UploadCloud } from 'lucide-react';

type UploadState = 'IDLE' | 'SELECTED' | 'UPLOADING' | 'SUCCESS' | 'VALIDATION_ERROR' | 'ERROR' | 'FORBIDDEN';
type ModelType = 'PLAN' | 'ACTUAL' | 'FORECAST';

function bytesLabel(value: number): string {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function ModelUploadArea({
  name,
  modelType,
  modelYearDraft,
  version,
  file,
  uploadState,
  uploadMessage,
  onNameChange,
  onModelTypeChange,
  onModelYearDraftChange,
  onVersionChange,
  onFileChange,
  onSubmit,
}: {
  name: string;
  modelType: ModelType;
  modelYearDraft: string;
  version: string;
  file: File | null;
  uploadState: UploadState;
  uploadMessage: string | null;
  onNameChange: (value: string) => void;
  onModelTypeChange: (value: ModelType) => void;
  onModelYearDraftChange: (value: string) => void;
  onVersionChange: (value: string) => void;
  onFileChange: (file: File | null) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadBusy = uploadState === 'UPLOADING';

  return <section className="data-management__upload-card" aria-labelledby="model-upload-heading">
    <div className="data-management__section-heading">
      <div className="data-management__section-title">
        <UploadCloud size={16} aria-hidden="true" />
        <h2 id="model-upload-heading">손익 데이터 모형 등록</h2>
      </div>
      <button
        type="button"
        className="data-management__secondary data-management__template-action"
        disabled
        title="DEFERRED_CAPABILITY: 실제 표준 템플릿 다운로드가 아직 제공되지 않습니다."
      >표준 템플릿 준비 중</button>
    </div>

    <form onSubmit={onSubmit} className="data-management__upload-form" noValidate>
      <div className="data-management__metadata-grid">
        <label>모형명<input aria-label="모형명" value={name} disabled={uploadBusy} onChange={(event) => onNameChange(event.target.value)} required /></label>
        <label>모형 유형<select aria-label="모형 유형" value={modelType} disabled={uploadBusy} onChange={(event) => onModelTypeChange(event.target.value as ModelType)}><option value="PLAN">계획</option><option value="ACTUAL">실적</option><option value="FORECAST">추정</option></select></label>
        <label>기준년도<input
          aria-label="모델 연도"
          type="text"
          inputMode="numeric"
          autoComplete="off"
          value={modelYearDraft}
          disabled={uploadBusy}
          onFocus={(event) => event.currentTarget.select()}
          onChange={(event) => onModelYearDraftChange(event.target.value)}
          required
        /></label>
        <label>버전<input aria-label="버전" value={version} disabled={uploadBusy} onChange={(event) => onVersionChange(event.target.value)} required /></label>
      </div>

      <div
        className={`data-management__dropzone ${isDragging ? 'is-dragging' : ''} ${uploadBusy ? 'is-disabled' : ''}`}
        onDragOver={(event) => { event.preventDefault(); if (!uploadBusy) setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          if (!uploadBusy) onFileChange(event.dataTransfer.files?.[0] || null);
        }}
        onClick={() => { if (!uploadBusy) inputRef.current?.click(); }}
        role="button"
        tabIndex={uploadBusy ? -1 : 0}
        aria-disabled={uploadBusy}
        onKeyDown={(event) => {
          if (!uploadBusy && (event.key === 'Enter' || event.key === ' ')) {
            event.preventDefault(); inputRef.current?.click();
          }
        }}
      >
        <input
          key={file ? `${file.name}-${file.size}` : 'empty'}
          ref={inputRef}
          aria-label="워크북 파일"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          disabled={uploadBusy}
          onClick={(event) => event.stopPropagation()}
          onChange={(event) => onFileChange(event.target.files?.[0] || null)}
        />
        <FileSpreadsheet size={28} className="data-management__dropzone-icon" aria-hidden="true" />
        <strong>{file ? `선택된 파일: ${file.name} (${bytesLabel(file.size)})` : '파일을 선택하거나 이 영역으로 끌어 놓으세요.'}</strong>
        <span>.xlsx 형식만 지원 · 최대 50MiB · 선택한 원본 파일을 그대로 등록합니다.</span>
        {uploadBusy && <span className="data-management__spinner" aria-hidden="true" />}
      </div>

      <div className="data-management__upload-actions">
        <span role="status" data-testid="upload-state">{uploadState === 'UPLOADING' ? '등록 처리 중' : uploadState === 'SUCCESS' ? '등록 완료' : file ? '등록 준비' : '파일 선택 대기'}</span>
        <button type="submit" className="data-management__primary" disabled={uploadBusy || !file}>{uploadBusy ? '등록 처리 중…' : '모형 등록'}</button>
      </div>
      {uploadMessage && <p role={uploadState === 'ERROR' || uploadState === 'VALIDATION_ERROR' || uploadState === 'FORBIDDEN' ? 'alert' : 'status'} className={`data-management__message ${uploadState === 'SUCCESS' ? 'is-success' : ''}`}>{uploadMessage}</p>}
    </form>
  </section>;
}

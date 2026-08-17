import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Clipboard, Database, FileUp, LockKeyhole, RefreshCw, Search, Settings2, ShieldCheck, Trash2, X } from 'lucide-react';
import { ApiClientError, AdminModelDto, PersistentDeleteBatchDto } from './types';
import { bffClient } from './client';
import { CalculationHistoryView } from './CalculationHistoryView';
import { persistentDeleteReason, persistentDeleteSummary } from './persistentDeleteUi';

type ListState = 'LOADING' | 'READY' | 'EMPTY' | 'FILTER_EMPTY' | 'ERROR' | 'FORBIDDEN';
type UploadState = 'IDLE' | 'SELECTED' | 'UPLOADING' | 'SUCCESS' | 'VALIDATION_ERROR' | 'ERROR' | 'FORBIDDEN';
type ModelType = 'PLAN' | 'ACTUAL' | 'FORECAST';
type PublicationFilter = 'ALL' | 'PUBLISHED' | 'UNPUBLISHED';

const MAX_BYTES = 50 * 1024 * 1024;

export interface ModelManagementViewProps {
  onNavigateToForecast?: () => void;
  onNavigateToAnalysis?: () => void;
  onNavigateToAnalysisResult?: (resultId: string) => void;
  initialHistoryOpen?: boolean;
}

type PublicationAction = {
  model: AdminModelDto;
  is_published: boolean;
  is_default: boolean;
  label: string;
};

function modelTypeLabel(type: string): string {
  if (type === 'PLAN') return '계획';
  if (type === 'ACTUAL') return '실적';
  if (type === 'FORECAST') return '추정';
  return '미분류';
}

function modelTypeClass(type: string): string {
  if (type === 'PLAN' || type === 'ACTUAL' || type === 'FORECAST') return type.toLowerCase();
  return 'unknown';
}

function periodLabel(model: Pick<AdminModelDto, 'model_year' | 'start_month' | 'end_month'>): string {
  return `${model.model_year}년 ${model.start_month}~${model.end_month}월`;
}

function dateLabel(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' });
}

function bytesLabel(value: number): string {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function safeMessage(value: unknown): string {
  if (!(value instanceof ApiClientError)) return '요청을 처리할 수 없습니다. 잠시 후 다시 시도하세요.';
  if (value.status === 403 || value.code === 'FORBIDDEN') return '데이터 관리 권한이 없습니다.';
  switch (value.code) {
    case 'VALIDATION_ERROR': return '입력값 또는 파일 형식을 확인하세요.';
    case 'IDEMPOTENCY_CONFLICT': return '같은 등록 키가 다른 내용에 사용되었습니다. 파일을 다시 선택하세요.';
    case 'INPUT_INTEGRITY_MISMATCH': return '모형 결과를 확인할 수 없습니다. 관리자에게 문의하세요.';
    case 'INGESTION_CLEANUP_REQUIRED': return '모형 등록 정리가 완료되지 않았습니다. 관리자에게 문의하세요.';
    case 'MODEL_NOT_FOUND': return '선택한 모형을 찾을 수 없습니다. 목록을 새로 고쳐 주세요.';
    default: return '요청을 처리할 수 없습니다. 잠시 후 다시 시도하세요.';
  }
}

function isForbidden(value: unknown): boolean {
  return value instanceof ApiClientError && (value.status === 403 || value.code === 'FORBIDDEN');
}

export function ModelManagementView({ onNavigateToForecast, onNavigateToAnalysis, onNavigateToAnalysisResult, initialHistoryOpen = false }: ModelManagementViewProps) {
  const [models, setModels] = useState<AdminModelDto[]>([]);
  const [listState, setListState] = useState<ListState>('LOADING');
  const [listMessage, setListMessage] = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>('IDLE');
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [modelType, setModelType] = useState<ModelType>('ACTUAL');
  const [modelYear, setModelYear] = useState(new Date().getFullYear());
  const [version, setVersion] = useState('V1');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<'ALL' | ModelType>('ALL');
  const [publicationFilter, setPublicationFilter] = useState<PublicationFilter>('ALL');
  const [selectedModel, setSelectedModel] = useState<AdminModelDto | null>(null);
  const [pendingPublication, setPendingPublication] = useState<PublicationAction | null>(null);
  const [publicationPending, setPublicationPending] = useState(false);
  const [publicationMessage, setPublicationMessage] = useState<string | null>(null);
  const [publicationError, setPublicationError] = useState(false);
  const [copiedSha, setCopiedSha] = useState(false);
  const [deleteSelection, setDeleteSelection] = useState<Set<string>>(new Set());
  const [deleteConfirmationOpen, setDeleteConfirmationOpen] = useState(false);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteResult, setDeleteResult] = useState<PersistentDeleteBatchDto | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const uploadSubmittingRef = useRef(false);

  const publicationPendingRef = useRef(false);

  const refresh = useCallback(async () => {
    setListState('LOADING');
    setListMessage(null);
    try {
      const rows = await bffClient.adminModels();
      setModels(rows);
      const available = new Set(rows.map((row) => row.model_id));
      setDeleteSelection((current) => new Set([...current].filter((id) => available.has(id))));
      setSelectedModel((current) => current ? rows.find((row) => row.model_id === current.model_id) || null : null);
      setListState(rows.length ? 'READY' : 'EMPTY');
    } catch (value) {
      setModels([]);
      setSelectedModel(null);
      setListState(isForbidden(value) ? 'FORBIDDEN' : 'ERROR');
      setListMessage(safeMessage(value));
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const filteredModels = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('ko-KR');
    return models.filter((model) => {
      const period = periodLabel(model).toLocaleLowerCase('ko-KR');
      const matchesSearch = !needle || [model.display_name, model.file_name, period].some((value) => value.toLocaleLowerCase('ko-KR').includes(needle));
      const matchesType = typeFilter === 'ALL' || model.model_type === typeFilter;
      const matchesPublication = publicationFilter === 'ALL'
        || (publicationFilter === 'PUBLISHED' ? model.is_published : !model.is_published);
      return matchesSearch && matchesType && matchesPublication;
    });
  }, [models, publicationFilter, search, typeFilter]);

  useEffect(() => {
    setDeleteSelection(new Set());
  }, [publicationFilter, search, typeFilter]);

  const visibleListState: ListState = listState === 'READY' && filteredModels.length === 0 ? 'FILTER_EMPTY' : listState;

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] || null;
    setFile(next);
    setIdempotencyKey(next ? crypto.randomUUID() : '');
    setUploadMessage(null);
    setUploadState(next ? 'SELECTED' : 'IDLE');
    if (next && !name) setName(next.name.replace(/\.xlsx$/i, ''));
  }

  function changeMetadata(setter: () => void) {
    setter();
    setIdempotencyKey(crypto.randomUUID());
    setUploadMessage(null);
    if (file) setUploadState('SELECTED');
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (uploadSubmittingRef.current || uploadState === 'UPLOADING') return;
    setUploadMessage(null);
    if (!file) {
      setUploadState('VALIDATION_ERROR'); setUploadMessage('업로드할 .xlsx 파일을 선택하세요.'); return;
    }
    if (!/\.xlsx$/i.test(file.name)) {
      setUploadState('VALIDATION_ERROR'); setUploadMessage('.xlsx 파일만 등록할 수 있습니다.'); return;
    }
    if (file.size > MAX_BYTES) {
      setUploadState('VALIDATION_ERROR'); setUploadMessage('파일이 50MB 제한을 초과했습니다.'); return;
    }
    if (!name.trim() || !version.trim() || !Number.isInteger(modelYear) || modelYear < 2000 || modelYear > 2200) {
      setUploadState('VALIDATION_ERROR'); setUploadMessage('모형명, 연도, 버전을 확인하세요.'); return;
    }
    uploadSubmittingRef.current = true;
    setUploadState('UPLOADING');
    const key = idempotencyKey || crypto.randomUUID();
    if (!idempotencyKey) setIdempotencyKey(key);
    try {
      const response = await bffClient.uploadModel({ name: name.trim(), modelType, modelYear, version: version.trim(), idempotencyKey: key, file });
      setUploadState('SUCCESS');
      setUploadMessage(`${response.model.display_name} · ${periodLabel(response.model)} · ${response.model.is_published ? '공개' : '비공개'} 등록 완료`);
      setSelectedModel(response.model);
      setFile(null);
      await refresh();
    } catch (value) {
      setUploadState(isForbidden(value) ? 'FORBIDDEN' : value instanceof ApiClientError && value.code === 'VALIDATION_ERROR' ? 'VALIDATION_ERROR' : 'ERROR');
      setUploadMessage(safeMessage(value));
    } finally {
      uploadSubmittingRef.current = false;
    }
  }

  function requestPublication(model: AdminModelDto, is_published: boolean, is_default: boolean, label: string) {
    setPublicationMessage(null);
    setPublicationError(false);
    setPendingPublication({ model, is_published, is_default, label });
  }

  async function confirmPublication() {
    if (!pendingPublication || publicationPendingRef.current || publicationPending) return;
    publicationPendingRef.current = true;
    setPublicationPending(true);
    setPublicationMessage(null);
    setPublicationError(false);
    try {
      const updated = await bffClient.publishModel(pendingPublication.model.model_id, {
        is_published: pendingPublication.is_published,
        is_default: pendingPublication.is_default,
      });
      setSelectedModel(updated);
      setPublicationMessage(`${updated.display_name} · ${pendingPublication.label} 완료`);
      setPendingPublication(null);
      await refresh();
    } catch (value) {
      setPublicationError(true);
      setPublicationMessage(safeMessage(value));
    } finally {
      publicationPendingRef.current = false;
      setPublicationPending(false);
    }
  }

  async function copySha(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedSha(true);
      window.setTimeout(() => setCopiedSha(false), 1600);
    } catch {
      setCopiedSha(false);
    }
  }

  async function confirmDelete(ids: string[] = [...deleteSelection]) {
    if (deletePending || ids.length === 0) return;
    setDeletePending(true);
    setDeleteResult(null);
    setDeleteError(null);
    try {
      const result = await bffClient.deleteModels(ids);
      setDeleteResult(result);
      setDeleteSelection(new Set(result.items.filter((item) => item.status !== 'DELETED').map((item) => item.resource_id)));
      setDeleteConfirmationOpen(false);
      await refresh();
    } catch (value) {
      setDeleteError(safeMessage(value));
    } finally {
      setDeletePending(false);
    }
  }

  async function checkDeleteRecovery() {
    if (deletePending) return;
    setDeletePending(true);
    setDeleteError(null);
    try {
      setDeleteResult(await bffClient.modelDeleteRecovery());
    } catch (value) {
      setDeleteError(safeMessage(value));
    } finally {
      setDeletePending(false);
    }
  }

  async function retryDeleteCleanup(ids: string[]) {
    if (deletePending || ids.length === 0) return;
    setDeletePending(true);
    setDeleteError(null);
    try {
      const result = await bffClient.retryModelDeleteCleanup(ids);
      setDeleteResult(result);
      await refresh();
    } catch (value) {
      setDeleteError(safeMessage(value));
    } finally {
      setDeletePending(false);
    }
  }

  const uploadBusy = uploadState === 'UPLOADING';

  return <div className="data-management" aria-labelledby="management-page-heading">
    <header className="view-header-bar data-management__header">
      <div className="data-management__title"><Settings2 size={16} aria-hidden="true" /><h1 id="management-page-heading">손익 모형 데이터 관리</h1></div>
      <div className="data-management__header-actions">
        {onNavigateToForecast && <button type="button" className="data-management__secondary" onClick={onNavigateToForecast}>추정 산출</button>}
        {onNavigateToAnalysis && <button type="button" className="data-management__secondary" onClick={onNavigateToAnalysis}>손익분석 결과</button>}
      </div>
    </header>

    {listState !== 'FORBIDDEN' && <section className="data-management__upload-card" aria-labelledby="model-upload-heading">
      <div className="data-management__section-heading">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 6, backgroundColor: '#eff6ff',
            display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #bfdbfe',
          }}>
            <FileUp size={15} color="#2563eb" />
          </div>
          <div>
            <h2 id="model-upload-heading" style={{ margin: 0, fontSize: '15px' }}>새 모형 등록</h2>
          </div>
        </div>
        <span className="data-management__badge">.xlsx · 최대 50MB</span>
      </div>
      <form onSubmit={upload} className="data-management__upload-form">
        <div className="data-management__metadata-grid">
          <label>모형명<input aria-label="모형명" value={name} disabled={uploadBusy} onChange={(event) => changeMetadata(() => setName(event.target.value))} required /></label>
          <label>모형 유형<select aria-label="모형 유형" value={modelType} disabled={uploadBusy} onChange={(event) => changeMetadata(() => setModelType(event.target.value as ModelType))}><option value="PLAN">계획</option><option value="ACTUAL">실적</option><option value="FORECAST">추정</option></select></label>
          <label>기준 연도<input aria-label="모델 연도" type="number" min="2000" max="2200" value={modelYear} disabled={uploadBusy} onChange={(event) => changeMetadata(() => setModelYear(Number(event.target.value)))} required /></label>
          <label>버전<input aria-label="버전" value={version} disabled={uploadBusy} onChange={(event) => changeMetadata(() => setVersion(event.target.value))} required /></label>
        </div>
        <label className="data-management__file-picker"><span className="data-management__file-icon"><FileUp size={20} /></span><strong>{file ? file.name : 'Excel 모형 파일을 선택하세요'}</strong><small>{file ? `${bytesLabel(file.size)} · 브라우저에서 선택한 원본 파일` : '.xlsx 파일만 등록할 수 있습니다.'}</small><input aria-label="워크북 파일" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={uploadBusy} onChange={selectFile} /></label>
        <div className="data-management__upload-actions"><button type="submit" className="data-management__primary" disabled={uploadBusy || !file}>{uploadBusy ? '등록 처리 중…' : '모형 등록'}</button><span role="status" data-testid="upload-state">{uploadState === 'UPLOADING' ? '등록 처리 중' : uploadState === 'SUCCESS' ? '등록 완료' : file ? '등록 준비' : '파일 선택 대기'}</span></div>
        {uploadMessage && <p role={uploadState === 'ERROR' || uploadState === 'VALIDATION_ERROR' || uploadState === 'FORBIDDEN' ? 'alert' : 'status'} className={`data-management__message ${uploadState === 'SUCCESS' ? 'is-success' : ''}`}>{uploadMessage}</p>}
      </form>
    </section>}

    <section className="data-management__list-card" aria-labelledby="management-list-heading">
      <div className="data-management__section-heading">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 6, backgroundColor: '#eff6ff',
            display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #bfdbfe',
          }}>
            <Database size={15} color="#2563eb" />
          </div>
          <div>
            <h2 id="management-list-heading" style={{ margin: 0, fontSize: '15px' }}>등록 모형 목록</h2>
          </div>
        </div>
        <button type="button" className="data-management__icon-button" onClick={() => void refresh()} aria-label="모형 목록 새로고침"><RefreshCw size={15} /></button>
      </div>
      <div className="data-management__filters"><label className="data-management__search"><Search size={15} /><input aria-label="모형 검색" placeholder="모형명·파일명·기간 검색" value={search} onChange={(event) => setSearch(event.target.value)} /></label><label>유형<select aria-label="유형 필터" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as typeof typeFilter)}><option value="ALL">전체 유형</option><option value="PLAN">계획</option><option value="ACTUAL">실적</option><option value="FORECAST">추정</option></select></label><label>공개 상태<select aria-label="공개 상태 필터" value={publicationFilter} onChange={(event) => setPublicationFilter(event.target.value as PublicationFilter)}><option value="ALL">전체 상태</option><option value="PUBLISHED">공개</option><option value="UNPUBLISHED">비공개</option></select></label></div>
      {listState !== 'FORBIDDEN' && <div className="data-management__bulk-actions"><span>{models.length > 0 ? `${deleteSelection.size}건 선택` : '완료되지 않은 삭제 작업을 확인할 수 있습니다.'}</span><button type="button" className="data-management__secondary" disabled={deletePending} onClick={() => void checkDeleteRecovery()}>모형 삭제 복구 상태 확인</button>{models.length > 0 && <button type="button" className="data-management__danger" aria-label="선택 모형 삭제" disabled={deleteSelection.size === 0 || deletePending} onClick={() => { setDeleteResult(null); setDeleteError(null); setDeleteConfirmationOpen(true); }}><Trash2 size={14} />선택 삭제</button>}</div>}
      {deleteResult && <div className="data-management__delete-result" role="status"><strong>{persistentDeleteSummary(deleteResult)}</strong>{deleteResult.items.some((item) => item.status !== 'DELETED') && <ul>{deleteResult.items.filter((item) => item.status !== 'DELETED').map((item) => <li key={item.resource_id}><code>{item.resource_id}</code> · {persistentDeleteReason(item)}</li>)}</ul>}{deleteResult.items.some((item) => item.status === 'CLEANUP_REQUIRED' || item.status === 'STORAGE_CLEANUP_FAILED') && <button type="button" className="data-management__secondary" disabled={deletePending} onClick={() => void retryDeleteCleanup(deleteResult.items.filter((item) => item.status === 'CLEANUP_REQUIRED' || item.status === 'STORAGE_CLEANUP_FAILED').map((item) => item.resource_id))}>모형 Storage 정리 재시도</button>}</div>}
      {deleteError && <p className="data-management__message" role="alert">{deleteError}</p>}
      {listState === 'LOADING' && <div className="data-management__state" role="status">모형 목록을 확인하고 있습니다…</div>}
      {listState === 'EMPTY' && <div className="data-management__state"><Database size={24} /><h3>등록된 모형이 없습니다.</h3><p>업무에 사용할 .xlsx 모형을 등록하면 이 목록에서 관리할 수 있습니다.</p></div>}
      {listState === 'FORBIDDEN' && <div className="data-management__state"><LockKeyhole size={24} /><h3>데이터 관리 권한이 없습니다.</h3><p role="alert">{listMessage}</p></div>}
      {listState === 'ERROR' && <div className="data-management__state"><ShieldCheck size={24} /><h3>모형 목록을 불러오지 못했습니다.</h3><p role="alert">{listMessage}</p><button type="button" className="data-management__secondary" onClick={() => void refresh()}>다시 시도</button></div>}
      {visibleListState === 'FILTER_EMPTY' && <div className="data-management__filter-empty"><Search size={20} /><strong>조건에 맞는 모형이 없습니다.</strong><span>검색어나 필터를 조정해 보세요.</span></div>}
      {visibleListState === 'READY' && <div className="data-management__table-wrap"><table className="data-management__table"><thead><tr><th><input type="checkbox" aria-label="표시된 모형 전체 선택" checked={filteredModels.length > 0 && filteredModels.every((model) => deleteSelection.has(model.model_id))} onChange={(event) => setDeleteSelection((current) => { const next = new Set(current); filteredModels.forEach((model) => { if (event.target.checked) next.add(model.model_id); else next.delete(model.model_id); }); return next; })} /></th><th>모형</th><th>구분</th><th>적용 기간</th><th>버전</th><th>공개 상태</th><th>등록일</th><th>작업</th></tr></thead><tbody>{filteredModels.map((model) => <tr key={model.model_id} className={selectedModel?.model_id === model.model_id ? 'is-selected' : ''} onClick={() => setSelectedModel(model)}><td><input type="checkbox" aria-label={`${model.display_name} 삭제 선택`} checked={deleteSelection.has(model.model_id)} onClick={(event) => event.stopPropagation()} onChange={(event) => setDeleteSelection((current) => { const next = new Set(current); if (event.target.checked) next.add(model.model_id); else next.delete(model.model_id); return next; })} /></td><td><button type="button" className="data-management__model-link" onClick={(event) => { event.stopPropagation(); setSelectedModel(model); }}>{model.display_name}<small>{model.file_name}</small></button></td><td><span className={`data-management__scenario data-management__scenario--${modelTypeClass(model.model_type)}`}>{modelTypeLabel(model.model_type)}</span></td><td className="tabular-nums">{periodLabel(model)}</td><td className="tabular-nums">{model.version}</td><td><span className={`data-management__publication ${model.is_published ? 'is-published' : ''}`}>{model.is_published ? '공개' : '비공개'}</span>{model.is_default && <span className="data-management__default">기본</span>}</td><td className="tabular-nums">{dateLabel(model.uploaded_at)}</td><td><button type="button" className="data-management__small-action" onClick={(event) => { event.stopPropagation(); setSelectedModel(model); }}>상세</button></td></tr>)}</tbody></table></div>}
    </section>

    {selectedModel && <section className="data-management__detail-card" aria-labelledby="model-detail-heading"><div className="data-management__section-heading"><div><p className="data-management__eyebrow">SELECTED MODEL</p><h2 id="model-detail-heading">{selectedModel.display_name}</h2></div><button type="button" className="data-management__icon-button" aria-label="선택 해제" onClick={() => setSelectedModel(null)}><X size={16} /></button></div><div className="data-management__detail-summary"><div><span>구분</span><strong className={`data-management__scenario data-management__scenario--${modelTypeClass(selectedModel.model_type)}`}>{modelTypeLabel(selectedModel.model_type)}</strong></div><div><span>적용 기간</span><strong>{periodLabel(selectedModel)}</strong></div><div><span>공개 상태</span><strong>{selectedModel.is_published ? '공개' : '비공개'}</strong>{selectedModel.is_default && <span className="data-management__default">기본 모형</span>}</div><div><span>버전</span><strong>{selectedModel.version}</strong></div></div><div className="data-management__detail-actions">{!selectedModel.is_published && <><button type="button" className="data-management__primary" disabled={publicationPending} onClick={() => requestPublication(selectedModel, true, false, '공개')}>공개</button><button type="button" className="data-management__secondary" disabled={publicationPending} onClick={() => requestPublication(selectedModel, true, true, '공개 및 기본 지정')}>공개 + 기본</button></>}{selectedModel.is_published && !selectedModel.is_default && <button type="button" className="data-management__secondary" disabled={publicationPending} onClick={() => requestPublication(selectedModel, true, true, '기본 모형 지정')}>기본 모형 지정</button>}{selectedModel.is_published && <button type="button" className="data-management__danger" disabled={publicationPending} onClick={() => requestPublication(selectedModel, false, false, '공개 해제')}>공개 해제</button>}</div><details className="data-management__technical"><summary>관리자 기술 정보 <ChevronDown size={15} /></summary><dl><div><dt>모형 ID</dt><dd>{selectedModel.model_id}</dd></div><div><dt>파일명</dt><dd>{selectedModel.file_name}</dd></div><div><dt>등록일</dt><dd>{dateLabel(selectedModel.uploaded_at)}</dd></div><div><dt>SHA-256</dt><dd>{selectedModel.workbook_sha256 ? <span className="data-management__sha"><code>{selectedModel.workbook_sha256}</code><button type="button" className="data-management__copy" onClick={() => void copySha(selectedModel.workbook_sha256!)}>{copiedSha ? <Check size={13} /> : <Clipboard size={13} />} {copiedSha ? '복사됨' : '복사'}</button></span> : '제공되지 않음'}</dd></div></dl></details></section>}

    {publicationMessage && <p className={`data-management__global-message ${publicationError ? 'is-error' : ''}`} role={publicationError ? 'alert' : 'status'}>{publicationMessage}</p>}
    {listState !== 'LOADING' && listState !== 'FORBIDDEN' && <section className="data-management__history-card" aria-label="계산 이력" data-history-requested={initialHistoryOpen || undefined}>
      <CalculationHistoryView onOpenResult={onNavigateToAnalysisResult} />
    </section>}
    {pendingPublication && <div className="data-management__modal-backdrop" role="presentation"><section className="data-management__modal" role="dialog" aria-modal="true" aria-labelledby="publication-confirm-heading"><p className="data-management__eyebrow">PUBLICATION CONFIRMATION</p><h2 id="publication-confirm-heading">{pendingPublication.label}</h2><p><strong>{pendingPublication.model.display_name}</strong><br />{periodLabel(pendingPublication.model)}</p><p className="data-management__modal-copy">{pendingPublication.is_published ? (pendingPublication.is_default ? '이 모형을 공개하고 기본 모형으로 지정합니다.' : '이 모형을 공개합니다.') : '이 모형의 공개를 해제하고 기본 모형 지정도 함께 해제합니다.'}</p><div className="data-management__modal-actions"><button type="button" className="data-management__secondary" disabled={publicationPending} onClick={() => setPendingPublication(null)}>취소</button><button type="button" className={pendingPublication.is_published ? 'data-management__primary' : 'data-management__danger'} disabled={publicationPending} onClick={() => void confirmPublication()}>{publicationPending ? '처리 중…' : '확인'}</button></div></section></div>}
    {deleteConfirmationOpen && <div className="data-management__modal-backdrop" role="presentation"><section className="data-management__modal" role="dialog" aria-modal="true" aria-labelledby="model-delete-confirm-heading"><p className="data-management__eyebrow">HARD DELETE</p><h2 id="model-delete-confirm-heading">선택한 모형 {deleteSelection.size}건을 삭제할까요?</h2><p className="data-management__modal-copy">삭제 후 복구할 수 없습니다. 분석·Forecast 이력에서 참조 중인 모형은 삭제가 차단되며, 차단된 항목의 DB와 Storage는 유지됩니다.</p><div className="data-management__modal-actions"><button type="button" className="data-management__secondary" disabled={deletePending} onClick={() => setDeleteConfirmationOpen(false)}>취소</button><button type="button" className="data-management__danger" disabled={deletePending} onClick={() => void confirmDelete()}>{deletePending ? '삭제 중…' : '영구 삭제'}</button></div></section></div>}
  </div>;
}

import { Database, Filter, LockKeyhole, RefreshCw, Search, ShieldCheck, Trash2 } from 'lucide-react';
import { persistentDeleteReason, persistentDeleteSummary } from '../persistentDeleteUi';
import { AdminModelDto, PersistentDeleteBatchDto } from '../types';

export type ModelListState = 'LOADING' | 'READY' | 'EMPTY' | 'FILTER_EMPTY' | 'ERROR' | 'FORBIDDEN';

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

export function modelPeriodLabel(model: Pick<AdminModelDto, 'model_year' | 'start_month' | 'end_month'>): string {
  return `${model.start_month}~${model.end_month}월`;
}

export function modelDateLabel(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' });
}

export function ModelTable({
  models,
  filteredModels,
  listState,
  visibleListState,
  listMessage,
  selectedModelId,
  deleteSelection,
  deletePending,
  deleteResult,
  deleteError,
  onRefresh,
  onSelectAll,
  onToggleSelection,
  onSelectModel,
  onOpenDelete,
  onCheckDeleteRecovery,
  onRetryDeleteCleanup,
}: {
  models: AdminModelDto[];
  filteredModels: AdminModelDto[];
  listState: ModelListState;
  visibleListState: ModelListState;
  listMessage: string | null;
  selectedModelId: string | null;
  deleteSelection: Set<string>;
  deletePending: boolean;
  deleteResult: PersistentDeleteBatchDto | null;
  deleteError: string | null;
  onRefresh: () => void;
  onSelectAll: (checked: boolean) => void;
  onToggleSelection: (modelId: string, checked: boolean) => void;
  onSelectModel: (model: AdminModelDto) => void;
  onOpenDelete: () => void;
  onCheckDeleteRecovery: () => void;
  onRetryDeleteCleanup: (ids: string[]) => void;
}) {
  const allVisibleSelected = filteredModels.length > 0 && filteredModels.every((model) => deleteSelection.has(model.model_id));

  return <section className="data-management__table-card" aria-labelledby="management-list-heading">
    <div className="data-management__table-card-header">
      <div className="data-management__section-title">
        <Filter size={16} aria-hidden="true" />
        <h2 id="management-list-heading">손익 데이터 모형 목록</h2>
      </div>
      <div className="data-management__table-card-actions">
        <span className="data-management__model-count">총 {models.length}건</span>
        <span className="data-management__selection-count" aria-live="polite">{deleteSelection.size}건 선택</span>
        <button type="button" className="data-management__secondary data-management__compact-action" disabled={deletePending} onClick={onCheckDeleteRecovery}>모형 삭제 복구 상태 확인</button>
        <button type="button" className="data-management__danger data-management__compact-action" aria-label="선택 모형 삭제" disabled={deleteSelection.size === 0 || deletePending} onClick={onOpenDelete}><Trash2 size={13} />선택 삭제{deleteSelection.size > 0 ? ` (${deleteSelection.size})` : ''}</button>
        <button type="button" className="data-management__icon-button" onClick={onRefresh} aria-label="모형 목록 새로고침"><RefreshCw size={14} /></button>
      </div>
    </div>

    {deleteResult && <div className="data-management__delete-result" role="status"><strong>{persistentDeleteSummary(deleteResult)}</strong>{deleteResult.items.some((item) => item.status !== 'DELETED') && <ul>{deleteResult.items.filter((item) => item.status !== 'DELETED').map((item) => <li key={item.resource_id}><code>{item.resource_id}</code> · {persistentDeleteReason(item)}</li>)}</ul>}{deleteResult.items.some((item) => item.status === 'CLEANUP_REQUIRED' || item.status === 'STORAGE_CLEANUP_FAILED') && <button type="button" className="data-management__secondary" disabled={deletePending} onClick={() => onRetryDeleteCleanup(deleteResult.items.filter((item) => item.status === 'CLEANUP_REQUIRED' || item.status === 'STORAGE_CLEANUP_FAILED').map((item) => item.resource_id))}>모형 Storage 정리 재시도</button>}</div>}
    {deleteError && <p className="data-management__message data-management__table-message" role="alert">{deleteError}</p>}
    {listState === 'LOADING' && <div className="data-management__state" role="status"><span className="data-management__spinner" aria-hidden="true" />모형 목록을 확인하고 있습니다…</div>}
    {listState === 'EMPTY' && <div className="data-management__state"><Database size={30} /><h3>등록된 모형이 없습니다.</h3><p>업무에 사용할 .xlsx 모형을 등록하면 이 목록에서 관리할 수 있습니다.</p></div>}
    {listState === 'FORBIDDEN' && <div className="data-management__state"><LockKeyhole size={30} /><h3>데이터 관리 권한이 없습니다.</h3><p role="alert">{listMessage}</p></div>}
    {listState === 'ERROR' && <div className="data-management__state"><ShieldCheck size={30} /><h3>모형 목록을 불러오지 못했습니다.</h3><p role="alert">{listMessage}</p><button type="button" className="data-management__secondary" onClick={onRefresh}>다시 시도</button></div>}
    {visibleListState === 'FILTER_EMPTY' && <div className="data-management__filter-empty"><Search size={24} /><strong>조건에 맞는 모형이 없습니다.</strong><span>검색어나 필터를 조정해 보세요.</span></div>}

    {visibleListState === 'READY' && <div className="data-management__table-wrap">
      <table className="data-management__table">
        <colgroup><col className="col-select" /><col className="col-model" /><col className="col-type" /><col className="col-year" /><col className="col-period" /><col className="col-version" /><col className="col-date" /><col className="col-publication" /><col className="col-default" /><col className="col-detail" /></colgroup>
        <thead><tr><th className="text-center"><input type="checkbox" aria-label="표시된 모형 전체 선택" checked={allVisibleSelected} onChange={(event) => onSelectAll(event.target.checked)} /></th><th>모형명</th><th className="text-center">구분</th><th className="text-center">기준년도</th><th className="text-center">적용기간</th><th className="text-center">버전</th><th>등록일시</th><th className="text-center">공개 상태</th><th className="text-center">기본 지정</th><th className="text-center">상세</th></tr></thead>
        <tbody>{filteredModels.map((model) => {
          const deleteSelected = deleteSelection.has(model.model_id);
          return <tr key={model.model_id} className={deleteSelected || selectedModelId === model.model_id ? 'is-selected' : ''}>
            <td className="text-center"><input type="checkbox" aria-label={`${model.display_name} 삭제 선택`} checked={deleteSelected} onChange={(event) => onToggleSelection(model.model_id, event.target.checked)} /></td>
            <td><button type="button" className="data-management__model-link" onClick={() => onSelectModel(model)}>{model.display_name}<small>{model.file_name}</small></button></td>
            <td className="text-center"><span className={`data-management__scenario data-management__scenario--${modelTypeClass(model.model_type)}`}>{modelTypeLabel(model.model_type)}</span></td>
            <td className="text-center tabular-nums">{model.model_year}</td>
            <td className="text-center tabular-nums">{modelPeriodLabel(model)}</td>
            <td className="text-center tabular-nums"><strong>{model.version}</strong></td>
            <td className="tabular-nums data-management__date-cell">{modelDateLabel(model.uploaded_at)}</td>
            <td className="text-center"><span className={`data-management__publication ${model.is_published ? 'is-published' : ''}`}>{model.is_published ? '공개' : '비공개'}</span></td>
            <td className="text-center"><span className={`data-management__default ${model.is_default ? 'is-default' : ''}`}>{model.is_default ? '기본' : '—'}</span></td>
            <td className="text-center"><button type="button" className="data-management__detail-button" onClick={() => onSelectModel(model)}>상세</button></td>
          </tr>;
        })}</tbody>
      </table>
    </div>}
  </section>;
}

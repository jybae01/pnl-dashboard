import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { ApiClientError, AdminModelDto, PersistentDeleteBatchDto } from './types';
import {
  bffClient,
  PnlReportingWorkbookValidationError,
  type PnlReportingUploadResponseDto,
  type PnlReportingValidationIssueDto,
} from './client';
import { CalculationHistoryView } from './CalculationHistoryView';
import { ManagementHeader } from './management/ManagementHeader';
import { ModelUploadArea } from './management/ModelUploadArea';
import { ModelListState, ModelTable, modelPeriodLabel } from './management/ModelTable';
import { ModelDetailModal } from './management/ModelDetailModal';
import { ModelDeleteConfirmModal } from './management/ModelDeleteConfirmModal';
import {
  PnlReportingUploadSection,
  type PnlReportingActualSubmitPayload,
  type PnlReportingExistingDatasetSummary,
  type PnlReportingPlanSubmitPayload,
  type PnlReportingUploadPresentation,
  type PnlReportingValidationIssue,
  type PnlReportingValidationSummary,
} from './management/PnlReportingUploadSection';

type UploadState = 'IDLE' | 'SELECTED' | 'UPLOADING' | 'SUCCESS' | 'VALIDATION_ERROR' | 'ERROR' | 'FORBIDDEN';
type ModelType = 'PLAN' | 'ACTUAL' | 'FORECAST';
type PublicationFilter = 'ALL' | 'PUBLISHED' | 'UNPUBLISHED';

const MAX_BYTES = 50 * 1024 * 1024;

export interface ModelManagementViewProps {
  onNavigateToForecast?: () => void;
  onNavigateToAnalysis?: () => void;
  onNavigateToAnalysisResult?: (resultId: string) => void;
  initialHistoryOpen?: boolean;
  onPnlReportingChanged?: () => void;
}

type PnlUploadAttempt = {
  file: File;
  reportingYear: number;
  actualThroughMonth: number | null;
  idempotencyKey: string;
};

const PNL_UPLOAD_IDLE: PnlReportingUploadPresentation = { status: 'IDLE' };

function uploadIssue(issue: PnlReportingValidationIssueDto): PnlReportingValidationIssue {
  return {
    ...issue,
    severity: issue.severity === 'BLOCKING' ? 'ERROR' : 'WARNING',
  };
}

function successValidation(response: PnlReportingUploadResponseDto): PnlReportingValidationSummary {
  return {
    status: 'VALID',
    errorCount: 0,
    warningCount: response.warnings.length,
    truncated: false,
    errors: [],
    warnings: response.warnings.map(uploadIssue),
  };
}

function invalidValidation(value: PnlReportingWorkbookValidationError): PnlReportingValidationSummary {
  return {
    ...value.summary,
    errors: value.summary.errors.map(uploadIssue),
    warnings: value.summary.warnings.map(uploadIssue),
  };
}

function fieldValidation(value: ApiClientError): PnlReportingValidationSummary {
  const errors = Object.entries(value.fieldErrors).map(([field, message]): PnlReportingValidationIssue => ({
    severity: 'ERROR',
    errorCode: 'VALIDATION_ERROR',
    field,
    message,
  }));
  return {
    status: 'INVALID',
    errorCount: errors.length,
    warningCount: 0,
    truncated: false,
    errors,
    warnings: [],
  };
}

function pnlUploadMessage(value: unknown): string {
  if (!(value instanceof ApiClientError)) return '업로드 요청을 처리할 수 없습니다. 같은 파일로 다시 시도하세요.';
  if (value.status === 401 || value.code === 'AUTH_REQUIRED') return '로그인 세션이 만료되었습니다. 다시 로그인하세요.';
  if (value.status === 403) return 'P&L Reporting 업로드 권한 또는 CSRF 보안 토큰을 확인하세요.';
  if (value.code === 'IDEMPOTENCY_CONFLICT') return '동일한 업로드 키가 다른 입력에 사용되었습니다. 자동 재시도하지 않았습니다.';
  if (value.code === 'INPUT_INTEGRITY_MISMATCH') return '업로드 입력 무결성을 확인할 수 없습니다. 관리자에게 문의하세요.';
  if (value.code === 'INGESTION_CLEANUP_REQUIRED') return '업로드 정리가 필요합니다. 관리자 복구 절차를 진행하세요.';
  if (value.status === 0 || value.status === 503) return '일시적인 연결 오류입니다. 같은 업로드 키로 다시 시도할 수 있습니다.';
  if (value.status === 422 || value.code === 'VALIDATION_ERROR') return '업로드 입력값 또는 workbook 검증 결과를 확인하세요.';
  return '업로드 요청을 처리할 수 없습니다. 같은 파일로 다시 시도하세요.';
}

function pnlTemplateDownloadMessage(value: unknown): string {
  if (!(value instanceof ApiClientError)) return 'P&L Reporting 표준 양식을 내려받을 수 없습니다. 잠시 후 다시 시도하세요.';
  if (value.status === 401 || value.code === 'AUTH_REQUIRED') return '로그인 세션이 만료되었습니다. 다시 로그인하세요.';
  if (value.status === 403 || value.code === 'FORBIDDEN') return 'P&L Reporting 표준 양식 다운로드 권한이 없습니다.';
  if (value.status >= 500 || value.code === 'INPUT_INTEGRITY_MISMATCH') {
    return 'P&L Reporting 표준 양식을 내려받을 수 없습니다. 시스템 관리자에게 문의하세요.';
  }
  if (value.status === 0) return '다운로드 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.';
  return 'P&L Reporting 표준 양식을 내려받을 수 없습니다. 잠시 후 다시 시도하세요.';
}

type PublicationAction = {
  model: AdminModelDto;
  is_published: boolean;
  is_default: boolean;
  label: string;
};

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

export function ModelManagementView({ onNavigateToForecast, onNavigateToAnalysis, onNavigateToAnalysisResult, initialHistoryOpen = false, onPnlReportingChanged }: ModelManagementViewProps) {
  const [models, setModels] = useState<AdminModelDto[]>([]);
  const [listState, setListState] = useState<ModelListState>('LOADING');
  const [listMessage, setListMessage] = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>('IDLE');
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [modelType, setModelType] = useState<ModelType>('ACTUAL');
  const [modelYearDraft, setModelYearDraft] = useState(String(new Date().getFullYear()));
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
  const [pnlPlanState, setPnlPlanState] = useState<PnlReportingUploadPresentation>(PNL_UPLOAD_IDLE);
  const [pnlActualState, setPnlActualState] = useState<PnlReportingUploadPresentation>(PNL_UPLOAD_IDLE);
  const [pnlValidation, setPnlValidation] = useState<PnlReportingValidationSummary | null>(null);
  const [existingPnlPlan, setExistingPnlPlan] = useState<PnlReportingExistingDatasetSummary | null>(null);
  const [existingPnlActual, setExistingPnlActual] = useState<PnlReportingExistingDatasetSummary | null>(null);
  const [pnlTemplateError, setPnlTemplateError] = useState<string | null>(null);
  const pnlPlanAttempt = useRef<PnlUploadAttempt | null>(null);
  const pnlActualAttempt = useRef<PnlUploadAttempt | null>(null);
  const pnlPlanPending = useRef(false);
  const pnlActualPending = useRef(false);
  const pnlTemplatePending = useRef(false);

  const publicationPendingRef = useRef(false);

  function uploadKey(
    current: PnlUploadAttempt | null,
    file: File,
    reportingYear: number,
    actualThroughMonth: number | null,
  ): PnlUploadAttempt {
    if (current
      && current.file === file
      && current.reportingYear === reportingYear
      && current.actualThroughMonth === actualThroughMonth) return current;
    return { file, reportingYear, actualThroughMonth, idempotencyKey: crypto.randomUUID() };
  }

  async function submitPnlPlan(payload: PnlReportingPlanSubmitPayload) {
    if (pnlPlanPending.current) return;
    const attempt = uploadKey(pnlPlanAttempt.current, payload.file, payload.reportingYear, null);
    pnlPlanAttempt.current = attempt;
    pnlPlanPending.current = true;
    setPnlPlanState({ status: 'PENDING' });
    setPnlValidation(null);
    try {
      const response = await bffClient.uploadPnlReportingPlan({
        reportingYear: payload.reportingYear,
        idempotencyKey: attempt.idempotencyKey,
        file: payload.file,
      });
      setPnlPlanState({
        status: 'SUCCESS',
        reportingYear: response.reportingYear,
        registeredAt: response.uploadedAt,
        replacedExisting: response.supersededDatasetId !== null,
        warningCount: response.warnings.length,
      });
      setExistingPnlPlan({ reportingYear: response.reportingYear, registeredAt: response.uploadedAt });
      setPnlValidation(successValidation(response));
      pnlPlanAttempt.current = null;
      onPnlReportingChanged?.();
    } catch (value) {
      if (value instanceof PnlReportingWorkbookValidationError) {
        setPnlPlanState({ status: 'INVALID', message: pnlUploadMessage(value) });
        setPnlValidation(invalidValidation(value));
      } else {
        setPnlPlanState({ status: value instanceof ApiClientError && value.status === 422 ? 'INVALID' : 'ERROR', message: pnlUploadMessage(value) });
        setPnlValidation(value instanceof ApiClientError && value.status === 422 ? fieldValidation(value) : {
          status: 'ERROR', errorCount: 0, warningCount: 0, truncated: false, errors: [], warnings: [],
        });
      }
    } finally {
      pnlPlanPending.current = false;
    }
  }

  async function submitPnlActual(payload: PnlReportingActualSubmitPayload) {
    if (pnlActualPending.current) return;
    const attempt = uploadKey(pnlActualAttempt.current, payload.file, payload.reportingYear, payload.actualThroughMonth);
    pnlActualAttempt.current = attempt;
    pnlActualPending.current = true;
    setPnlActualState({ status: 'PENDING' });
    setPnlValidation(null);
    try {
      const response = await bffClient.uploadPnlReportingActual({
        reportingYear: payload.reportingYear,
        actualThroughMonth: payload.actualThroughMonth,
        idempotencyKey: attempt.idempotencyKey,
        file: payload.file,
      });
      setPnlActualState({
        status: 'SUCCESS',
        reportingYear: response.reportingYear,
        actualThroughMonth: response.actualThroughMonth ?? undefined,
        registeredAt: response.uploadedAt,
        replacedExisting: response.supersededDatasetId !== null,
        warningCount: response.warnings.length,
      });
      setExistingPnlActual({
        reportingYear: response.reportingYear,
        actualThroughMonth: response.actualThroughMonth ?? undefined,
        registeredAt: response.uploadedAt,
      });
      setPnlValidation(successValidation(response));
      pnlActualAttempt.current = null;
      onPnlReportingChanged?.();
    } catch (value) {
      if (value instanceof PnlReportingWorkbookValidationError) {
        setPnlActualState({ status: 'INVALID', message: pnlUploadMessage(value) });
        setPnlValidation(invalidValidation(value));
      } else {
        setPnlActualState({ status: value instanceof ApiClientError && value.status === 422 ? 'INVALID' : 'ERROR', message: pnlUploadMessage(value) });
        setPnlValidation(value instanceof ApiClientError && value.status === 422 ? fieldValidation(value) : {
          status: 'ERROR', errorCount: 0, warningCount: 0, truncated: false, errors: [], warnings: [],
        });
      }
    } finally {
      pnlActualPending.current = false;
    }
  }

  async function downloadPnlReportingTemplate() {
    if (pnlTemplatePending.current) return;
    pnlTemplatePending.current = true;
    setPnlTemplateError(null);
    try {
      await bffClient.downloadPnlReportingTemplate();
    } catch (value) {
      setPnlTemplateError(pnlTemplateDownloadMessage(value));
    } finally {
      pnlTemplatePending.current = false;
    }
  }

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
      const period = `${model.model_year}년 ${modelPeriodLabel(model)}`.toLocaleLowerCase('ko-KR');
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

  const visibleListState: ModelListState = listState === 'READY' && filteredModels.length === 0 ? 'FILTER_EMPTY' : listState;

  function selectFile(next: File | null) {
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
      setUploadState('VALIDATION_ERROR'); setUploadMessage('파일이 50MiB 제한을 초과했습니다.'); return;
    }
    const normalizedYear = modelYearDraft.trim();
    const modelYear = Number(normalizedYear);
    if (!name.trim() || !version.trim() || !/^\d{4}$/.test(normalizedYear) || !Number.isInteger(modelYear) || modelYear < 2000 || modelYear > 2200) {
      setUploadState('VALIDATION_ERROR'); setUploadMessage('모형명, 연도, 버전을 확인하세요.'); return;
    }
    uploadSubmittingRef.current = true;
    setUploadState('UPLOADING');
    const key = idempotencyKey || crypto.randomUUID();
    if (!idempotencyKey) setIdempotencyKey(key);
    try {
      const response = await bffClient.uploadModel({ name: name.trim(), modelType, modelYear, version: version.trim(), idempotencyKey: key, file });
      setUploadState('SUCCESS');
      setUploadMessage(`${response.model.display_name} · ${response.model.model_year}년 ${modelPeriodLabel(response.model)} · ${response.model.is_published ? '공개' : '비공개'} 등록 완료`);
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
    setSelectedModel(null);
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

  const selectedDeleteModels = models.filter((model) => deleteSelection.has(model.model_id));

  return <div className="data-management" aria-labelledby="management-page-heading">
    <ManagementHeader
      search={search}
      typeFilter={typeFilter}
      publicationFilter={publicationFilter}
      onSearchChange={setSearch}
      onTypeFilterChange={setTypeFilter}
      onPublicationFilterChange={setPublicationFilter}
      onNavigateToForecast={onNavigateToForecast}
      onNavigateToAnalysis={onNavigateToAnalysis}
    />

    {listState !== 'FORBIDDEN' && <ModelUploadArea
      name={name}
      modelType={modelType}
      modelYearDraft={modelYearDraft}
      version={version}
      file={file}
      uploadState={uploadState}
      uploadMessage={uploadMessage}
      onNameChange={(value) => changeMetadata(() => setName(value))}
      onModelTypeChange={(value) => changeMetadata(() => setModelType(value))}
      onModelYearDraftChange={(value) => changeMetadata(() => setModelYearDraft(value))}
      onVersionChange={(value) => changeMetadata(() => setVersion(value))}
      onFileChange={selectFile}
      onSubmit={upload}
    />}

    <PnlReportingUploadSection
      templateDownloadAvailable
      onTemplateDownload={() => void downloadPnlReportingTemplate()}
      planState={pnlPlanState}
      actualState={pnlActualState}
      validationSummary={pnlValidation}
      existingPlan={existingPnlPlan}
      existingActual={existingPnlActual}
      onPlanSubmit={(payload) => void submitPnlPlan(payload)}
      onActualSubmit={(payload) => void submitPnlActual(payload)}
    />

    {pnlTemplateError && <div className="data-management__notice is-error" role="alert">{pnlTemplateError}</div>}

    {publicationMessage && <div className={`data-management__notice ${publicationError ? 'is-error' : 'is-success'}`} role={publicationError ? 'alert' : 'status'}>{publicationMessage}</div>}

    <ModelTable
      models={models}
      filteredModels={filteredModels}
      listState={listState}
      visibleListState={visibleListState}
      listMessage={listMessage}
      selectedModelId={selectedModel?.model_id || null}
      deleteSelection={deleteSelection}
      deletePending={deletePending}
      deleteResult={deleteResult}
      deleteError={deleteError}
      onRefresh={() => void refresh()}
      onSelectAll={(checked) => setDeleteSelection((current) => {
        const next = new Set(current);
        filteredModels.forEach((model) => { if (checked) next.add(model.model_id); else next.delete(model.model_id); });
        return next;
      })}
      onToggleSelection={(modelId, checked) => setDeleteSelection((current) => {
        const next = new Set(current);
        if (checked) next.add(modelId); else next.delete(modelId);
        return next;
      })}
      onSelectModel={setSelectedModel}
      onOpenDelete={() => { setDeleteResult(null); setDeleteError(null); setDeleteConfirmationOpen(true); }}
      onCheckDeleteRecovery={() => void checkDeleteRecovery()}
      onRetryDeleteCleanup={(ids) => void retryDeleteCleanup(ids)}
    />

    {listState !== 'LOADING' && listState !== 'FORBIDDEN' && <section className="data-management__history-card" aria-label="계산 이력" data-history-requested={initialHistoryOpen || undefined}>
      <CalculationHistoryView onOpenResult={onNavigateToAnalysisResult} />
    </section>}

    <div className="data-management__dialog-region">
      {selectedModel && <ModelDetailModal
        model={selectedModel}
        publicationPending={publicationPending}
        copiedSha={copiedSha}
        onClose={() => setSelectedModel(null)}
        onRequestPublication={requestPublication}
        onCopySha={(value) => void copySha(value)}
      />}

      {pendingPublication && <div className="data-management__modal-backdrop" role="presentation">
        <section className="data-management__modal data-management__modal--confirm" role="dialog" aria-modal="true" aria-labelledby="publication-confirm-heading">
          <header className="data-management__modal-header"><span className="data-management__modal-icon is-warning"><AlertTriangle size={17} /></span><div><p className="data-management__eyebrow">PUBLICATION CONFIRMATION</p><h2 id="publication-confirm-heading">{pendingPublication.label}</h2></div></header>
          <div className="data-management__modal-body"><p><strong>{pendingPublication.model.display_name}</strong><br />{pendingPublication.model.model_year}년 {modelPeriodLabel(pendingPublication.model)}</p><p className="data-management__modal-copy">{pendingPublication.is_published ? (pendingPublication.is_default ? '이 모형을 공개하고 기본 모형으로 지정합니다.' : '이 모형을 공개합니다.') : '이 모형의 공개를 해제하고 기본 모형 지정도 함께 해제합니다.'}</p></div>
          <footer className="data-management__modal-footer"><button type="button" className="data-management__secondary" disabled={publicationPending} onClick={() => setPendingPublication(null)}>취소</button><button type="button" className={pendingPublication.is_published ? 'data-management__primary' : 'data-management__danger'} disabled={publicationPending} onClick={() => void confirmPublication()}>{publicationPending ? '처리 중…' : '확인'}</button></footer>
        </section>
      </div>}

      {deleteConfirmationOpen && <ModelDeleteConfirmModal
        selectedModels={selectedDeleteModels}
        selectedCount={deleteSelection.size}
        pending={deletePending}
        onCancel={() => setDeleteConfirmationOpen(false)}
        onConfirm={() => void confirmDelete()}
      />}
    </div>
  </div>;
}

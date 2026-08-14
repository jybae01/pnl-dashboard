import {
  AnalysisModelDto,
  AdminModelDto,
  ApiClientError,
  ApiErrorDto,
  JobStatusDto,
  SessionDto,
  StoredResultDto,
  SubmitRequest,
  SubmitResponse,
  ModelUploadInput,
  ModelUploadResponse,
  CalculationHistoryDto,
  CalculationHistoryItemDto,
  ResultPublicationDto,
  Role,
  AnalysisPresentationDto,
  AnalysisPresentationEffectDto,
  PnlDashboardDto,
  ForecastGenerateRequestDto,
  ForecastGenerateResponseDto,
  ForecastExcelPreviewDto,
  ForecastInputMetadataDto,
  WorkerStatusDto,
} from './types';

const API_ROOT = (import.meta.env.VITE_BFF_BASE_URL || '').replace(/\/$/, '');

function csrfToken(): string {
  const entry = document.cookie
    .split('; ')
    .find((value) => value.startsWith('pnl_csrf='));
  if (!entry) return '';
  try { return decodeURIComponent(entry.slice('pnl_csrf='.length)); } catch { return ''; }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (init.method && !['GET', 'HEAD'].includes(init.method.toUpperCase()) && path !== '/api/session/login') {
    headers.set('X-CSRF-Token', csrfToken());
  }
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      ...init,
      headers,
      credentials: 'include',
    });
  } catch {
    throw new ApiClientError(0, 'TRANSIENT_SYSTEM_ERROR', '서버에 연결할 수 없습니다.');
  }
  if (!response.ok) {
    let payload: ApiErrorDto | null = null;
    try {
      const candidate: unknown = await response.json();
      if (isRecord(candidate) && isRecord(candidate.error) && typeof candidate.error.code === 'string' && typeof candidate.error.message === 'string') {
        payload = candidate as unknown as ApiErrorDto;
      }
    } catch { /* safe fallback */ }
    throw new ApiClientError(
      response.status,
      payload?.error.code || 'TRANSIENT_SYSTEM_ERROR',
      payload?.error.message || '요청을 처리할 수 없습니다.',
      payload?.error.correlation_id || response.headers.get('X-Correlation-ID'),
      parseRetryAfter(response.headers.get('Retry-After')),
    );
  }
  return response.json() as Promise<T>;
}

function parseRetryAfter(value: string | null): number | null {
  if (value === null || !/^\d+$/.test(value)) return null;
  const seconds = Number(value);
  return Number.isSafeInteger(seconds) && seconds > 0 ? seconds : null;
}

export const bffClient = {
  login: async (accessCode: string) => validateSession(await request<unknown>('/api/session/login', {
    method: 'POST', body: JSON.stringify({ access_code: accessCode }),
  })),
  session: async () => validateSession(await request<unknown>('/api/session')),
  logout: () => request<{ authenticated: false }>('/api/session/logout', { method: 'POST' }),
  models: async () => validateModels(await request<unknown>('/api/models')),
  adminModels: async () => validateAdminModels(await request<unknown>('/api/admin/models')),
  uploadModel: async (input: ModelUploadInput) => {
    const body = new FormData();
    body.set('name', input.name);
    body.set('model_type', input.modelType);
    body.set('model_year', String(input.modelYear));
    body.set('version', input.version);
    body.set('idempotency_key', input.idempotencyKey);
    body.set('file', input.file, input.file.name);
    return validateModelUpload(await request<unknown>('/api/admin/models', { method: 'POST', body }));
  },
  publishModel: async (modelId: string, publication: boolean | { is_published: boolean; is_default: boolean } = false) => validateAdminModelResponse(
    await request<unknown>(`/api/admin/models/${modelId}/publication`, {
      method: 'POST', body: JSON.stringify(typeof publication === 'boolean'
        ? { is_published: true, is_default: publication }
        : publication),
    }),
  ),
  submit: async (body: SubmitRequest) => validateSubmit(await request<unknown>('/api/analyses', {
    method: 'POST', body: JSON.stringify(body),
  })),
  workerStatus: async () => validateWorkerStatus(await request<unknown>('/api/admin/worker')),
  emergencyWorkerWake: async () => validateWorkerStatus(await request<unknown>('/api/admin/worker/emergency-wake', { method: 'POST' })),
  safeWorkerStop: async () => validateWorkerStatus(await request<unknown>('/api/admin/worker/safe-stop', { method: 'POST' })),
  forecastInputMetadata: async (baseModelId: string) => {
    const value = validateForecastInputMetadata(
      await request<unknown>(`/api/admin/forecasts/input-metadata?base_model_id=${encodeURIComponent(baseModelId)}`),
    );
    if (value.base_model_id !== baseModelId) invalidPayload();
    return value;
  },
  downloadForecastInputTemplate: () => downloadForecastInputTemplate(),
  previewForecastExcel: async (file: File, startMonth: number, endMonth: number) => {
    const body = new FormData();
    body.set('start_month', String(startMonth));
    body.set('end_month', String(endMonth));
    body.set('file', file, file.name);
    return validateForecastExcelPreview(await request<unknown>('/api/admin/forecasts/input-preview', {
      method: 'POST', body,
    }));
  },
  generateForecast: async (body: ForecastGenerateRequestDto) => validateForecast(
    await request<unknown>('/api/admin/forecasts', { method: 'POST', body: JSON.stringify(body) }),
  ),
  job: async (jobId: string, signal?: AbortSignal) => validateJob(await request<unknown>(`/api/jobs/${jobId}`, { signal })),
  adminResult: async (resultId: string) => validateResult(await request<unknown>(`/api/admin/results/${resultId}`)),
  publishResult: async (resultId: string, publication: { is_published: boolean; is_default: boolean }) => validateResultPublication(
    await request<unknown>(`/api/admin/results/${resultId}/publication`, {
      method: 'POST', body: JSON.stringify(publication),
    }),
  ),
  viewerResult: async (resultId: string) => validateResult(await request<unknown>(`/api/viewer/results/${resultId}`)),
  adminPresentation: async (resultId: string) => validatePresentation(
    await request<unknown>(`/api/admin/results/${resultId}/presentation`),
  ),
  viewerPresentation: async (resultId: string) => validatePresentation(
    await request<unknown>(`/api/viewer/results/${resultId}/presentation`),
  ),
  pnlDashboard: async (signal?: AbortSignal) => validatePnlDashboard(
    await request<unknown>('/api/viewer/pnl-dashboard', { signal, cache: 'no-store' }),
  ),
  history: async (limit = 25, beforeCreatedAt?: string, beforeJobId?: string) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (beforeCreatedAt && beforeJobId) {
      query.set('before_created_at', beforeCreatedAt);
      query.set('before_job_id', beforeJobId);
    }
    return validateHistory(await request<unknown>(`/api/admin/calculation-history?${query}`));
  },
  downloadEvidence: (resultId: string, role: Role) => downloadEvidence(resultId, role),
  downloadForecastWorkbook: (modelId: string) => downloadForecastWorkbook(modelId),
};

function validateForecast(value: unknown): ForecastGenerateResponseDto {
  if (!isRecord(value) || !uuid(value.generation_id) || !uuid(value.model_id)
    || typeof value.display_name !== 'string' || !integerInRange(value.model_year, 2000, 2200)
    || !integerInRange(value.start_month, 1, 12) || !integerInRange(value.end_month, 1, 12)
    || typeof value.is_published !== 'boolean' || typeof value.is_default !== 'boolean'
    || typeof value.workbook_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(value.workbook_sha256)
    || typeof value.idempotency_replayed !== 'boolean'
    || value.execution_mode !== 'SYNCHRONOUS' || value.dto_version !== '1') invalidPayload();
  return value as unknown as ForecastGenerateResponseDto;
}

async function downloadForecastInputTemplate(): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}/api/admin/forecasts/input-template`, { credentials: 'include' });
  } catch {
    throw new ApiClientError(0, 'TRANSIENT_SYSTEM_ERROR', '엑셀 양식 다운로드 서버에 연결할 수 없습니다.');
  }
  if (!response.ok) {
    let code = 'TRANSIENT_SYSTEM_ERROR';
    try {
      const value: unknown = await response.json();
      if (isRecord(value) && isRecord(value.error) && typeof value.error.code === 'string') code = value.error.code;
    } catch { /* safe fallback */ }
    throw new ApiClientError(response.status, code, '엑셀 입력 양식을 내려받을 수 없습니다.', response.headers.get('X-Correlation-ID'));
  }
  const contentType = response.headers.get('Content-Type') || '';
  if (!contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) invalidPayload();
  const blob = await response.blob();
  if (!blob.size) invalidPayload();
  deliverBlob(blob, safeXlsxFilename(response.headers.get('Content-Disposition'), 'Forecast_Input_Template.xlsx'));
}

function validateForecastExcelPreview(value: unknown): ForecastExcelPreviewDto {
  if (!isRecord(value)
    || typeof value.source_filename !== 'string'
    || !/^[^\\/\r\n]+\.xlsx$/i.test(value.source_filename)
    || typeof value.valid !== 'boolean'
    || typeof value.blocking !== 'boolean'
    || value.valid === value.blocking
    || !Array.isArray(value.sales_rows)
    || !Array.isArray(value.business_production_rows)
    || !Array.isArray(value.issues)
    || !Array.isArray(value.sales_summary)
    || !Array.isArray(value.production_summary)
    || value.dto_version !== '1') invalidPayload();

  const sourceRow = (row: unknown, sheet: '판매계획' | '생산계획') => isRecord(row)
    && row.source_sheet === sheet
    && Number.isSafeInteger(row.source_row)
    && Number(row.source_row) >= 2;
  const nonnegativeNumber = (candidate: unknown) => typeof candidate === 'number'
    && Number.isFinite(candidate) && candidate >= 0;

  for (const row of value.sales_rows) {
    if (!sourceRow(row, '판매계획') || !isRecord(row)
      || !integerInRange(row.month, 1, 12)
      || typeof row.product_code !== 'string' || row.product_code.trim() === ''
      || typeof row.product_name !== 'string' || row.product_name.trim() === ''
      || typeof row.product_group !== 'string' || row.product_group.trim() === ''
      || !nonnegativeNumber(row.quantity) || !nonnegativeNumber(row.amount)) invalidPayload();
  }
  for (const row of value.business_production_rows) {
    if (!sourceRow(row, '생산계획') || !isRecord(row)
      || !integerInRange(row.month, 1, 12)
      || !['전공정', '후공정'].includes(String(row.process))
      || !['SW', 'BW', 'TW', 'LC'].includes(String(row.product_group))
      || !['PCS', 'm'].includes(String(row.unit))
      || !nonnegativeNumber(row.quantity)) invalidPayload();
  }
  for (const issue of value.issues) {
    if (!isRecord(issue)
      || !['판매계획', '생산계획'].includes(String(issue.source_sheet))
      || !Number.isSafeInteger(issue.source_row) || Number(issue.source_row) < 1
      || typeof issue.field !== 'string' || typeof issue.code !== 'string'
      || typeof issue.message !== 'string'
      || !['ERROR', 'WARNING'].includes(String(issue.severity))
      || typeof issue.blocking !== 'boolean') invalidPayload();
  }
  if (value.blocking !== value.issues.some((issue) => isRecord(issue) && issue.blocking === true)) {
    invalidPayload();
  }
  for (const summary of [...value.sales_summary, ...value.production_summary]) {
    if (!isRecord(summary)
      || !['PCS', 'm', 'L', '—'].includes(String(summary.unit))
      || !Number.isSafeInteger(summary.row_count) || Number(summary.row_count) < 0
      || !nonnegativeNumber(summary.quantity_total)
      || 'amount_total' in summary) invalidPayload();
  }
  return value as unknown as ForecastExcelPreviewDto;
}

async function downloadEvidence(resultId: string, role: Role): Promise<void> {
  const path = `/api/${role === 'admin' ? 'admin' : 'viewer'}/results/${encodeURIComponent(resultId)}/evidence`;
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, { credentials: 'include' });
  } catch {
    throw new ApiClientError(0, 'TRANSIENT_SYSTEM_ERROR', '다운로드 서버에 연결할 수 없습니다.');
  }
  if (!response.ok) {
    let code = 'TRANSIENT_SYSTEM_ERROR';
    let message = '분석 근거 엑셀을 내려받을 수 없습니다.';
    try {
      const value: unknown = await response.json();
      if (isRecord(value) && isRecord(value.error)) {
        if (typeof value.error.code === 'string') code = value.error.code;
        if (typeof value.error.message === 'string') message = value.error.message;
      }
    } catch { /* safe fallback */ }
    throw new ApiClientError(response.status, code, message, response.headers.get('X-Correlation-ID'));
  }
  const contentType = response.headers.get('Content-Type') || '';
  if (!contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) invalidPayload();
  const blob = await response.blob();
  if (!blob.size) invalidPayload();
  const filename = safeXlsxFilename(
    response.headers.get('Content-Disposition'),
    '손익분석_근거.xlsx',
  );
  deliverBlob(blob, filename);
}

async function downloadForecastWorkbook(modelId: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      `${API_ROOT}/api/admin/forecast-models/${encodeURIComponent(modelId)}/workbook`,
      { credentials: 'include' },
    );
  } catch {
    throw new ApiClientError(0, 'TRANSIENT_SYSTEM_ERROR', '다운로드 서버에 연결할 수 없습니다.');
  }
  if (!response.ok) {
    let code = 'TRANSIENT_SYSTEM_ERROR';
    try {
      const value: unknown = await response.json();
      if (isRecord(value) && isRecord(value.error) && typeof value.error.code === 'string') {
        code = value.error.code;
      }
    } catch { /* safe fallback */ }
    throw new ApiClientError(
      response.status,
      code,
      '생성된 추정 모형을 내려받을 수 없습니다.',
      response.headers.get('X-Correlation-ID'),
    );
  }
  const contentType = response.headers.get('Content-Type') || '';
  if (!contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
    invalidPayload();
  }
  const blob = await response.blob();
  if (!blob.size) invalidPayload();
  const filename = safeXlsxFilename(
    response.headers.get('Content-Disposition'),
    'Forecast_Model.xlsx',
  );
  deliverBlob(blob, filename);
}

function deliverBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

function safeXlsxFilename(header: string | null, fallback: string): string {
  const encoded = header?.match(/filename\*=utf-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      const value = decodeURIComponent(encoded);
      if (/^[^\\/\r\n]+\.xlsx$/i.test(value)) return value;
    } catch { /* safe fallback */ }
  }
  return fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function invalidPayload(): never {
  throw new ApiClientError(502, 'INPUT_INTEGRITY_MISMATCH', '서버 응답 형식이 올바르지 않습니다.');
}

function validateSession(value: unknown): SessionDto {
  if (!isRecord(value) || value.authenticated !== true || !['viewer', 'admin'].includes(String(value.role)) || typeof value.expires_at !== 'string') invalidPayload();
  return value as unknown as SessionDto;
}

function validateAdminModel(value: unknown): AdminModelDto {
  if (!isRecord(value)
    || typeof value.model_id !== 'string'
    || typeof value.display_name !== 'string'
    || typeof value.model_type !== 'string'
    || typeof value.model_year !== 'number'
    || typeof value.version !== 'string'
    || typeof value.file_name !== 'string'
    || !((typeof value.workbook_sha256 === 'string' && /^[0-9a-f]{64}$/.test(value.workbook_sha256)) || value.workbook_sha256 === null)
    || typeof value.has_workbook_sha256 !== 'boolean'
    || value.has_workbook_sha256 !== (typeof value.workbook_sha256 === 'string')
    || typeof value.is_published !== 'boolean'
    || typeof value.is_default !== 'boolean'
    || typeof value.uploaded_at !== 'string') invalidPayload();
  return value as unknown as AdminModelDto;
}

function validateAdminModels(value: unknown): AdminModelDto[] {
  if (!isRecord(value) || !Array.isArray(value.models)) invalidPayload();
  return value.models.map(validateAdminModel);
}

function validateAdminModelResponse(value: unknown): AdminModelDto {
  if (!isRecord(value)) invalidPayload();
  return validateAdminModel(value.model);
}

function validateModelUpload(value: unknown): ModelUploadResponse {
  if (!isRecord(value) || typeof value.idempotency_replayed !== 'boolean') invalidPayload();
  return {
    model: validateAdminModel(value.model),
    idempotency_replayed: value.idempotency_replayed,
    dto_version: '1',
  };
}

function validateModels(value: unknown): AnalysisModelDto[] {
  if (!isRecord(value) || !Array.isArray(value.models)) invalidPayload();
  for (const model of value.models) {
    if (!isRecord(model) || typeof model.model_id !== 'string' || typeof model.display_name !== 'string' || typeof model.model_year !== 'number' || model.is_published !== true) invalidPayload();
  }
  return value.models as AnalysisModelDto[];
}

function validateJob(value: unknown): JobStatusDto {
  if (!isRecord(value) || typeof value.job_id !== 'string' || !['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'].includes(String(value.status))
    || !['QUEUED', 'STARTING_WORKER', 'PROCESSING', 'COMPLETED', 'FAILED'].includes(String(value.execution_state))) invalidPayload();
  if (value.status === 'COMPLETED' && typeof value.result_id !== 'string') invalidPayload();
  return value as unknown as JobStatusDto;
}

function validateSubmit(value: unknown): SubmitResponse {
  if (!isRecord(value) || typeof value.job_id !== 'string' || !['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'].includes(String(value.status))
    || !['QUEUED', 'STARTING_WORKER', 'PROCESSING', 'COMPLETED', 'FAILED'].includes(String(value.execution_state))
    || typeof value.idempotency_replayed !== 'boolean') invalidPayload();
  return value as unknown as SubmitResponse;
}

function validateWorkerStatus(value: unknown): WorkerStatusDto {
  if (!isRecord(value) || ![0, 1].includes(Number(value.desired_instance_count))
    || ![0, 1].includes(Number(value.configured_instance_count))
    || !(value.actual_instance_count === null || [0, 1].includes(Number(value.actual_instance_count)))
    || value.operating_policy !== 'DEMAND_ONLY' || value.idle_policy_seconds !== 1800
    || typeof value.work_exists !== 'boolean' || typeof value.platform_reconciling !== 'boolean'
    || typeof value.platform_ready !== 'boolean' || typeof value.last_worker_activity_at !== 'string'
    || !(value.last_scaling_result === null || typeof value.last_scaling_result === 'string')) invalidPayload();
  for (const name of ['queue_depth', 'claimable_count', 'pending_count', 'processing_count',
    'active_lease_count', 'active_heartbeat_count', 'recovery_pending_count', 'idle_seconds']) {
    if (!Number.isSafeInteger(value[name]) || Number(value[name]) < 0) invalidPayload();
  }
  return value as unknown as WorkerStatusDto;
}

function validateResult(value: unknown): StoredResultDto {
  if (!isRecord(value) || typeof value.result_id !== 'string' || typeof value.job_id !== 'string' || !isRecord(value.analysis_view) || !isRecord(value.provenance)) invalidPayload();
  return value as unknown as StoredResultDto;
}

function validateForecastInputMetadata(value: unknown): ForecastInputMetadataDto {
  if (!isRecord(value)
    || !uuid(value.base_model_id)
    || !Array.isArray(value.manufacturing)
    || !Array.isArray(value.sga)
    || value.reason_max_length !== 500
    || value.dto_version !== '1') invalidPayload();

  const validateItems = (items: unknown[], requireSection: boolean) => items.map((item) => {
    if (!isRecord(item)
      || typeof item.adjustment_key !== 'string'
      || item.adjustment_key.trim() === ''
      || typeof item.display_name !== 'string'
      || item.display_name.trim() === ''
      || typeof item.unit !== 'string'
      || !['manufacturing', 'sga'].includes(String(item.category))
      || !(item.section === null || typeof item.section === 'string')
      || 'row' in item
      || 'cell' in item
      || (requireSection && item.category !== 'sga')
      || (!requireSection && item.category !== 'manufacturing')) invalidPayload();
    return item as unknown as ForecastInputMetadataDto['manufacturing'][number];
  });
  return {
    base_model_id: String(value.base_model_id),
    manufacturing: validateItems(value.manufacturing, false),
    sga: validateItems(value.sga, true),
    reason_max_length: 500,
    dto_version: '1',
  };
}

function validateResultPublication(value: unknown): ResultPublicationDto {
  if (!isRecord(value)
    || !uuid(value.result_id)
    || typeof value.is_published !== 'boolean'
    || typeof value.is_default !== 'boolean'
    || (value.is_default && !value.is_published)
    || !(value.published_at === null || typeof value.published_at === 'string')
    || (value.is_published !== (typeof value.published_at === 'string'))
    || value.dto_version !== '1') invalidPayload();
  return value as unknown as ResultPublicationDto;
}

const PRESENTATION_EFFECT_ORDER = [
  'sales_quantity', 'sales_mix', 'sales_price', 'sales_fx', 'material_total',
  'manufacturing_realized', 'inventory_timing', 'sga_variable', 'sga_fixed', 'tariff',
] as const;
const RESIDUAL_CLASSIFICATIONS = new Set([
  'VALIDATION_ARTIFACT', 'FORMULA_EVALUATOR_GAP', 'MAPPING_GAP', 'ENGINE_BUG',
  'INTENTIONAL_SCOPE_GAP', 'INVENTORY_TIMING', 'BUSINESS_POLICY_GAP', 'UNEXPLAINED',
]);

function validatePresentationEffect(value: unknown): AnalysisPresentationEffectDto {
  if (!isRecord(value)
    || !PRESENTATION_EFFECT_ORDER.includes(value.code as typeof PRESENTATION_EFFECT_ORDER[number])
    || !['INTERNAL', 'EXTERNAL', 'COST'].includes(String(value.category))
    || typeof value.label !== 'string'
    || typeof value.description !== 'string'
    || !finite(value.profit_effect)
    || !isRecord(value.drilldown)
    || !['sales', 'material', 'manufacturing', 'inventory', 'sga', 'tariff', 'unavailable'].includes(String(value.drilldown.kind))
    || typeof value.drilldown.available !== 'boolean'
    || !Array.isArray(value.drilldown.rows)) invalidPayload();
  for (const row of value.drilldown.rows) {
    if (!isRecord(row)
      || typeof row.row_id !== 'string'
      || typeof row.label !== 'string'
      || typeof row.unit !== 'string'
      || !optionalFinite(row.baseline)
      || !optionalFinite(row.comparison)
      || !optionalFinite(row.delta)
      || !optionalFinite(row.profit_effect)
      || typeof row.note !== 'string') invalidPayload();
  }
  if (value.drilldown.available !== (value.drilldown.rows.length > 0)) invalidPayload();
  return value as unknown as AnalysisPresentationEffectDto;
}

function validatePresentation(value: unknown): AnalysisPresentationDto {
  if (!isRecord(value)
    || !isRecord(value.identity)
    || !isRecord(value.kpis)
    || !Array.isArray(value.effects)
    || !isRecord(value.residual)
    || !Array.isArray(value.product_groups)
    || !Array.isArray(value.manufacturing_activities)
    || !isRecord(value.executive_summary)
    || value.currency_unit !== 'KRW'
    || value.dto_version !== '1') invalidPayload();
  const identity = value.identity;
  if (!uuid(identity.result_id) || !uuid(identity.job_id)
    || !uuid(identity.baseline_model_id) || !uuid(identity.comparison_model_id)
    || identity.baseline_model_id === identity.comparison_model_id
    || typeof identity.baseline_model_name !== 'string' || !identity.baseline_model_name
    || typeof identity.comparison_model_name !== 'string' || !identity.comparison_model_name
    || !integerInRange(identity.start_month, 1, 12)
    || !integerInRange(identity.end_month, 1, 12)
    || Number(identity.start_month) > Number(identity.end_month)
    || !positiveFinite(identity.baseline_sales_fx) || !positiveFinite(identity.comparison_sales_fx)
    || typeof identity.result_schema_version !== 'string'
    || typeof identity.completed_at !== 'string'
    || typeof identity.is_published !== 'boolean'
    || typeof identity.is_default !== 'boolean'
    || !(identity.published_at === null || typeof identity.published_at === 'string')) invalidPayload();
  const kpis = value.kpis;
  for (const key of [
    'baseline_revenue', 'comparison_revenue', 'revenue_delta',
    'baseline_operating_profit', 'comparison_operating_profit',
    'operating_profit_delta', 'effects_total', 'residual',
  ]) if (!finite(kpis[key])) invalidPayload();
  if (!close(Number(kpis.comparison_revenue) - Number(kpis.baseline_revenue), Number(kpis.revenue_delta))
    || !close(Number(kpis.comparison_operating_profit) - Number(kpis.baseline_operating_profit), Number(kpis.operating_profit_delta))) invalidPayload();

  const effects = value.effects.map(validatePresentationEffect);
  if (effects.length !== PRESENTATION_EFFECT_ORDER.length
    || effects.some((effect, index) => effect.code !== PRESENTATION_EFFECT_ORDER[index])) invalidPayload();
  const residual = value.residual;
  if (!finite(residual.amount)
    || !RESIDUAL_CLASSIFICATIONS.has(String(residual.classification))
    || typeof residual.display_label !== 'string'
    || !close(Number(residual.amount), Number(kpis.residual))
    || !close(effects.reduce((sum, effect) => sum + effect.profit_effect, 0), Number(kpis.effects_total))
    || !close(Number(kpis.effects_total) + Number(residual.amount), Number(kpis.operating_profit_delta))) invalidPayload();

  const groups = new Set<string>();
  for (const group of value.product_groups) {
    if (!isRecord(group)
      || !['SW', 'BW', 'LC', 'FS', '신사업'].includes(String(group.code))
      || groups.has(String(group.code))
      || typeof group.display_name !== 'string'
      || (group.code === 'LC' && group.display_name !== '4인치 LC')
      || (group.code === 'FS' ? group.quantity_unit !== 'm' : group.quantity_unit !== 'PCS')
      || !finite(group.baseline_quantity) || !finite(group.comparison_quantity)
      || !finite(group.baseline_revenue) || !finite(group.comparison_revenue)) invalidPayload();
    groups.add(String(group.code));
  }
  for (const activity of value.manufacturing_activities) {
    if (!isRecord(activity)
      || typeof activity.process !== 'string'
      || typeof activity.production_basis !== 'string'
      || (activity.production_basis === 'FS' ? activity.unit !== 'm' : activity.unit !== 'PCS')
      || !finite(activity.baseline) || !finite(activity.comparison) || !finite(activity.delta)
      || !close(Number(activity.comparison) - Number(activity.baseline), Number(activity.delta))) invalidPayload();
  }
  const summary = value.executive_summary;
  if (!finite(summary.operating_profit_delta)
    || !close(Number(summary.operating_profit_delta), Number(kpis.operating_profit_delta))
    || !Array.isArray(summary.top_positive_effects)
    || !Array.isArray(summary.top_negative_effects)
    || !isRecord(summary.residual)) invalidPayload();
  summary.top_positive_effects.forEach(validatePresentationEffect);
  summary.top_negative_effects.forEach(validatePresentationEffect);
  return value as unknown as AnalysisPresentationDto;
}

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function optionalFinite(value: unknown): boolean {
  return value === null || finite(value);
}

function positiveFinite(value: unknown): boolean {
  return finite(value) && value > 0;
}

function integerInRange(value: unknown, low: number, high: number): boolean {
  return typeof value === 'number' && Number.isInteger(value) && value >= low && value <= high;
}

function uuid(value: unknown): boolean {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function close(left: number, right: number): boolean {
  return Math.abs(left - right) <= Math.max(1, Math.abs(left), Math.abs(right)) * 1e-9;
}

function validateFinancial(value: unknown): void {
  if (!isRecord(value) || typeof value.code !== 'string' || typeof value.label !== 'string'
    || !finite(value.baseline) || !finite(value.comparison) || !finite(value.delta)
    || !optionalFinite(value.comparison_ratio_to_revenue)
    || !close(value.comparison - value.baseline, value.delta)) invalidPayload();
}

function validatePnlDashboard(value: unknown): PnlDashboardDto {
  if (!isRecord(value) || !uuid(value.result_id) || !uuid(value.job_id)
    || !isRecord(value.identity) || !isRecord(value.kpis)
    || !Array.isArray(value.monthly_series) || !Array.isArray(value.pnl_statement)
    || !isRecord(value.manufacturing) || !isRecord(value.sga)
    || !Array.isArray(value.product_groups) || !isRecord(value.key_facts)
    || value.currency_unit !== 'KRW' || value.dto_version !== '1') invalidPayload();
  const identity = value.identity;
  if (!uuid(identity.baseline_model_id) || !uuid(identity.comparison_model_id)
    || identity.baseline_model_id === identity.comparison_model_id
    || !integerInRange(identity.start_month, 1, 12) || !integerInRange(identity.end_month, 1, 12)
    || !Array.isArray(identity.available_months) || !Array.isArray(identity.actual_months)
    || !(identity.actual_through_month === null || integerInRange(identity.actual_through_month, 1, 12))) invalidPayload();
  const months = identity.available_months as unknown[];
  if (months.length === 0 || months.some((month, index) => !integerInRange(month, 1, 12)
    || Number(month) !== Number(identity.start_month) + index
    || Number(month) > Number(identity.end_month))) invalidPayload();
  if (Number(months[months.length - 1]) !== Number(identity.end_month)) invalidPayload();
  const actualMonths = identity.actual_months as unknown[];
  if (actualMonths.some((month, index) => month !== months[index])
    || ((actualMonths.length === 0) !== (identity.actual_through_month === null))
    || (actualMonths.length > 0 && identity.actual_through_month !== actualMonths[actualMonths.length - 1])) invalidPayload();

  const kpis = value.kpis;
  if (!integerInRange(kpis.latest_month, 1, 12)) invalidPayload();
  for (const code of ['revenue', 'gross_profit', 'operating_profit']) {
    const metric = kpis[code];
    if (!isRecord(metric)) invalidPayload();
    validateFinancial(metric.latest); validateFinancial(metric.period);
  }
  for (const key of ['latest_operating_margin', 'period_operating_margin']) {
    const margin = kpis[key];
    if (!isRecord(margin) || !optionalFinite(margin.baseline) || !optionalFinite(margin.comparison)
      || !optionalFinite(margin.delta_percentage_points)) invalidPayload();
    if (finite(margin.baseline) && finite(margin.comparison)
      && (!finite(margin.delta_percentage_points)
        || !close(margin.comparison - margin.baseline, margin.delta_percentage_points))) invalidPayload();
  }
  const latestMargin = kpis.latest_operating_margin as Record<string, unknown>;
  const periodMargin = kpis.period_operating_margin as Record<string, unknown>;
  const opKpi = kpis.operating_profit as Record<string, Record<string, unknown>>;
  const revenueKpi = kpis.revenue as Record<string, Record<string, unknown>>;
  validateRatio(latestMargin.baseline, opKpi.latest.baseline, revenueKpi.latest.baseline);
  validateRatio(latestMargin.comparison, opKpi.latest.comparison, revenueKpi.latest.comparison);
  validateRatio(periodMargin.baseline, opKpi.period.baseline, revenueKpi.period.baseline);
  validateRatio(periodMargin.comparison, opKpi.period.comparison, revenueKpi.period.comparison);
  if (value.monthly_series.length !== months.length) invalidPayload();
  value.monthly_series.forEach((row, index) => {
    if (!isRecord(row) || row.month !== months[index]
      || !['실적', '추정', '계획', null].includes(row.comparison_period_type as never)) invalidPayload();
    validateFinancial(row.revenue); validateFinancial(row.cogs); validateFinancial(row.gross_profit); validateFinancial(row.operating_profit);
    const revenue = row.revenue as Record<string, number>;
    const cogs = row.cogs as Record<string, number>;
    const gp = row.gross_profit as Record<string, number>;
    const op = row.operating_profit as Record<string, number>;
    if (!close(revenue.baseline - cogs.baseline, gp.baseline)
      || !close(revenue.comparison - cogs.comparison, gp.comparison)) invalidPayload();
    if (!optionalFinite(row.baseline_operating_margin) || !optionalFinite(row.comparison_operating_margin)) invalidPayload();
    validateRatio(row.baseline_operating_margin, op.baseline, revenue.baseline);
    validateRatio(row.comparison_operating_margin, op.comparison, revenue.comparison);
  });
  const required = new Set(['revenue', 'cogs', 'gross_profit', 'operating_profit']);
  value.pnl_statement.forEach((row) => { validateFinancial(row); if (isRecord(row)) required.delete(String(row.code)); });
  if (required.size) invalidPayload();

  const manufacturing = value.manufacturing;
  if (!Array.isArray(manufacturing.cost_lines) || !Array.isArray(manufacturing.accounts)
    || !isRecord(manufacturing.material_components) || !isRecord(manufacturing.fixed_cost_policy)
    || manufacturing.material_components.jpy_fx_unit !== 'KRW/JPY'
    || manufacturing.material_components.mcm_is_separate_effect !== false
    || manufacturing.fixed_cost_policy.manufacturing_effect_includes_variable_and_fixed !== true
    || manufacturing.fixed_cost_policy.fixed_manufacturing_is_not_a_separate_top_level_effect !== true) invalidPayload();
  manufacturing.cost_lines.forEach(validateFinancial);
  if (!Array.isArray(value.sga.accounts) || typeof value.sga.fixed_scope !== 'string') invalidPayload();
  const groups = new Set<string>();
  for (const group of value.product_groups) {
    if (!isRecord(group) || !['SW', 'BW', 'LC', 'FS', '신사업'].includes(String(group.code))
      || groups.has(String(group.code)) || (group.code === 'LC' && group.display_name !== '4인치 LC')
      || (group.code === 'FS' ? group.quantity_unit !== 'm' : group.quantity_unit !== 'PCS')) invalidPayload();
    groups.add(String(group.code));
  }
  const facts = value.key_facts;
  const dashboardEffectCodes = new Set([
    'sales_quantity', 'sales_mix', 'sales_price', 'sales_fx', 'tariff',
    'material_total', 'manufacturing_realized', 'inventory_timing', 'sga_variable', 'sga_fixed',
  ]);
  if (!Array.isArray(facts.effects) || !finite(facts.effects_total) || !finite(facts.residual)
    || !finite(facts.operating_profit_delta) || typeof facts.reconciled !== 'boolean'
    || !close(facts.effects_total + facts.residual, facts.operating_profit_delta)) invalidPayload();
  if (facts.effects.length !== dashboardEffectCodes.size
    || facts.effects.some((effect) => !isRecord(effect) || !dashboardEffectCodes.delete(String(effect.code))
      || typeof effect.label !== 'string' || !finite(effect.profit_effect))) invalidPayload();
  if (!close(facts.effects.reduce((sum, effect) => sum + Number(effect.profit_effect), 0), facts.effects_total)) invalidPayload();
  return value as unknown as PnlDashboardDto;
}

function validateRatio(value: unknown, numerator: unknown, denominator: unknown): void {
  if (!finite(numerator) || !finite(denominator)) invalidPayload();
  if (denominator === 0) {
    if (value !== null) invalidPayload();
  } else if (!finite(value) || !close(value, numerator / denominator * 100)) invalidPayload();
}

function validateHistory(value: unknown): CalculationHistoryDto {
  if (!isRecord(value) || !Array.isArray(value.items)) invalidPayload();
  const items = value.items.map((item): CalculationHistoryItemDto => {
    if (!isRecord(item)
      || typeof item.job_id !== 'string'
      || !['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'].includes(String(item.status))
      || (item.status === 'COMPLETED'
        ? !(typeof item.result_id === 'string' || item.result_id === null)
        : item.result_id !== null)
      || typeof item.baseline_model_name !== 'string'
      || typeof item.comparison_model_name !== 'string'
      || typeof item.created_at !== 'string'
      || typeof item.is_published !== 'boolean'
      || typeof item.is_default !== 'boolean'
      || (item.is_default && !item.is_published)
      || !(item.published_at === null || typeof item.published_at === 'string')
      || (item.is_published !== (typeof item.published_at === 'string'))) invalidPayload();
    return item as unknown as CalculationHistoryItemDto;
  });
  return {
    items,
    next_before_created_at: typeof value.next_before_created_at === 'string' ? value.next_before_created_at : null,
    next_before_job_id: typeof value.next_before_job_id === 'string' ? value.next_before_job_id : null,
    dto_version: '1',
  };
}

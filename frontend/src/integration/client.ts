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
  Role,
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
  publishModel: async (modelId: string, isDefault = false) => validateAdminModelResponse(
    await request<unknown>(`/api/admin/models/${modelId}/publication`, {
      method: 'POST', body: JSON.stringify({ is_published: true, is_default: isDefault }),
    }),
  ),
  submit: async (body: SubmitRequest) => validateSubmit(await request<unknown>('/api/analyses', {
    method: 'POST', body: JSON.stringify(body),
  })),
  job: async (jobId: string, signal?: AbortSignal) => validateJob(await request<unknown>(`/api/jobs/${jobId}`, { signal })),
  adminResult: async (resultId: string) => validateResult(await request<unknown>(`/api/admin/results/${resultId}`)),
  viewerResult: async (resultId: string) => validateResult(await request<unknown>(`/api/viewer/results/${resultId}`)),
  history: async (limit = 25, beforeCreatedAt?: string, beforeJobId?: string) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (beforeCreatedAt && beforeJobId) {
      query.set('before_created_at', beforeCreatedAt);
      query.set('before_job_id', beforeJobId);
    }
    return validateHistory(await request<unknown>(`/api/admin/calculation-history?${query}`));
  },
  downloadEvidence: (resultId: string, role: Role) => downloadEvidence(resultId, role),
};

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
  const filename = evidenceFilename(response.headers.get('Content-Disposition'));
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

function evidenceFilename(header: string | null): string {
  const encoded = header?.match(/filename\*=utf-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      const value = decodeURIComponent(encoded);
      if (/^[^\\/\r\n]+\.xlsx$/i.test(value)) return value;
    } catch { /* safe fallback */ }
  }
  return '손익분석_근거.xlsx';
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
  if (!isRecord(value) || typeof value.job_id !== 'string' || !['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'].includes(String(value.status))) invalidPayload();
  if (value.status === 'COMPLETED' && typeof value.result_id !== 'string') invalidPayload();
  return value as unknown as JobStatusDto;
}

function validateSubmit(value: unknown): SubmitResponse {
  if (!isRecord(value) || typeof value.job_id !== 'string' || !['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'].includes(String(value.status)) || typeof value.idempotency_replayed !== 'boolean') invalidPayload();
  return value as unknown as SubmitResponse;
}

function validateResult(value: unknown): StoredResultDto {
  if (!isRecord(value) || typeof value.result_id !== 'string' || typeof value.job_id !== 'string' || !isRecord(value.analysis_view) || !isRecord(value.provenance)) invalidPayload();
  return value as unknown as StoredResultDto;
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
      || typeof item.created_at !== 'string') invalidPayload();
    return item as unknown as CalculationHistoryItemDto;
  });
  return {
    items,
    next_before_created_at: typeof value.next_before_created_at === 'string' ? value.next_before_created_at : null,
    next_before_job_id: typeof value.next_before_job_id === 'string' ? value.next_before_job_id : null,
    dto_version: '1',
  };
}

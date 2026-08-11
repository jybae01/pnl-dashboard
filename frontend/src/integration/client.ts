import {
  AnalysisModelDto,
  ApiClientError,
  ApiErrorDto,
  JobStatusDto,
  SessionDto,
  StoredResultDto,
  SubmitRequest,
  SubmitResponse,
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
  if (init.body) headers.set('Content-Type', 'application/json');
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
    );
  }
  return response.json() as Promise<T>;
}

export const bffClient = {
  login: async (accessCode: string) => validateSession(await request<unknown>('/api/session/login', {
    method: 'POST', body: JSON.stringify({ access_code: accessCode }),
  })),
  session: async () => validateSession(await request<unknown>('/api/session')),
  logout: () => request<{ authenticated: false }>('/api/session/logout', { method: 'POST' }),
  models: async () => validateModels(await request<unknown>('/api/models')),
  submit: async (body: SubmitRequest) => validateSubmit(await request<unknown>('/api/analyses', {
    method: 'POST', body: JSON.stringify(body),
  })),
  job: async (jobId: string, signal?: AbortSignal) => validateJob(await request<unknown>(`/api/jobs/${jobId}`, { signal })),
  adminResult: async (resultId: string) => validateResult(await request<unknown>(`/api/admin/results/${resultId}`)),
  viewerResult: async (resultId: string) => validateResult(await request<unknown>(`/api/viewer/results/${resultId}`)),
};

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

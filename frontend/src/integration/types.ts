export type Role = 'viewer' | 'admin';
export type JobStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
export type ViewerState = 'LOADING' | 'READY' | 'EMPTY' | 'ERROR' | 'INVALID_PAYLOAD';

export interface SessionDto {
  authenticated: true;
  role: Role;
  expires_at: string;
  dto_version: '1';
}

export interface AnalysisModelDto {
  model_id: string;
  display_name: string;
  model_type: string;
  model_year: number;
  start_month: number;
  end_month: number;
  is_published: true;
  is_default: boolean;
  dto_version: '1';
}

export interface SubmitRequest {
  baseline_model_id: string;
  comparison_model_id: string;
  start_month: number;
  end_month: number;
  baseline_sales_fx: number;
  comparison_sales_fx: number;
  idempotency_key: string;
}

export interface SubmitResponse {
  job_id: string;
  status: JobStatus;
  idempotency_replayed: boolean;
  dto_version: '1';
}

export interface JobStatusDto {
  job_id: string;
  status: JobStatus;
  baseline_model_id: string;
  comparison_model_id: string;
  start_month: number;
  end_month: number;
  attempt: number;
  max_attempts: number;
  created_at: string;
  heartbeat_at: string | null;
  completed_at: string | null;
  result_id: string | null;
  error_code: string | null;
  error_message: string | null;
  dto_version: '1';
}

export interface StoredResultDto {
  result_id: string;
  job_id: string;
  analysis_view: Record<string, unknown>;
  provenance: Record<string, string>;
  is_published?: boolean;
  is_default: boolean;
  published_at: string | null;
  created_at: string;
  dto_version: '1';
}

export interface ApiErrorDto {
  error: {
    code: string;
    message: string;
    field_errors: Record<string, string>;
    correlation_id: string | null;
    dto_version: '1';
  };
}

export class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly correlationId: string | null = null,
    public readonly retryAfterSeconds: number | null = null,
  ) {
    super(message);
  }
}

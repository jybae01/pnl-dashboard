export type Role = 'viewer' | 'admin';
export type JobStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
export type WorkerExecutionState = 'QUEUED' | 'STARTING_WORKER' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
export type ViewerState = 'LOADING' | 'READY' | 'EMPTY' | 'ERROR' | 'FORBIDDEN' | 'INVALID_PAYLOAD';

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

export interface AdminModelDto {
  model_id: string;
  display_name: string;
  model_type: string;
  model_year: number;
  start_month: number;
  end_month: number;
  version: string;
  file_name: string;
  workbook_sha256: string | null;
  has_workbook_sha256: boolean;
  is_published: boolean;
  is_default: boolean;
  uploaded_at: string;
  dto_version: '1';
}

export interface ModelUploadInput {
  name: string;
  modelType: 'PLAN' | 'ACTUAL' | 'FORECAST';
  modelYear: number;
  version: string;
  idempotencyKey: string;
  file: File;
}

export interface ModelUploadResponse {
  model: AdminModelDto;
  idempotency_replayed: boolean;
  dto_version: '1';
}

export interface ForecastMonthInputDto {
  month: number;
  sales: Array<{ product_code: string; quantity: number; amount: number }>;
  production: Array<{ product_code: string; quantity: number }>;
  mcm: Array<{ product_code: string; quantity: number }>;
  manufacturing_adjustments: Array<{ adjustment_key: string; amount: number; reason: string }>;
  sga_adjustments: Array<{ adjustment_key: string; amount: number; reason: string }>;
  disposal_adjustment?: number; disposal_reason?: string;
  obsolescence_adjustment?: number; obsolescence_reason?: string;
  new_business_goods_cogs?: number; new_business_goods_cogs_reason?: string;
  uf_mbr_cogs_rate?: number; ix_cogs_rate?: number;
  uf_mbr_transport_rate?: number; ix_transport_rate?: number;
  ix_pack_liters?: number; ix_pack_cost?: number;
  plan_na_sa_sales?: number; na_sa_sales?: number;
  tariff_applicable_rate?: number; tariff_rate?: number;
  raw_material_basis?: 'model' | 'direct'; raw_material_direct?: number | null;
  raw_material_adjustment?: number; raw_material_reason?: string; refund_rate?: number;
}

/**
 * Forecast adjustment identities are intentionally opaque to the browser.
 * The BFF resolves them against its provenance-validated workbook mapping;
 * row/cell numbers must never become a frontend contract.
 */
export interface ForecastAdjustmentMetadataDto {
  adjustment_key: string;
  display_name: string;
  unit: string;
  category: 'manufacturing' | 'sga';
  section: string | null;
}

export interface ForecastInputMetadataDto {
  base_model_id: string;
  manufacturing: ForecastAdjustmentMetadataDto[];
  sga: ForecastAdjustmentMetadataDto[];
  reason_max_length: 500;
  dto_version: '1';
}

export interface ForecastGenerateRequestDto {
  base_model_id: string; name: string; model_year: number; version: string;
  start_month: number; end_month: number; months: ForecastMonthInputDto[];
  idempotency_key: string;
}

export interface ForecastGenerateResponseDto {
  generation_id: string; model_id: string; display_name: string; model_year: number;
  start_month: number; end_month: number; is_published: boolean; is_default: boolean;
  workbook_sha256: string; idempotency_replayed: boolean;
  execution_mode: 'SYNCHRONOUS'; dto_version: '1';
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
  execution_state: WorkerExecutionState;
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
  execution_state: WorkerExecutionState;
  dto_version: '1';
}

export interface WorkerStatusDto {
  desired_instance_count: 0 | 1; configured_instance_count: 0 | 1;
  actual_instance_count: 0 | 1 | null;
  queue_depth: number; claimable_count: number; pending_count: number; processing_count: number;
  active_lease_count: number; active_heartbeat_count: number; recovery_pending_count: number;
  work_exists: boolean; idle_seconds: number; last_worker_activity_at: string;
  last_scaling_result: string | null; platform_reconciling: boolean; platform_ready: boolean;
  operating_policy: 'DEMAND_ONLY'; idle_policy_seconds: 1800; dto_version: '1';
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

export type PresentationEffectCode =
  | 'sales_quantity' | 'sales_mix' | 'sales_price' | 'sales_fx' | 'material_total'
  | 'manufacturing_realized' | 'sga_variable' | 'sga_fixed' | 'tariff';
export type PresentationEffectCategory = 'INTERNAL' | 'EXTERNAL' | 'COST';
export type ResidualClassification =
  | 'VALIDATION_ARTIFACT' | 'FORMULA_EVALUATOR_GAP' | 'MAPPING_GAP' | 'ENGINE_BUG'
  | 'INTENTIONAL_SCOPE_GAP' | 'INVENTORY_TIMING' | 'BUSINESS_POLICY_GAP' | 'UNEXPLAINED';

export interface AnalysisDrilldownRowDto {
  row_id: string;
  label: string;
  unit: string;
  baseline: number | null;
  comparison: number | null;
  delta: number | null;
  profit_effect: number | null;
  note: string;
}

export interface AnalysisDrilldownDto {
  kind: 'sales' | 'material' | 'manufacturing' | 'sga' | 'tariff' | 'unavailable';
  available: boolean;
  rows: AnalysisDrilldownRowDto[];
  unavailable_reason: string | null;
}

export interface AnalysisPresentationEffectDto {
  code: PresentationEffectCode;
  label: string;
  category: PresentationEffectCategory;
  profit_effect: number;
  description: string;
  drilldown: AnalysisDrilldownDto;
}

export interface AnalysisResidualDto {
  amount: number;
  classification: ResidualClassification;
  display_label: string;
}

export interface AnalysisPresentationDto {
  identity: {
    result_id: string; job_id: string;
    baseline_model_id: string; comparison_model_id: string;
    baseline_model_name: string; comparison_model_name: string;
    start_month: number; end_month: number;
    baseline_sales_fx: number; comparison_sales_fx: number;
    result_schema_version: string; completed_at: string;
    is_published: boolean; is_default: boolean; published_at: string | null;
  };
  kpis: {
    baseline_revenue: number; comparison_revenue: number; revenue_delta: number;
    baseline_operating_profit: number; comparison_operating_profit: number;
    operating_profit_delta: number; effects_total: number; residual: number;
  };
  effects: AnalysisPresentationEffectDto[];
  residual: AnalysisResidualDto;
  product_groups: Array<{
    code: 'SW' | 'BW' | 'LC' | 'FS' | '신사업'; display_name: string;
    quantity_unit: 'PCS' | 'm'; baseline_quantity: number; comparison_quantity: number;
    baseline_revenue: number; comparison_revenue: number;
  }>;
  manufacturing_activities: Array<{
    process: string; production_basis: string; unit: 'PCS' | 'm';
    baseline: number; comparison: number; delta: number;
  }>;
  executive_summary: {
    operating_profit_delta: number;
    top_positive_effects: AnalysisPresentationEffectDto[];
    top_negative_effects: AnalysisPresentationEffectDto[];
    residual: AnalysisResidualDto;
  };
  currency_unit: 'KRW';
  dto_version: '1';
}

export interface CalculationHistoryItemDto {
  job_id: string;
  result_id: string | null;
  status: JobStatus;
  baseline_model_id: string;
  baseline_model_name: string;
  comparison_model_id: string;
  comparison_model_name: string;
  start_month: number | null;
  end_month: number | null;
  attempt: number;
  max_attempts: number;
  created_at: string;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
  is_published: boolean;
  is_default: boolean;
  published_at: string | null;
}

export interface ResultPublicationDto {
  result_id: string;
  is_published: boolean;
  is_default: boolean;
  published_at: string | null;
  dto_version: '1';
}

export interface CalculationHistoryDto {
  items: CalculationHistoryItemDto[];
  next_before_created_at: string | null;
  next_before_job_id: string | null;
  dto_version: '1';
}

export interface DashboardFinancialLineDto {
  code: string;
  label: string;
  baseline: number;
  comparison: number;
  delta: number;
  comparison_ratio_to_revenue: number | null;
}

export interface PnlDashboardDto {
  result_id: string;
  job_id: string;
  identity: {
    baseline_model_id: string; baseline_model_name: string;
    comparison_model_id: string; comparison_model_name: string;
    model_year: number; start_month: number; end_month: number;
    available_months: number[]; actual_months: number[];
    actual_through_month: number | null;
  };
  kpis: {
    latest_month: number;
    revenue: { latest: DashboardFinancialLineDto; period: DashboardFinancialLineDto };
    gross_profit: { latest: DashboardFinancialLineDto; period: DashboardFinancialLineDto };
    operating_profit: { latest: DashboardFinancialLineDto; period: DashboardFinancialLineDto };
    latest_operating_margin: { baseline: number | null; comparison: number | null; delta_percentage_points: number | null };
    period_operating_margin: { baseline: number | null; comparison: number | null; delta_percentage_points: number | null };
  };
  monthly_series: Array<{
    month: number; comparison_period_type: '실적' | '추정' | '계획' | null;
    revenue: DashboardFinancialLineDto; cogs: DashboardFinancialLineDto;
    gross_profit: DashboardFinancialLineDto;
    operating_profit: DashboardFinancialLineDto;
    baseline_operating_margin: number | null; comparison_operating_margin: number | null;
  }>;
  pnl_statement: DashboardFinancialLineDto[];
  manufacturing: {
    cost_lines: DashboardFinancialLineDto[];
    material_components: {
      nonwoven_price_ex_fx: number | null; nonwoven_jpy: number | null;
      materials_ex_nonwoven: number | null; total: number | null;
      jpy_fx_unit: 'KRW/JPY'; mcm_is_separate_effect: false;
    };
    accounts: DashboardAccountDto[];
    fixed_cost_policy: {
      manufacturing_effect_includes_variable_and_fixed: true;
      fixed_manufacturing_is_not_a_separate_top_level_effect: true;
    };
  };
  sga: { accounts: DashboardAccountDto[]; fixed_scope: string };
  product_groups: Array<{
    code: 'SW' | 'BW' | 'LC' | 'FS' | '신사업'; display_name: string;
    quantity_unit: 'PCS' | 'm'; baseline_quantity: number; comparison_quantity: number;
    baseline_revenue: number; comparison_revenue: number; revenue_delta: number;
    baseline_cogs: number; comparison_cogs: number;
    baseline_gross_profit: number; comparison_gross_profit: number;
  }>;
  key_facts: {
    effects: Array<{ code: string; label: string; profit_effect: number }>;
    effects_total: number; residual: number; operating_profit_delta: number; reconciled: boolean;
  };
  result_schema_version: string;
  completed_at: string;
  published_at: string;
  currency_unit: 'KRW';
  dto_version: '1';
}

export interface DashboardAccountDto {
  account: string; classification: string; section: string;
  baseline: number; comparison: number; delta: number; profit_effect: number | null;
  inventory_realization_rate: number | null; activity_effect: number | null;
  unit_effect: number | null; fixed_effect: number | null;
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

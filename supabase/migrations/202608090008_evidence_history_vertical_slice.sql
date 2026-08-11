-- Evidence Excel delivery and bounded calculation history read capabilities.
-- This migration does not persist derived evidence and never runs calculations.

begin;

create or replace function public.get_calculation_result_evidence_admin_by_id(
    p_result_id uuid,
    p_supported_result_schema_versions text[]
) returns table (
    result_id uuid,
    job_id uuid,
    result_payload jsonb,
    analysis_request jsonb,
    baseline_model_id uuid,
    comparison_model_id uuid,
    baseline_workbook_sha256 text,
    comparison_workbook_sha256 text,
    baseline_workbook_bucket text,
    baseline_workbook_path text,
    comparison_workbook_bucket text,
    comparison_workbook_path text,
    engine_version text,
    mapping_version text,
    mapping_hash text,
    result_schema_version text
)
language sql
stable
security definer
set search_path = ''
as $$
    select result_row.id,
           result_row.job_id,
           result_row.result,
           job.analysis_request,
           result_row.baseline_model_id,
           result_row.comparison_model_id,
           result_row.baseline_workbook_sha256,
           result_row.comparison_workbook_sha256,
           baseline_model.workbook_bucket,
           baseline_model.workbook_path,
           comparison_model.workbook_bucket,
           comparison_model.workbook_path,
           result_row.engine_version,
           result_row.mapping_version,
           result_row.mapping_hash,
           result_row.result_schema_version
      from public.calculation_results result_row
      join public.calculation_jobs job on job.id = result_row.job_id
      join public.models baseline_model on baseline_model.id = result_row.baseline_model_id
      join public.models comparison_model on comparison_model.id = result_row.comparison_model_id
     where result_row.id = p_result_id
       and coalesce(array_length(p_supported_result_schema_versions, 1), 0) > 0
       and result_row.result_schema_version = any(p_supported_result_schema_versions)
       and job.status = 'completed'
       and result_row.baseline_model_id = job.baseline_model_id
       and result_row.comparison_model_id = job.comparison_model_id
       and result_row.model_id = result_row.comparison_model_id
       and result_row.baseline_workbook_sha256 = job.baseline_workbook_sha256
       and result_row.comparison_workbook_sha256 = job.comparison_workbook_sha256
       and baseline_model.workbook_sha256 = result_row.baseline_workbook_sha256
       and comparison_model.workbook_sha256 = result_row.comparison_workbook_sha256
       and result_row.engine_version = job.engine_version
       and result_row.mapping_version = job.mapping_version
       and result_row.mapping_hash = job.mapping_hash
       and result_row.result_schema_version = job.result_schema_version
       and jsonb_typeof(result_row.result -> 'comparison_result') = 'object'
       and exists (
           select 1
             from public.app_config config
            where config.config_key = 'model_mapping'
              and config.status = 'published'
              and config.version = result_row.mapping_version
              and config.content_hash = result_row.mapping_hash
       );
$$;

create or replace function public.get_calculation_result_evidence_viewer_by_id(
    p_result_id uuid,
    p_supported_result_schema_versions text[]
) returns table (
    result_id uuid,
    job_id uuid,
    result_payload jsonb,
    analysis_request jsonb,
    baseline_model_id uuid,
    comparison_model_id uuid,
    baseline_workbook_sha256 text,
    comparison_workbook_sha256 text,
    baseline_workbook_bucket text,
    baseline_workbook_path text,
    comparison_workbook_bucket text,
    comparison_workbook_path text,
    engine_version text,
    mapping_version text,
    mapping_hash text,
    result_schema_version text
)
language sql
stable
security definer
set search_path = ''
as $$
    select evidence.*
      from public.get_calculation_result_evidence_admin_by_id(
          p_result_id,
          p_supported_result_schema_versions
      ) evidence
     where public.validate_calculation_result_availability(
          p_result_id,
          p_supported_result_schema_versions
     );
$$;

create or replace function public.list_calculation_history_admin(
    p_limit integer default 25,
    p_before_created_at timestamptz default null,
    p_before_job_id uuid default null
) returns table (
    job_id uuid,
    result_id uuid,
    status text,
    baseline_model_id uuid,
    baseline_model_name text,
    comparison_model_id uuid,
    comparison_model_name text,
    start_month smallint,
    end_month smallint,
    attempt integer,
    max_attempts integer,
    created_at timestamptz,
    completed_at timestamptz,
    error_code text,
    error_message text,
    is_published boolean
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
    if p_limit < 1 or p_limit > 50 then
        raise exception 'history limit must be between 1 and 50';
    end if;
    if (p_before_created_at is null) <> (p_before_job_id is null) then
        raise exception 'history cursor fields must be provided together';
    end if;

    return query
    select job.id,
           case when job.status = 'completed' then result_row.id else null end,
           job.status,
           job.baseline_model_id,
           baseline_model.name,
           job.comparison_model_id,
           comparison_model.name,
           (job.analysis_request ->> 'start_month')::smallint,
           (job.analysis_request ->> 'end_month')::smallint,
           job.attempt,
           job.max_attempts,
           job.created_at,
           job.completed_at,
           job.error_code,
           case
               when job.error_code is null then null
               when job.error_code = 'INPUT_INTEGRITY_MISMATCH' then 'Calculation input integrity check failed'
               when job.error_code = 'INPUT_PROVENANCE_UNRESOLVED' then 'Calculation input provenance is unresolved'
               when job.error_code = 'preflight_failed' then 'Workbook preflight failed'
               when job.error_code = 'upload_timeout' then 'Workbook upload timed out'
               when job.error_code = 'attempts_exhausted' then 'Calculation retry limit was reached'
               else 'Calculation failed'
           end,
           coalesce(result_row.is_published, false)
      from public.calculation_jobs job
      join public.models baseline_model on baseline_model.id = job.baseline_model_id
      join public.models comparison_model on comparison_model.id = job.comparison_model_id
      left join public.calculation_results result_row on result_row.job_id = job.id
     where p_before_created_at is null
        or (job.created_at, job.id) < (p_before_created_at, p_before_job_id)
     order by job.created_at desc, job.id desc
     limit p_limit + 1;
end;
$$;

revoke all on function public.get_calculation_result_evidence_admin_by_id(uuid, text[])
    from public, anon, authenticated;
grant execute on function public.get_calculation_result_evidence_admin_by_id(uuid, text[])
    to service_role;

revoke all on function public.get_calculation_result_evidence_viewer_by_id(uuid, text[])
    from public, anon, authenticated;
grant execute on function public.get_calculation_result_evidence_viewer_by_id(uuid, text[])
    to service_role;

revoke all on function public.list_calculation_history_admin(integer, timestamptz, uuid)
    from public, anon, authenticated;
grant execute on function public.list_calculation_history_admin(integer, timestamptz, uuid)
    to service_role;

commit;

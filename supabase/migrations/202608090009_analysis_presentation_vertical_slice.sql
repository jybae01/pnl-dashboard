-- Narrow stored-Result payload for the trusted analysis presentation mapper.
-- No workbook or calculation engine is invoked by these read capabilities.

begin;

create or replace function public.get_calculation_result_presentation_admin_by_id(
    p_result_id uuid,
    p_supported_result_schema_versions text[]
) returns table (
    result_id uuid,
    job_id uuid,
    result_payload jsonb,
    analysis_request jsonb,
    baseline_model_id uuid,
    baseline_model_name text,
    comparison_model_id uuid,
    comparison_model_name text,
    baseline_workbook_sha256 text,
    comparison_workbook_sha256 text,
    engine_version text,
    mapping_version text,
    mapping_hash text,
    result_schema_version text,
    completed_at timestamptz,
    created_at timestamptz,
    is_published boolean,
    is_default boolean,
    published_at timestamptz
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
           baseline_model.name,
           result_row.comparison_model_id,
           comparison_model.name,
           result_row.baseline_workbook_sha256,
           result_row.comparison_workbook_sha256,
           result_row.engine_version,
           result_row.mapping_version,
           result_row.mapping_hash,
           result_row.result_schema_version,
           job.completed_at,
           result_row.created_at,
           result_row.is_published,
           result_row.is_default,
           result_row.published_at
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
       and jsonb_typeof(result_row.result -> 'analysis_view') = 'object'
       and jsonb_typeof(result_row.result -> 'fact_pack') = 'object'
       and exists (
           select 1
             from public.app_config config
            where config.config_key = 'model_mapping'
              and config.status = 'published'
              and config.version = result_row.mapping_version
              and config.content_hash = result_row.mapping_hash
       );
$$;

create or replace function public.get_calculation_result_presentation_viewer_by_id(
    p_result_id uuid,
    p_supported_result_schema_versions text[]
) returns table (
    result_id uuid,
    job_id uuid,
    result_payload jsonb,
    analysis_request jsonb,
    baseline_model_id uuid,
    baseline_model_name text,
    comparison_model_id uuid,
    comparison_model_name text,
    baseline_workbook_sha256 text,
    comparison_workbook_sha256 text,
    engine_version text,
    mapping_version text,
    mapping_hash text,
    result_schema_version text,
    completed_at timestamptz,
    created_at timestamptz,
    is_published boolean,
    is_default boolean,
    published_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
    select presentation.*
      from public.get_calculation_result_presentation_admin_by_id(
          p_result_id,
          p_supported_result_schema_versions
      ) presentation
     where public.validate_calculation_result_availability(
          p_result_id,
          p_supported_result_schema_versions
     );
$$;

revoke all on function public.get_calculation_result_presentation_admin_by_id(uuid, text[])
    from public, anon, authenticated;
grant execute on function public.get_calculation_result_presentation_admin_by_id(uuid, text[])
    to service_role;

revoke all on function public.get_calculation_result_presentation_viewer_by_id(uuid, text[])
    from public, anon, authenticated;
grant execute on function public.get_calculation_result_presentation_viewer_by_id(uuid, text[])
    to service_role;

commit;

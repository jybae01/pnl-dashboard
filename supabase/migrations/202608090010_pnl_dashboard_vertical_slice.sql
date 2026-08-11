-- Read-only P&L dashboard snapshot capability.
-- The Worker persists the snapshot; Viewer requests never open Excel or run an engine.

begin;

create or replace function public.get_pnl_dashboard_viewer(
    p_supported_result_schema_versions text[]
) returns table (
    result_id uuid,
    job_id uuid,
    dashboard jsonb,
    baseline_model_id uuid,
    comparison_model_id uuid,
    result_schema_version text,
    completed_at timestamptz,
    published_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
    select available.result_id,
           available.job_id,
           available.result_payload -> 'pnl_dashboard',
           available.baseline_model_id,
           available.comparison_model_id,
           available.result_schema_version,
           available.completed_at,
           available.published_at
      from public.calculation_results candidate
      join lateral public.get_calculation_result_presentation_viewer_by_id(
          candidate.id,
          p_supported_result_schema_versions
      ) available on true
     where coalesce(array_length(p_supported_result_schema_versions, 1), 0) > 0
       and jsonb_typeof(available.result_payload -> 'pnl_dashboard') = 'object'
       and available.result_payload -> 'pnl_dashboard' ->> 'snapshot_version' = '1'
     order by available.is_default desc,
              available.created_at desc,
              available.result_id desc
     limit 1;
$$;

revoke all on function public.get_pnl_dashboard_viewer(text[])
    from public, anon, authenticated;
grant execute on function public.get_pnl_dashboard_viewer(text[])
    to service_role;

commit;

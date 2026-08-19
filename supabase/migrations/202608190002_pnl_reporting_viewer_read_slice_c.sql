-- P&L Reporting Slice C: service-role-only active canonical read source.
-- Reporting arithmetic remains in the pure Python read model.

begin;

create or replace function public.get_pnl_reporting_viewer_source(
    p_reporting_year integer
) returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
    if p_reporting_year is null or p_reporting_year not between 2000 and 2200 then
        raise exception 'invalid P&L Reporting year';
    end if;

    return pg_catalog.jsonb_build_object(
        'available_years', coalesce((
            select pg_catalog.jsonb_agg(
                active_years.reporting_year order by active_years.reporting_year desc
            )
            from (
                select distinct active.reporting_year
                from public.pnl_reporting_active_datasets as active
            ) as active_years
        ), '[]'::jsonb),
        'datasets', coalesce((
            select pg_catalog.jsonb_agg(
                pg_catalog.jsonb_build_object(
                    'pointer_reporting_year', active.reporting_year,
                    'pointer_dataset_type', active.dataset_type,
                    'pointer_dataset_id', active.dataset_id,
                    'dataset_id', dataset.id,
                    'dataset_type', dataset.dataset_type,
                    'reporting_year', dataset.reporting_year,
                    'canonical_schema_version', dataset.canonical_schema_version,
                    'template_version', dataset.template_version,
                    'actual_through_month', dataset.actual_through_month,
                    'canonical_payload', dataset.canonical_payload,
                    'uploaded_at', dataset.uploaded_at,
                    'superseded_at', dataset.superseded_at,
                    'superseded_by_dataset_id', dataset.superseded_by_dataset_id
                ) order by active.dataset_type
            )
            from public.pnl_reporting_active_datasets as active
            left join public.pnl_reporting_datasets as dataset
                on dataset.id = active.dataset_id
            where active.reporting_year = p_reporting_year
        ), '[]'::jsonb)
    );
end;
$$;

revoke all on function public.get_pnl_reporting_viewer_source(integer)
    from public, anon, authenticated, service_role;
grant execute on function public.get_pnl_reporting_viewer_source(integer)
    to service_role;

commit;

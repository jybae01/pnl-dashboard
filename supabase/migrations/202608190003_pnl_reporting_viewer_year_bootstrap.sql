-- P&L Reporting final frontend integration: backend-authoritative year bootstrap.
-- The optional request year never changes reporting arithmetic or dataset identity.

begin;

create or replace function public.get_pnl_reporting_viewer_source(
    p_reporting_year integer default null
) returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v_selected_year integer;
begin
    if p_reporting_year is not null and p_reporting_year not between 2000 and 2200 then
        raise exception 'invalid P&L Reporting year';
    end if;

    select coalesce(
        p_reporting_year,
        pg_catalog.max(active.reporting_year),
        pg_catalog.date_part('year', pg_catalog.now())::integer
    )
    into v_selected_year
    from public.pnl_reporting_active_datasets as active;

    return pg_catalog.jsonb_build_object(
        'selected_year', v_selected_year,
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
            where active.reporting_year = v_selected_year
        ), '[]'::jsonb)
    );
end;
$$;

revoke all on function public.get_pnl_reporting_viewer_source(integer)
    from public, anon, authenticated, service_role;
grant execute on function public.get_pnl_reporting_viewer_source(integer)
    to service_role;

commit;

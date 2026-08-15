-- Slice 3A: make post-error status lookup mirror prepare preflight outcomes.

begin;

create or replace function public.get_persistent_delete_status(
    p_resource_type text,
    p_resource_id uuid
) returns table (
    delete_status text,
    storage_bucket text,
    storage_path text,
    owner_model_id uuid,
    reference_counts jsonb,
    idempotent_replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_receipt public.persistent_delete_receipts%rowtype;
    v_model public.models%rowtype;
    v_job public.calculation_jobs%rowtype;
    v_result public.calculation_results%rowtype;
    v_has_result boolean := false;
    v_generation_id uuid;
    v_analysis_jobs bigint;
    v_analysis_results bigint;
    v_forecast_uses bigint;
    v_derived_models bigint;
    v_ingestion_status text;
    v_generation_status text;
    v_references jsonb;
begin
    if p_resource_type not in ('model', 'analysis') or p_resource_id is null then
        raise exception 'invalid persistent delete operation';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'persistent-delete:' || p_resource_type || ':' || p_resource_id::text,
            0
        )
    );

    select * into v_receipt
      from public.persistent_delete_receipts receipt
     where receipt.resource_type = p_resource_type
       and receipt.resource_id = p_resource_id;
    if found then
        return query select
            case when v_receipt.storage_status = 'complete'
                 then 'DELETED' else 'CLEANUP_REQUIRED' end,
            v_receipt.storage_bucket,
            v_receipt.storage_path,
            v_receipt.owner_model_id,
            pg_catalog.jsonb_strip_nulls(pg_catalog.jsonb_build_object(
                'cleanup_attempts', v_receipt.cleanup_attempts,
                'last_error_code', v_receipt.last_error_code
            )),
            true;
        return;
    end if;

    if p_resource_type = 'model' then
        select * into v_model
          from public.models model_row
         where model_row.id = p_resource_id
         for update;
        if not found then
            return query select
                'PREPARE_UNCERTAIN'::text, null::text, null::text,
                p_resource_id, '{}'::jsonb, false;
            return;
        end if;

        if v_model.is_default or v_model.is_published or v_model.confirmed then
            return query select
                'BLOCKED_PROTECTED'::text, null::text, null::text,
                p_resource_id,
                pg_catalog.jsonb_build_object(
                    'publication_state',
                    case when v_model.is_default then 'default' else 'published' end
                ),
                false;
            return;
        end if;

        if v_model.workbook_bucket <> 'pnl-models'
           or v_model.workbook_path <> pg_catalog.format(
               'models/%s/source.xlsx', p_resource_id
           )
           or not public.is_valid_pnl_storage_path(v_model.workbook_path, 'source') then
            return query select
                'FAILED'::text, null::text, null::text, p_resource_id,
                pg_catalog.jsonb_build_object(
                    'integrity', 'model_storage_ownership_invalid'
                ),
                false;
            return;
        end if;

        select request_row.status into v_ingestion_status
          from public.model_ingestion_requests request_row
         where request_row.model_id = p_resource_id
         for update;
        if found and v_ingestion_status <> 'completed' then
            return query select
                'BLOCKED_IN_USE'::text, null::text, null::text, p_resource_id,
                pg_catalog.jsonb_build_object(
                    'model_ingestion_status', v_ingestion_status
                ),
                false;
            return;
        end if;

        select request_row.id, request_row.status
          into v_generation_id, v_generation_status
          from public.forecast_generation_requests request_row
         where request_row.model_id = p_resource_id
         for update;
        if found and (
            v_generation_status <> 'completed'
            or v_model.forecast_generation_id is distinct from v_generation_id
        ) then
            return query select
                'BLOCKED_IN_USE'::text, null::text, null::text, p_resource_id,
                pg_catalog.jsonb_build_object(
                    'forecast_generation_status', v_generation_status
                ),
                false;
            return;
        end if;

        select count(*) into v_analysis_jobs
          from public.calculation_jobs job
         where p_resource_id in (
             job.model_id, job.baseline_model_id, job.comparison_model_id
         );
        select count(*) into v_analysis_results
          from public.calculation_results result_row
         where p_resource_id in (
             result_row.model_id,
             result_row.baseline_model_id,
             result_row.comparison_model_id
         );
        select count(*) into v_forecast_uses
          from public.forecast_generation_requests request_row
         where request_row.base_model_id = p_resource_id;
        select count(*) into v_derived_models
          from public.models derived
         where derived.source_model_id = p_resource_id;

        v_references := pg_catalog.jsonb_build_object(
            'analysis_jobs', v_analysis_jobs,
            'analysis_results', v_analysis_results,
            'forecast_generations', v_forecast_uses,
            'derived_models', v_derived_models
        );
        if v_analysis_jobs + v_analysis_results + v_forecast_uses + v_derived_models > 0 then
            return query select
                'BLOCKED_IN_USE'::text, null::text, null::text,
                p_resource_id, v_references, false;
            return;
        end if;

        return query select
            'NOT_COMMITTED'::text, null::text, null::text,
            p_resource_id, '{}'::jsonb, false;
        return;
    end if;

    select * into v_job
      from public.calculation_jobs job
     where job.id = p_resource_id
     for update;
    if not found then
        return query select
            'PREPARE_UNCERTAIN'::text, null::text, null::text,
            p_resource_id, '{}'::jsonb, false;
        return;
    end if;
    if v_job.status not in ('completed', 'failed') then
        return query select
            'BLOCKED_NON_TERMINAL'::text, null::text, null::text,
            v_job.model_id,
            pg_catalog.jsonb_build_object('status', v_job.status), false;
        return;
    end if;
    if v_job.queue_message_id is not null and v_job.queue_archived_at is null then
        return query select
            'FAILED'::text, null::text, null::text, v_job.model_id,
            pg_catalog.jsonb_build_object('queue_state', 'unsettled'), false;
        return;
    end if;

    select * into v_result
      from public.calculation_results result_row
     where result_row.job_id = p_resource_id
     for update;
    v_has_result := found;
    if v_job.status = 'completed' and not v_has_result then
        return query select
            'FAILED'::text, null::text, null::text, v_job.model_id,
            pg_catalog.jsonb_build_object('integrity', 'completed_result_missing'), false;
        return;
    end if;
    if v_job.status = 'failed' and v_has_result then
        return query select
            'FAILED'::text, null::text, null::text, v_job.model_id,
            pg_catalog.jsonb_build_object('integrity', 'failed_result_present'), false;
        return;
    end if;
    if v_has_result and (v_result.is_default or v_result.is_published) then
        return query select
            'BLOCKED_PROTECTED'::text, null::text, null::text, v_job.model_id,
            pg_catalog.jsonb_build_object(
                'publication_state',
                case when v_result.is_default then 'default' else 'published' end
            ),
            false;
        return;
    end if;
    if v_has_result and (
        (v_result.workbook_bucket is null) <> (v_result.workbook_path is null)
        or (v_result.workbook_path is not null and (
            v_result.workbook_bucket <> 'pnl-models'
            or v_result.workbook_path <> pg_catalog.format(
                'models/%s/jobs/%s/result.xlsx', v_result.model_id, p_resource_id
            )
            or not public.is_valid_pnl_storage_path(
                v_result.workbook_path, 'result'
            )
        ))
    ) then
        return query select
            'FAILED'::text, null::text, null::text, v_job.model_id,
            pg_catalog.jsonb_build_object(
                'integrity', 'analysis_storage_ownership_invalid'
            ),
            false;
        return;
    end if;

    return query select
        'NOT_COMMITTED'::text, null::text, null::text,
        v_job.model_id, '{}'::jsonb, false;
end;
$$;

revoke all on function public.get_persistent_delete_status(text, uuid)
    from public, anon, authenticated;
grant execute on function public.get_persistent_delete_status(text, uuid)
    to service_role;

commit;

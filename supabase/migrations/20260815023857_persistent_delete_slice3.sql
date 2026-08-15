-- Slice 3: Admin-only persistent Model and analysis-history deletion.
-- Storage objects are deleted by the trusted BFF through the Storage API.

begin;

create table public.persistent_delete_receipts (
    id uuid primary key default gen_random_uuid(),
    resource_type text not null check (resource_type in ('model', 'analysis')),
    resource_id uuid not null,
    owner_model_id uuid not null,
    storage_bucket text,
    storage_path text,
    storage_status text not null default 'pending'
        check (storage_status in ('pending', 'cleanup_required', 'complete')),
    cleanup_attempts integer not null default 0 check (cleanup_attempts >= 0),
    last_error_code text check (
        last_error_code is null or last_error_code ~ '^[A-Z][A-Z0-9_]{1,79}$'
    ),
    db_deleted_at timestamptz not null default now(),
    storage_deleted_at timestamptz,
    updated_at timestamptz not null default now(),
    unique (resource_type, resource_id),
    check ((storage_bucket is null) = (storage_path is null)),
    check (
        storage_path is null
        or (resource_type = 'model'
            and storage_bucket = 'pnl-models'
            and storage_path = format('models/%s/source.xlsx', resource_id))
        or (resource_type = 'analysis'
            and storage_bucket = 'pnl-models'
            and storage_path = format(
                'models/%s/jobs/%s/result.xlsx', owner_model_id, resource_id
            ))
    ),
    check (
        (storage_status = 'complete' and storage_deleted_at is not null)
        or (storage_status <> 'complete' and storage_deleted_at is null)
    )
);

alter table public.persistent_delete_receipts enable row level security;
revoke all on table public.persistent_delete_receipts
    from public, anon, authenticated, service_role;

create trigger persistent_delete_receipts_audit
after insert or update or delete on public.persistent_delete_receipts
for each row execute function public.append_row_audit_log();

create or replace function public.prepare_model_persistent_delete(p_model_id uuid)
returns table (
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
    v_generation_id uuid;
    v_analysis_jobs bigint;
    v_analysis_results bigint;
    v_forecast_uses bigint;
    v_derived_models bigint;
    v_ingestion_status text;
    v_generation_status text;
    v_references jsonb;
begin
    if p_model_id is null then
        raise exception 'model id is required';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('persistent-delete:model:' || p_model_id::text, 0)
    );

    select * into v_receipt
      from public.persistent_delete_receipts receipt
     where receipt.resource_type = 'model'
       and receipt.resource_id = p_model_id
     for update;
    if found then
        return query select
            case when v_receipt.storage_status = 'complete'
                 then 'DELETED' else 'READY_FOR_STORAGE' end,
            v_receipt.storage_bucket,
            v_receipt.storage_path,
            v_receipt.owner_model_id,
            '{}'::jsonb,
            true;
        return;
    end if;

    select * into v_model
      from public.models model_row
     where model_row.id = p_model_id
     for update;
    if not found then
        return query select
            'NOT_FOUND'::text, null::text, null::text, p_model_id,
            '{}'::jsonb, false;
        return;
    end if;

    if v_model.workbook_bucket <> 'pnl-models'
       or v_model.workbook_path <> format('models/%s/source.xlsx', p_model_id)
       or not public.is_valid_pnl_storage_path(v_model.workbook_path, 'source') then
        raise exception 'model storage ownership is invalid';
    end if;

    -- These creation-saga rows intentionally have no model_id FK. Lock and
    -- validate them explicitly so a physical delete cannot strand an active
    -- upload/generation or silently erase its recovery state.
    select request_row.status into v_ingestion_status
      from public.model_ingestion_requests request_row
     where request_row.model_id = p_model_id
     for update;
    if found and v_ingestion_status <> 'completed' then
        return query select
            'BLOCKED_IN_USE'::text, null::text, null::text, p_model_id,
            jsonb_build_object('model_ingestion_status', v_ingestion_status), false;
        return;
    end if;

    select request_row.id, request_row.status into v_generation_id, v_generation_status
      from public.forecast_generation_requests request_row
     where request_row.model_id = p_model_id
     for update;
    if found and (
        v_generation_status <> 'completed'
        or v_model.forecast_generation_id is distinct from v_generation_id
    ) then
        return query select
            'BLOCKED_IN_USE'::text, null::text, null::text, p_model_id,
            jsonb_build_object('forecast_generation_status', v_generation_status), false;
        return;
    end if;

    select count(*) into v_analysis_jobs
      from public.calculation_jobs job
     where p_model_id in (job.model_id, job.baseline_model_id, job.comparison_model_id);
    select count(*) into v_analysis_results
      from public.calculation_results result_row
     where p_model_id in (
         result_row.model_id,
         result_row.baseline_model_id,
         result_row.comparison_model_id
     );
    select count(*) into v_forecast_uses
      from public.forecast_generation_requests request_row
     where request_row.base_model_id = p_model_id;
    select count(*) into v_derived_models
      from public.models derived
     where derived.source_model_id = p_model_id;

    v_references := jsonb_build_object(
        'analysis_jobs', v_analysis_jobs,
        'analysis_results', v_analysis_results,
        'forecast_generations', v_forecast_uses,
        'derived_models', v_derived_models
    );
    if v_analysis_jobs + v_analysis_results + v_forecast_uses + v_derived_models > 0 then
        return query select
            'BLOCKED_IN_USE'::text, null::text, null::text, p_model_id,
            v_references, false;
        return;
    end if;

    insert into public.persistent_delete_receipts (
        resource_type, resource_id, owner_model_id,
        storage_bucket, storage_path, storage_status
    ) values (
        'model', p_model_id, p_model_id,
        v_model.workbook_bucket, v_model.workbook_path, 'pending'
    ) returning * into v_receipt;

    delete from public.models model_row where model_row.id = p_model_id;
    delete from public.model_ingestion_requests request_row
     where request_row.model_id = p_model_id;
    delete from public.forecast_generation_requests request_row
     where request_row.model_id = p_model_id;

    return query select
        'READY_FOR_STORAGE'::text,
        v_receipt.storage_bucket,
        v_receipt.storage_path,
        v_receipt.owner_model_id,
        '{}'::jsonb,
        false;
end;
$$;

create or replace function public.prepare_analysis_persistent_delete(p_job_id uuid)
returns table (
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
    v_job public.calculation_jobs%rowtype;
    v_result public.calculation_results%rowtype;
    v_has_result boolean := false;
begin
    if p_job_id is null then
        raise exception 'job id is required';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('persistent-delete:analysis:' || p_job_id::text, 0)
    );

    select * into v_receipt
      from public.persistent_delete_receipts receipt
     where receipt.resource_type = 'analysis'
       and receipt.resource_id = p_job_id
     for update;
    if found then
        return query select
            case when v_receipt.storage_status = 'complete'
                 then 'DELETED' else 'READY_FOR_STORAGE' end,
            v_receipt.storage_bucket,
            v_receipt.storage_path,
            v_receipt.owner_model_id,
            '{}'::jsonb,
            true;
        return;
    end if;

    select * into v_job
      from public.calculation_jobs job
     where job.id = p_job_id
     for update;
    if not found then
        return query select
            'NOT_FOUND'::text, null::text, null::text, p_job_id,
            '{}'::jsonb, false;
        return;
    end if;
    if v_job.status not in ('completed', 'failed') then
        return query select
            'BLOCKED_NON_TERMINAL'::text, null::text, null::text,
            v_job.model_id, jsonb_build_object('status', v_job.status), false;
        return;
    end if;
    if v_job.queue_message_id is not null and v_job.queue_archived_at is null then
        return query select
            'FAILED'::text, null::text, null::text, v_job.model_id,
            jsonb_build_object('queue_state', 'unsettled'), false;
        return;
    end if;

    select * into v_result
      from public.calculation_results result_row
     where result_row.job_id = p_job_id
     for update;
    v_has_result := found;
    if v_job.status = 'completed' and not v_has_result then
        return query select
            'FAILED'::text, null::text, null::text, v_job.model_id,
            jsonb_build_object('integrity', 'completed_result_missing'), false;
        return;
    end if;
    if v_job.status = 'failed' and v_has_result then
        return query select
            'FAILED'::text, null::text, null::text, v_job.model_id,
            jsonb_build_object('integrity', 'failed_result_present'), false;
        return;
    end if;
    if v_has_result and (
        (v_result.workbook_bucket is null) <> (v_result.workbook_path is null)
        or (v_result.workbook_path is not null and (
            v_result.workbook_bucket <> 'pnl-models'
            or v_result.workbook_path <> format(
                'models/%s/jobs/%s/result.xlsx', v_result.model_id, p_job_id
            )
            or not public.is_valid_pnl_storage_path(v_result.workbook_path, 'result')
        ))
    ) then
        raise exception 'analysis storage ownership is invalid';
    end if;

    insert into public.persistent_delete_receipts (
        resource_type, resource_id, owner_model_id,
        storage_bucket, storage_path, storage_status
    ) values (
        'analysis', p_job_id, v_job.model_id,
        case when v_has_result then v_result.workbook_bucket else null end,
        case when v_has_result then v_result.workbook_path else null end,
        'pending'
    ) returning * into v_receipt;

    if v_has_result then
        delete from public.calculation_results result_row
         where result_row.id = v_result.id;
    end if;
    if v_job.queue_message_id is not null then
        delete from pgmq.a_calculation_jobs archived
         where archived.msg_id = v_job.queue_message_id;
    end if;
    delete from public.calculation_jobs job where job.id = p_job_id;

    return query select
        'READY_FOR_STORAGE'::text,
        v_receipt.storage_bucket,
        v_receipt.storage_path,
        v_receipt.owner_model_id,
        '{}'::jsonb,
        false;
end;
$$;

create or replace function public.complete_persistent_delete(
    p_resource_type text,
    p_resource_id uuid
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.persistent_delete_receipts receipt
       set storage_status = 'complete',
           storage_deleted_at = coalesce(receipt.storage_deleted_at, now()),
           last_error_code = null,
           updated_at = now()
     where receipt.resource_type = p_resource_type
       and receipt.resource_id = p_resource_id;
    if not found then
        raise exception 'persistent delete receipt not found';
    end if;
    return true;
end;
$$;

create or replace function public.record_persistent_delete_cleanup_failure(
    p_resource_type text,
    p_resource_id uuid,
    p_error_code text
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    if p_error_code is null or p_error_code !~ '^[A-Z][A-Z0-9_]{1,79}$' then
        raise exception 'invalid cleanup error code';
    end if;
    update public.persistent_delete_receipts receipt
       set storage_status = 'cleanup_required',
           cleanup_attempts = receipt.cleanup_attempts + 1,
           last_error_code = p_error_code,
           updated_at = now()
     where receipt.resource_type = p_resource_type
       and receipt.resource_id = p_resource_id
       and receipt.storage_status <> 'complete';
    if not found then
        raise exception 'persistent delete receipt is unavailable';
    end if;
    return true;
end;
$$;

revoke all on function public.prepare_model_persistent_delete(uuid)
    from public, anon, authenticated;
revoke all on function public.prepare_analysis_persistent_delete(uuid)
    from public, anon, authenticated;
revoke all on function public.complete_persistent_delete(text, uuid)
    from public, anon, authenticated;
revoke all on function public.record_persistent_delete_cleanup_failure(text, uuid, text)
    from public, anon, authenticated;

grant execute on function public.prepare_model_persistent_delete(uuid) to service_role;
grant execute on function public.prepare_analysis_persistent_delete(uuid) to service_role;
grant execute on function public.complete_persistent_delete(text, uuid) to service_role;
grant execute on function public.record_persistent_delete_cleanup_failure(text, uuid, text)
    to service_role;

commit;

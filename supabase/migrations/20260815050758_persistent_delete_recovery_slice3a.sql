-- Slice 3A: recover persistent deletes whose prepare/complete response was lost.
-- The existing (resource_type, resource_id) receipt key remains the operation ID.

begin;

create or replace function public.protect_published_persistent_delete()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if tg_table_name = 'models' then
        if old.is_default or old.is_published or old.confirmed then
            raise exception using
                errcode = '23503',
                message = 'DELETE_PROTECTED_RESOURCE';
        end if;
    elsif tg_table_name = 'calculation_results' then
        if old.is_default or old.is_published then
            raise exception using
                errcode = '23503',
                message = 'DELETE_PROTECTED_RESOURCE';
        end if;
    else
        raise exception 'unsupported persistent delete protection target';
    end if;
    return old;
end;
$$;

drop trigger if exists models_protect_published_delete on public.models;
create trigger models_protect_published_delete
before delete on public.models
for each row execute function public.protect_published_persistent_delete();

drop trigger if exists calculation_results_protect_published_delete on public.calculation_results;
create trigger calculation_results_protect_published_delete
before delete on public.calculation_results
for each row execute function public.protect_published_persistent_delete();

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
begin
    if p_resource_type not in ('model', 'analysis') or p_resource_id is null then
        raise exception 'invalid persistent delete operation';
    end if;

    -- Serialize with prepare_* so absence after this lock is authoritative.
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
        if found then
            return query select
                case when v_model.is_default or v_model.is_published or v_model.confirmed
                     then 'BLOCKED_PROTECTED' else 'NOT_COMMITTED' end,
                null::text,
                null::text,
                p_resource_id,
                case when v_model.is_default or v_model.is_published or v_model.confirmed
                     then pg_catalog.jsonb_build_object(
                         'publication_state',
                         case when v_model.is_default then 'default' else 'published' end
                     )
                     else '{}'::jsonb end,
                false;
            return;
        end if;
    else
        select * into v_job
          from public.calculation_jobs job
         where job.id = p_resource_id
         for update;
        if found then
            select * into v_result
              from public.calculation_results result_row
             where result_row.job_id = p_resource_id;
            v_has_result := found;
            return query select
                case when v_has_result and (v_result.is_default or v_result.is_published)
                     then 'BLOCKED_PROTECTED' else 'NOT_COMMITTED' end,
                null::text,
                null::text,
                v_job.model_id,
                case when v_has_result and (v_result.is_default or v_result.is_published)
                     then pg_catalog.jsonb_build_object(
                         'publication_state',
                         case when v_result.is_default then 'default' else 'published' end
                     )
                     else '{}'::jsonb end,
                false;
            return;
        end if;
    end if;

    -- No receipt and no domain row is not enough evidence to claim pre-commit failure.
    return query select
        'PREPARE_UNCERTAIN'::text,
        null::text,
        null::text,
        p_resource_id,
        '{}'::jsonb,
        false;
end;
$$;

create or replace function public.list_persistent_delete_recovery(
    p_resource_type text,
    p_limit integer default 100
) returns table (
    delete_status text,
    storage_bucket text,
    storage_path text,
    owner_model_id uuid,
    resource_id uuid,
    reference_counts jsonb,
    idempotent_replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
begin
    if p_resource_type not in ('model', 'analysis')
       or p_limit is null or p_limit < 1 or p_limit > 100 then
        raise exception 'invalid persistent delete recovery query';
    end if;
    return query
    select
        'CLEANUP_REQUIRED'::text,
        receipt.storage_bucket,
        receipt.storage_path,
        receipt.owner_model_id,
        receipt.resource_id,
        pg_catalog.jsonb_strip_nulls(pg_catalog.jsonb_build_object(
            'cleanup_attempts', receipt.cleanup_attempts,
            'last_error_code', receipt.last_error_code
        )),
        true
      from public.persistent_delete_receipts receipt
     where receipt.resource_type = p_resource_type
       and receipt.storage_status in ('pending', 'cleanup_required')
     order by receipt.updated_at, receipt.resource_id
     limit p_limit;
end;
$$;

revoke all on function public.protect_published_persistent_delete()
    from public, anon, authenticated, service_role;
revoke all on function public.get_persistent_delete_status(text, uuid)
    from public, anon, authenticated;
revoke all on function public.list_persistent_delete_recovery(text, integer)
    from public, anon, authenticated;

grant execute on function public.get_persistent_delete_status(text, uuid)
    to service_role;
grant execute on function public.list_persistent_delete_recovery(text, integer)
    to service_role;

commit;

-- Forecast orchestration and strict P&L dashboard selection.
-- Forecast calculations remain in the trusted Python ForecastEngine.

begin;

alter table public.models
    add column if not exists source_kind text not null default 'uploaded'
        check (source_kind in ('uploaded', 'forecast_generated')),
    add column if not exists source_model_id uuid references public.models(id) on delete restrict,
    add column if not exists forecast_generation_id uuid unique,
    add column if not exists generation_input_fingerprint text
        check (generation_input_fingerprint is null or generation_input_fingerprint ~ '^[0-9a-f]{64}$'),
    add column if not exists generation_engine_version text,
    add column if not exists generated_at timestamptz;

create table public.forecast_generation_requests (
    id uuid primary key default gen_random_uuid(),
    idempotency_actor text not null check (length(btrim(idempotency_actor)) between 1 and 256),
    idempotency_key text not null check (idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
    request_fingerprint text not null check (request_fingerprint ~ '^[0-9a-f]{64}$'),
    request_payload jsonb not null check (jsonb_typeof(request_payload) = 'object'),
    base_model_id uuid not null references public.models(id) on delete restrict,
    base_workbook_sha256 text not null check (base_workbook_sha256 ~ '^[0-9a-f]{64}$'),
    mapping_version text not null,
    mapping_hash text not null check (mapping_hash ~ '^[0-9a-f]{64}$'),
    engine_version text not null,
    result_schema_version text not null,
    model_id uuid not null unique,
    generated_workbook_sha256 text check (generated_workbook_sha256 ~ '^[0-9a-f]{64}$'),
    status text not null check (status in ('reserved', 'completed', 'failed', 'cleanup_required')),
    lease_token uuid,
    lease_expires_at timestamptz,
    error_code text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    unique (idempotency_actor, idempotency_key),
    check ((status = 'reserved' and lease_token is not null and lease_expires_at is not null and completed_at is null)
        or (status = 'completed' and lease_token is null and lease_expires_at is null
            and completed_at is not null and generated_workbook_sha256 is not null)
        or (status in ('failed','cleanup_required') and lease_token is null
            and lease_expires_at is null and completed_at is null))
);

alter table public.models add constraint models_forecast_generation_fk
    foreign key (forecast_generation_id) references public.forecast_generation_requests(id) on delete restrict;
alter table public.models add constraint models_generated_source_shape check (
    (source_kind = 'uploaded' and source_model_id is null and forecast_generation_id is null
        and generation_input_fingerprint is null and generation_engine_version is null and generated_at is null)
    or (source_kind = 'forecast_generated' and source_model_id is not null
        and forecast_generation_id is not null and generation_input_fingerprint is not null
        and generation_engine_version is not null and generated_at is not null)
);

alter table public.forecast_generation_requests enable row level security;
revoke all on table public.forecast_generation_requests from public, anon, authenticated, service_role;

create or replace function public.reserve_forecast_generation(
    p_idempotency_actor text,
    p_idempotency_key text,
    p_request_fingerprint text,
    p_request_payload jsonb,
    p_base_model_id uuid,
    p_model_year integer,
    p_mapping_version text,
    p_mapping_hash text,
    p_engine_version text,
    p_result_schema_version text
) returns table (
    generation_id uuid, model_id uuid, generation_status text, lease_token uuid,
    idempotency_replayed boolean, base_workbook_bucket text,
    base_workbook_path text, base_workbook_sha256 text
)
language plpgsql security definer set search_path = '' as $$
declare
    v_existing public.forecast_generation_requests%rowtype;
    v_base public.models%rowtype;
    v_generation_id uuid := gen_random_uuid();
    v_model_id uuid := gen_random_uuid();
    v_lease uuid := gen_random_uuid();
    v_has_existing boolean := false;
begin
    if p_idempotency_actor is null or length(btrim(p_idempotency_actor)) not between 1 and 256
       or p_idempotency_key is null or p_idempotency_key !~ '^[A-Za-z0-9._:-]{1,128}$'
       or p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$'
       or p_request_payload is null or jsonb_typeof(p_request_payload) <> 'object'
       or jsonb_typeof(p_request_payload -> 'request') <> 'object'
       or jsonb_typeof(p_request_payload -> 'provenance') <> 'object'
       or p_request_payload #>> '{request,base_model_id}' <> p_base_model_id::text
       or coalesce(p_request_payload #>> '{request,model_year}', '') !~ '^[0-9]{4}$'
       or (p_request_payload #>> '{request,model_year}')::integer <> p_model_year
       or coalesce(p_request_payload #>> '{request,start_month}', '') !~ '^[0-9]{1,2}$'
       or coalesce(p_request_payload #>> '{request,end_month}', '') !~ '^[0-9]{1,2}$'
       or (p_request_payload #>> '{request,start_month}')::integer not between 1 and 12
       or (p_request_payload #>> '{request,end_month}')::integer
            < (p_request_payload #>> '{request,start_month}')::integer
       or (p_request_payload #>> '{request,end_month}')::integer > 12
       or jsonb_typeof(p_request_payload #> '{request,months}') <> 'array'
       or jsonb_array_length(p_request_payload #> '{request,months}')
            <> (p_request_payload #>> '{request,end_month}')::integer
               - (p_request_payload #>> '{request,start_month}')::integer + 1
       or p_request_payload #>> '{provenance,mapping_version}' <> p_mapping_version
       or p_request_payload #>> '{provenance,mapping_hash}' <> p_mapping_hash
       or p_request_payload #>> '{provenance,engine_version}' <> p_engine_version
       or p_request_payload #>> '{provenance,result_schema_version}' <> p_result_schema_version
       or p_model_year not between 2000 and 2200
       or p_engine_version is null or length(btrim(p_engine_version)) = 0
       or p_result_schema_version is null or length(btrim(p_result_schema_version)) = 0 then
        raise exception 'invalid forecast generation request';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_idempotency_actor || ':' || p_idempotency_key, 0));
    select * into v_existing from public.forecast_generation_requests request_row
     where request_row.idempotency_actor = p_idempotency_actor
       and request_row.idempotency_key = p_idempotency_key for update;
    v_has_existing := found;
    if v_has_existing then
        if v_existing.request_fingerprint <> p_request_fingerprint
           or v_existing.request_payload <> p_request_payload
           or v_existing.base_model_id <> p_base_model_id
           or v_existing.mapping_version <> p_mapping_version
           or v_existing.mapping_hash <> p_mapping_hash
           or v_existing.engine_version <> p_engine_version
           or v_existing.result_schema_version <> p_result_schema_version then
            raise exception 'IDEMPOTENCY_CONFLICT';
        end if;
        if v_existing.status = 'completed' then
            return query select v_existing.id, v_existing.model_id, v_existing.status,
                null::uuid, true, 'pnl-models'::text,
                format('models/%s/source.xlsx', v_existing.base_model_id),
                v_existing.base_workbook_sha256;
            return;
        end if;
    end if;
    select * into v_base from public.models model
     where model.id = p_base_model_id for share;
    if not found then raise exception 'MODEL_NOT_FOUND'; end if;
    if not v_base.is_published or v_base.mapping_status <> 'published'
       or v_base.workbook_sha256 is null
       or v_base.workbook_sha256 !~ '^[0-9a-f]{64}$'
       or v_base.workbook_bucket <> 'pnl-models'
       or v_base.workbook_path <> format('models/%s/source.xlsx', v_base.id) then
        raise exception 'MODEL_NOT_AVAILABLE';
    end if;
    if v_base.model_year <> p_model_year then
        raise exception 'MODEL_NOT_AVAILABLE';
    end if;
    if v_base.mapping_version <> p_mapping_version or v_base.mapping_hash <> p_mapping_hash
       or not exists (
           select 1 from public.app_config config
            where config.config_key = 'model_mapping'
              and config.version = p_mapping_version
              and config.content_hash = p_mapping_hash
              and config.status = 'published'
       ) then raise exception 'MAPPING_NOT_AVAILABLE'; end if;

    if v_has_existing then
        if v_existing.request_fingerprint <> p_request_fingerprint
           or v_existing.request_payload <> p_request_payload
           or v_existing.base_model_id <> p_base_model_id
           or v_existing.mapping_version <> p_mapping_version
           or v_existing.mapping_hash <> p_mapping_hash
           or v_existing.engine_version <> p_engine_version
           or v_existing.result_schema_version <> p_result_schema_version then
            raise exception 'IDEMPOTENCY_CONFLICT';
        end if;
        if v_existing.status = 'reserved' then
            if v_existing.lease_expires_at <= now() then
                update public.forecast_generation_requests request_row
                   set status='cleanup_required', lease_token=null, lease_expires_at=null,
                       error_code='FORECAST_LEASE_EXPIRED', updated_at=now()
                 where request_row.id=v_existing.id;
                raise exception 'INGESTION_CLEANUP_REQUIRED';
            end if;
            raise exception 'FORECAST_IN_PROGRESS';
        end if;
        if v_existing.status = 'cleanup_required' then raise exception 'INGESTION_CLEANUP_REQUIRED'; end if;
        update public.forecast_generation_requests request_row
           set status='reserved', lease_token=v_lease, lease_expires_at=now()+interval '30 minutes',
               error_code=null, updated_at=now()
         where request_row.id=v_existing.id;
        return query select v_existing.id, v_existing.model_id, 'reserved'::text,
            v_lease, true, v_base.workbook_bucket, v_base.workbook_path,
            v_existing.base_workbook_sha256;
        return;
    end if;
    insert into public.forecast_generation_requests(
        id, idempotency_actor, idempotency_key, request_fingerprint, request_payload,
        base_model_id, base_workbook_sha256, mapping_version, mapping_hash,
        engine_version, result_schema_version, model_id, status, lease_token, lease_expires_at
    ) values (
        v_generation_id, p_idempotency_actor, p_idempotency_key, p_request_fingerprint,
        p_request_payload, p_base_model_id, v_base.workbook_sha256, p_mapping_version,
        p_mapping_hash, p_engine_version, p_result_schema_version, v_model_id, 'reserved',
        v_lease, now()+interval '30 minutes'
    );
    return query select v_generation_id, v_model_id, 'reserved'::text, v_lease, false,
        v_base.workbook_bucket, v_base.workbook_path, v_base.workbook_sha256;
end;
$$;

create or replace function public.finalize_forecast_generation(
    p_generation_id uuid, p_lease_token uuid, p_generated_workbook_sha256 text,
    p_name text, p_model_year integer, p_version text, p_file_name text,
    p_period_types jsonb, p_mapping_version text, p_mapping_hash text,
    p_engine_version text
) returns public.models
language plpgsql security definer set search_path = '' as $$
declare
    v_request public.forecast_generation_requests%rowtype;
    v_model public.models%rowtype;
begin
    select * into v_request from public.forecast_generation_requests request_row
     where request_row.id = p_generation_id for update;
    if not found or v_request.status <> 'reserved' or p_lease_token is null
       or v_request.lease_token <> p_lease_token or v_request.lease_expires_at <= now()
       or p_generated_workbook_sha256 is null or p_generated_workbook_sha256 !~ '^[0-9a-f]{64}$'
       or p_model_year not between 2000 and 2200
       or p_name is null or length(btrim(p_name)) not between 1 and 200 or p_name ~ '[[:cntrl:]]'
       or p_version is null or length(btrim(p_version)) not between 1 and 64 or p_version ~ '[[:cntrl:]]'
       or p_file_name !~ '^[^/\\]+\.[xX][lL][sS][xX]$' or p_file_name ~ '[[:cntrl:]]'
       or p_period_types is null or jsonb_typeof(p_period_types) <> 'object'
       or p_mapping_version is null or p_mapping_hash is null
       or p_engine_version is null or length(btrim(p_engine_version)) = 0
       or p_mapping_version <> v_request.mapping_version or p_mapping_hash <> v_request.mapping_hash
       or p_engine_version <> v_request.engine_version then
        raise exception 'forecast generation claim is invalid';
    end if;
    if not exists (select 1 from public.models base where base.id = v_request.base_model_id
        and base.is_published and base.mapping_status='published'
        and base.workbook_sha256 = v_request.base_workbook_sha256
        and base.model_year = p_model_year and base.workbook_bucket='pnl-models'
        and base.workbook_path=format('models/%s/source.xlsx', base.id)
        and base.mapping_version = p_mapping_version and base.mapping_hash = p_mapping_hash) then
        raise exception 'MODEL_NOT_AVAILABLE';
    end if;
    insert into public.models(
        id, name, model_type, model_year, start_month, end_month, created_date, version,
        confirmed, is_published, is_default, mapping_status, mapping_version, mapping_hash,
        workbook_bucket, workbook_path, file_name, period_types, workbook_sha256,
        source_kind, source_model_id, forecast_generation_id, generation_input_fingerprint,
        generation_engine_version, generated_at
    ) values (
        v_request.model_id, btrim(p_name), 'FORECAST', p_model_year, 1, 12, current_date, btrim(p_version),
        false, false, false, 'published', p_mapping_version, p_mapping_hash,
        'pnl-models', format('models/%s/source.xlsx', v_request.model_id), p_file_name,
        p_period_types, p_generated_workbook_sha256, 'forecast_generated', v_request.base_model_id,
        v_request.id, v_request.request_fingerprint, p_engine_version, now()
    ) returning * into v_model;
    update public.forecast_generation_requests request_row
       set status='completed', lease_token=null, lease_expires_at=null,
           generated_workbook_sha256=p_generated_workbook_sha256,
           completed_at=now(), updated_at=now(), error_code=null where request_row.id=v_request.id;
    return v_model;
end;
$$;

create or replace function public.get_completed_forecast_generation(p_generation_id uuid)
returns public.models language sql stable security definer set search_path = '' as $$
    select model.* from public.forecast_generation_requests request_row
    join public.models model on model.id=request_row.model_id
    where request_row.id=p_generation_id and request_row.status='completed';
$$;

create or replace function public.record_forecast_generation_failure(
    p_generation_id uuid, p_lease_token uuid, p_cleanup_succeeded boolean, p_error_code text
) returns void language plpgsql security definer set search_path = '' as $$
begin
    update public.forecast_generation_requests request_row
       set status=case when p_cleanup_succeeded then 'failed' else 'cleanup_required' end,
           lease_token=null, lease_expires_at=null, updated_at=now(),
           error_code=left(coalesce(p_error_code, 'FORECAST_GENERATION_FAILED'), 80)
     where request_row.id=p_generation_id and request_row.status='reserved'
       and request_row.lease_token=p_lease_token;
    if not found then raise exception 'forecast generation claim is invalid'; end if;
end;
$$;

create or replace function public.get_forecast_generation_recovery_queue()
returns table (generation_id uuid, model_id uuid, generation_status text,
base_model_id uuid, generated_workbook_sha256 text, error_code text,
created_at timestamptz, updated_at timestamptz)
language sql stable security definer set search_path = '' as $$
    select request_row.id, request_row.model_id, request_row.status,
           request_row.base_model_id, request_row.generated_workbook_sha256,
           request_row.error_code, request_row.created_at, request_row.updated_at
      from public.forecast_generation_requests request_row
     where request_row.status='cleanup_required'
        or (request_row.status='reserved' and request_row.lease_expires_at <= now())
     order by request_row.created_at;
$$;

create or replace function public.acknowledge_forecast_generation_cleanup(
    p_generation_id uuid, p_storage_cleanup_confirmed boolean
) returns void language plpgsql security definer set search_path = '' as $$
begin
    if not coalesce(p_storage_cleanup_confirmed, false) then
        raise exception 'storage cleanup confirmation is required';
    end if;
    update public.forecast_generation_requests request_row
       set status='failed', lease_token=null, lease_expires_at=null,
           updated_at=now(), error_code='ADMIN_CLEANUP_CONFIRMED'
     where request_row.id=p_generation_id
       and (request_row.status='cleanup_required'
         or (request_row.status='reserved' and request_row.lease_expires_at <= now()));
    if not found then raise exception 'forecast recovery item is not eligible'; end if;
end;
$$;

-- Canonical dashboard context is the explicitly published default Result only.
-- Absence of a default is EMPTY; never select an arbitrary recent analysis pair.
create or replace function public.get_pnl_dashboard_viewer(p_supported_result_schema_versions text[])
returns table (result_id uuid, job_id uuid, dashboard jsonb, baseline_model_id uuid,
comparison_model_id uuid, result_schema_version text, completed_at timestamptz, published_at timestamptz)
language sql stable security definer set search_path = '' as $$
    select available.result_id, available.job_id, available.result_payload -> 'pnl_dashboard',
           available.baseline_model_id, available.comparison_model_id,
           available.result_schema_version, available.completed_at, available.published_at
      from public.calculation_results candidate
      join lateral public.get_calculation_result_presentation_viewer_by_id(
          candidate.id, p_supported_result_schema_versions) available on true
     where coalesce(array_length(p_supported_result_schema_versions, 1), 0) > 0
       and available.is_default
       and exists (select 1 from public.models dashboard_model
                    where dashboard_model.id=available.comparison_model_id
                      and dashboard_model.is_default and dashboard_model.is_published)
       and jsonb_typeof(available.result_payload -> 'pnl_dashboard') = 'object'
       and available.result_payload -> 'pnl_dashboard' ->> 'snapshot_version' = '1'
     order by available.created_at desc, available.result_id desc limit 1;
$$;

revoke all on function public.reserve_forecast_generation(text,text,text,jsonb,uuid,integer,text,text,text,text) from public, anon, authenticated;
revoke all on function public.finalize_forecast_generation(uuid,uuid,text,text,integer,text,text,jsonb,text,text,text) from public, anon, authenticated;
revoke all on function public.get_completed_forecast_generation(uuid) from public, anon, authenticated;
revoke all on function public.record_forecast_generation_failure(uuid,uuid,boolean,text) from public, anon, authenticated;
revoke all on function public.get_forecast_generation_recovery_queue() from public, anon, authenticated;
revoke all on function public.acknowledge_forecast_generation_cleanup(uuid,boolean) from public, anon, authenticated;
revoke all on function public.get_pnl_dashboard_viewer(text[]) from public, anon, authenticated;
grant execute on function public.reserve_forecast_generation(text,text,text,jsonb,uuid,integer,text,text,text,text) to service_role;
grant execute on function public.finalize_forecast_generation(uuid,uuid,text,text,integer,text,text,jsonb,text,text,text) to service_role;
grant execute on function public.get_completed_forecast_generation(uuid) to service_role;
grant execute on function public.record_forecast_generation_failure(uuid,uuid,boolean,text) to service_role;
grant execute on function public.get_forecast_generation_recovery_queue() to service_role;
grant execute on function public.acknowledge_forecast_generation_cleanup(uuid,boolean) to service_role;
grant execute on function public.get_pnl_dashboard_viewer(text[]) to service_role;

commit;

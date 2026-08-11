-- Trusted-BFF model ingestion idempotency, saga recovery and publication hardening.
-- Source bytes are uploaded through the private Storage API; SQL never receives them.

begin;

create table if not exists public.model_ingestion_requests (
    id uuid primary key default gen_random_uuid(),
    idempotency_actor text not null check (length(btrim(idempotency_actor)) between 1 and 256),
    idempotency_key text not null check (idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
    request_fingerprint jsonb not null check (jsonb_typeof(request_fingerprint) = 'object'),
    workbook_sha256 text not null check (workbook_sha256 ~ '^[0-9a-f]{64}$'),
    model_id uuid not null unique,
    status text not null default 'reserved'
        check (status in ('reserved', 'completed', 'failed', 'cleanup_required')),
    lease_token uuid,
    error_code text,
    error_detail jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    unique (idempotency_actor, idempotency_key),
    constraint model_ingestion_completed_shape check (
        (status = 'completed' and completed_at is not null and lease_token is null)
        or (status = 'reserved' and completed_at is null and lease_token is not null)
        or (status in ('failed', 'cleanup_required') and completed_at is null and lease_token is null)
    )
);

alter table public.model_ingestion_requests enable row level security;
revoke all on table public.model_ingestion_requests from public, anon, authenticated;
revoke all on table public.model_ingestion_requests from service_role;

create or replace function public.guard_model_ingestion_identity()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if row(
        new.idempotency_actor, new.idempotency_key, new.request_fingerprint,
        new.workbook_sha256, new.model_id, new.created_at
    ) is distinct from row(
        old.idempotency_actor, old.idempotency_key, old.request_fingerprint,
        old.workbook_sha256, old.model_id, old.created_at
    ) then
        raise exception 'model ingestion identity is immutable';
    end if;
    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists model_ingestion_requests_guard_identity on public.model_ingestion_requests;
create trigger model_ingestion_requests_guard_identity
before update on public.model_ingestion_requests
for each row execute function public.guard_model_ingestion_identity();

drop trigger if exists model_ingestion_requests_audit on public.model_ingestion_requests;
create trigger model_ingestion_requests_audit
after insert or update or delete on public.model_ingestion_requests
for each row execute function public.append_row_audit_log();

create or replace function public.reserve_model_ingestion(
    p_idempotency_actor text,
    p_idempotency_key text,
    p_name text,
    p_model_type text,
    p_model_year integer,
    p_version text,
    p_file_name text,
    p_workbook_sha256 text,
    p_period_types jsonb,
    p_mapping_version text,
    p_mapping_hash text
) returns table (
    ingestion_id uuid,
    model_id uuid,
    ingestion_status text,
    lease_token uuid,
    idempotency_replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_fingerprint jsonb;
    v_existing public.model_ingestion_requests%rowtype;
    v_lease uuid := gen_random_uuid();
    v_model_id uuid := gen_random_uuid();
begin
    if p_idempotency_actor is null or length(btrim(p_idempotency_actor)) not between 1 and 256
       or p_idempotency_key is null or p_idempotency_key !~ '^[A-Za-z0-9._:-]{1,128}$' then
        raise exception 'invalid model ingestion idempotency identity';
    end if;
    if p_name is null or length(btrim(p_name)) = 0
       or p_model_type not in ('PLAN', 'ACTUAL', 'FORECAST')
       or p_model_year not between 2000 and 2200
       or p_version is null or length(btrim(p_version)) = 0
       or p_file_name is null or length(btrim(p_file_name)) = 0
       or p_file_name !~ '^[^/\\]+\.[xX][lL][sS][xX]$'
       or p_file_name ~ '[[:cntrl:]]'
       or p_workbook_sha256 !~ '^[0-9a-f]{64}$'
       or jsonb_typeof(coalesce(p_period_types, '{}'::jsonb)) <> 'object'
       or p_mapping_version is null or length(btrim(p_mapping_version)) = 0
       or p_mapping_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid model ingestion request';
    end if;

    if not exists (
        select 1 from public.app_config config
         where config.config_key = 'model_mapping'
           and config.version = p_mapping_version
           and config.content_hash = p_mapping_hash
           and config.status = 'published'
    ) then
        raise exception 'published mapping provenance is unavailable';
    end if;

    v_fingerprint := jsonb_build_object(
        'name', btrim(p_name),
        'model_type', p_model_type,
        'model_year', p_model_year,
        'version', btrim(p_version),
        'file_name', p_file_name,
        'workbook_sha256', p_workbook_sha256,
        'period_types', coalesce(p_period_types, '{}'::jsonb),
        'mapping_version', p_mapping_version,
        'mapping_hash', p_mapping_hash
    );

    perform pg_advisory_xact_lock(
        hashtextextended(p_idempotency_actor || ':' || p_idempotency_key, 0)
    );
    select * into v_existing
      from public.model_ingestion_requests request_row
     where request_row.idempotency_actor = p_idempotency_actor
       and request_row.idempotency_key = p_idempotency_key
     for update;

    if found then
        if v_existing.request_fingerprint is distinct from v_fingerprint
           or v_existing.workbook_sha256 is distinct from p_workbook_sha256 then
            raise exception 'IDEMPOTENCY_CONFLICT';
        end if;
        if v_existing.status = 'completed' then
            return query select v_existing.id, v_existing.model_id,
                v_existing.status, null::uuid, true;
            return;
        end if;
        if v_existing.status = 'cleanup_required' then
            raise exception 'INGESTION_CLEANUP_REQUIRED';
        end if;
        if v_existing.status = 'reserved' then
            return query select v_existing.id, v_existing.model_id,
                'in_progress'::text, null::uuid, true;
            return;
        end if;
        update public.model_ingestion_requests request_row
           set status = 'reserved', lease_token = v_lease,
               error_code = null, error_detail = '{}'::jsonb
         where request_row.id = v_existing.id;
        return query select v_existing.id, v_existing.model_id,
            'reserved'::text, v_lease, true;
        return;
    end if;

    insert into public.model_ingestion_requests (
        idempotency_actor, idempotency_key, request_fingerprint,
        workbook_sha256, model_id, status, lease_token
    ) values (
        p_idempotency_actor, p_idempotency_key, v_fingerprint,
        p_workbook_sha256, v_model_id, 'reserved', v_lease
    ) returning id into ingestion_id;
    model_id := v_model_id;
    ingestion_status := 'reserved';
    lease_token := v_lease;
    idempotency_replayed := false;
    return next;
end;
$$;

create or replace function public.finalize_model_ingestion(
    p_ingestion_id uuid,
    p_lease_token uuid
) returns public.models
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_request public.model_ingestion_requests%rowtype;
    v_model public.models%rowtype;
    v_fingerprint jsonb;
begin
    select * into v_request
      from public.model_ingestion_requests request_row
     where request_row.id = p_ingestion_id
     for update;
    if not found or v_request.status <> 'reserved'
       or v_request.lease_token is distinct from p_lease_token then
        raise exception 'model ingestion claim is invalid';
    end if;
    v_fingerprint := v_request.request_fingerprint;
    if not exists (
        select 1 from public.app_config config
         where config.config_key = 'model_mapping'
           and config.version = v_fingerprint ->> 'mapping_version'
           and config.content_hash = v_fingerprint ->> 'mapping_hash'
           and config.status = 'published'
    ) then
        raise exception 'published mapping provenance is unavailable';
    end if;

    insert into public.models (
        id, name, model_type, model_year, start_month, end_month,
        created_date, version, confirmed, is_published, is_default,
        mapping_status, mapping_version, mapping_hash,
        workbook_bucket, workbook_path, file_name, period_types,
        workbook_sha256
    ) values (
        v_request.model_id,
        v_fingerprint ->> 'name',
        v_fingerprint ->> 'model_type',
        (v_fingerprint ->> 'model_year')::integer,
        1, 12, current_date,
        v_fingerprint ->> 'version',
        false, false, false,
        'published',
        v_fingerprint ->> 'mapping_version',
        v_fingerprint ->> 'mapping_hash',
        'pnl-models',
        format('models/%s/source.xlsx', v_request.model_id),
        v_fingerprint ->> 'file_name',
        coalesce(v_fingerprint -> 'period_types', '{}'::jsonb),
        v_request.workbook_sha256
    ) returning * into v_model;

    update public.model_ingestion_requests request_row
       set status = 'completed', lease_token = null,
           completed_at = now(), error_code = null, error_detail = '{}'::jsonb
     where request_row.id = v_request.id;
    return v_model;
end;
$$;

create or replace function public.record_model_ingestion_failure(
    p_ingestion_id uuid,
    p_lease_token uuid,
    p_cleanup_succeeded boolean,
    p_error_code text,
    p_error_detail jsonb default '{}'::jsonb
) returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.model_ingestion_requests request_row
       set status = case when p_cleanup_succeeded then 'failed' else 'cleanup_required' end,
           lease_token = null,
           error_code = left(coalesce(nullif(btrim(p_error_code), ''), 'INGESTION_FAILED'), 128),
           error_detail = coalesce(p_error_detail, '{}'::jsonb)
     where request_row.id = p_ingestion_id
       and request_row.status = 'reserved'
       and request_row.lease_token is not distinct from p_lease_token;
    if not found then
        raise exception 'model ingestion claim is invalid';
    end if;
end;
$$;

-- Idempotent recovery for a lost HTTP response after DB commit. This narrow
-- server-only read is the only safe signal that Storage compensation must stop.
create or replace function public.get_completed_model_ingestion(
    p_ingestion_id uuid
) returns public.models
language sql
security definer
set search_path = ''
as $$
    select model_row
      from public.model_ingestion_requests request_row
      join public.models model_row on model_row.id = request_row.model_id
     where request_row.id = p_ingestion_id
       and request_row.status = 'completed';
$$;

-- Narrow operator diagnostics keep direct saga-table access revoked. Reserved
-- rows older than one hour represent interrupted requests; cleanup_required
-- rows represent a failed Storage compensation that must be retried manually.
create or replace function public.get_model_ingestion_recovery_queue()
returns table (
    ingestion_id uuid,
    model_id uuid,
    ingestion_status text,
    workbook_sha256 text,
    error_code text,
    error_detail jsonb,
    created_at timestamptz,
    updated_at timestamptz
)
language sql
security definer
set search_path = ''
as $$
    select request_row.id, request_row.model_id, request_row.status,
           request_row.workbook_sha256, request_row.error_code,
           request_row.error_detail, request_row.created_at, request_row.updated_at
      from public.model_ingestion_requests request_row
     where request_row.status = 'cleanup_required'
        or (request_row.status = 'reserved'
            and request_row.updated_at < now() - interval '1 hour')
     order by request_row.created_at;
$$;

-- The trusted operator calls this only after deleting (or confirming absence
-- of) the exact canonical Storage object via the Storage API.
create or replace function public.acknowledge_model_ingestion_cleanup(
    p_ingestion_id uuid,
    p_storage_cleanup_confirmed boolean
) returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not coalesce(p_storage_cleanup_confirmed, false) then
        raise exception 'storage cleanup confirmation is required';
    end if;
    update public.model_ingestion_requests request_row
       set status = 'failed', lease_token = null,
           error_code = 'ADMIN_CLEANUP_CONFIRMED',
           error_detail = request_row.error_detail
               || jsonb_build_object('cleanup_confirmed_at', now())
     where request_row.id = p_ingestion_id
       and (
           request_row.status = 'cleanup_required'
           or (request_row.status = 'reserved'
               and request_row.updated_at < now() - interval '1 hour')
       );
    if not found then
        raise exception 'model ingestion recovery item is not eligible';
    end if;
end;
$$;

-- Publication remains a separate Admin capability. This replacement keeps the
-- existing ABI while requiring complete source and published mapping provenance.
create or replace function public.set_model_publication(
    p_model_id uuid,
    p_is_published boolean,
    p_is_default boolean default false
) returns public.models
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_model public.models%rowtype;
begin
    if p_is_default and not p_is_published then
        raise exception 'a default model must be published';
    end if;
    select * into v_model from public.models where id = p_model_id for update;
    if not found then
        raise exception 'model not found';
    end if;
    if p_is_published then
        if v_model.workbook_sha256 is null
           or v_model.workbook_sha256 !~ '^[0-9a-f]{64}$'
           or v_model.workbook_bucket <> 'pnl-models'
           or v_model.workbook_path <> format('models/%s/source.xlsx', v_model.id)
           or v_model.mapping_status <> 'published' then
            raise exception 'model source provenance is incomplete';
        end if;
        if not exists (
            select 1 from public.app_config config
             where config.config_key = 'model_mapping'
               and config.version = v_model.mapping_version
               and config.content_hash = v_model.mapping_hash
               and config.status = 'published'
        ) then
            raise exception 'published mapping provenance is unavailable';
        end if;
    end if;
    if p_is_default then
        update public.models set is_default = false where is_default and id <> p_model_id;
    end if;
    update public.models
       set is_published = p_is_published,
           confirmed = p_is_published,
           is_default = p_is_default
     where id = p_model_id
     returning * into v_model;
    return v_model;
end;
$$;

revoke all on function public.reserve_model_ingestion(
    text, text, text, text, integer, text, text, text, jsonb, text, text
) from public, anon, authenticated;
revoke all on function public.finalize_model_ingestion(uuid, uuid)
    from public, anon, authenticated;
revoke all on function public.record_model_ingestion_failure(uuid, uuid, boolean, text, jsonb)
    from public, anon, authenticated;
revoke all on function public.get_completed_model_ingestion(uuid)
    from public, anon, authenticated;
revoke all on function public.get_model_ingestion_recovery_queue()
    from public, anon, authenticated;
revoke all on function public.acknowledge_model_ingestion_cleanup(uuid, boolean)
    from public, anon, authenticated;
revoke all on function public.set_model_publication(uuid, boolean, boolean)
    from public, anon, authenticated;

grant execute on function public.reserve_model_ingestion(
    text, text, text, text, integer, text, text, text, jsonb, text, text
) to service_role;
grant execute on function public.finalize_model_ingestion(uuid, uuid) to service_role;
grant execute on function public.record_model_ingestion_failure(uuid, uuid, boolean, text, jsonb)
    to service_role;
grant execute on function public.get_completed_model_ingestion(uuid) to service_role;
grant execute on function public.get_model_ingestion_recovery_queue() to service_role;
grant execute on function public.acknowledge_model_ingestion_cleanup(uuid, boolean)
    to service_role;
grant execute on function public.set_model_publication(uuid, boolean, boolean) to service_role;

commit;

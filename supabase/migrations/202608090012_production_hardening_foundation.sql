-- Production hardening: shared BFF auth/lockout/audit and global Forecast permits.
-- Browser roles receive no access to these trusted-server capabilities.

begin;

-- SECURITY DEFINER functions from earlier migrations may resolve objects in
-- public. Prevent untrusted roles from creating shadow objects there.
revoke create on schema public from public, anon, authenticated;
revoke insert on table public.audit_logs from service_role;
revoke select on table public.audit_logs from service_role;
revoke usage, select on sequence public.audit_logs_id_seq from service_role;

-- New Results must remain bounded before any BFF RPC materializes JSON. Existing
-- historical rows are audited separately during staging, hence NOT VALID.
alter table public.calculation_results
    add constraint calculation_results_payload_size_limit
    check (octet_length(result::text) <= 26214400) not valid;
alter table public.calculation_jobs
    add constraint calculation_jobs_analysis_request_size_limit
    check (octet_length(analysis_request::text) <= 1048576) not valid;

create table public.bff_sessions (
    session_digest text primary key check (session_digest ~ '^[0-9a-f]{64}$'),
    session_ref text not null unique check (session_ref ~ '^session-v1:[0-9a-f]{24}$'),
    principal_id text not null check (length(principal_id) between 1 and 256),
    session_role text not null check (session_role in ('viewer','admin')),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    revoked_at timestamptz,
    check (expires_at > created_at)
);
alter table public.bff_sessions enable row level security;
revoke all on table public.bff_sessions from public, anon, authenticated, service_role;
create index bff_sessions_expiry_idx on public.bff_sessions (expires_at)
    where revoked_at is null;

create table public.bff_login_lockouts (
    client_key text primary key check (client_key ~ '^[0-9a-f]{64}$'),
    failure_count integer not null check (failure_count >= 0),
    window_started_at timestamptz not null,
    locked_until timestamptz,
    updated_at timestamptz not null default now()
);
alter table public.bff_login_lockouts enable row level security;
revoke all on table public.bff_login_lockouts from public, anon, authenticated, service_role;
create index bff_login_lockouts_expiry_idx on public.bff_login_lockouts (locked_until)
    where locked_until is not null;

create table public.bff_audit_events (
    id bigint generated always as identity primary key,
    event_type text not null check (event_type ~ '^[a-z][a-z0-9_]{1,63}$'),
    principal_id text check (principal_id is null or length(principal_id) between 1 and 256),
    session_role text check (session_role is null or session_role in ('viewer','admin')),
    session_ref text check (session_ref is null or session_ref ~ '^session-v1:[0-9a-f]{24}$'),
    correlation_id uuid not null,
    operation_type text check (operation_type is null or operation_type ~ '^[a-z][a-z0-9_]{1,63}$'),
    operation_id uuid,
    outcome text not null check (outcome in ('success','denied','failed','cleanup_required')),
    error_code text check (error_code is null or error_code ~ '^[A-Z][A-Z0-9_]{1,79}$'),
    occurred_at timestamptz not null default now()
);
alter table public.bff_audit_events enable row level security;
revoke all on table public.bff_audit_events from public, anon, authenticated, service_role;
create index bff_audit_events_operation_idx
    on public.bff_audit_events (operation_type, operation_id, occurred_at desc);

create table public.forecast_execution_permits (
    operation_id uuid primary key,
    lease_token uuid not null unique,
    acquired_at timestamptz not null default now(),
    lease_expires_at timestamptz not null,
    check (lease_expires_at > acquired_at)
);
alter table public.forecast_execution_permits enable row level security;
revoke all on table public.forecast_execution_permits from public, anon, authenticated, service_role;
create table public.bff_runtime_limits (
    singleton boolean primary key default true check (singleton),
    forecast_max_concurrency integer not null check (forecast_max_concurrency between 1 and 64)
);
insert into public.bff_runtime_limits(singleton,forecast_max_concurrency) values(true,1)
on conflict (singleton) do nothing;
alter table public.bff_runtime_limits enable row level security;
revoke all on table public.bff_runtime_limits from public, anon, authenticated, service_role;
create index forecast_execution_permits_expiry_idx
    on public.forecast_execution_permits (lease_expires_at);
create index if not exists forecast_generation_recovery_idx
    on public.forecast_generation_requests (status, lease_expires_at, created_at);
alter table public.model_ingestion_requests add column if not exists recovery_token uuid;
alter table public.model_ingestion_requests add column if not exists lease_expires_at timestamptz;
alter table public.forecast_generation_requests add column if not exists recovery_token uuid;
update public.model_ingestion_requests set lease_expires_at=now()+interval '30 minutes'
 where status='reserved' and lease_expires_at is null;

create or replace function public.set_model_ingestion_lease()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
    if new.status='reserved' and new.lease_token is not null and new.lease_expires_at is null then
        new.lease_expires_at := now()+interval '30 minutes';
    elsif new.status<>'reserved' then new.lease_expires_at := null;
    end if;
    return new;
end;
$$;
drop trigger if exists model_ingestion_lease_guard on public.model_ingestion_requests;
create trigger model_ingestion_lease_guard before insert or update on public.model_ingestion_requests
for each row execute function public.set_model_ingestion_lease();

create or replace function public.heartbeat_model_ingestion(p_ingestion_id uuid,p_lease_token uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
    update public.model_ingestion_requests request_row
       set lease_expires_at=now()+interval '30 minutes',updated_at=now()
     where request_row.id=p_ingestion_id and request_row.status='reserved'
       and request_row.lease_token=p_lease_token and request_row.lease_expires_at>now();
    if not found then raise exception 'model ingestion lease is invalid'; end if;
end;
$$;

create or replace function public.create_bff_session(
    p_session_digest text, p_session_ref text, p_principal_id text,
    p_role text, p_ttl_seconds integer
) returns void language plpgsql security definer set search_path = '' as $$
begin
    if p_session_digest is null or p_session_digest !~ '^[0-9a-f]{64}$'
       or p_session_ref is null or p_session_ref !~ '^session-v1:[0-9a-f]{24}$'
       or p_principal_id is null or length(p_principal_id) not between 1 and 256
       or p_role is null or p_role not in ('viewer','admin')
       or p_ttl_seconds not between 60 and 86400 then
        raise exception 'invalid session record';
    end if;
    insert into public.bff_sessions(session_digest, session_ref, principal_id, session_role, expires_at)
    values (p_session_digest, p_session_ref, p_principal_id, p_role,
            now()+make_interval(secs=>p_ttl_seconds));
end;
$$;

create or replace function public.get_bff_session(p_session_digest text)
returns table(session_ref text, principal_id text, session_role text, expires_at timestamptz)
language sql stable security definer set search_path = '' as $$
    select value.session_ref, value.principal_id, value.session_role, value.expires_at
      from public.bff_sessions value
     where value.session_digest = p_session_digest
       and value.revoked_at is null and value.expires_at > now()
       and p_session_digest ~ '^[0-9a-f]{64}$';
$$;

create or replace function public.revoke_bff_session(p_session_digest text)
returns void language plpgsql security definer set search_path = '' as $$
begin
    if p_session_digest is null or p_session_digest !~ '^[0-9a-f]{64}$' then
        return;
    end if;
    update public.bff_sessions value set revoked_at=coalesce(value.revoked_at, now())
     where value.session_digest=p_session_digest;
end;
$$;

create or replace function public.check_bff_login_lockout(p_client_key text)
returns table(allowed boolean, retry_after_seconds integer)
language plpgsql security definer set search_path = '' as $$
declare v_locked_until timestamptz;
begin
    if p_client_key is null or p_client_key !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid login client key';
    end if;
    select value.locked_until into v_locked_until from public.bff_login_lockouts value
     where value.client_key=p_client_key;
    return query select
        coalesce(v_locked_until <= now(), true),
        case when v_locked_until > now()
             then greatest(1, ceil(extract(epoch from v_locked_until-now()))::integer) else 0 end;
end;
$$;

create or replace function public.record_bff_login_failure(
    p_client_key text, p_max_attempts integer, p_window_seconds integer
) returns table(allowed boolean, retry_after_seconds integer)
language plpgsql security definer set search_path = '' as $$
declare v_row public.bff_login_lockouts%rowtype;
begin
    if p_client_key is null or p_client_key !~ '^[0-9a-f]{64}$'
       or p_max_attempts not between 1 and 100
       or p_window_seconds not between 1 and 86400 then
        raise exception 'invalid login lockout policy';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('bff-login:' || p_client_key, 0));
    select * into v_row from public.bff_login_lockouts value
     where value.client_key=p_client_key for update;
    if not found or v_row.window_started_at + make_interval(secs => p_window_seconds) <= now() then
        insert into public.bff_login_lockouts(client_key, failure_count, window_started_at, locked_until)
        values (p_client_key, 1, now(), null)
        on conflict (client_key) do update set failure_count=1, window_started_at=now(),
            locked_until=null, updated_at=now()
        returning * into v_row;
    elsif v_row.locked_until > now() then
        null;
    else
        update public.bff_login_lockouts value
           set failure_count=value.failure_count+1,
               locked_until=case when value.failure_count+1 >= p_max_attempts
                   then value.window_started_at + make_interval(secs => p_window_seconds) end,
               updated_at=now()
         where value.client_key=p_client_key returning * into v_row;
    end if;
    return query select
        not (v_row.locked_until > now()),
        case when v_row.locked_until > now()
             then greatest(1, ceil(extract(epoch from v_row.locked_until-now()))::integer) else 0 end;
end;
$$;

create or replace function public.clear_bff_login_failures(p_client_key text)
returns void language plpgsql security definer set search_path = '' as $$
begin
    if p_client_key is null or p_client_key !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid login client key';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('bff-login:' || p_client_key, 0));
    delete from public.bff_login_lockouts value where value.client_key=p_client_key;
end;
$$;

create or replace function public.append_bff_audit_event(
    p_event_type text, p_principal_id text, p_role text, p_session_ref text,
    p_correlation_id uuid, p_operation_type text, p_operation_id uuid,
    p_outcome text, p_error_code text
) returns void language plpgsql security definer set search_path = '' as $$
begin
    insert into public.bff_audit_events(
        event_type, principal_id, session_role, session_ref, correlation_id,
        operation_type, operation_id, outcome, error_code
    ) values (
        p_event_type, p_principal_id, p_role, p_session_ref, p_correlation_id,
        p_operation_type, p_operation_id, p_outcome, p_error_code
    );
end;
$$;

create or replace function public.acquire_forecast_execution_permit(
    p_operation_id uuid, p_max_concurrency integer, p_lease_seconds integer
) returns table(lease_token uuid, lease_expires_at timestamptz)
language plpgsql security definer set search_path = '' as $$
declare v_token uuid := gen_random_uuid(); v_expiry timestamptz; v_global_max integer;
begin
    if p_operation_id is null or p_max_concurrency not between 1 and 64
       or p_lease_seconds not between 30 and 3600 then
        raise exception 'invalid forecast permit request';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('forecast-global-permits', 0));
    select value.forecast_max_concurrency into v_global_max
      from public.bff_runtime_limits value where value.singleton;
    if v_global_max is null then raise exception 'forecast global limit is not configured'; end if;
    delete from public.forecast_execution_permits value where value.lease_expires_at <= now();
    return query select value.lease_token,value.lease_expires_at
      from public.forecast_execution_permits value
     where value.operation_id=p_operation_id and value.lease_expires_at>now();
    if found then return; end if;
    if (select count(*) from public.forecast_execution_permits) >= least(p_max_concurrency,v_global_max) then
        raise exception 'FORECAST_CAPACITY_EXHAUSTED';
    end if;
    v_expiry := now()+make_interval(secs => p_lease_seconds);
    insert into public.forecast_execution_permits(operation_id,lease_token,lease_expires_at)
    values(p_operation_id,v_token,v_expiry);
    return query select v_token,v_expiry;
end;
$$;

create or replace function public.set_bff_forecast_max_concurrency(p_max integer)
returns void language plpgsql security definer set search_path = '' as $$
begin
    if p_max not between 1 and 64 then raise exception 'invalid forecast concurrency limit'; end if;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('forecast-global-permits',0));
    insert into public.bff_runtime_limits(singleton,forecast_max_concurrency) values(true,p_max)
    on conflict(singleton) do update set forecast_max_concurrency=excluded.forecast_max_concurrency;
end;
$$;

create or replace function public.renew_forecast_execution_permit(
    p_operation_id uuid, p_lease_token uuid, p_lease_seconds integer
) returns void language plpgsql security definer set search_path = '' as $$
begin
    if p_lease_seconds not between 30 and 3600 then raise exception 'invalid forecast permit lease'; end if;
    update public.forecast_execution_permits value
       set lease_expires_at=now()+make_interval(secs => p_lease_seconds)
     where value.operation_id=p_operation_id and value.lease_token=p_lease_token
       and value.lease_expires_at > now();
    if not found then raise exception 'forecast permit claim is invalid'; end if;
end;
$$;

create or replace function public.release_forecast_execution_permit(
    p_operation_id uuid, p_lease_token uuid
) returns void language plpgsql security definer set search_path = '' as $$
begin
    delete from public.forecast_execution_permits value
     where value.operation_id=p_operation_id and value.lease_token=p_lease_token;
end;
$$;

create or replace function public.bff_readiness_check()
returns boolean language sql stable security definer set search_path = '' as $$
    select exists(select 1 from public.app_config config
                   where config.config_key='model_mapping' and config.status='published'
                     and config.content_hash ~ '^[0-9a-f]{64}$')
       and exists(select 1 from storage.buckets bucket
                   where bucket.id='pnl-models' and not bucket.public)
       and exists(select 1 from public.bff_runtime_limits limits where limits.singleton);
$$;

create or replace function public.get_bounded_evidence_admin(
    p_result_id uuid,p_supported_result_schema_versions text[]
) returns table(payload jsonb)
language sql stable security definer set search_path = '' as $$
    select to_jsonb(evidence)
      from public.get_calculation_result_evidence_admin_by_id(
          p_result_id,p_supported_result_schema_versions) evidence
     where octet_length(evidence.result_payload::text) <= 26214400
       and octet_length(evidence.analysis_request::text) <= 1048576;
$$;

create or replace function public.get_bounded_evidence_viewer(
    p_result_id uuid,p_supported_result_schema_versions text[]
) returns table(payload jsonb)
language sql stable security definer set search_path = '' as $$
    select to_jsonb(evidence)
      from public.get_calculation_result_evidence_viewer_by_id(
          p_result_id,p_supported_result_schema_versions) evidence
     where octet_length(evidence.result_payload::text) <= 26214400
       and octet_length(evidence.analysis_request::text) <= 1048576;
$$;

create or replace function public.cleanup_bff_auth_state(p_retention_seconds integer)
returns table(expired_sessions bigint, expired_lockouts bigint)
language plpgsql security definer set search_path = '' as $$
declare v_sessions bigint; v_lockouts bigint;
begin
    if p_retention_seconds not between 3600 and 31536000 then
        raise exception 'invalid auth retention policy';
    end if;
    delete from public.bff_sessions value
     where coalesce(value.revoked_at,value.expires_at) < now()-make_interval(secs=>p_retention_seconds);
    get diagnostics v_sessions=row_count;
    delete from public.bff_login_lockouts value
     where value.updated_at < now()-make_interval(secs=>p_retention_seconds)
       and coalesce(value.locked_until,value.updated_at) < now();
    get diagnostics v_lockouts=row_count;
    return query select v_sessions,v_lockouts;
end;
$$;

create or replace function public.claim_model_ingestion_cleanup()
returns table(ingestion_id uuid, model_id uuid, recovery_token uuid)
language plpgsql security definer set search_path = '' as $$
begin
    return query
    with candidate as (
        select request_row.id from public.model_ingestion_requests request_row
         where request_row.recovery_token is null
           and not exists(select 1 from public.models model where model.id=request_row.model_id)
           and (request_row.status='cleanup_required'
             or (request_row.status='reserved' and request_row.lease_expires_at <= now()))
         order by request_row.created_at for update skip locked limit 50
    ), claimed as (
        update public.model_ingestion_requests request_row
           set status='cleanup_required', lease_token=null, recovery_token=gen_random_uuid(),
               updated_at=now(), error_code=coalesce(request_row.error_code,'MAINTENANCE_CLAIMED')
          from candidate where request_row.id=candidate.id
        returning request_row.id,request_row.model_id,request_row.recovery_token
    ) select claimed.id,claimed.model_id,claimed.recovery_token from claimed;
end;
$$;

create or replace function public.claim_forecast_generation_cleanup()
returns table(generation_id uuid, model_id uuid, recovery_token uuid)
language plpgsql security definer set search_path = '' as $$
begin
    return query
    with candidate as (
        select request_row.id from public.forecast_generation_requests request_row
         where request_row.recovery_token is null
           and not exists(select 1 from public.models model where model.id=request_row.model_id)
           and (request_row.status='cleanup_required'
             or (request_row.status='reserved' and request_row.lease_expires_at <= now()))
         order by request_row.created_at for update skip locked limit 50
    ), claimed as (
        update public.forecast_generation_requests request_row
           set status='cleanup_required', lease_token=null, lease_expires_at=null,
               recovery_token=gen_random_uuid(), updated_at=now(),
               error_code=coalesce(request_row.error_code,'MAINTENANCE_CLAIMED')
          from candidate where request_row.id=candidate.id
        returning request_row.id,request_row.model_id,request_row.recovery_token
    ) select claimed.id,claimed.model_id,claimed.recovery_token from claimed;
end;
$$;

create or replace function public.complete_model_ingestion_cleanup(
    p_ingestion_id uuid,p_recovery_token uuid
) returns void language plpgsql security definer set search_path = '' as $$
begin
    update public.model_ingestion_requests request_row set status='failed',recovery_token=null,
        updated_at=now(),error_code='ADMIN_CLEANUP_CONFIRMED'
     where request_row.id=p_ingestion_id and request_row.status='cleanup_required'
       and request_row.recovery_token=p_recovery_token;
    if not found then raise exception 'model ingestion recovery claim is invalid'; end if;
end;
$$;

create or replace function public.complete_forecast_generation_cleanup(
    p_generation_id uuid,p_recovery_token uuid
) returns void language plpgsql security definer set search_path = '' as $$
begin
    update public.forecast_generation_requests request_row set status='failed',recovery_token=null,
        updated_at=now(),error_code='ADMIN_CLEANUP_CONFIRMED'
     where request_row.id=p_generation_id and request_row.status='cleanup_required'
       and request_row.recovery_token=p_recovery_token;
    if not found then raise exception 'forecast recovery claim is invalid'; end if;
end;
$$;

-- Reject malformed trusted-RPC payloads even where Migration 011 comparisons
-- could evaluate SQL NULL/UNKNOWN, and make generated linkage immutable.
create or replace function public.guard_forecast_request_contract()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
    if jsonb_typeof(new.request_payload->'request') is distinct from 'object'
       or jsonb_typeof(new.request_payload->'provenance') is distinct from 'object'
       or (new.request_payload #>> '{request,base_model_id}') is distinct from new.base_model_id::text
       or (new.request_payload #>> '{provenance,mapping_version}') is distinct from new.mapping_version
       or (new.request_payload #>> '{provenance,mapping_hash}') is distinct from new.mapping_hash
       or (new.request_payload #>> '{provenance,engine_version}') is distinct from new.engine_version
       or (new.request_payload #>> '{provenance,result_schema_version}') is distinct from new.result_schema_version then
        raise exception 'invalid forecast generation payload contract';
    end if;
    if coalesce(new.request_payload #>> '{request,model_year}', '') !~ '^[0-9]{4}$'
       or (new.request_payload #>> '{request,model_year}')::integer not between 2000 and 2200
       or coalesce(new.request_payload #>> '{request,start_month}', '') !~ '^[0-9]{1,2}$'
       or coalesce(new.request_payload #>> '{request,end_month}', '') !~ '^[0-9]{1,2}$'
       or (new.request_payload #>> '{request,start_month}')::integer not between 1 and 12
       or (new.request_payload #>> '{request,end_month}')::integer
            not between (new.request_payload #>> '{request,start_month}')::integer and 12
       or jsonb_typeof(new.request_payload #> '{request,months}') is distinct from 'array'
       or coalesce(jsonb_array_length(new.request_payload #> '{request,months}'),-1)
            <> (new.request_payload #>> '{request,end_month}')::integer
             - (new.request_payload #>> '{request,start_month}')::integer + 1
       or octet_length(new.request_payload::text) > 1048576 then
        raise exception 'invalid forecast generation payload shape';
    end if;
    return new;
end;
$$;
drop trigger if exists forecast_request_contract_guard on public.forecast_generation_requests;
create trigger forecast_request_contract_guard before insert or update
on public.forecast_generation_requests for each row execute function public.guard_forecast_request_contract();

create or replace function public.guard_generated_model_linkage()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
    if old.source_kind='forecast_generated' and
       (new.source_kind is distinct from old.source_kind
        or new.source_model_id is distinct from old.source_model_id
        or new.forecast_generation_id is distinct from old.forecast_generation_id
        or new.generation_input_fingerprint is distinct from old.generation_input_fingerprint
        or new.generation_engine_version is distinct from old.generation_engine_version
        or new.generated_at is distinct from old.generated_at) then
        raise exception 'generated model provenance is immutable';
    end if;
    return new;
end;
$$;
drop trigger if exists generated_model_linkage_guard on public.models;
create trigger generated_model_linkage_guard before update on public.models
for each row execute function public.guard_generated_model_linkage();

-- Preserve the existing generic audit trigger while redacting queue claims,
-- raw errors and idempotency/request payloads. Principal/session attribution is
-- written separately to bff_audit_events by the trusted HTTP boundary.
create or replace function public.append_row_audit_log()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_old jsonb; v_new jsonb; v_entity_id text; v_request_id text;
begin
    v_old := case when tg_op in ('UPDATE','DELETE') then to_jsonb(old) else null end;
    v_new := case when tg_op in ('INSERT','UPDATE') then to_jsonb(new) else null end;
    v_old := v_old - array['claim_token','claimed_by','queue_message_id','error_detail',
        'error_message','idempotency_actor','idempotency_key','request_payload','analysis_request',
        'result','content','regional_sales_monthly','tariff_adjustment_monthly','period_types',
        'workbook_path','workbook_bucket'];
    v_new := v_new - array['claim_token','claimed_by','queue_message_id','error_detail',
        'error_message','idempotency_actor','idempotency_key','request_payload','analysis_request',
        'result','content','regional_sales_monthly','tariff_adjustment_monthly','period_types',
        'workbook_path','workbook_bucket'];
    v_entity_id := coalesce(v_new->>'id',v_old->>'id');
    begin
        v_request_id := nullif(current_setting('request.headers',true),'')::jsonb->>'x-request-id';
    exception when others then v_request_id := null;
    end;
    insert into public.audit_logs(actor_id,action,entity_type,entity_id,old_data,new_data,request_id)
    values(auth.uid(),lower(tg_op),tg_table_name,v_entity_id,v_old,v_new,v_request_id);
    return null;
end;
$$;

revoke all on function public.create_bff_session(text,text,text,text,integer) from public, anon, authenticated;
revoke all on function public.get_bff_session(text) from public, anon, authenticated;
revoke all on function public.revoke_bff_session(text) from public, anon, authenticated;
revoke all on function public.check_bff_login_lockout(text) from public, anon, authenticated;
revoke all on function public.record_bff_login_failure(text,integer,integer) from public, anon, authenticated;
revoke all on function public.clear_bff_login_failures(text) from public, anon, authenticated;
revoke all on function public.append_bff_audit_event(text,text,text,text,uuid,text,uuid,text,text) from public, anon, authenticated;
revoke all on function public.acquire_forecast_execution_permit(uuid,integer,integer) from public, anon, authenticated;
revoke all on function public.renew_forecast_execution_permit(uuid,uuid,integer) from public, anon, authenticated;
revoke all on function public.set_bff_forecast_max_concurrency(integer) from public, anon, authenticated;
revoke all on function public.release_forecast_execution_permit(uuid,uuid) from public, anon, authenticated;
revoke all on function public.bff_readiness_check() from public, anon, authenticated;
revoke all on function public.get_bounded_evidence_admin(uuid,text[]) from public, anon, authenticated;
revoke all on function public.get_bounded_evidence_viewer(uuid,text[]) from public, anon, authenticated;
revoke all on function public.cleanup_bff_auth_state(integer) from public, anon, authenticated;
revoke all on function public.claim_model_ingestion_cleanup() from public, anon, authenticated;
revoke all on function public.claim_forecast_generation_cleanup() from public, anon, authenticated;
revoke all on function public.complete_model_ingestion_cleanup(uuid,uuid) from public, anon, authenticated;
revoke all on function public.complete_forecast_generation_cleanup(uuid,uuid) from public, anon, authenticated;
revoke all on function public.guard_forecast_request_contract() from public, anon, authenticated, service_role;
revoke all on function public.set_model_ingestion_lease() from public, anon, authenticated, service_role;
revoke all on function public.heartbeat_model_ingestion(uuid,uuid) from public, anon, authenticated;
revoke all on function public.guard_generated_model_linkage() from public, anon, authenticated, service_role;

grant execute on function public.create_bff_session(text,text,text,text,integer) to service_role;
grant execute on function public.get_bff_session(text) to service_role;
grant execute on function public.revoke_bff_session(text) to service_role;
grant execute on function public.check_bff_login_lockout(text) to service_role;
grant execute on function public.record_bff_login_failure(text,integer,integer) to service_role;
grant execute on function public.clear_bff_login_failures(text) to service_role;
grant execute on function public.append_bff_audit_event(text,text,text,text,uuid,text,uuid,text,text) to service_role;
grant execute on function public.acquire_forecast_execution_permit(uuid,integer,integer) to service_role;
grant execute on function public.renew_forecast_execution_permit(uuid,uuid,integer) to service_role;
grant execute on function public.set_bff_forecast_max_concurrency(integer) to service_role;
grant execute on function public.release_forecast_execution_permit(uuid,uuid) to service_role;
grant execute on function public.bff_readiness_check() to service_role;
grant execute on function public.get_bounded_evidence_admin(uuid,text[]) to service_role;
grant execute on function public.get_bounded_evidence_viewer(uuid,text[]) to service_role;
grant execute on function public.cleanup_bff_auth_state(integer) to service_role;
grant execute on function public.claim_model_ingestion_cleanup() to service_role;
grant execute on function public.claim_forecast_generation_cleanup() to service_role;
grant execute on function public.complete_model_ingestion_cleanup(uuid,uuid) to service_role;
grant execute on function public.complete_forecast_generation_cleanup(uuid,uuid) to service_role;
grant execute on function public.heartbeat_model_ingestion(uuid,uuid) to service_role;

commit;

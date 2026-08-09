Exit code: 0
Wall time: 1.1 seconds
Output:
-- P&L Dashboard Phase 1 persistence/control-plane foundation.
-- Excel parsing and deterministic calculations intentionally do not run in SQL.

begin;

create extension if not exists pgcrypto;

create or replace function public.is_valid_pnl_storage_path(
    p_path text,
    p_kind text default null
) returns boolean
language sql
immutable
set search_path = public
as $$
    select case
        when p_kind = 'source' then
            p_path ~ '^models/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/source\.xlsx$'
        when p_kind = 'result' then
            p_path ~ '^models/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/jobs/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/result\.xlsx$'
        else
            public.is_valid_pnl_storage_path(p_path, 'source')
            or public.is_valid_pnl_storage_path(p_path, 'result')
    end;
$$;

create table if not exists public.models (
    id uuid primary key default gen_random_uuid(),
    name text not null check (length(btrim(name)) > 0),
    model_type text not null check (length(btrim(model_type)) > 0),
    model_year integer not null check (model_year between 2000 and 2200),
    start_month smallint not null default 1 check (start_month = 1),
    end_month smallint not null default 12 check (end_month = 12),
    created_date date not null default current_date,
    version text not null default 'V1',
    -- Backward compatibility: remove only after all clients read is_published.
    confirmed boolean not null default false,
    is_published boolean not null default false,
    is_default boolean not null default false,
    mapping_status text not null default 'draft'
        check (mapping_status in ('draft', 'validated', 'published')),
    mapping_version text not null default 'legacy',
    mapping_hash text not null default ''
        check (mapping_hash = '' or mapping_hash ~ '^[0-9a-f]{64}$'),
    workbook_bucket text not null default 'pnl-models',
    workbook_path text not null unique
        check (public.is_valid_pnl_storage_path(workbook_path, 'source')),
    file_name text not null default 'model.xlsx',
    period_types jsonb not null default '{}'::jsonb,
    regional_sales_monthly jsonb not null default '{}'::jsonb,
    tariff_applicable_rate numeric not null default 0.10,
    tariff_rate numeric not null default 0.13,
    tariff_adjustment_monthly jsonb not null default '{}'::jsonb,
    tariff_in_workbook boolean not null default false,
    created_by uuid references auth.users(id) on delete set null,
    uploaded_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint models_default_requires_publication
        check (not is_default or is_published)
);

-- Additive upgrade path for a pre-foundation models table. No legacy column
-- is removed or renamed in this migration.
alter table public.models add column if not exists confirmed boolean not null default false;
alter table public.models add column if not exists is_published boolean not null default false;
alter table public.models add column if not exists is_default boolean not null default false;
alter table public.models add column if not exists mapping_status text not null default 'draft';
alter table public.models add column if not exists mapping_version text not null default 'legacy';
alter table public.models add column if not exists mapping_hash text not null default '';

-- Existing deployments can keep writing confirmed during the migration window.
update public.models
set is_published = true
where confirmed and not is_published;

create unique index if not exists uq_models_single_default
    on public.models ((1))
    where is_default;
create index if not exists idx_models_year_type
    on public.models (model_year, model_type, uploaded_at desc);

create table if not exists public.calculation_jobs (
    id uuid primary key default gen_random_uuid(),
    model_id uuid not null references public.models(id) on delete restrict,
    status text not null default 'pending'
        check (status in ('pending', 'processing', 'completed', 'failed')),
    storage_bucket text not null default 'pnl-models',
    storage_path text not null
        check (public.is_valid_pnl_storage_path(storage_path, 'source')),
    upload_completed_at timestamptz,
    engine_version text not null check (length(btrim(engine_version)) > 0),
    mapping_version text not null check (length(btrim(mapping_version)) > 0),
    mapping_hash text not null check (mapping_hash ~ '^[0-9a-f]{64}$'),
    result_schema_version text not null check (length(btrim(result_schema_version)) > 0),
    claimed_by text,
    claim_token uuid,
    heartbeat_at timestamptz,
    lease_expires_at timestamptz,
    attempt integer not null default 0 check (attempt >= 0),
    max_attempts integer not null default 3 check (max_attempts between 1 and 20),
    error_code text,
    error_message text,
    error_detail jsonb not null default '{}'::jsonb,
    idempotency_key text unique,
    created_by uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    constraint calculation_jobs_claim_shape check (
        (status = 'processing' and claimed_by is not null and claim_token is not null
            and heartbeat_at is not null and lease_expires_at is not null)
        or status <> 'processing'
    ),
    constraint calculation_jobs_completion_shape check (
        (status = 'completed' and completed_at is not null)
        or status <> 'completed'
    )
);

create index if not exists idx_calculation_jobs_claim
    on public.calculation_jobs (status, lease_expires_at, created_at)
    where status in ('pending', 'processing');
create index if not exists idx_calculation_jobs_model
    on public.calculation_jobs (model_id, created_at desc);

create table if not exists public.calculation_results (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null unique references public.calculation_jobs(id) on delete restrict,
    model_id uuid not null references public.models(id) on delete restrict,
    model_year integer not null check (model_year between 2000 and 2200),
    result jsonb not null,
    engine_version text not null check (length(btrim(engine_version)) > 0),
    mapping_version text not null check (length(btrim(mapping_version)) > 0),
    mapping_hash text not null check (mapping_hash ~ '^[0-9a-f]{64}$'),
    result_schema_version text not null check (length(btrim(result_schema_version)) > 0),
    workbook_bucket text,
    workbook_path text check (
        workbook_path is null
        or public.is_valid_pnl_storage_path(workbook_path, 'result')
    ),
    is_published boolean not null default false,
    is_default boolean not null default false,
    published_at timestamptz,
    created_at timestamptz not null default now(),
    constraint calculation_results_default_requires_publication
        check (not is_default or is_published),
    constraint calculation_results_publication_timestamp check (
        (is_published and published_at is not null)
        or (not is_published and published_at is null)
    )
);

create unique index if not exists uq_calculation_results_default_per_model
    on public.calculation_results (model_id)
    where is_default;
create index if not exists idx_calc_model_year
    on public.calculation_results (model_id, model_year, created_at desc);

create table if not exists public.app_config (
    id uuid primary key default gen_random_uuid(),
    config_key text not null check (length(btrim(config_key)) > 0),
    version text not null check (length(btrim(version)) > 0),
    status text not null default 'draft'
        check (status in ('draft', 'validated', 'published')),
    content jsonb not null,
    content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
    is_default boolean not null default false,
    created_by uuid references auth.users(id) on delete set null,
    validated_by uuid references auth.users(id) on delete set null,
    published_by uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    validated_at timestamptz,
    published_at timestamptz,
    unique (config_key, version),
    constraint app_config_default_requires_published
        check (not is_default or status = 'published'),
    constraint app_config_validation_timestamp check (
        status = 'draft' or validated_at is not null
    ),
    constraint app_config_publication_timestamp check (
        status <> 'published' or published_at is not null
    )
);

create unique index if not exists uq_app_config_default_per_key
    on public.app_config (config_key)
    where is_default;
create index if not exists idx_app_config_lookup
    on public.app_config (config_key, status, published_at desc);

create table if not exists public.audit_logs (
    id bigint generated always as identity primary key,
    occurred_at timestamptz not null default now(),
    actor_id uuid references auth.users(id) on delete set null,
    action text not null,
    entity_type text not null,
    entity_id text,
    old_data jsonb,
    new_data jsonb,
    request_id text,
    metadata jsonb not null default '{}'::jsonb
);

create index if not exists idx_audit_logs_entity
    on public.audit_logs (entity_type, entity_id, occurred_at desc);
create index if not exists idx_audit_logs_occurred_at
    on public.audit_logs (occurred_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

create or replace function public.sync_model_publication_flags()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if tg_op = 'INSERT' then
        new.is_published := coalesce(new.is_published, false) or coalesce(new.confirmed, false);
        new.confirmed := new.is_published;
    elsif new.is_published is distinct from old.is_published then
        new.confirmed := new.is_published;
    elsif new.confirmed is distinct from old.confirmed then
        new.is_published := new.confirmed;
    end if;
    if new.is_default and not new.is_published then
        raise exception 'a default model must be published';
    end if;
    return new;
end;
$$;

create or replace function public.guard_model_storage_binding()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.workbook_bucket <> 'pnl-models'
       or new.workbook_path <> format('models/%s/source.xlsx', new.id) then
        raise exception 'model workbook must use its canonical private Storage path';
    end if;
    return new;
end;
$$;

create or replace function public.guard_job_storage_binding()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.storage_bucket <> 'pnl-models'
       or new.storage_path <> format('models/%s/source.xlsx', new.model_id) then
        raise exception 'calculation job must reference its model source workbook';
    end if;
    return new;
end;
$$;

create or replace function public.guard_result_storage_binding()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.workbook_bucket is null and new.workbook_path is null then
        return new;
    end if;
    if new.workbook_bucket is null
       or new.workbook_path is null
       or new.workbook_bucket <> 'pnl-models'
       or new.workbook_path <> format(
            'models/%s/jobs/%s/result.xlsx', new.model_id, new.job_id
       ) then
        raise exception 'calculation result must use its canonical job Storage path';
    end if;
    return new;
end;
$$;

create or replace function public.guard_job_status_transition()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.status = old.status then
        return new;
    end if;
    if old.status = 'pending' and new.status not in ('processing', 'failed') then
        raise exception 'invalid job transition: % -> %', old.status, new.status;
    elsif old.status = 'processing' and new.status not in ('pending', 'completed', 'failed') then
        raise exception 'invalid job transition: % -> %', old.status, new.status;
    elsif old.status in ('completed', 'failed') then
        raise exception 'terminal job cannot transition: % -> %', old.status, new.status;
    end if;
    return new;
end;
$$;

create or replace function public.guard_job_immutable_fields()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if (new.model_id, new.storage_bucket, new.storage_path,
        new.engine_version, new.mapping_version, new.mapping_hash, new.result_schema_version)
       is distinct from
       (old.model_id, old.storage_bucket, old.storage_path,
        old.engine_version, old.mapping_version, old.mapping_hash, old.result_schema_version) then
        raise exception 'calculation job source and provenance are immutable';
    end if;
    return new;
end;
$$;

create or replace function public.guard_calculation_result_fields()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if (new.job_id, new.model_id, new.model_year, new.result,
        new.engine_version, new.mapping_version, new.mapping_hash, new.result_schema_version,
        new.workbook_bucket, new.workbook_path)
       is distinct from
       (old.job_id, old.model_id, old.model_year, old.result,
        old.engine_version, old.mapping_version, old.mapping_hash, old.result_schema_version,
        old.workbook_bucket, old.workbook_path) then
        raise exception 'calculation result payload and provenance are immutable';
    end if;
    return new;
end;
$$;

create or replace function public.guard_app_config_transition()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if old.status in ('validated', 'published') and (
        new.config_key is distinct from old.config_key
        or new.version is distinct from old.version
        or new.content is distinct from old.content
        or new.content_hash is distinct from old.content_hash
    ) then
        raise exception 'validated/published mapping content is immutable';
    end if;
    if new.status = old.status then
        return new;
    end if;
    if old.status = 'draft' and new.status <> 'validated' then
        raise exception 'mapping must transition draft -> validated';
    elsif old.status = 'validated' and new.status <> 'published' then
        raise exception 'mapping must transition validated -> published';
    elsif old.status = 'published' then
        raise exception 'published mapping is immutable';
    end if;
    return new;
end;
$$;

create or replace function public.guard_app_config_insert()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.status <> 'draft'
       or new.is_default
       or new.validated_at is not null
       or new.published_at is not null
       or new.validated_by is not null
       or new.published_by is not null then
        raise exception 'mapping config must be created as a draft';
    end if;
    return new;
end;
$$;

create or replace function public.append_row_audit_log()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_old jsonb;
    v_new jsonb;
    v_entity_id text;
begin
    v_old := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) else null end;
    v_new := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) else null end;
    v_entity_id := coalesce(v_new ->> 'id', v_old ->> 'id');
    insert into public.audit_logs (
        actor_id, action, entity_type, entity_id, old_data, new_data, request_id
    ) values (
        auth.uid(), lower(tg_op), tg_table_name, v_entity_id, v_old, v_new,
        nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-request-id'
    );
    -- Return value is ignored for an AFTER trigger.
    return null;
end;
$$;

create or replace function public.prevent_audit_log_mutation()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    raise exception 'audit_logs is append-only';
end;
$$;

drop trigger if exists models_sync_publication on public.models;
create trigger models_sync_publication
before insert or update of confirmed, is_published, is_default on public.models
for each row execute function public.sync_model_publication_flags();
drop trigger if exists models_guard_storage_binding on public.models;
create trigger models_guard_storage_binding
before insert or update of id, workbook_bucket, workbook_path on public.models
for each row execute function public.guard_model_storage_binding();

drop trigger if exists models_updated_at on public.models;
create trigger models_updated_at before update on public.models
for each row execute function public.set_updated_at();
drop trigger if exists calculation_jobs_updated_at on public.calculation_jobs;
create trigger calculation_jobs_updated_at before update on public.calculation_jobs
for each row execute function public.set_updated_at();
drop trigger if exists app_config_updated_at on public.app_config;
create trigger app_config_updated_at before update on public.app_config
for each row execute function public.set_updated_at();

drop trigger if exists calculation_jobs_guard_transition on public.calculation_jobs;
create trigger calculation_jobs_guard_transition
before update of status on public.calculation_jobs
for each row execute function public.guard_job_status_transition();
drop trigger if exists calculation_jobs_guard_immutable on public.calculation_jobs;
create trigger calculation_jobs_guard_immutable
before update on public.calculation_jobs
for each row execute function public.guard_job_immutable_fields();
drop trigger if exists calculation_jobs_guard_storage_binding on public.calculation_jobs;
create trigger calculation_jobs_guard_storage_binding
before insert or update of model_id, storage_bucket, storage_path on public.calculation_jobs
for each row execute function public.guard_job_storage_binding();
drop trigger if exists calculation_results_guard_immutable on public.calculation_results;
create trigger calculation_results_guard_immutable
before update on public.calculation_results
for each row execute function public.guard_calculation_result_fields();
drop trigger if exists calculation_results_guard_storage_binding on public.calculation_results;
create trigger calculation_results_guard_storage_binding
before insert or update of job_id, model_id, workbook_bucket, workbook_path
on public.calculation_results
for each row execute function public.guard_result_storage_binding();
drop trigger if exists app_config_guard_transition on public.app_config;
create trigger app_config_guard_transition
before update on public.app_config
for each row execute function public.guard_app_config_transition();
drop trigger if exists app_config_guard_insert on public.app_config;
create trigger app_config_guard_insert
before insert on public.app_config
for each row execute function public.guard_app_config_insert();

drop trigger if exists models_audit on public.models;
create trigger models_audit after insert or update or delete on public.models
for each row execute function public.append_row_audit_log();
drop trigger if exists calculation_jobs_audit on public.calculation_jobs;
create trigger calculation_jobs_audit after insert or update or delete on public.calculation_jobs
for each row execute function public.append_row_audit_log();
drop trigger if exists calculation_results_audit on public.calculation_results;
create trigger calculation_results_audit after insert or update or delete on public.calculation_results
for each row execute function public.append_row_audit_log();
drop trigger if exists app_config_audit on public.app_config;
create trigger app_config_audit after insert or update or delete on public.app_config
for each row execute function public.append_row_audit_log();

drop trigger if exists audit_logs_append_only on public.audit_logs;
create trigger audit_logs_append_only
before update or delete or truncate on public.audit_logs
for each statement execute function public.prevent_audit_log_mutation();

create or replace function public.claim_calculation_job(
    p_worker_id text,
    p_lease_seconds integer default 300
) returns setof public.calculation_jobs
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_job_id uuid;
begin
    if length(btrim(p_worker_id)) = 0 or p_lease_seconds not between 1 and 3600 then
        raise exception 'invalid worker id or lease';
    end if;
    select job.id
      into v_job_id
      from public.calculation_jobs as job
     where (
            job.status = 'pending'
            or (job.status = 'processing' and job.lease_expires_at <= now())
        )
       and job.upload_completed_at is not null
       and job.attempt < job.max_attempts
     order by job.created_at
     for update skip locked
     limit 1;

    if v_job_id is null then
        return;
    end if;

    update public.calculation_jobs
       set status = 'processing',
           claimed_by = p_worker_id,
           claim_token = gen_random_uuid(),
           heartbeat_at = now(),
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           attempt = attempt + 1,
           error_code = null,
           error_message = null,
           error_detail = '{}'::jsonb
     where id = v_job_id;

    return query
        select job.* from public.calculation_jobs as job where job.id = v_job_id;
end;
$$;

create or replace function public.mark_calculation_upload_completed(
    p_job_id uuid,
    p_created_by uuid
) returns public.calculation_jobs
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_job public.calculation_jobs%rowtype;
begin
    update public.calculation_jobs
       set upload_completed_at = coalesce(upload_completed_at, now())
     where id = p_job_id
       and status = 'pending'
       and created_by = p_created_by
     returning * into v_job;
    if not found then
        raise exception 'pending upload job not found';
    end if;
    return v_job;
end;
$$;

create or replace function public.heartbeat_calculation_job(
    p_job_id uuid,
    p_claim_token uuid,
    p_lease_seconds integer default 300
) returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if p_lease_seconds not between 1 and 3600 then
        raise exception 'invalid lease';
    end if;
    update public.calculation_jobs
       set heartbeat_at = now(),
           lease_expires_at = now() + make_interval(secs => p_lease_seconds)
     where id = p_job_id
       and status = 'processing'
       and claim_token = p_claim_token
       and lease_expires_at > now();
    return found;
end;
$$;

create or replace function public.initialize_calculation_upload(
    p_model_id uuid,
    p_job_id uuid,
    p_name text,
    p_model_type text,
    p_model_year integer,
    p_created_date date,
    p_version text,
    p_file_name text,
    p_storage_bucket text,
    p_storage_path text,
    p_engine_version text,
    p_mapping_version text,
    p_mapping_hash text,
    p_result_schema_version text,
    p_created_by uuid,
    p_max_attempts integer default 3
) returns public.calculation_jobs
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_job public.calculation_jobs%rowtype;
begin
    if not public.is_valid_pnl_storage_path(p_storage_path, 'source') then
        raise exception 'invalid source workbook path';
    end if;
    if not exists (
        select 1
          from public.app_config
         where config_key = 'model_mapping'
           and version = p_mapping_version
           and content_hash = p_mapping_hash
           and status = 'published'
    ) then
        raise exception 'mapping provenance is not published';
    end if;
    insert into public.models (
        id, name, model_type, model_year, created_date, version,
        confirmed, is_published, is_default,
        mapping_status, mapping_version, mapping_hash,
        workbook_bucket, workbook_path, file_name, created_by
    ) values (
        p_model_id, p_name, p_model_type, p_model_year, p_created_date, p_version,
        false, false, false,
        'published', p_mapping_version, p_mapping_hash,
        p_storage_bucket, p_storage_path, p_file_name, p_created_by
    );
    insert into public.calculation_jobs (
        id, model_id, status, storage_bucket, storage_path,
        engine_version, mapping_version, mapping_hash, result_schema_version,
        max_attempts, created_by
    ) values (
        p_job_id, p_model_id, 'pending', p_storage_bucket, p_storage_path,
        p_engine_version, p_mapping_version, p_mapping_hash, p_result_schema_version,
        p_max_attempts, p_created_by
    ) returning * into v_job;
    return v_job;
end;
$$;

create or replace function public.complete_calculation_job(
    p_job_id uuid,
    p_claim_token uuid,
    p_result jsonb,
    p_engine_version text,
    p_mapping_version text,
    p_mapping_hash text,
    p_result_schema_version text,
    p_workbook_bucket text default null,
    p_workbook_path text default null,
    p_is_published boolean default false,
    p_is_default boolean default false
) returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_job public.calculation_jobs%rowtype;
    v_result_id uuid;
    v_model_year integer;
begin
    select * into v_job
      from public.calculation_jobs
     where id = p_job_id
     for update;
    if not found or v_job.status <> 'processing' or v_job.claim_token <> p_claim_token then
        raise exception 'job claim is not active';
    end if;
    if v_job.lease_expires_at <= now() then
        raise exception 'job claim lease expired';
    end if;
    if (p_engine_version, p_mapping_version, p_mapping_hash, p_result_schema_version)
       is distinct from
       (v_job.engine_version, v_job.mapping_version, v_job.mapping_hash, v_job.result_schema_version) then
        raise exception 'result provenance does not match job provenance';
    end if;
    if p_is_default and not p_is_published then
        raise exception 'a default result must be published';
    end if;
    select model_year into v_model_year from public.models where id = v_job.model_id;
    if p_is_default then
        update public.calculation_results
           set is_default = false
         where model_id = v_job.model_id and is_default;
    end if;
    insert into public.calculation_results (
        job_id, model_id, model_year, result,
        engine_version, mapping_version, mapping_hash, result_schema_version,
        workbook_bucket, workbook_path, is_published, is_default, published_at
    ) values (
        v_job.id, v_job.model_id, v_model_year, p_result,
        p_engine_version, p_mapping_version, p_mapping_hash, p_result_schema_version,
        p_workbook_bucket, p_workbook_path, p_is_published, p_is_default,
        case when p_is_published then now() else null end
    ) returning id into v_result_id;

    update public.calculation_jobs
       set status = 'completed',
           completed_at = now(),
           heartbeat_at = now(),
           lease_expires_at = null
     where id = v_job.id;
    return v_result_id;
end;
$$;

create or replace function public.fail_calculation_job(
    p_job_id uuid,
    p_claim_token uuid,
    p_error_code text,
    p_error_message text,
    p_error_detail jsonb default '{}'::jsonb,
    p_retryable boolean default false
) returns text
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_job public.calculation_jobs%rowtype;
    v_status text;
begin
    select * into v_job
      from public.calculation_jobs
     where id = p_job_id
     for update;
    if not found or v_job.status <> 'processing' or v_job.claim_token <> p_claim_token then
        raise exception 'job claim is not active';
    end if;
    v_status := case
        when p_retryable and v_job.attempt < v_job.max_attempts then 'pending'
        else 'failed'
    end;
    update public.calculation_jobs
       set status = v_status,
           claimed_by = null,
           claim_token = null,
           heartbeat_at = now(),
           lease_expires_at = null,
           error_code = p_error_code,
           error_message = p_error_message,
           error_detail = coalesce(p_error_detail, '{}'::jsonb)
     where id = v_job.id;
    return v_status;
end;
$$;

create or replace function public.expire_stale_calculation_jobs(
    p_pending_timeout_seconds integer default 3600
) returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_count integer;
begin
    if p_pending_timeout_seconds not between 60 and 86400 then
        raise exception 'invalid pending timeout';
    end if;
    update public.calculation_jobs
       set status = 'failed',
           claimed_by = null,
           claim_token = null,
           lease_expires_at = null,
           error_code = case
               when status = 'pending' then 'upload_timeout'
               else 'attempts_exhausted'
           end,
           error_message = case
               when status = 'pending' then 'signed upload was not completed before expiry'
               else 'worker lease expired after maximum attempts'
           end
     where (
            status = 'pending'
            and upload_completed_at is null
            and created_at < now() - make_interval(secs => p_pending_timeout_seconds)
        )
        or (
            status = 'processing'
            and lease_expires_at <= now()
            and attempt >= max_attempts
        );
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

create or replace function public.set_model_publication(
    p_model_id uuid,
    p_is_published boolean,
    p_is_default boolean default false
) returns public.models
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_model public.models%rowtype;
begin
    if p_is_default and not p_is_published then
        raise exception 'a default model must be published';
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
    if not found then
        raise exception 'model not found';
    end if;
    return v_model;
end;
$$;

create or replace function public.validate_app_config(
    p_config_key text,
    p_version text
) returns public.app_config
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_config public.app_config%rowtype;
begin
    update public.app_config
       set status = 'validated', validated_at = now(), validated_by = auth.uid()
     where config_key = p_config_key and version = p_version and status = 'draft'
     returning * into v_config;
    if not found then
        raise exception 'draft mapping config not found';
    end if;
    return v_config;
end;
$$;

create or replace function public.publish_app_config(
    p_config_key text,
    p_version text,
    p_is_default boolean default true
) returns public.app_config
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_config public.app_config%rowtype;
begin
    if p_is_default then
        update public.app_config
           set is_default = false
         where config_key = p_config_key and is_default;
    end if;
    update public.app_config
       set status = 'published',
           is_default = p_is_default,
           published_at = now(),
           published_by = auth.uid()
     where config_key = p_config_key and version = p_version and status = 'validated'
     returning * into v_config;
    if not found then
        raise exception 'validated mapping config not found';
    end if;
    return v_config;
end;
$$;

alter table public.models enable row level security;
alter table public.calculation_jobs enable row level security;
alter table public.calculation_results enable row level security;
alter table public.app_config enable row level security;
alter table public.audit_logs enable row level security;

drop policy if exists models_read_policy on public.models;
create policy models_read_policy on public.models for select to authenticated
using (is_published or created_by = auth.uid());
drop policy if exists calculation_jobs_read_own on public.calculation_jobs;
create policy calculation_jobs_read_own on public.calculation_jobs for select to authenticated
using (created_by = auth.uid());
drop policy if exists calculation_results_read_policy on public.calculation_results;
create policy calculation_results_read_policy on public.calculation_results for select to authenticated
using (
    is_published or exists (
        select 1 from public.calculation_jobs job
        where job.id = calculation_results.job_id and job.created_by = auth.uid()
    )
);
drop policy if exists app_config_read_published on public.app_config;
create policy app_config_read_published on public.app_config for select to authenticated
using (status = 'published');

revoke all on table public.audit_logs from anon, authenticated;
grant select on table public.audit_logs to authenticated;
grant select, insert on table public.audit_logs to service_role;
revoke update, delete, truncate on table public.audit_logs from anon, authenticated, service_role;
grant usage, select on sequence public.audit_logs_id_seq to service_role;

revoke all on function public.claim_calculation_job(text, integer) from public, anon, authenticated;
revoke all on function public.initialize_calculation_upload(
    uuid, uuid, text, text, integer, date, text, text, text, text,
    text, text, text, text, uuid, integer
) from public, anon, authenticated;
revoke all on function public.heartbeat_calculation_job(uuid, uuid, integer) from public, anon, authenticated;
revoke all on function public.mark_calculation_upload_completed(uuid, uuid)
    from public, anon, authenticated;
revoke all on function public.complete_calculation_job(
    uuid, uuid, jsonb, text, text, text, text, text, text, boolean, boolean
) from public, anon, authenticated;
revoke all on function public.fail_calculation_job(uuid, uuid, text, text, jsonb, boolean)
    from public, anon, authenticated;
revoke all on function public.expire_stale_calculation_jobs(integer)
    from public, anon, authenticated;
revoke all on function public.set_model_publication(uuid, boolean, boolean)
    from public, anon, authenticated;
revoke all on function public.validate_app_config(text, text)
    from public, anon, authenticated;
revoke all on function public.publish_app_config(text, text, boolean)
    from public, anon, authenticated;
grant execute on function public.claim_calculation_job(text, integer) to service_role;
grant execute on function public.initialize_calculation_upload(
    uuid, uuid, text, text, integer, date, text, text, text, text,
    text, text, text, text, uuid, integer
) to service_role;
grant execute on function public.heartbeat_calculation_job(uuid, uuid, integer) to service_role;
grant execute on function public.mark_calculation_upload_completed(uuid, uuid) to service_role;
grant execute on function public.complete_calculation_job(
    uuid, uuid, jsonb, text, text, text, text, text, text, boolean, boolean
) to service_role;
grant execute on function public.fail_calculation_job(uuid, uuid, text, text, jsonb, boolean)
    to service_role;
grant execute on function public.expire_stale_calculation_jobs(integer) to service_role;
grant execute on function public.set_model_publication(uuid, boolean, boolean) to service_role;
grant execute on function public.validate_app_config(text, text) to service_role;
grant execute on function public.publish_app_config(text, text, boolean) to service_role;

grant select on table public.models, public.calculation_jobs,
    public.calculation_results, public.app_config to authenticated;
-- Trusted adapters may create source models, pending jobs and mapping drafts.
-- All lifecycle mutations and result creation must go through the narrow
-- SECURITY DEFINER RPCs above; direct UPDATE/DELETE would bypass immutability.
revoke update, delete, truncate on table public.models, public.calculation_jobs,
    public.calculation_results, public.app_config from service_role;
grant select, insert on table public.models, public.calculation_jobs, public.app_config
    to service_role;
grant select on table public.calculation_results to service_role;

-- Private object bucket. Only Edge/service-role code creates signed uploads.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'pnl-models',
    'pnl-models',
    false,
    52428800,
    array['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
)
on conflict (id) do update set
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists pnl_storage_read_policy on storage.objects;
create policy pnl_storage_read_policy on storage.objects for select to authenticated
using (
    bucket_id = 'pnl-models'
    and public.is_valid_pnl_storage_path(name)
    and (
        exists (
            select 1 from public.models model
            where model.workbook_bucket = bucket_id
              and model.workbook_path = name
              and (model.is_published or model.created_by = auth.uid())
        )
        or exists (
            select 1 from public.calculation_results result
            join public.calculation_jobs job on job.id = result.job_id
            where result.workbook_bucket = bucket_id
              and result.workbook_path = name
              and (result.is_published or job.created_by = auth.uid())
        )
    )
);

commit;

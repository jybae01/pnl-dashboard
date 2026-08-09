-- P&L Dashboard Phase 2 durable queue and worker transitions.
-- pgmq is consumed only through the service-role-only RPCs below. The
-- pgmq_public schema is intentionally neither created nor exposed.

begin;

create extension if not exists pgmq;
create extension if not exists pg_cron;

do $queue$
begin
    if to_regclass('pgmq.q_calculation_jobs') is null then
        perform pgmq.create('calculation_jobs');
    end if;
end;
$queue$;

alter table public.calculation_jobs
    add column if not exists analysis_request jsonb not null default '{}'::jsonb,
    add column if not exists queue_name text not null default 'calculation_jobs',
    add column if not exists queue_message_id bigint,
    add column if not exists queue_enqueued_at timestamptz,
    add column if not exists queue_archived_at timestamptz;

do $constraints$
begin
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'public.calculation_jobs'::regclass
          and conname = 'calculation_jobs_analysis_request_object'
    ) then
        alter table public.calculation_jobs
            add constraint calculation_jobs_analysis_request_object
            check (jsonb_typeof(analysis_request) = 'object');
    end if;
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'public.calculation_jobs'::regclass
          and conname = 'calculation_jobs_queue_name'
    ) then
        alter table public.calculation_jobs
            add constraint calculation_jobs_queue_name
            check (queue_name = 'calculation_jobs');
    end if;
end;
$constraints$;

create unique index if not exists uq_calculation_jobs_queue_message
    on public.calculation_jobs (queue_name, queue_message_id)
    where queue_message_id is not null;
create index if not exists idx_calculation_jobs_queue_repair
    on public.calculation_jobs (status, queue_archived_at, updated_at)
    where queue_message_id is not null and queue_archived_at is null;

create or replace function public.guard_job_immutable_fields()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if (new.model_id, new.storage_bucket, new.storage_path,
        new.engine_version, new.mapping_version, new.mapping_hash,
        new.result_schema_version, new.analysis_request, new.queue_name)
       is distinct from
       (old.model_id, old.storage_bucket, old.storage_path,
        old.engine_version, old.mapping_version, old.mapping_hash,
        old.result_schema_version, old.analysis_request, old.queue_name) then
        raise exception 'calculation job source, request and provenance are immutable';
    end if;
    return new;
end;
$$;

create or replace function public.enqueue_calculation_job(
    p_job_id uuid
) returns bigint
language plpgsql
security definer
set search_path = public, pgmq, pg_temp
as $$
declare
    v_job public.calculation_jobs%rowtype;
    v_message_id bigint;
begin
    select * into v_job
      from public.calculation_jobs
     where id = p_job_id
     for update;
    if not found then
        raise exception 'calculation job not found';
    end if;
    if v_job.status <> 'pending' or v_job.upload_completed_at is null then
        raise exception 'only an uploaded pending job can be enqueued';
    end if;
    if v_job.queue_message_id is not null then
        return v_job.queue_message_id;
    end if;

    select pgmq.send(
        'calculation_jobs',
        jsonb_build_object(
            'schema_version', '1',
            'job_id', v_job.id,
            'model_id', v_job.model_id
        )
    ) into v_message_id;

    update public.calculation_jobs
       set queue_name = 'calculation_jobs',
           queue_message_id = v_message_id,
           queue_enqueued_at = now(),
           queue_archived_at = null
     where id = v_job.id;
    return v_message_id;
end;
$$;

-- The upload-complete transition and queue send are one database transaction.
create or replace function public.mark_calculation_upload_completed(
    p_job_id uuid,
    p_created_by uuid
) returns public.calculation_jobs
language plpgsql
security definer
set search_path = public, pgmq, pg_temp
as $$
declare
    v_job public.calculation_jobs%rowtype;
begin
    select * into v_job
      from public.calculation_jobs
     where id = p_job_id and created_by = p_created_by
     for update;
    if not found then
        raise exception 'upload job not found';
    end if;
    if v_job.upload_completed_at is null then
        if v_job.status <> 'pending' then
            raise exception 'only a pending job can complete an upload';
        end if;
        update public.calculation_jobs
           set upload_completed_at = now()
         where id = v_job.id
         returning * into v_job;
    end if;
    if v_job.queue_message_id is null then
        if v_job.status <> 'pending' then
            raise exception 'uploaded job has no queue receipt';
        end if;
        perform public.enqueue_calculation_job(v_job.id);
    end if;
    select * into v_job from public.calculation_jobs where id = v_job.id;
    return v_job;
end;
$$;

-- Add a versioned analysis request while preserving calls that omit it.
drop function if exists public.initialize_calculation_upload(
    uuid, uuid, text, text, integer, date, text, text, text, text,
    text, text, text, text, uuid, integer
);
create function public.initialize_calculation_upload(
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
    p_max_attempts integer default 3,
    p_analysis_request jsonb default '{}'::jsonb
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
    if jsonb_typeof(coalesce(p_analysis_request, '{}'::jsonb)) <> 'object' then
        raise exception 'analysis request must be a JSON object';
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
        max_attempts, created_by, analysis_request
    ) values (
        p_job_id, p_model_id, 'pending', p_storage_bucket, p_storage_path,
        p_engine_version, p_mapping_version, p_mapping_hash, p_result_schema_version,
        p_max_attempts, p_created_by, coalesce(p_analysis_request, '{}'::jsonb)
    ) returning * into v_job;
    return v_job;
end;
$$;

-- Durable pull: pgmq.read applies the same visibility timeout as the job
-- lease. pop() is never used because it would make delivery at-most-once.
create or replace function public.claim_calculation_job(
    p_worker_id text,
    p_lease_seconds integer default 300
) returns setof public.calculation_jobs
language plpgsql
security definer
set search_path = public, pgmq, pg_temp
as $$
declare
    v_message_id bigint;
    v_message jsonb;
    v_job_id uuid;
begin
    if length(btrim(p_worker_id)) = 0 or p_lease_seconds not between 1 and 3600 then
        raise exception 'invalid worker id or lease';
    end if;

    select message.msg_id, message.message
      into v_message_id, v_message
      from pgmq.read('calculation_jobs', p_lease_seconds, 1) as message
     limit 1;
    if v_message_id is null then
        return;
    end if;

    begin
        v_job_id := (v_message ->> 'job_id')::uuid;
    exception when others then
        perform pgmq.archive('calculation_jobs', v_message_id);
        return;
    end;

    perform 1
      from public.calculation_jobs as job
     where job.id = v_job_id
       and job.queue_message_id = v_message_id
       and job.upload_completed_at is not null
       and job.queue_archived_at is null
       and job.attempt < job.max_attempts
       and (
            job.status = 'pending'
            or (job.status = 'processing' and job.lease_expires_at <= now())
       )
     for update;
    if not found then
        -- Any mismatched/orphan receipt is poisoned. Archive it regardless of
        -- job state so it cannot be delivered forever.
        if pgmq.archive('calculation_jobs', v_message_id) then
            update public.calculation_jobs
               set queue_archived_at = coalesce(queue_archived_at, now())
             where id = v_job_id and queue_message_id = v_message_id;
        end if;
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

create or replace function public.heartbeat_calculation_job(
    p_job_id uuid,
    p_claim_token uuid,
    p_lease_seconds integer default 300
) returns boolean
language plpgsql
security definer
set search_path = public, pgmq, pg_temp
as $$
declare
    v_message_id bigint;
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
       and lease_expires_at > now()
     returning queue_message_id into v_message_id;
    if not found or v_message_id is null then
        return false;
    end if;
    perform pgmq.set_vt('calculation_jobs', v_message_id, p_lease_seconds);
    return true;
end;
$$;

-- Archive/delete are explicit acknowledgement operations. Normal successful
-- and terminal-failure transitions use archive so delivery history is kept.
create or replace function public.settle_calculation_queue_message(
    p_job_id uuid,
    p_claim_token uuid,
    p_archive boolean default true
) returns boolean
language plpgsql
security definer
set search_path = public, pgmq, pg_temp
as $$
declare
    v_job public.calculation_jobs%rowtype;
    v_settled boolean;
begin
    select * into v_job
      from public.calculation_jobs
     where id = p_job_id and claim_token = p_claim_token
     for update;
    if not found or v_job.queue_message_id is null or v_job.queue_archived_at is not null then
        return false;
    end if;
    if p_archive then
        v_settled := pgmq.archive(v_job.queue_name, v_job.queue_message_id);
    else
        v_settled := pgmq.delete(v_job.queue_name, v_job.queue_message_id);
    end if;
    if v_settled then
        update public.calculation_jobs
           set queue_archived_at = case when p_archive then now() else queue_archived_at end,
               queue_message_id = case when p_archive then queue_message_id else null end
         where id = v_job.id;
    end if;
    return coalesce(v_settled, false);
end;
$$;

-- Replace completion so the result commit, terminal status and queue archive
-- are atomic. Provenance checks from Phase 1 are retained unchanged.
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
set search_path = public, pgmq, pg_temp
as $$
declare
    v_job public.calculation_jobs%rowtype;
    v_result_id uuid;
    v_model_year integer;
begin
    select * into v_job from public.calculation_jobs where id = p_job_id for update;
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
    if v_job.queue_message_id is null then
        raise exception 'job has no queue receipt';
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

    if not pgmq.archive(v_job.queue_name, v_job.queue_message_id) then
        raise exception 'queue message acknowledgement failed';
    end if;
    update public.calculation_jobs
       set status = 'completed', completed_at = now(), heartbeat_at = now(),
           lease_expires_at = null, queue_archived_at = now()
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
set search_path = public, pgmq, pg_temp
as $$
declare
    v_job public.calculation_jobs%rowtype;
    v_status text;
begin
    select * into v_job from public.calculation_jobs where id = p_job_id for update;
    if not found or v_job.status <> 'processing' or v_job.claim_token <> p_claim_token then
        raise exception 'job claim is not active';
    end if;
    v_status := case
        when p_retryable and v_job.attempt < v_job.max_attempts then 'pending'
        else 'failed'
    end;
    if v_status = 'pending' then
        perform pgmq.set_vt(v_job.queue_name, v_job.queue_message_id, 0);
    elsif not pgmq.archive(v_job.queue_name, v_job.queue_message_id) then
        raise exception 'queue message archive failed';
    end if;
    update public.calculation_jobs
       set status = v_status, claimed_by = null, claim_token = null,
           heartbeat_at = now(), lease_expires_at = null,
           error_code = p_error_code, error_message = p_error_message,
           error_detail = coalesce(p_error_detail, '{}'::jsonb),
           queue_archived_at = case when v_status = 'failed' then now() else null end
     where id = v_job.id;
    return v_status;
end;
$$;

-- Five-minute cron execution is short, in-database and idempotent. It also
-- repairs terminal jobs whose worker committed state before an old Phase 1
-- deployment acknowledged its queue message.
create or replace function public.expire_stale_calculation_jobs(
    p_pending_timeout_seconds integer default 3600
) returns integer
language plpgsql
security definer
set search_path = public, pgmq, pg_temp
as $$
declare
    v_job record;
    v_count integer := 0;
begin
    if p_pending_timeout_seconds not between 60 and 86400 then
        raise exception 'invalid pending timeout';
    end if;
    update public.calculation_jobs
       set status = 'failed', error_code = 'upload_timeout',
           error_message = 'signed upload was not completed before expiry'
     where status = 'pending' and upload_completed_at is null
       and created_at < now() - make_interval(secs => p_pending_timeout_seconds);
    get diagnostics v_count = row_count;

    for v_job in
        select id, queue_name, queue_message_id
          from public.calculation_jobs
         where status = 'processing' and lease_expires_at <= now()
           and attempt >= max_attempts
         for update skip locked
    loop
        if v_job.queue_message_id is not null then
            perform pgmq.archive(v_job.queue_name, v_job.queue_message_id);
        end if;
        update public.calculation_jobs
           set status = 'failed', claimed_by = null, claim_token = null,
               lease_expires_at = null, error_code = 'attempts_exhausted',
               error_message = 'worker lease expired after maximum attempts',
               queue_archived_at = now()
         where id = v_job.id;
        v_count := v_count + 1;
    end loop;

    for v_job in
        select id, queue_name, queue_message_id
          from public.calculation_jobs
         where status in ('completed', 'failed')
           and queue_message_id is not null and queue_archived_at is null
         for update skip locked
    loop
        perform pgmq.archive(v_job.queue_name, v_job.queue_message_id);
        update public.calculation_jobs set queue_archived_at = now() where id = v_job.id;
        v_count := v_count + 1;
    end loop;
    return v_count;
end;
$$;

-- RLS predicates use init-plan evaluation and explicit grants because Data API
-- exposure and table privileges are separate controls.
drop policy if exists models_read_policy on public.models;
create policy models_read_policy on public.models for select to authenticated
using (is_published or created_by = (select auth.uid()));
drop policy if exists calculation_jobs_read_own on public.calculation_jobs;
create policy calculation_jobs_read_own on public.calculation_jobs for select to authenticated
using (created_by = (select auth.uid()));
drop policy if exists calculation_results_read_policy on public.calculation_results;
create policy calculation_results_read_policy on public.calculation_results for select to authenticated
using (
    is_published and exists (
        select 1 from public.calculation_jobs job
         where job.id = calculation_results.job_id
           and job.status = 'completed'
    )
);

grant select on table public.models, public.calculation_jobs,
    public.calculation_results, public.app_config to authenticated;

-- Result creation is exclusively owned by complete_calculation_job. Make this
-- revocation explicit so an environment that previously applied a broader
-- Phase 1 grant cannot retain direct INSERT or mutation privileges.
revoke insert, update, delete, truncate on table public.calculation_results
    from service_role;

revoke all on function public.enqueue_calculation_job(uuid)
    from public, anon, authenticated;
revoke all on function public.initialize_calculation_upload(
    uuid, uuid, text, text, integer, date, text, text, text, text,
    text, text, text, text, uuid, integer, jsonb
) from public, anon, authenticated;
revoke all on function public.claim_calculation_job(text, integer)
    from public, anon, authenticated;
revoke all on function public.heartbeat_calculation_job(uuid, uuid, integer)
    from public, anon, authenticated;
revoke all on function public.settle_calculation_queue_message(uuid, uuid, boolean)
    from public, anon, authenticated;
revoke all on function public.complete_calculation_job(
    uuid, uuid, jsonb, text, text, text, text, text, text, boolean, boolean
) from public, anon, authenticated;
revoke all on function public.fail_calculation_job(uuid, uuid, text, text, jsonb, boolean)
    from public, anon, authenticated;
revoke all on function public.expire_stale_calculation_jobs(integer)
    from public, anon, authenticated;

grant execute on function public.enqueue_calculation_job(uuid) to service_role;
grant execute on function public.initialize_calculation_upload(
    uuid, uuid, text, text, integer, date, text, text, text, text,
    text, text, text, text, uuid, integer, jsonb
) to service_role;
grant execute on function public.claim_calculation_job(text, integer) to service_role;
grant execute on function public.heartbeat_calculation_job(uuid, uuid, integer) to service_role;
grant execute on function public.settle_calculation_queue_message(uuid, uuid, boolean)
    to service_role;
grant execute on function public.complete_calculation_job(
    uuid, uuid, jsonb, text, text, text, text, text, text, boolean, boolean
) to service_role;
grant execute on function public.fail_calculation_job(uuid, uuid, text, text, jsonb, boolean)
    to service_role;
grant execute on function public.expire_stale_calculation_jobs(integer) to service_role;

revoke usage on schema pgmq from anon, authenticated;

do $cron$
begin
    if not exists (select 1 from cron.job where jobname = 'pnl-stale-job-cleanup') then
        perform cron.schedule(
            'pnl-stale-job-cleanup',
            '*/5 * * * *',
            'select public.expire_stale_calculation_jobs(3600);'
        );
    end if;
end;
$cron$;

commit;

-- Phase 2.5: durable Base/Comparison workbook provenance.
-- Historical values are backfilled only from evidence captured with the job
-- or result. The current default model and current workbook objects are never
-- used to guess past input identity.

begin;

alter table public.models
    add column if not exists workbook_sha256 text;

alter table public.calculation_jobs
    add column if not exists baseline_model_id uuid,
    add column if not exists comparison_model_id uuid,
    add column if not exists baseline_workbook_sha256 text,
    add column if not exists comparison_workbook_sha256 text;

alter table public.calculation_results
    add column if not exists baseline_model_id uuid,
    add column if not exists comparison_model_id uuid,
    add column if not exists baseline_workbook_sha256 text,
    add column if not exists comparison_workbook_sha256 text;

do $constraints$
begin
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.models'::regclass
           and conname = 'models_workbook_sha256_format'
    ) then
        alter table public.models add constraint models_workbook_sha256_format
            check (workbook_sha256 is null or workbook_sha256 ~ '^[0-9a-f]{64}$');
    end if;
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_jobs'::regclass
           and conname = 'calculation_jobs_baseline_model_fk'
    ) then
        alter table public.calculation_jobs add constraint calculation_jobs_baseline_model_fk
            foreign key (baseline_model_id) references public.models(id) on delete restrict;
    end if;
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_jobs'::regclass
           and conname = 'calculation_jobs_comparison_model_fk'
    ) then
        alter table public.calculation_jobs add constraint calculation_jobs_comparison_model_fk
            foreign key (comparison_model_id) references public.models(id) on delete restrict;
    end if;
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_jobs'::regclass
           and conname = 'calculation_jobs_baseline_sha256_format'
    ) then
        alter table public.calculation_jobs add constraint calculation_jobs_baseline_sha256_format
            check (baseline_workbook_sha256 is null or baseline_workbook_sha256 ~ '^[0-9a-f]{64}$');
    end if;
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_jobs'::regclass
           and conname = 'calculation_jobs_comparison_sha256_format'
    ) then
        alter table public.calculation_jobs add constraint calculation_jobs_comparison_sha256_format
            check (comparison_workbook_sha256 is null or comparison_workbook_sha256 ~ '^[0-9a-f]{64}$');
    end if;
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_results'::regclass
           and conname = 'calculation_results_baseline_model_fk'
    ) then
        alter table public.calculation_results add constraint calculation_results_baseline_model_fk
            foreign key (baseline_model_id) references public.models(id) on delete restrict;
    end if;
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_results'::regclass
           and conname = 'calculation_results_comparison_model_fk'
    ) then
        alter table public.calculation_results add constraint calculation_results_comparison_model_fk
            foreign key (comparison_model_id) references public.models(id) on delete restrict;
    end if;
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_results'::regclass
           and conname = 'calculation_results_baseline_sha256_format'
    ) then
        alter table public.calculation_results add constraint calculation_results_baseline_sha256_format
            check (baseline_workbook_sha256 is null or baseline_workbook_sha256 ~ '^[0-9a-f]{64}$');
    end if;
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_results'::regclass
           and conname = 'calculation_results_comparison_sha256_format'
    ) then
        alter table public.calculation_results add constraint calculation_results_comparison_sha256_format
            check (comparison_workbook_sha256 is null or comparison_workbook_sha256 ~ '^[0-9a-f]{64}$');
    end if;
end;
$constraints$;

-- model_id has always identified the Comparison model.
update public.calculation_jobs
   set comparison_model_id = model_id
 where comparison_model_id is null;

-- Baseline recovery priority 1: the request captured with the job. Invalid or
-- non-existent UUIDs remain unresolved instead of aborting the migration.
with request_baselines as (
    select job.id, (job.analysis_request ->> 'baseline_model_id')::uuid as baseline_model_id
      from public.calculation_jobs job
     where job.baseline_model_id is null
       and job.analysis_request ->> 'baseline_model_id'
           ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
), valid_request_baselines as (
    select candidate.id, candidate.baseline_model_id
      from request_baselines candidate
      join public.calculation_jobs job on job.id = candidate.id
      join public.models baseline_model on baseline_model.id = candidate.baseline_model_id
      join public.models comparison_model on comparison_model.id = job.comparison_model_id
     where candidate.baseline_model_id <> job.comparison_model_id
       and baseline_model.model_year = comparison_model.model_year
)
update public.calculation_jobs job
   set baseline_model_id = candidate.baseline_model_id
  from valid_request_baselines candidate
 where job.id = candidate.id
   and job.baseline_model_id is null;

-- Baseline recovery priority 2: a completed result's captured comparison
-- payload. No current/default model lookup is permitted.
with result_baselines as (
    select job.id,
           (result_row.result -> 'comparison_result' -> 'baseline' ->> 'id')::uuid
               as baseline_model_id
      from public.calculation_jobs job
      join public.calculation_results result_row on result_row.job_id = job.id
     where job.status = 'completed'
       and job.baseline_model_id is null
       and result_row.result -> 'comparison_result' -> 'baseline' ->> 'id'
           ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
), valid_result_baselines as (
    select candidate.id, candidate.baseline_model_id
      from result_baselines candidate
      join public.calculation_jobs job on job.id = candidate.id
      join public.models baseline_model on baseline_model.id = candidate.baseline_model_id
      join public.models comparison_model on comparison_model.id = job.comparison_model_id
     where candidate.baseline_model_id <> job.comparison_model_id
       and baseline_model.model_year = comparison_model.model_year
)
update public.calculation_jobs job
   set baseline_model_id = candidate.baseline_model_id
  from valid_result_baselines candidate
 where job.id = candidate.id
   and job.baseline_model_id is null;

-- Result backfill only copies evidence already pinned to the linked job.
update public.calculation_results result_row
   set comparison_model_id = coalesce(job.comparison_model_id, result_row.model_id),
       baseline_model_id = job.baseline_model_id,
       baseline_workbook_sha256 = job.baseline_workbook_sha256,
       comparison_workbook_sha256 = job.comparison_workbook_sha256
  from public.calculation_jobs job
 where job.id = result_row.job_id
   and (
       result_row.comparison_model_id is null
       or result_row.baseline_model_id is null
       or result_row.baseline_workbook_sha256 is null
       or result_row.comparison_workbook_sha256 is null
   );

alter table public.calculation_jobs
    alter column comparison_model_id set not null;
alter table public.calculation_results
    alter column comparison_model_id set not null;

do $constraints$
begin
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_jobs'::regclass
           and conname = 'calculation_jobs_comparison_matches_legacy'
    ) then
        alter table public.calculation_jobs
            add constraint calculation_jobs_comparison_matches_legacy
            check (model_id = comparison_model_id);
    end if;
    if not exists (
        select 1 from pg_constraint
         where conrelid = 'public.calculation_results'::regclass
           and conname = 'calculation_results_comparison_matches_legacy'
    ) then
        alter table public.calculation_results
            add constraint calculation_results_comparison_matches_legacy
            check (model_id = comparison_model_id);
    end if;
end;
$constraints$;

create or replace function public.guard_model_workbook_sha256()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if old.workbook_sha256 is not null
       and new.workbook_sha256 is distinct from old.workbook_sha256 then
        raise exception 'model workbook SHA-256 is immutable once recorded';
    end if;
    return new;
end;
$$;

drop trigger if exists models_guard_workbook_sha256 on public.models;
create trigger models_guard_workbook_sha256
before update of workbook_sha256 on public.models
for each row execute function public.guard_model_workbook_sha256();

create or replace function public.guard_new_durable_job_inputs()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    v_baseline public.models%rowtype;
    v_comparison public.models%rowtype;
begin
    if new.baseline_model_id is null or new.comparison_model_id is null then
        raise exception 'durable job requires explicit baseline_model_id and comparison_model_id';
    end if;
    if new.baseline_model_id = new.comparison_model_id then
        raise exception 'baseline and comparison models must be different';
    end if;
    if new.model_id <> new.comparison_model_id then
        raise exception 'legacy model_id must equal comparison_model_id';
    end if;
    if new.baseline_workbook_sha256 is null or new.comparison_workbook_sha256 is null then
        raise exception 'durable job requires both workbook SHA-256 snapshots';
    end if;

    select * into v_baseline from public.models where id = new.baseline_model_id;
    if not found then
        raise exception 'baseline model does not exist';
    end if;
    select * into v_comparison from public.models where id = new.comparison_model_id;
    if not found then
        raise exception 'comparison model does not exist';
    end if;
    if v_baseline.model_year <> v_comparison.model_year then
        raise exception 'baseline and comparison models must have the same year';
    end if;
    if v_baseline.workbook_sha256 is null or v_comparison.workbook_sha256 is null then
        raise exception 'both models must have recorded workbook SHA-256 values';
    end if;
    if new.baseline_workbook_sha256 <> v_baseline.workbook_sha256
       or new.comparison_workbook_sha256 <> v_comparison.workbook_sha256 then
        raise exception 'job workbook SHA-256 snapshot does not match model provenance';
    end if;
    if not exists (
        select 1 from public.app_config config
         where config.config_key = 'model_mapping'
           and config.status = 'published'
           and config.version = new.mapping_version
           and config.content_hash = new.mapping_hash
    ) then
        raise exception 'mapping provenance is not published';
    end if;
    return new;
end;
$$;

drop trigger if exists calculation_jobs_guard_durable_inputs on public.calculation_jobs;
create trigger calculation_jobs_guard_durable_inputs
before insert on public.calculation_jobs
for each row execute function public.guard_new_durable_job_inputs();

create or replace function public.guard_job_immutable_fields()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if (new.baseline_model_id, new.comparison_model_id, new.model_id,
        new.baseline_workbook_sha256, new.comparison_workbook_sha256,
        new.storage_bucket, new.storage_path,
        new.engine_version, new.mapping_version, new.mapping_hash,
        new.result_schema_version, new.analysis_request, new.queue_name)
       is distinct from
       (old.baseline_model_id, old.comparison_model_id, old.model_id,
        old.baseline_workbook_sha256, old.comparison_workbook_sha256,
        old.storage_bucket, old.storage_path,
        old.engine_version, old.mapping_version, old.mapping_hash,
        old.result_schema_version, old.analysis_request, old.queue_name) then
        raise exception 'calculation job inputs, request and provenance are immutable';
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
    if (new.job_id, new.baseline_model_id, new.comparison_model_id, new.model_id,
        new.baseline_workbook_sha256, new.comparison_workbook_sha256,
        new.model_year, new.result,
        new.engine_version, new.mapping_version, new.mapping_hash,
        new.result_schema_version, new.workbook_bucket, new.workbook_path)
       is distinct from
       (old.job_id, old.baseline_model_id, old.comparison_model_id, old.model_id,
        old.baseline_workbook_sha256, old.comparison_workbook_sha256,
        old.model_year, old.result,
        old.engine_version, old.mapping_version, old.mapping_hash,
        old.result_schema_version, old.workbook_bucket, old.workbook_path) then
        raise exception 'calculation result payload and provenance are immutable';
    end if;
    return new;
end;
$$;

-- Deployment precheck. Active legacy jobs returned here must be resubmitted;
-- this migration deliberately does not rewrite queue state or job status.
create or replace function public.get_unresolved_active_calculation_jobs()
returns setof public.calculation_jobs
language sql
stable
set search_path = public
as $$
    select job.*
      from public.calculation_jobs job
     where job.status in ('pending', 'processing')
       and (
           job.baseline_model_id is null
           or job.comparison_model_id is null
           or job.baseline_workbook_sha256 is null
           or job.comparison_workbook_sha256 is null
       )
     order by job.created_at;
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
    if v_job.baseline_model_id is null
       or v_job.comparison_model_id is null
       or v_job.baseline_workbook_sha256 is null
       or v_job.comparison_workbook_sha256 is null then
        raise exception 'INPUT_PROVENANCE_UNRESOLVED: active legacy job must be resubmitted';
    end if;
    if v_job.queue_message_id is not null then
        return v_job.queue_message_id;
    end if;

    select pgmq.send(
        'calculation_jobs',
        jsonb_build_object('job_id', v_job.id),
        0
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

    -- Preserve the receipt and job status for administrator resubmission.
    -- The deployment precheck exposes the same rows before worker rollout.
    if exists (
        select 1 from public.calculation_jobs job
         where job.id = v_job_id
           and job.queue_message_id = v_message_id
           and job.status in ('pending', 'processing')
           and (
               job.baseline_model_id is null
               or job.comparison_model_id is null
               or job.baseline_workbook_sha256 is null
               or job.comparison_workbook_sha256 is null
           )
    ) then
        perform pgmq.set_vt('calculation_jobs', v_message_id, greatest(p_lease_seconds, 3600));
        return;
    end if;

    perform 1
      from public.calculation_jobs job
     where job.id = v_job_id
       and job.queue_message_id = v_message_id
       and job.upload_completed_at is not null
       and job.queue_archived_at is null
       and job.baseline_model_id is not null
       and job.comparison_model_id is not null
       and job.baseline_workbook_sha256 is not null
       and job.comparison_workbook_sha256 is not null
       and job.attempt < job.max_attempts
       and (
            job.status = 'pending'
            or (job.status = 'processing' and job.lease_expires_at <= now())
       )
     for update;
    if not found then
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

    return query select job.* from public.calculation_jobs job where job.id = v_job_id;
end;
$$;

create or replace function public.create_durable_calculation_job(
    p_baseline_model_id uuid,
    p_comparison_model_id uuid,
    p_engine_version text,
    p_mapping_version text,
    p_mapping_hash text,
    p_result_schema_version text,
    p_created_by uuid default null,
    p_max_attempts integer default 3,
    p_analysis_request jsonb default '{}'::jsonb
) returns public.calculation_jobs
language plpgsql
security definer
set search_path = public, pgmq, pg_temp
as $$
declare
    v_baseline public.models%rowtype;
    v_comparison public.models%rowtype;
    v_job public.calculation_jobs%rowtype;
    v_request jsonb;
begin
    if p_baseline_model_id is null then
        raise exception 'baseline_model_id is required';
    end if;
    if p_comparison_model_id is null then
        raise exception 'comparison_model_id is required';
    end if;
    if p_baseline_model_id = p_comparison_model_id then
        raise exception 'baseline and comparison models must be different';
    end if;
    if jsonb_typeof(coalesce(p_analysis_request, '{}'::jsonb)) <> 'object' then
        raise exception 'analysis request must be a JSON object';
    end if;

    select * into v_baseline
      from public.models where id = p_baseline_model_id for share;
    if not found then
        raise exception 'baseline model does not exist';
    end if;
    select * into v_comparison
      from public.models where id = p_comparison_model_id for share;
    if not found then
        raise exception 'comparison model does not exist';
    end if;
    if v_baseline.model_year <> v_comparison.model_year then
        raise exception 'baseline and comparison models must have the same year';
    end if;
    if v_baseline.workbook_sha256 is null or v_comparison.workbook_sha256 is null then
        raise exception 'both models must have recorded workbook SHA-256 values';
    end if;
    if not exists (
        select 1 from public.app_config config
         where config.config_key = 'model_mapping'
           and config.status = 'published'
           and config.version = p_mapping_version
           and config.content_hash = p_mapping_hash
    ) then
        raise exception 'mapping provenance is not published';
    end if;

    v_request := jsonb_set(
        coalesce(p_analysis_request, '{}'::jsonb),
        '{baseline_model_id}',
        to_jsonb(p_baseline_model_id::text),
        true
    );
    insert into public.calculation_jobs (
        model_id, baseline_model_id, comparison_model_id,
        baseline_workbook_sha256, comparison_workbook_sha256,
        status, storage_bucket, storage_path, upload_completed_at,
        engine_version, mapping_version, mapping_hash, result_schema_version,
        max_attempts, created_by, analysis_request
    ) values (
        p_comparison_model_id, p_baseline_model_id, p_comparison_model_id,
        v_baseline.workbook_sha256, v_comparison.workbook_sha256,
        'pending', v_comparison.workbook_bucket, v_comparison.workbook_path, now(),
        p_engine_version, p_mapping_version, p_mapping_hash, p_result_schema_version,
        p_max_attempts, p_created_by, v_request
    ) returning * into v_job;

    perform public.enqueue_calculation_job(v_job.id);
    select * into v_job from public.calculation_jobs where id = v_job.id;
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
set search_path = public, pgmq, pg_temp
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
    if v_job.baseline_model_id is null
       or v_job.comparison_model_id is null
       or v_job.baseline_workbook_sha256 is null
       or v_job.comparison_workbook_sha256 is null then
        raise exception 'INPUT_PROVENANCE_UNRESOLVED: job must be resubmitted';
    end if;
    if (p_engine_version, p_mapping_version, p_mapping_hash, p_result_schema_version)
       is distinct from
       (v_job.engine_version, v_job.mapping_version, v_job.mapping_hash, v_job.result_schema_version) then
        raise exception 'result provenance does not match job provenance';
    end if;
    if v_job.queue_message_id is null then
        raise exception 'job has no queue receipt';
    end if;

    select model_year into strict v_model_year
      from public.models
     where id = v_job.comparison_model_id;
    insert into public.calculation_results (
        job_id, model_id, baseline_model_id, comparison_model_id, model_year, result,
        baseline_workbook_sha256, comparison_workbook_sha256,
        engine_version, mapping_version, mapping_hash, result_schema_version,
        workbook_bucket, workbook_path, is_published, is_default, published_at
    ) values (
        v_job.id, v_job.comparison_model_id,
        v_job.baseline_model_id, v_job.comparison_model_id, v_model_year, p_result,
        v_job.baseline_workbook_sha256, v_job.comparison_workbook_sha256,
        v_job.engine_version, v_job.mapping_version, v_job.mapping_hash,
        v_job.result_schema_version,
        p_workbook_bucket, p_workbook_path, false, false, null
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

create or replace function public.set_calculation_result_publication(
    p_result_id uuid,
    p_is_published boolean,
    p_is_default boolean default false
) returns public.calculation_results
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_result public.calculation_results%rowtype;
    v_job public.calculation_jobs%rowtype;
    v_job_id uuid;
begin
    if p_is_default and not p_is_published then
        raise exception 'a default result must be published';
    end if;

    select job_id into v_job_id
      from public.calculation_results
     where id = p_result_id;
    if not found then
        raise exception 'only a completed calculation result can be published';
    end if;
    select * into v_job from public.calculation_jobs where id = v_job_id;

    -- Stable lock order for two-model publication and same-comparison defaults.
    perform 1
      from public.models
     where id in (v_job.baseline_model_id, v_job.comparison_model_id)
     order by id
     for update;

    select result_row.* into v_result
      from public.calculation_results result_row
      join public.calculation_jobs job on job.id = result_row.job_id
     where result_row.id = p_result_id
       and job.status = 'completed'
       and job.baseline_model_id is not null
       and job.comparison_model_id is not null
       and job.baseline_workbook_sha256 is not null
       and job.comparison_workbook_sha256 is not null
       and result_row.baseline_model_id = job.baseline_model_id
       and result_row.comparison_model_id = job.comparison_model_id
       and result_row.model_id = result_row.comparison_model_id
       and result_row.baseline_workbook_sha256 = job.baseline_workbook_sha256
       and result_row.comparison_workbook_sha256 = job.comparison_workbook_sha256
       and result_row.engine_version = job.engine_version
       and result_row.mapping_version = job.mapping_version
       and result_row.mapping_hash = job.mapping_hash
       and result_row.result_schema_version = job.result_schema_version
     for update of result_row;
    if not found then
        raise exception 'result input provenance does not match completed job';
    end if;

    if p_is_published and not exists (
        select 1
          from public.models baseline_model
          join public.models comparison_model
            on comparison_model.id = v_result.comparison_model_id
         where baseline_model.id = v_result.baseline_model_id
           and baseline_model.is_published
           and comparison_model.is_published
           and baseline_model.workbook_sha256 = v_result.baseline_workbook_sha256
           and comparison_model.workbook_sha256 = v_result.comparison_workbook_sha256
    ) then
        raise exception 'baseline and comparison models must be published';
    end if;
    if p_is_published and not exists (
        select 1 from public.app_config config
         where config.config_key = 'model_mapping'
           and config.status = 'published'
           and config.version = v_result.mapping_version
           and config.content_hash = v_result.mapping_hash
    ) then
        raise exception 'result mapping provenance is not published';
    end if;

    if p_is_default then
        update public.calculation_results
           set is_default = false
         where comparison_model_id = v_result.comparison_model_id
           and id <> v_result.id
           and is_default;
    end if;
    update public.calculation_results
       set is_published = p_is_published,
           is_default = p_is_default,
           published_at = case
               when p_is_published then coalesce(published_at, now())
               else null
           end
     where id = v_result.id
     returning * into v_result;
    return v_result;
end;
$$;

create or replace function public.get_published_calculation_result()
returns setof public.calculation_results
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select result_row.*
      from public.calculation_results result_row
      join public.calculation_jobs job on job.id = result_row.job_id
      join public.models baseline_model on baseline_model.id = result_row.baseline_model_id
      join public.models comparison_model on comparison_model.id = result_row.comparison_model_id
     where result_row.is_published
       and job.status = 'completed'
       and baseline_model.is_published
       and comparison_model.is_published
       and baseline_model.workbook_sha256 = result_row.baseline_workbook_sha256
       and comparison_model.workbook_sha256 = result_row.comparison_workbook_sha256
       and result_row.baseline_model_id = job.baseline_model_id
       and result_row.comparison_model_id = job.comparison_model_id
       and result_row.model_id = result_row.comparison_model_id
       and result_row.baseline_workbook_sha256 is not null
       and result_row.comparison_workbook_sha256 is not null
       and result_row.baseline_workbook_sha256 = job.baseline_workbook_sha256
       and result_row.comparison_workbook_sha256 = job.comparison_workbook_sha256
       and result_row.engine_version = job.engine_version
       and result_row.mapping_version = job.mapping_version
       and result_row.mapping_hash = job.mapping_hash
       and result_row.result_schema_version = job.result_schema_version
       and exists (
           select 1 from public.app_config config
            where config.config_key = 'model_mapping'
              and config.status = 'published'
              and config.version = result_row.mapping_version
              and config.content_hash = result_row.mapping_hash
       )
     order by result_row.is_default desc, result_row.created_at desc
     limit 1;
$$;

drop policy if exists calculation_results_read_policy on public.calculation_results;
create policy calculation_results_read_policy on public.calculation_results
for select to authenticated
using (
    (
        is_published
        and baseline_model_id is not null
        and comparison_model_id is not null
        and baseline_workbook_sha256 is not null
        and comparison_workbook_sha256 is not null
        and model_id = comparison_model_id
        and exists (
            select 1
              from public.calculation_jobs job
              join public.models baseline_model on baseline_model.id = job.baseline_model_id
              join public.models comparison_model on comparison_model.id = job.comparison_model_id
             where job.id = calculation_results.job_id
               and job.status = 'completed'
               and baseline_model.is_published
               and comparison_model.is_published
               and baseline_model.workbook_sha256 = calculation_results.baseline_workbook_sha256
               and comparison_model.workbook_sha256 = calculation_results.comparison_workbook_sha256
               and job.baseline_model_id = calculation_results.baseline_model_id
               and job.comparison_model_id = calculation_results.comparison_model_id
               and job.baseline_workbook_sha256 = calculation_results.baseline_workbook_sha256
               and job.comparison_workbook_sha256 = calculation_results.comparison_workbook_sha256
               and job.engine_version = calculation_results.engine_version
               and job.mapping_version = calculation_results.mapping_version
               and job.mapping_hash = calculation_results.mapping_hash
               and job.result_schema_version = calculation_results.result_schema_version
        )
        and exists (
            select 1 from public.app_config config
             where config.config_key = 'model_mapping'
               and config.status = 'published'
               and config.version = calculation_results.mapping_version
               and config.content_hash = calculation_results.mapping_hash
        )
    )
    or exists (
        select 1 from public.calculation_jobs job
         where job.id = calculation_results.job_id
           and job.created_by = auth.uid()
    )
);

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
            select 1
              from public.calculation_results result_row
              join public.calculation_jobs job on job.id = result_row.job_id
              join public.models baseline_model on baseline_model.id = result_row.baseline_model_id
              join public.models comparison_model on comparison_model.id = result_row.comparison_model_id
             where result_row.workbook_bucket = bucket_id
               and result_row.workbook_path = name
               and (
                   job.created_by = auth.uid()
                   or (
                       result_row.is_published
                       and job.status = 'completed'
                       and baseline_model.is_published
                       and comparison_model.is_published
                       and baseline_model.workbook_sha256 = result_row.baseline_workbook_sha256
                       and comparison_model.workbook_sha256 = result_row.comparison_workbook_sha256
                       and result_row.baseline_model_id = job.baseline_model_id
                       and result_row.comparison_model_id = job.comparison_model_id
                       and result_row.model_id = result_row.comparison_model_id
                       and result_row.baseline_workbook_sha256 = job.baseline_workbook_sha256
                       and result_row.comparison_workbook_sha256 = job.comparison_workbook_sha256
                       and result_row.engine_version = job.engine_version
                       and result_row.mapping_version = job.mapping_version
                       and result_row.mapping_hash = job.mapping_hash
                       and result_row.result_schema_version = job.result_schema_version
                       and exists (
                           select 1 from public.app_config config
                            where config.config_key = 'model_mapping'
                              and config.status = 'published'
                              and config.version = result_row.mapping_version
                              and config.content_hash = result_row.mapping_hash
                       )
                   )
               )
        )
    )
);

revoke all on function public.get_unresolved_active_calculation_jobs()
    from public, anon, authenticated;
grant execute on function public.get_unresolved_active_calculation_jobs() to service_role;

revoke all on function public.create_durable_calculation_job(
    uuid, uuid, text, text, text, text, uuid, integer, jsonb
) from public, anon, authenticated;
grant execute on function public.create_durable_calculation_job(
    uuid, uuid, text, text, text, text, uuid, integer, jsonb
) to service_role;

revoke all on function public.enqueue_calculation_job(uuid)
    from public, anon, authenticated;
grant execute on function public.enqueue_calculation_job(uuid) to service_role;

revoke all on function public.claim_calculation_job(text, integer)
    from public, anon, authenticated;
grant execute on function public.claim_calculation_job(text, integer) to service_role;

-- The Phase 2 signed-upload initializer creates a job before the server can
-- hash uploaded bytes, so it cannot satisfy the Phase 2.5 durable contract.
-- It is deliberately retired until an upload-session/finalization path is
-- implemented in the later application-integration goal.
revoke execute on function public.initialize_calculation_upload(
    uuid, uuid, text, text, integer, date, text, text, text, text,
    text, text, text, text, uuid, integer, jsonb
) from service_role;
revoke execute on function public.mark_calculation_upload_completed(uuid, uuid)
    from service_role;

revoke all on function public.complete_calculation_job(
    uuid, uuid, jsonb, text, text, text, text, text, text, boolean, boolean
) from public, anon, authenticated;
grant execute on function public.complete_calculation_job(
    uuid, uuid, jsonb, text, text, text, text, text, text, boolean, boolean
) to service_role;

revoke all on function public.set_calculation_result_publication(uuid, boolean, boolean)
    from public, anon, authenticated;
grant execute on function public.set_calculation_result_publication(uuid, boolean, boolean)
    to service_role;

revoke all on function public.get_published_calculation_result()
    from public, anon, authenticated;
grant execute on function public.get_published_calculation_result() to service_role;

commit;

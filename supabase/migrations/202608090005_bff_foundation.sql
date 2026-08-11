-- Trusted BFF foundation: actor-scoped idempotent submission and narrow by-ID reads.
-- No browser role is granted direct access; the server-only application gateway
-- reauthorizes the access-code session before calling these service_role RPCs.

begin;

alter table public.calculation_jobs
    add column if not exists idempotency_actor text,
    add column if not exists request_fingerprint jsonb;

alter table public.calculation_jobs
    drop constraint if exists calculation_jobs_idempotency_key_key;

do $constraints$
begin
    if not exists (
        select 1 from pg_constraint
         where conname = 'calculation_jobs_idempotency_actor_shape'
           and conrelid = 'public.calculation_jobs'::regclass
    ) then
        alter table public.calculation_jobs
            add constraint calculation_jobs_idempotency_actor_shape
            check (
                idempotency_actor is null
                or length(idempotency_actor) between 1 and 200
            );
    end if;
    if not exists (
        select 1 from pg_constraint
         where conname = 'calculation_jobs_request_fingerprint_shape'
           and conrelid = 'public.calculation_jobs'::regclass
    ) then
        alter table public.calculation_jobs
            add constraint calculation_jobs_request_fingerprint_shape
            check (
                request_fingerprint is null
                or jsonb_typeof(request_fingerprint) = 'object'
            );
    end if;
end;
$constraints$;

create unique index if not exists uq_calculation_jobs_idempotency_actor_key
    on public.calculation_jobs (idempotency_actor, idempotency_key)
    where idempotency_actor is not null and idempotency_key is not null;

create or replace function public.guard_job_immutable_fields()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if (new.baseline_model_id, new.comparison_model_id, new.model_id,
        new.baseline_workbook_sha256, new.comparison_workbook_sha256,
        new.storage_bucket, new.storage_path,
        new.engine_version, new.mapping_version, new.mapping_hash,
        new.result_schema_version, new.analysis_request, new.queue_name,
        new.idempotency_actor, new.idempotency_key, new.request_fingerprint)
       is distinct from
       (old.baseline_model_id, old.comparison_model_id, old.model_id,
        old.baseline_workbook_sha256, old.comparison_workbook_sha256,
        old.storage_bucket, old.storage_path,
        old.engine_version, old.mapping_version, old.mapping_hash,
        old.result_schema_version, old.analysis_request, old.queue_name,
        old.idempotency_actor, old.idempotency_key, old.request_fingerprint) then
        raise exception 'calculation job inputs, request, idempotency and provenance are immutable';
    end if;
    return new;
end;
$$;

create or replace function public.create_durable_calculation_job_idempotent(
    p_baseline_model_id uuid,
    p_comparison_model_id uuid,
    p_start_month smallint,
    p_end_month smallint,
    p_baseline_sales_fx numeric,
    p_comparison_sales_fx numeric,
    p_idempotency_actor text,
    p_idempotency_key text,
    p_engine_version text,
    p_mapping_version text,
    p_mapping_hash text,
    p_result_schema_version text,
    p_max_attempts integer default 3
) returns table (
    job_id uuid,
    status text,
    idempotency_replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_baseline public.models%rowtype;
    v_comparison public.models%rowtype;
    v_existing public.calculation_jobs%rowtype;
    v_job public.calculation_jobs%rowtype;
    v_fingerprint jsonb;
    v_request jsonb;
begin
    if p_baseline_model_id is null or p_comparison_model_id is null then
        raise exception 'baseline_model_id and comparison_model_id are required';
    end if;
    if p_baseline_model_id = p_comparison_model_id then
        raise exception 'baseline and comparison models must be different';
    end if;
    if p_start_month is null or p_end_month is null
       or p_start_month < 1 or p_end_month > 12 or p_start_month > p_end_month then
        raise exception 'invalid analysis month range';
    end if;
    if p_baseline_sales_fx is null or p_baseline_sales_fx <= 0
       or p_comparison_sales_fx is null or p_comparison_sales_fx <= 0
       or p_baseline_sales_fx = 'NaN'::numeric
       or p_comparison_sales_fx = 'NaN'::numeric then
        raise exception 'sales FX values must be positive';
    end if;
    if p_idempotency_actor is null
       or length(btrim(p_idempotency_actor)) < 1
       or length(p_idempotency_actor) > 200 then
        raise exception 'idempotency actor is required';
    end if;
    if p_idempotency_key is null
       or p_idempotency_key !~ '^[A-Za-z0-9._:-]{1,128}$' then
        raise exception 'invalid idempotency key';
    end if;
    if p_max_attempts is null or p_max_attempts < 1 or p_max_attempts > 20 then
        raise exception 'max_attempts must be between 1 and 20';
    end if;
    if p_engine_version is null or length(btrim(p_engine_version)) < 1
       or p_mapping_version is null or length(btrim(p_mapping_version)) < 1
       or p_mapping_hash is null or p_mapping_hash !~ '^[0-9a-f]{64}$'
       or p_result_schema_version is null
       or length(btrim(p_result_schema_version)) < 1 then
        raise exception 'invalid release provenance';
    end if;

    -- Collision-free canonical request fingerprint owned by the database.
    -- JSONB numeric equality makes 1480 and 1480.0 the same semantic request.
    -- Release provenance is included so a key cannot replay another release.
    v_fingerprint := jsonb_build_object(
        'baseline_model_id', p_baseline_model_id::text,
        'comparison_model_id', p_comparison_model_id::text,
        'start_month', p_start_month,
        'end_month', p_end_month,
        'baseline_sales_fx', p_baseline_sales_fx,
        'comparison_sales_fx', p_comparison_sales_fx,
        'engine_version', p_engine_version,
        'mapping_version', p_mapping_version,
        'mapping_hash', p_mapping_hash,
        'result_schema_version', p_result_schema_version,
        'max_attempts', p_max_attempts
    );

    -- Actor/key-scoped transaction lock makes lookup + insert race-safe. Hash
    -- collisions only serialize unrelated requests; the unique index remains
    -- the final invariant.
    perform pg_advisory_xact_lock(hashtextextended(
        p_idempotency_actor || chr(31) || p_idempotency_key,
        0
    ));

    select * into v_existing
      from public.calculation_jobs existing_job
     where existing_job.idempotency_actor = p_idempotency_actor
       and existing_job.idempotency_key = p_idempotency_key
     for update;
    if found then
        if v_existing.request_fingerprint is distinct from v_fingerprint then
            raise exception 'IDEMPOTENCY_CONFLICT: key already used for another request';
        end if;
        return query select v_existing.id, v_existing.status, true;
        return;
    end if;

    select * into v_baseline
      from public.models baseline_model
     where baseline_model.id = p_baseline_model_id
     for share;
    if not found then
        raise exception 'baseline model does not exist';
    end if;
    select * into v_comparison
      from public.models comparison_model
     where comparison_model.id = p_comparison_model_id
     for share;
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

    v_request := jsonb_build_object(
        'baseline_model_id', p_baseline_model_id::text,
        'comparison_model_id', p_comparison_model_id::text,
        'start_month', p_start_month,
        'end_month', p_end_month,
        'months', (
            select jsonb_agg(month_number order by month_number)
              from generate_series(p_start_month, p_end_month) month_number
        ),
        'baseline_sales_fx', p_baseline_sales_fx,
        'comparison_sales_fx', p_comparison_sales_fx
    );

    insert into public.calculation_jobs (
        model_id, baseline_model_id, comparison_model_id,
        baseline_workbook_sha256, comparison_workbook_sha256,
        status, storage_bucket, storage_path, upload_completed_at,
        engine_version, mapping_version, mapping_hash, result_schema_version,
        max_attempts, created_by, analysis_request,
        idempotency_actor, idempotency_key, request_fingerprint
    ) values (
        p_comparison_model_id, p_baseline_model_id, p_comparison_model_id,
        v_baseline.workbook_sha256, v_comparison.workbook_sha256,
        'pending', v_comparison.workbook_bucket, v_comparison.workbook_path, now(),
        p_engine_version, p_mapping_version, p_mapping_hash, p_result_schema_version,
        p_max_attempts, null, v_request,
        p_idempotency_actor, p_idempotency_key, v_fingerprint
    ) returning * into v_job;

    perform public.enqueue_calculation_job(v_job.id);
    select * into v_job from public.calculation_jobs job where job.id = v_job.id;
    return query select v_job.id, v_job.status, false;
end;
$$;

create or replace function public.get_calculation_job_status_by_id(p_job_id uuid)
returns table (
    job_id uuid,
    status text,
    baseline_model_id uuid,
    comparison_model_id uuid,
    start_month smallint,
    end_month smallint,
    attempt integer,
    max_attempts integer,
    created_at timestamptz,
    heartbeat_at timestamptz,
    completed_at timestamptz,
    result_id uuid,
    error_code text,
    error_message text
)
language sql
stable
security definer
set search_path = ''
as $$
    select job.id,
           job.status,
           job.baseline_model_id,
           job.comparison_model_id,
           (job.analysis_request ->> 'start_month')::smallint,
           (job.analysis_request ->> 'end_month')::smallint,
           job.attempt,
           job.max_attempts,
           job.created_at,
           job.heartbeat_at,
           job.completed_at,
           result_row.id,
           job.error_code,
           case
               when job.error_code is null then null
               when job.error_code = 'INPUT_INTEGRITY_MISMATCH' then 'Calculation input integrity check failed'
               when job.error_code = 'INPUT_PROVENANCE_UNRESOLVED' then 'Calculation input provenance is unresolved'
               when job.error_code = 'preflight_failed' then 'Workbook preflight failed'
               when job.error_code = 'upload_timeout' then 'Workbook upload timed out'
               when job.error_code = 'attempts_exhausted' then 'Calculation retry limit was reached'
               else 'Calculation failed'
           end
      from public.calculation_jobs job
      left join public.calculation_results result_row on result_row.job_id = job.id
     where job.id = p_job_id;
$$;

create or replace function public.get_calculation_result_admin_preview_by_id(
    p_result_id uuid
) returns table (
    result_id uuid,
    job_id uuid,
    analysis_view jsonb,
    baseline_model_id uuid,
    comparison_model_id uuid,
    baseline_workbook_sha256 text,
    comparison_workbook_sha256 text,
    engine_version text,
    mapping_version text,
    mapping_hash text,
    result_schema_version text,
    is_published boolean,
    is_default boolean,
    published_at timestamptz,
    created_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
    select result_row.id,
           result_row.job_id,
           result_row.result -> 'analysis_view',
           result_row.baseline_model_id,
           result_row.comparison_model_id,
           result_row.baseline_workbook_sha256,
           result_row.comparison_workbook_sha256,
           result_row.engine_version,
           result_row.mapping_version,
           result_row.mapping_hash,
           result_row.result_schema_version,
           result_row.is_published,
           result_row.is_default,
           result_row.published_at,
           result_row.created_at
      from public.calculation_results result_row
      join public.calculation_jobs job on job.id = result_row.job_id
     where result_row.id = p_result_id
       and job.status = 'completed'
       and result_row.baseline_model_id = job.baseline_model_id
       and result_row.comparison_model_id = job.comparison_model_id
       and result_row.model_id = result_row.comparison_model_id
       and result_row.baseline_workbook_sha256 = job.baseline_workbook_sha256
       and result_row.comparison_workbook_sha256 = job.comparison_workbook_sha256
       and result_row.engine_version = job.engine_version
       and result_row.mapping_version = job.mapping_version
       and result_row.mapping_hash = job.mapping_hash
       and result_row.result_schema_version = job.result_schema_version;
$$;

create or replace function public.validate_calculation_result_availability(
    p_result_id uuid,
    p_supported_result_schema_versions text[]
) returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select coalesce(array_length(p_supported_result_schema_versions, 1), 0) > 0
       and exists (
        select 1
          from public.calculation_results result_row
          join public.calculation_jobs job on job.id = result_row.job_id
          join public.models baseline_model on baseline_model.id = result_row.baseline_model_id
          join public.models comparison_model on comparison_model.id = result_row.comparison_model_id
         where result_row.id = p_result_id
           and result_row.is_published
           and result_row.published_at is not null
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
           and result_row.result_schema_version = any(p_supported_result_schema_versions)
           and jsonb_typeof(result_row.result -> 'analysis_view') = 'object'
           and exists (
               select 1 from public.app_config config
                where config.config_key = 'model_mapping'
                  and config.status = 'published'
                  and config.version = result_row.mapping_version
                  and config.content_hash = result_row.mapping_hash
           )
    );
$$;

create or replace function public.get_available_calculation_result_by_id(
    p_result_id uuid,
    p_supported_result_schema_versions text[]
) returns table (
    result_id uuid,
    job_id uuid,
    analysis_view jsonb,
    baseline_model_id uuid,
    comparison_model_id uuid,
    baseline_workbook_sha256 text,
    comparison_workbook_sha256 text,
    engine_version text,
    mapping_version text,
    mapping_hash text,
    result_schema_version text,
    is_published boolean,
    is_default boolean,
    published_at timestamptz,
    created_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
    select result_row.id,
           result_row.job_id,
           result_row.result -> 'analysis_view',
           result_row.baseline_model_id,
           result_row.comparison_model_id,
           result_row.baseline_workbook_sha256,
           result_row.comparison_workbook_sha256,
           result_row.engine_version,
           result_row.mapping_version,
           result_row.mapping_hash,
           result_row.result_schema_version,
           result_row.is_published,
           result_row.is_default,
           result_row.published_at,
           result_row.created_at
      from public.calculation_results result_row
     where result_row.id = p_result_id
       and public.validate_calculation_result_availability(
           result_row.id,
           p_supported_result_schema_versions
       );
$$;

revoke all on function public.create_durable_calculation_job_idempotent(
    uuid, uuid, smallint, smallint, numeric, numeric,
    text, text, text, text, text, text, integer
) from public, anon, authenticated;
grant execute on function public.create_durable_calculation_job_idempotent(
    uuid, uuid, smallint, smallint, numeric, numeric,
    text, text, text, text, text, text, integer
) to service_role;

revoke all on function public.get_calculation_job_status_by_id(uuid)
    from public, anon, authenticated;
grant execute on function public.get_calculation_job_status_by_id(uuid) to service_role;

revoke all on function public.get_calculation_result_admin_preview_by_id(uuid)
    from public, anon, authenticated;
grant execute on function public.get_calculation_result_admin_preview_by_id(uuid)
    to service_role;

revoke all on function public.validate_calculation_result_availability(uuid, text[])
    from public, anon, authenticated;
grant execute on function public.validate_calculation_result_availability(uuid, text[])
    to service_role;

revoke all on function public.get_available_calculation_result_by_id(uuid, text[])
    from public, anon, authenticated;
grant execute on function public.get_available_calculation_result_by_id(uuid, text[])
    to service_role;

commit;

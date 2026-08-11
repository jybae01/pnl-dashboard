-- Live PostgreSQL 17 compatibility correction for the Analysis month series.

begin;

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
              from pg_catalog.generate_series(
                  p_start_month::integer,
                  p_end_month::integer
              ) month_number
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

revoke all on function public.create_durable_calculation_job_idempotent(
    uuid, uuid, smallint, smallint, numeric, numeric,
    text, text, text, text, text, text, integer
) from public, anon, authenticated;
grant execute on function public.create_durable_calculation_job_idempotent(
    uuid, uuid, smallint, smallint, numeric, numeric,
    text, text, text, text, text, text, integer
) to service_role;

commit;

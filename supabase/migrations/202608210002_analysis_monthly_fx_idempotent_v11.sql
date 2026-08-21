-- Slice E: durable monthly sales-FX analysis requests.
--
-- This is an additive v11 submission boundary.  The legacy scalar RPC remains
-- unchanged for existing callers and persisted requests.  New requests carry
-- complete YYYY-MM maps in calculation_jobs.analysis_request; no scalar value
-- is broadcast, averaged, or stored as a substitute for a monthly value.

begin;

create or replace function public.create_durable_calculation_job_idempotent_v11(
    p_baseline_model_id uuid,
    p_comparison_model_id uuid,
    p_start_month smallint,
    p_end_month smallint,
    p_baseline_sales_fx_monthly jsonb,
    p_comparison_sales_fx_monthly jsonb,
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
    v_expected_year text;
    v_expected_count integer;
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
    if p_idempotency_actor is null
       or pg_catalog.length(pg_catalog.btrim(p_idempotency_actor)) < 1
       or pg_catalog.length(p_idempotency_actor) > 200 then
        raise exception 'idempotency actor is required';
    end if;
    if p_idempotency_key is null
       or p_idempotency_key !~ '^[A-Za-z0-9._:-]{1,128}$' then
        raise exception 'invalid idempotency key';
    end if;
    if p_max_attempts is null or p_max_attempts < 1 or p_max_attempts > 20 then
        raise exception 'max_attempts must be between 1 and 20';
    end if;
    if p_engine_version is null or pg_catalog.length(pg_catalog.btrim(p_engine_version)) < 1
       or p_mapping_version is null or pg_catalog.length(pg_catalog.btrim(p_mapping_version)) < 1
       or p_mapping_hash is null or p_mapping_hash !~ '^[0-9a-f]{64}$'
       or p_result_schema_version is null
       or pg_catalog.length(pg_catalog.btrim(p_result_schema_version)) < 1 then
        raise exception 'invalid release provenance';
    end if;
    if pg_catalog.jsonb_typeof(p_baseline_sales_fx_monthly) <> 'object'
       or pg_catalog.jsonb_typeof(p_comparison_sales_fx_monthly) <> 'object' then
        raise exception 'monthly sales FX values must be JSON objects';
    end if;

    -- The model rows establish the authoritative year for YYYY-MM keys.  Keep
    -- the same immutable workbook/provenance gates as the legacy RPC.
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
        select 1
          from public.app_config config
         where config.config_key = 'model_mapping'
           and config.status = 'published'
           and config.version = p_mapping_version
           and config.content_hash = p_mapping_hash
    ) then
        raise exception 'mapping provenance is not published';
    end if;

    v_expected_year := v_baseline.model_year::text;
    v_expected_count := p_end_month - p_start_month + 1;

    -- Every key must be canonical YYYY-MM and every value must be a finite,
    -- strictly positive JSON number.  CASE prevents a non-number JSON value
    -- from being cast to numeric while evaluating the same predicate.
    if exists (
        select 1
          from pg_catalog.jsonb_each(p_baseline_sales_fx_monthly) as entry(key, value)
         where entry.key !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
            or case
                 when pg_catalog.jsonb_typeof(entry.value) <> 'number' then true
                 else (entry.value #>> '{}') in ('NaN', 'Infinity', '-Infinity')
                      or not ((entry.value #>> '{}')::numeric > 0)
               end
    ) or exists (
        select 1
          from pg_catalog.jsonb_each(p_comparison_sales_fx_monthly) as entry(key, value)
         where entry.key !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
            or case
                 when pg_catalog.jsonb_typeof(entry.value) <> 'number' then true
                 else (entry.value #>> '{}') in ('NaN', 'Infinity', '-Infinity')
                      or not ((entry.value #>> '{}')::numeric > 0)
               end
    ) then
        raise exception 'monthly sales FX values must be finite positive JSON numbers with YYYY-MM keys';
    end if;

    -- Exact set equality: no missing, extra, wrong-year, or duplicate-period
    -- values can reach the immutable job request. JSONB object keys are unique.
    if (
        select count(*) from pg_catalog.jsonb_object_keys(p_baseline_sales_fx_monthly)
    ) <> v_expected_count
       or exists (
           select 1
             from pg_catalog.generate_series(
                 p_start_month::integer, p_end_month::integer
             ) as series(month_number)
            where not (p_baseline_sales_fx_monthly ? pg_catalog.format(
                '%s-%s', v_expected_year, pg_catalog.to_char(series.month_number, 'FM00')
            ))
       )
       or (
        select count(*) from pg_catalog.jsonb_object_keys(p_comparison_sales_fx_monthly)
       ) <> v_expected_count
       or exists (
           select 1
             from pg_catalog.generate_series(
                 p_start_month::integer, p_end_month::integer
             ) as series(month_number)
            where not (p_comparison_sales_fx_monthly ? pg_catalog.format(
                '%s-%s', v_expected_year, pg_catalog.to_char(series.month_number, 'FM00')
            ))
       ) then
        raise exception 'monthly sales FX keys must exactly match the selected model-year month range';
    end if;

    -- JSONB canonicalization makes equivalent numeric spellings and key order
    -- the same semantic request, while retaining both monthly maps in replay
    -- identity and in the persisted request provenance.
    v_fingerprint := pg_catalog.jsonb_build_object(
        'baseline_model_id', p_baseline_model_id::text,
        'comparison_model_id', p_comparison_model_id::text,
        'start_month', p_start_month,
        'end_month', p_end_month,
        'baseline_sales_fx_monthly', p_baseline_sales_fx_monthly,
        'comparison_sales_fx_monthly', p_comparison_sales_fx_monthly,
        'engine_version', p_engine_version,
        'mapping_version', p_mapping_version,
        'mapping_hash', p_mapping_hash,
        'result_schema_version', p_result_schema_version,
        'max_attempts', p_max_attempts
    );

    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
        p_idempotency_actor || pg_catalog.chr(31) || p_idempotency_key,
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

    v_request := pg_catalog.jsonb_build_object(
        'baseline_model_id', p_baseline_model_id::text,
        'comparison_model_id', p_comparison_model_id::text,
        'start_month', p_start_month,
        'end_month', p_end_month,
        'months', (
            select pg_catalog.jsonb_agg(series.month_number order by series.month_number)
              from pg_catalog.generate_series(
                  p_start_month::integer, p_end_month::integer
              ) as series(month_number)
        ),
        'baseline_sales_fx_monthly', p_baseline_sales_fx_monthly,
        'comparison_sales_fx_monthly', p_comparison_sales_fx_monthly
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
        'pending', v_comparison.workbook_bucket, v_comparison.workbook_path, pg_catalog.now(),
        p_engine_version, p_mapping_version, p_mapping_hash, p_result_schema_version,
        p_max_attempts, null, v_request,
        p_idempotency_actor, p_idempotency_key, v_fingerprint
    ) returning * into v_job;

    perform public.enqueue_calculation_job(v_job.id);
    select * into v_job
      from public.calculation_jobs job
     where job.id = v_job.id;
    return query select v_job.id, v_job.status, false;
end;
$$;

revoke all on function public.create_durable_calculation_job_idempotent_v11(
    uuid, uuid, smallint, smallint, jsonb, jsonb,
    text, text, text, text, text, text, integer
) from public, anon, authenticated;
grant execute on function public.create_durable_calculation_job_idempotent_v11(
    uuid, uuid, smallint, smallint, jsonb, jsonb,
    text, text, text, text, text, text, integer
) to service_role;

commit;

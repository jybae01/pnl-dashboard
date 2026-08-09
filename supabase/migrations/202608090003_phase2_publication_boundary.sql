-- Phase 2 final hardening: calculation and publication are distinct
-- capabilities.  Workers can only commit an unpublished immutable result.

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
    -- Deprecated ABI compatibility only. Values are deliberately ignored.
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
     where id = v_job.model_id;
    insert into public.calculation_results (
        job_id, model_id, model_year, result,
        engine_version, mapping_version, mapping_hash, result_schema_version,
        workbook_bucket, workbook_path, is_published, is_default, published_at
    ) values (
        v_job.id, v_job.model_id, v_model_year, p_result,
        p_engine_version, p_mapping_version, p_mapping_hash, p_result_schema_version,
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
begin
    if p_is_default and not p_is_published then
        raise exception 'a default result must be published';
    end if;

    select result_row.* into v_result
      from public.calculation_results result_row
      join public.calculation_jobs job on job.id = result_row.job_id
     where result_row.id = p_result_id
       and job.status = 'completed'
       and job.model_id = result_row.model_id
     for update of result_row;
    if not found then
        raise exception 'only a completed calculation result can be published';
    end if;

    if p_is_published and not exists (
        select 1
          from public.app_config config
         where config.config_key = 'model_mapping'
           and config.status = 'published'
           and config.version = v_result.mapping_version
           and config.content_hash = v_result.mapping_hash
    ) then
        raise exception 'result mapping provenance is not published';
    end if;

    if p_is_default then
        -- Serialize same-model default changes before clearing the old row.
        perform 1 from public.models where id = v_result.model_id for update;
        update public.calculation_results
           set is_default = false
         where model_id = v_result.model_id
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

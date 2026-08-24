-- Persistent model deletion: terminal analysis result artifacts are cleaned by
-- the trusted BFF before their FK-owned database rows are finalized.
-- This migration is forward-only and changes no table or constraint shape.

begin;

create or replace function public.assert_model_terminal_analysis_cleanup_safe(
    p_model_id uuid
) returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_model public.models%rowtype;
    v_generation_id uuid;
    v_generation_status text;
    v_ingestion_status text;
    v_active_analysis_jobs bigint;
    v_active_analysis_results bigint;
    v_forecast_uses bigint;
    v_derived_models bigint;
    v_job public.calculation_jobs%rowtype;
    v_result public.calculation_results%rowtype;
    v_has_result boolean;
begin
    if p_model_id is null then
        raise exception 'model id is required';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('persistent-delete:model:' || p_model_id::text, 0)
    );

    select * into v_model
      from public.models model_row
     where model_row.id = p_model_id
     for update;
    if not found then
        raise exception 'model not found';
    end if;

    if v_model.is_default or v_model.is_published or v_model.confirmed then
        raise exception 'model is protected';
    end if;

    if v_model.workbook_bucket <> 'pnl-models'
       or v_model.workbook_path <> pg_catalog.format('models/%s/source.xlsx', p_model_id)
       or not public.is_valid_pnl_storage_path(v_model.workbook_path, 'source') then
        raise exception 'model storage ownership is invalid';
    end if;

    select request_row.status into v_ingestion_status
      from public.model_ingestion_requests request_row
     where request_row.model_id = p_model_id
     for update;
    if found and v_ingestion_status <> 'completed' then
        raise exception 'model ingestion is active';
    end if;

    select request_row.id, request_row.status
      into v_generation_id, v_generation_status
      from public.forecast_generation_requests request_row
     where request_row.model_id = p_model_id
     for update;
    if found and (
        v_generation_status <> 'completed'
        or v_model.forecast_generation_id is distinct from v_generation_id
    ) then
        raise exception 'forecast generation is active';
    end if;

    select count(*) into v_active_analysis_jobs
      from public.calculation_jobs job
     where job.status in ('pending', 'processing')
       and p_model_id in (
           job.model_id, job.baseline_model_id, job.comparison_model_id
       );
    select count(*) into v_active_analysis_results
      from public.calculation_results result_row
      join public.calculation_jobs job on job.id = result_row.job_id
     where job.status in ('pending', 'processing')
       and p_model_id in (
           result_row.model_id,
           result_row.baseline_model_id,
           result_row.comparison_model_id
       );
    select count(*) into v_forecast_uses
      from public.forecast_generation_requests request_row
     where request_row.base_model_id = p_model_id;
    select count(*) into v_derived_models
      from public.models derived
     where derived.source_model_id = p_model_id;

    if v_active_analysis_jobs + v_active_analysis_results
       + v_forecast_uses + v_derived_models > 0 then
        raise exception 'model has active references';
    end if;

    -- The completion RPC may be called after the initial model prepare. Check
    -- the full terminal dependency set again so a newly protected or malformed
    -- sibling row cannot be bypassed by finalizing a different job first.
    for v_job in
        select job.*
          from public.calculation_jobs job
          left join public.calculation_results result_row
            on result_row.job_id = job.id
         where job.status in ('completed', 'failed')
           and (
               p_model_id in (
                   job.model_id, job.baseline_model_id, job.comparison_model_id
               )
               or p_model_id in (
                   result_row.model_id,
                   result_row.baseline_model_id,
                   result_row.comparison_model_id
               )
           )
         order by job.id
         for update of job
    loop
        select * into v_result
          from public.calculation_results result_row
         where result_row.job_id = v_job.id
         for update;
        v_has_result := found;
        if (v_job.status = 'completed' and not v_has_result)
           or (v_job.status = 'failed' and v_has_result) then
            raise exception 'terminal analysis shape is invalid';
        end if;
        if (v_job.queue_message_id is null and v_job.queue_archived_at is not null)
           or (v_job.queue_message_id is not null and v_job.queue_archived_at is null)
           or (
               v_job.queue_message_id is not null
               and not exists (
                   select 1
                     from pgmq.a_calculation_jobs archived
                    where archived.msg_id = v_job.queue_message_id
               )
           ) then
            raise exception 'terminal analysis queue state is unsettled';
        end if;
        if v_has_result and (v_result.is_default or v_result.is_published) then
            raise exception 'terminal analysis result is protected';
        end if;
        if v_has_result and (
            (v_result.workbook_bucket is null) <> (v_result.workbook_path is null)
            or (
                v_result.workbook_path is not null
                and (
                    v_result.workbook_bucket <> 'pnl-models'
                    or v_result.workbook_path <> pg_catalog.format(
                        'models/%s/jobs/%s/result.xlsx',
                        v_result.model_id,
                        v_job.id
                    )
                    or not public.is_valid_pnl_storage_path(
                        v_result.workbook_path, 'result'
                    )
                )
            )
        ) then
            raise exception 'terminal analysis storage ownership is invalid';
        end if;
        if exists (
            select 1
              from public.persistent_delete_receipts receipt
             where receipt.resource_type = 'analysis'
               and receipt.resource_id = v_job.id
        ) then
            raise exception 'terminal analysis delete receipt conflicts';
        end if;
    end loop;
end;
$$;

create or replace function public.list_model_terminal_analysis_dependencies(
    p_model_id uuid
) returns table (
    job_id uuid,
    owner_model_id uuid,
    storage_bucket text,
    storage_path text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_job public.calculation_jobs%rowtype;
    v_result public.calculation_results%rowtype;
    v_has_result boolean;
begin
    perform public.assert_model_terminal_analysis_cleanup_safe(p_model_id);

    -- Lock and validate every terminal row before exposing a path to the BFF.
    -- The BFF never receives a path for a row that has not passed these checks.
    for v_job in
        select job.*
          from public.calculation_jobs job
          left join public.calculation_results result_row
            on result_row.job_id = job.id
         where job.status in ('completed', 'failed')
           and (
               p_model_id in (
                   job.model_id, job.baseline_model_id, job.comparison_model_id
               )
               or p_model_id in (
                   result_row.model_id,
                   result_row.baseline_model_id,
                   result_row.comparison_model_id
               )
           )
         order by job.id
         for update of job
    loop
        select * into v_result
          from public.calculation_results result_row
         where result_row.job_id = v_job.id
         for update;
        v_has_result := found;

        if (v_job.status = 'completed' and not v_has_result)
           or (v_job.status = 'failed' and v_has_result) then
            raise exception 'terminal analysis shape is invalid';
        end if;
        if (v_job.queue_message_id is null and v_job.queue_archived_at is not null)
           or (v_job.queue_message_id is not null and v_job.queue_archived_at is null)
           or (
               v_job.queue_message_id is not null
               and not exists (
                   select 1
                     from pgmq.a_calculation_jobs archived
                    where archived.msg_id = v_job.queue_message_id
               )
           ) then
            raise exception 'terminal analysis queue state is unsettled';
        end if;
        if v_has_result and (v_result.is_default or v_result.is_published) then
            raise exception 'terminal analysis result is protected';
        end if;
        if v_has_result and (
            (v_result.workbook_bucket is null) <> (v_result.workbook_path is null)
            or (
                v_result.workbook_path is not null
                and (
                    v_result.workbook_bucket <> 'pnl-models'
                    or v_result.workbook_path <> pg_catalog.format(
                        'models/%s/jobs/%s/result.xlsx',
                        v_result.model_id,
                        v_job.id
                    )
                    or not public.is_valid_pnl_storage_path(
                        v_result.workbook_path, 'result'
                    )
                )
            )
        ) then
            raise exception 'terminal analysis storage ownership is invalid';
        end if;
        if exists (
            select 1
              from public.persistent_delete_receipts receipt
             where receipt.resource_type = 'analysis'
               and receipt.resource_id = v_job.id
        ) then
            raise exception 'terminal analysis delete receipt conflicts';
        end if;
    end loop;

    return query
    select job.id,
           result_row.model_id,
           result_row.workbook_bucket,
           result_row.workbook_path
      from public.calculation_jobs job
      join public.calculation_results result_row
        on result_row.job_id = job.id
     where job.status in ('completed', 'failed')
       and result_row.workbook_path is not null
       and (
           p_model_id in (
               job.model_id, job.baseline_model_id, job.comparison_model_id
           )
           or p_model_id in (
               result_row.model_id,
               result_row.baseline_model_id,
               result_row.comparison_model_id
           )
       )
     order by job.id;
end;
$$;

create or replace function public.complete_model_terminal_analysis_dependency(
    p_model_id uuid,
    p_job_id uuid,
    p_storage_bucket text,
    p_storage_path text
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_job public.calculation_jobs%rowtype;
    v_result public.calculation_results%rowtype;
    v_has_result boolean;
begin
    if p_model_id is null or p_job_id is null then
        raise exception 'model and job ids are required';
    end if;
    if (p_storage_bucket is null) <> (p_storage_path is null) then
        raise exception 'storage pair is invalid';
    end if;

    perform public.assert_model_terminal_analysis_cleanup_safe(p_model_id);

    select * into v_job
      from public.calculation_jobs job
     where job.id = p_job_id
     for update;
    if not found or v_job.status not in ('completed', 'failed') then
        raise exception 'terminal analysis job is unavailable';
    end if;

    select * into v_result
      from public.calculation_results result_row
     where result_row.job_id = p_job_id
     for update;
    v_has_result := found;

    if (v_job.status = 'completed' and not v_has_result)
       or (v_job.status = 'failed' and v_has_result) then
        raise exception 'terminal analysis shape is invalid';
    end if;
    if p_model_id is distinct from v_job.model_id
       and p_model_id is distinct from v_job.baseline_model_id
       and p_model_id is distinct from v_job.comparison_model_id
       and (
           not v_has_result
           or (
               p_model_id is distinct from v_result.model_id
               and p_model_id is distinct from v_result.baseline_model_id
               and p_model_id is distinct from v_result.comparison_model_id
           )
       ) then
        raise exception 'terminal analysis does not reference target model';
    end if;
    if (v_job.queue_message_id is null and v_job.queue_archived_at is not null)
       or (v_job.queue_message_id is not null and v_job.queue_archived_at is null)
       or (
           v_job.queue_message_id is not null
           and not exists (
               select 1
                 from pgmq.a_calculation_jobs archived
                where archived.msg_id = v_job.queue_message_id
           )
       ) then
        raise exception 'terminal analysis queue state is unsettled';
    end if;
    if v_has_result and (v_result.is_default or v_result.is_published) then
        raise exception 'terminal analysis result is protected';
    end if;
    if v_has_result and (
        (v_result.workbook_bucket is null) <> (v_result.workbook_path is null)
        or (
            v_result.workbook_path is not null
            and (
                v_result.workbook_bucket <> 'pnl-models'
                or v_result.workbook_path <> pg_catalog.format(
                    'models/%s/jobs/%s/result.xlsx', v_result.model_id, p_job_id
                )
                or not public.is_valid_pnl_storage_path(
                    v_result.workbook_path, 'result'
                )
            )
        )
    ) then
        raise exception 'terminal analysis storage ownership is invalid';
    end if;
    if p_storage_bucket is distinct from case
        when v_has_result then v_result.workbook_bucket else null end
       or p_storage_path is distinct from case
        when v_has_result then v_result.workbook_path else null end then
        raise exception 'terminal analysis storage binding changed';
    end if;
    if exists (
        select 1
          from public.persistent_delete_receipts receipt
         where receipt.resource_type = 'analysis'
           and receipt.resource_id = p_job_id
    ) then
        raise exception 'terminal analysis delete receipt conflicts';
    end if;

    -- calculation_results.job_id is ON DELETE RESTRICT. Remove the result,
    -- archived queue message, and job in FK-safe order. Storage is never
    -- touched by SQL; the BFF has already verified absence for a path.
    if v_has_result then
        delete from public.calculation_results result_row
         where result_row.job_id = p_job_id;
    end if;
    if v_job.queue_message_id is not null then
        delete from pgmq.a_calculation_jobs archived
         where archived.msg_id = v_job.queue_message_id;
    end if;
    delete from public.calculation_jobs job
     where job.id = p_job_id;
    if not found then
        raise exception 'terminal analysis job cleanup did not complete';
    end if;
    return true;
end;
$$;

revoke all on function public.assert_model_terminal_analysis_cleanup_safe(uuid)
    from public, anon, authenticated, service_role;
revoke all on function public.list_model_terminal_analysis_dependencies(uuid)
    from public, anon, authenticated;
revoke all on function public.complete_model_terminal_analysis_dependency(uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.list_model_terminal_analysis_dependencies(uuid)
    to service_role;
grant execute on function public.complete_model_terminal_analysis_dependency(uuid, uuid, text, text)
    to service_role;

commit;

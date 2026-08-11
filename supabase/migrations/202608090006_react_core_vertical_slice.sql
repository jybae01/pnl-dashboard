begin;

-- A browser can submit an arbitrary UUID even when the model-list endpoint
-- filters drafts. Enforce the V1 published-input rule atomically at the final
-- durable-job insert boundary. The FOR SHARE locks serialize publication
-- changes with job creation without weakening the legacy upload path.
create or replace function public.guard_bff_job_model_publication()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_baseline public.models%rowtype;
    v_comparison public.models%rowtype;
begin
    if new.idempotency_actor is null then
        return new;
    end if;

    -- Deterministic lock order avoids opposing Base/Comparison deadlocks.
    perform 1
      from public.models model_row
     where model_row.id in (new.baseline_model_id, new.comparison_model_id)
     order by model_row.id
     for share;

    select * into v_baseline
      from public.models model_row
     where model_row.id = new.baseline_model_id;
    select * into v_comparison
      from public.models model_row
     where model_row.id = new.comparison_model_id;

    if v_baseline.id is null or v_comparison.id is null then
        raise exception 'analysis models do not exist';
    end if;
    if not v_baseline.is_published or not v_comparison.is_published then
        raise exception 'analysis models must be published';
    end if;
    if v_baseline.workbook_sha256 is distinct from new.baseline_workbook_sha256
       or v_comparison.workbook_sha256 is distinct from new.comparison_workbook_sha256 then
        raise exception 'analysis model SHA-256 snapshot mismatch';
    end if;
    return new;
end;
$$;

drop trigger if exists calculation_jobs_bff_model_publication
    on public.calculation_jobs;
create trigger calculation_jobs_bff_model_publication
before insert on public.calculation_jobs
for each row execute function public.guard_bff_job_model_publication();

revoke all on function public.guard_bff_job_model_publication() from public;
revoke all on function public.guard_bff_job_model_publication() from anon;
revoke all on function public.guard_bff_job_model_publication() from authenticated;
revoke all on function public.guard_bff_job_model_publication() from service_role;

commit;

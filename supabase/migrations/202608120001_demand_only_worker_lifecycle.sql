-- Demand-only Cloud Run Worker Pool lifecycle state and race-safe reconciliation.
-- Google API calls are deliberately outside these short database transactions.

begin;

create table if not exists public.worker_lifecycle_state (
    singleton boolean primary key default true check (singleton),
    desired_instance_count smallint not null default 0
        check (desired_instance_count in (0, 1)),
    generation bigint not null default 0 check (generation >= 0),
    last_worker_activity_at timestamptz not null default now(),
    last_wake_requested_at timestamptz,
    last_sleep_requested_at timestamptz,
    observed_instance_count smallint check (observed_instance_count in (0, 1)),
    last_scaling_at timestamptz,
    last_scaling_result text check (last_scaling_result in (
        'noop', 'scaled', 'get_failed', 'wake_failed', 'sleep_failed'
    )),
    last_scaling_error_code text check (
        last_scaling_error_code is null
        or last_scaling_error_code ~ '^[A-Z0-9_]{1,64}$'
    ),
    updated_at timestamptz not null default now()
);

alter table public.worker_lifecycle_state enable row level security;

insert into public.worker_lifecycle_state (
    singleton, desired_instance_count, last_worker_activity_at
)
select true,
       case when exists (
           select 1 from public.calculation_jobs
            where (status = 'pending'
                   and upload_completed_at is not null
                   and queue_message_id is not null)
               or status = 'processing'
       ) then 1 else 0 end,
       coalesce((
           select max(updated_at) from public.calculation_jobs
            where queue_message_id is not null or status = 'processing'
       ), now())
on conflict (singleton) do nothing;

create or replace function public.mark_worker_required_activity()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    v_relevant boolean;
    v_worker_eligible_new boolean;
    v_worker_eligible_old boolean := false;
begin
    v_worker_eligible_new := (
        new.status = 'processing'
        or (
            new.status = 'pending'
            and new.upload_completed_at is not null
            and new.queue_message_id is not null
        )
    );
    if tg_op = 'INSERT' then
        v_relevant := v_worker_eligible_new;
    else
        v_worker_eligible_old := (
            old.status = 'processing'
            or (
                old.status = 'pending'
                and old.upload_completed_at is not null
                and old.queue_message_id is not null
            )
        );
        v_relevant := (
            new.status,
            new.upload_completed_at,
            new.heartbeat_at,
            new.lease_expires_at,
            new.attempt,
            new.queue_message_id,
            new.queue_archived_at,
            new.completed_at
        ) is distinct from (
            old.status,
            old.upload_completed_at,
            old.heartbeat_at,
            old.lease_expires_at,
            old.attempt,
            old.queue_message_id,
            old.queue_archived_at,
            old.completed_at
        ) and (v_worker_eligible_new or v_worker_eligible_old);
    end if;

    if v_relevant then
        perform pg_advisory_xact_lock(1777046461);
        update public.worker_lifecycle_state
           set desired_instance_count = case
                   when v_worker_eligible_new then 1
                   else desired_instance_count
               end,
               generation = generation + 1,
               last_worker_activity_at = now(),
               last_wake_requested_at = case
                   when v_worker_eligible_new then now()
                   else last_wake_requested_at
               end,
               updated_at = now()
         where singleton;
    end if;
    return new;
end;
$$;

drop trigger if exists calculation_jobs_worker_activity on public.calculation_jobs;
create trigger calculation_jobs_worker_activity
after insert or update on public.calculation_jobs
for each row execute function public.mark_worker_required_activity();

create or replace function public.worker_workload_snapshot()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_queue_depth bigint;
    v_claimable bigint;
    v_pending bigint;
    v_processing bigint;
    v_active_leases bigint;
    v_recovery bigint;
begin
    select count(*), count(*) filter (where vt <= now())
      into v_queue_depth, v_claimable
      from pgmq.q_calculation_jobs;

    select count(*) filter (
               where status = 'pending'
                 and upload_completed_at is not null
                 and queue_message_id is not null
           ),
           count(*) filter (where status = 'processing'),
           count(*) filter (
               where status = 'processing' and lease_expires_at > now()
           ),
           count(*) filter (
               where status = 'processing'
                 and (lease_expires_at is null or lease_expires_at <= now())
           )
      into v_pending, v_processing, v_active_leases, v_recovery
      from public.calculation_jobs
     where (status = 'pending'
            and upload_completed_at is not null
            and queue_message_id is not null)
        or status = 'processing';

    return jsonb_build_object(
        'queue_depth', v_queue_depth,
        'claimable_count', v_claimable,
        'pending_count', v_pending,
        'processing_count', v_processing,
        'active_lease_count', v_active_leases,
        'active_heartbeat_count', v_active_leases,
        'recovery_pending_count', v_recovery,
        'work_exists', (
            v_queue_depth > 0 or v_pending > 0 or v_processing > 0
            or v_active_leases > 0 or v_recovery > 0
        )
    );
end;
$$;

create or replace function public.get_worker_lifecycle_snapshot()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_state public.worker_lifecycle_state%rowtype;
begin
    select * into strict v_state
      from public.worker_lifecycle_state where singleton;
    return to_jsonb(v_state) || public.worker_workload_snapshot() || jsonb_build_object(
        'idle_seconds', greatest(
            0, floor(extract(epoch from (now() - v_state.last_worker_activity_at)))::bigint
        )
    );
end;
$$;

create or replace function public.reconcile_worker_lifecycle(
    p_idle_seconds integer default 1800
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_state public.worker_lifecycle_state%rowtype;
    v_work jsonb;
    v_target smallint;
begin
    if p_idle_seconds <> 1800 then
        raise exception 'WORKER_IDLE_POLICY_FIXED_1800';
    end if;
    perform pg_advisory_xact_lock(1777046461);
    select * into strict v_state
      from public.worker_lifecycle_state where singleton for update;
    v_work := public.worker_workload_snapshot();
    v_target := case
        when (v_work ->> 'work_exists')::boolean then 1
        when now() - v_state.last_worker_activity_at >= make_interval(secs => 1800) then 0
        else v_state.desired_instance_count
    end;
    if v_target <> v_state.desired_instance_count then
        update public.worker_lifecycle_state
           set desired_instance_count = v_target,
               generation = generation + 1,
               last_wake_requested_at = case when v_target = 1 then now() else last_wake_requested_at end,
               last_sleep_requested_at = case when v_target = 0 then now() else last_sleep_requested_at end,
               updated_at = now()
         where singleton
         returning * into v_state;
    end if;
    return to_jsonb(v_state) || v_work || jsonb_build_object(
        'idle_seconds', greatest(
            0, floor(extract(epoch from (now() - v_state.last_worker_activity_at)))::bigint
        )
    );
end;
$$;

create or replace function public.emergency_wake_worker()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
    perform pg_advisory_xact_lock(1777046461);
    update public.worker_lifecycle_state
       set desired_instance_count = 1,
           generation = generation + 1,
           last_worker_activity_at = now(),
           last_wake_requested_at = now(),
           updated_at = now()
     where singleton;
    return public.get_worker_lifecycle_snapshot();
end;
$$;

create or replace function public.safe_stop_worker()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_work jsonb;
begin
    perform pg_advisory_xact_lock(1777046461);
    perform 1 from public.worker_lifecycle_state where singleton for update;
    v_work := public.worker_workload_snapshot();
    if (v_work ->> 'work_exists')::boolean then
        raise exception 'WORKER_BUSY';
    end if;
    update public.worker_lifecycle_state
       set desired_instance_count = 0,
           generation = generation + 1,
           last_sleep_requested_at = now(),
           updated_at = now()
     where singleton;
    return public.get_worker_lifecycle_snapshot();
end;
$$;

create or replace function public.record_worker_scaling_result(
    p_generation bigint,
    p_observed_instance_count smallint,
    p_result text,
    p_error_code text default null
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    if (p_observed_instance_count is not null and p_observed_instance_count not in (0, 1))
       or p_result not in ('noop', 'scaled', 'get_failed', 'wake_failed', 'sleep_failed')
       or (p_error_code is not null and p_error_code !~ '^[A-Z0-9_]{1,64}$') then
        raise exception 'INVALID_SCALING_RESULT';
    end if;
    update public.worker_lifecycle_state
       set observed_instance_count = p_observed_instance_count,
           last_scaling_at = now(),
           last_scaling_result = p_result,
           last_scaling_error_code = p_error_code,
           updated_at = now()
     where singleton and generation = p_generation;
    return found;
end;
$$;

revoke all on table public.worker_lifecycle_state from public, anon, authenticated, service_role;
revoke all on function public.mark_worker_required_activity() from public, anon, authenticated, service_role;
revoke all on function public.worker_workload_snapshot() from public, anon, authenticated;
revoke all on function public.get_worker_lifecycle_snapshot() from public, anon, authenticated;
revoke all on function public.reconcile_worker_lifecycle(integer) from public, anon, authenticated;
revoke all on function public.emergency_wake_worker() from public, anon, authenticated;
revoke all on function public.safe_stop_worker() from public, anon, authenticated;
revoke all on function public.record_worker_scaling_result(bigint, smallint, text, text)
    from public, anon, authenticated;

grant execute on function public.worker_workload_snapshot() to service_role;
grant execute on function public.get_worker_lifecycle_snapshot() to service_role;
grant execute on function public.reconcile_worker_lifecycle(integer) to service_role;
grant execute on function public.emergency_wake_worker() to service_role;
grant execute on function public.safe_stop_worker() to service_role;
grant execute on function public.record_worker_scaling_result(bigint, smallint, text, text)
    to service_role;

commit;

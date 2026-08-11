-- Live PostgreSQL correction: an unlocked row has locked_until = NULL.
-- SQL three-valued logic made NOT (NULL > now()) return NULL, which the BFF
-- correctly treated as fail-closed and therefore denied the first login.
begin;

create or replace function public.record_bff_login_failure(
    p_client_key text, p_max_attempts integer, p_window_seconds integer
) returns table(allowed boolean, retry_after_seconds integer)
language plpgsql security definer set search_path = '' as $$
declare v_row public.bff_login_lockouts%rowtype;
begin
    if p_client_key is null or p_client_key !~ '^[0-9a-f]{64}$'
       or p_max_attempts not between 1 and 100
       or p_window_seconds not between 1 and 86400 then
        raise exception 'invalid login lockout policy';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('bff-login:' || p_client_key, 0));
    select * into v_row from public.bff_login_lockouts value
     where value.client_key=p_client_key for update;
    if not found or v_row.window_started_at + make_interval(secs => p_window_seconds) <= now() then
        insert into public.bff_login_lockouts(client_key, failure_count, window_started_at, locked_until)
        values (p_client_key, 1, now(), null)
        on conflict (client_key) do update set failure_count=1, window_started_at=now(),
            locked_until=null, updated_at=now()
        returning * into v_row;
    elsif v_row.locked_until > now() then
        null;
    else
        update public.bff_login_lockouts value
           set failure_count=value.failure_count+1,
               locked_until=case when value.failure_count+1 >= p_max_attempts
                   then value.window_started_at + make_interval(secs => p_window_seconds) end,
               updated_at=now()
         where value.client_key=p_client_key returning * into v_row;
    end if;
    return query select
        not coalesce(v_row.locked_until > now(), false),
        case when v_row.locked_until > now()
             then greatest(1, ceil(extract(epoch from v_row.locked_until-now()))::integer) else 0 end;
end;
$$;

commit;

-- Slice 3A: disambiguate a legitimate storage-less analysis receipt from a
-- malformed response that omitted an owned result object path.

begin;

create or replace function public.persistent_delete_storage_required(
    p_resource_type text,
    p_resource_id uuid
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_required boolean;
begin
    if p_resource_type not in ('model', 'analysis') or p_resource_id is null then
        raise exception 'invalid persistent delete operation';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'persistent-delete:' || p_resource_type || ':' || p_resource_id::text,
            0
        )
    );

    select receipt.storage_path is not null
      into v_required
      from public.persistent_delete_receipts receipt
     where receipt.resource_type = p_resource_type
       and receipt.resource_id = p_resource_id;
    if not found then
        raise exception 'persistent delete receipt not found';
    end if;
    return v_required;
end;
$$;

revoke all on function public.persistent_delete_storage_required(text, uuid)
    from public, anon, authenticated;
grant execute on function public.persistent_delete_storage_required(text, uuid)
    to service_role;

commit;

-- Live PostgreSQL 17/Supabase advisor correction.
-- append_row_audit_log is a trigger implementation, not a callable RPC.
-- Trigger execution does not require callers to hold EXECUTE on the function.
begin;

revoke execute on function public.append_row_audit_log()
from public, anon, authenticated;

commit;

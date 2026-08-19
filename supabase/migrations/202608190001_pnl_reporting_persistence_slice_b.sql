-- P&L Reporting Slice B: immutable canonical datasets, active pointers and
-- recovery-safe ingestion coordination. Source workbook bytes remain in the
-- existing private pnl-models Storage bucket and never pass through SQL.

begin;

create table public.pnl_reporting_datasets (
    id uuid primary key,
    dataset_type text not null,
    reporting_year integer not null,
    template_version text not null,
    canonical_schema_version text not null,
    actual_through_month smallint,
    canonical_payload jsonb not null,
    source_bucket text not null,
    source_path text not null,
    source_sha256 text not null,
    original_filename text not null,
    uploaded_by_actor text not null,
    uploaded_at timestamptz not null default now(),
    parser_version text not null,
    validation_summary jsonb not null,
    superseded_at timestamptz,
    superseded_by_dataset_id uuid,
    constraint pnl_reporting_datasets_type_check
        check (dataset_type in ('PLAN', 'ACTUAL')),
    constraint pnl_reporting_datasets_year_check
        check (reporting_year between 2000 and 2200),
    constraint pnl_reporting_datasets_through_check check (
        (dataset_type = 'PLAN' and actual_through_month is null)
        or
        (dataset_type = 'ACTUAL'
            and actual_through_month is not null
            and actual_through_month between 1 and 12)
    ),
    constraint pnl_reporting_datasets_template_check
        check (template_version = 'PNL_REPORTING_V1'),
    constraint pnl_reporting_datasets_canonical_schema_check
        check (canonical_schema_version = 'PNL_REPORTING_CANONICAL_V1'),
    constraint pnl_reporting_datasets_parser_check
        check (parser_version = 'PNL_REPORTING_PARSER_V1'),
    constraint pnl_reporting_datasets_payload_shape_check check (
        pg_catalog.jsonb_typeof(canonical_payload) = 'object'
        and canonical_payload ? 'template_version'
        and canonical_payload ? 'dataset_type'
        and canonical_payload ? 'reporting_year'
        and canonical_payload ? 'actual_through_month'
        and canonical_payload ? 'sheets'
        and canonical_payload ->> 'template_version' = template_version
        and canonical_payload ->> 'dataset_type' = dataset_type
        and (canonical_payload ->> 'reporting_year')::integer = reporting_year
        and pg_catalog.jsonb_typeof(canonical_payload -> 'sheets') = 'object'
        and (
            (actual_through_month is null
                and canonical_payload -> 'actual_through_month' = 'null'::jsonb)
            or
            (actual_through_month is not null
                and pg_catalog.jsonb_typeof(
                    canonical_payload -> 'actual_through_month'
                ) = 'number'
                and (canonical_payload ->> 'actual_through_month')::integer
                    = actual_through_month)
        )
    ),
    constraint pnl_reporting_datasets_source_bucket_check
        check (source_bucket = 'pnl-models'),
    constraint pnl_reporting_datasets_source_path_check
        check (source_path = 'reporting/' || id::text || '/source.xlsx'),
    constraint pnl_reporting_datasets_source_sha_check
        check (source_sha256 ~ '^[0-9a-f]{64}$'),
    constraint pnl_reporting_datasets_filename_check check (
        pg_catalog.length(pg_catalog.btrim(original_filename)) between 1 and 255
        and original_filename = pg_catalog.btrim(original_filename)
        and original_filename !~ '[/\\]'
        and original_filename !~ '[[:cntrl:]]'
        and pg_catalog.lower(pg_catalog.right(original_filename, 5)) = '.xlsx'
    ),
    constraint pnl_reporting_datasets_actor_check
        check (pg_catalog.length(pg_catalog.btrim(uploaded_by_actor)) between 1 and 256),
    constraint pnl_reporting_datasets_validation_summary_check
        check (pg_catalog.jsonb_typeof(validation_summary) = 'object'),
    constraint pnl_reporting_datasets_superseded_shape_check check (
        (superseded_at is null and superseded_by_dataset_id is null)
        or
        (superseded_at is not null
            and superseded_by_dataset_id is not null
            and superseded_by_dataset_id <> id)
    ),
    unique (id, reporting_year, dataset_type)
);

alter table public.pnl_reporting_datasets
    add constraint pnl_reporting_datasets_superseded_dataset_fk
    foreign key (superseded_by_dataset_id, reporting_year, dataset_type)
    references public.pnl_reporting_datasets (id, reporting_year, dataset_type)
    on update restrict on delete restrict;

create index pnl_reporting_datasets_history_idx
    on public.pnl_reporting_datasets (reporting_year, dataset_type, uploaded_at desc);

create table public.pnl_reporting_active_datasets (
    reporting_year integer not null,
    dataset_type text not null,
    dataset_id uuid not null,
    activated_at timestamptz not null,
    activated_by_actor text not null,
    primary key (reporting_year, dataset_type),
    constraint pnl_reporting_active_datasets_type_check
        check (dataset_type in ('PLAN', 'ACTUAL')),
    constraint pnl_reporting_active_datasets_year_check
        check (reporting_year between 2000 and 2200),
    constraint pnl_reporting_active_datasets_actor_check
        check (pg_catalog.length(pg_catalog.btrim(activated_by_actor)) between 1 and 256),
    constraint pnl_reporting_active_dataset_identity_fk
        foreign key (dataset_id, reporting_year, dataset_type)
        references public.pnl_reporting_datasets (id, reporting_year, dataset_type)
        on update restrict on delete restrict
);

create table public.pnl_reporting_ingestion_requests (
    id uuid primary key default gen_random_uuid(),
    idempotency_actor text not null,
    idempotency_key text not null,
    request_fingerprint text not null,
    dataset_type text not null,
    reporting_year integer not null,
    actual_through_month smallint,
    template_version text not null,
    source_sha256 text not null,
    reserved_dataset_id uuid not null unique,
    source_path text not null,
    status text not null default 'RESERVED',
    lease_token uuid,
    lease_expires_at timestamptz,
    dataset_id uuid unique,
    response_payload jsonb,
    safe_failure_classification text,
    failure_detail jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    constraint pnl_reporting_ingestion_actor_check
        check (pg_catalog.length(pg_catalog.btrim(idempotency_actor)) between 1 and 256),
    constraint pnl_reporting_ingestion_key_check
        check (idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
    constraint pnl_reporting_ingestion_fingerprint_check
        check (request_fingerprint ~ '^[0-9a-f]{64}$'),
    constraint pnl_reporting_ingestion_type_check
        check (dataset_type in ('PLAN', 'ACTUAL')),
    constraint pnl_reporting_ingestion_year_check
        check (reporting_year between 2000 and 2200),
    constraint pnl_reporting_ingestion_through_check check (
        (dataset_type = 'PLAN' and actual_through_month is null)
        or
        (dataset_type = 'ACTUAL'
            and actual_through_month is not null
            and actual_through_month between 1 and 12)
    ),
    constraint pnl_reporting_ingestion_template_check
        check (template_version = 'PNL_REPORTING_V1'),
    constraint pnl_reporting_ingestion_source_sha_check
        check (source_sha256 ~ '^[0-9a-f]{64}$'),
    constraint pnl_reporting_ingestion_source_path_check
        check (source_path = 'reporting/' || reserved_dataset_id::text || '/source.xlsx'),
    constraint pnl_reporting_ingestion_status_check
        check (status in ('RESERVED', 'COMPLETED', 'FAILED', 'CLEANUP_REQUIRED')),
    constraint pnl_reporting_ingestion_failure_detail_check
        check (pg_catalog.jsonb_typeof(failure_detail) = 'object'),
    constraint pnl_reporting_ingestion_response_shape_check
        check (response_payload is null or pg_catalog.jsonb_typeof(response_payload) = 'object'),
    constraint pnl_reporting_ingestion_failure_classification_check check (
        safe_failure_classification is null
        or pg_catalog.length(safe_failure_classification) between 1 and 128
    ),
    constraint pnl_reporting_ingestion_state_shape_check check (
        (status = 'RESERVED'
            and lease_token is not null
            and lease_expires_at is not null
            and dataset_id is null
            and response_payload is null
            and completed_at is null)
        or
        (status = 'COMPLETED'
            and lease_token is null
            and lease_expires_at is null
            and dataset_id = reserved_dataset_id
            and response_payload is not null
            and completed_at is not null)
        or
        (status in ('FAILED', 'CLEANUP_REQUIRED')
            and lease_token is null
            and lease_expires_at is null
            and dataset_id is null
            and response_payload is null
            and completed_at is null)
    ),
    constraint pnl_reporting_ingestion_dataset_fk
        foreign key (dataset_id) references public.pnl_reporting_datasets (id)
        on update restrict on delete restrict,
    unique (idempotency_actor, idempotency_key)
);

create index pnl_reporting_ingestion_recovery_idx
    on public.pnl_reporting_ingestion_requests (status, updated_at)
    where status in ('RESERVED', 'CLEANUP_REQUIRED');

alter table public.pnl_reporting_datasets enable row level security;
alter table public.pnl_reporting_active_datasets enable row level security;
alter table public.pnl_reporting_ingestion_requests enable row level security;

revoke all on table public.pnl_reporting_datasets
    from public, anon, authenticated, service_role;
revoke all on table public.pnl_reporting_active_datasets
    from public, anon, authenticated, service_role;
revoke all on table public.pnl_reporting_ingestion_requests
    from public, anon, authenticated, service_role;

create or replace function public.guard_pnl_reporting_dataset_immutability()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if row(
        new.id, new.dataset_type, new.reporting_year, new.template_version,
        new.canonical_schema_version, new.actual_through_month,
        new.canonical_payload, new.source_bucket, new.source_path,
        new.source_sha256, new.original_filename, new.uploaded_by_actor,
        new.uploaded_at, new.parser_version, new.validation_summary
    ) is distinct from row(
        old.id, old.dataset_type, old.reporting_year, old.template_version,
        old.canonical_schema_version, old.actual_through_month,
        old.canonical_payload, old.source_bucket, old.source_path,
        old.source_sha256, old.original_filename, old.uploaded_by_actor,
        old.uploaded_at, old.parser_version, old.validation_summary
    ) then
        raise exception 'pnl reporting dataset is immutable';
    end if;
    if old.superseded_at is not null and row(
        new.superseded_at, new.superseded_by_dataset_id
    ) is distinct from row(
        old.superseded_at, old.superseded_by_dataset_id
    ) then
        raise exception 'pnl reporting supersession is immutable';
    end if;
    return new;
end;
$$;

create or replace function public.prevent_pnl_reporting_dataset_delete()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    raise exception 'pnl reporting datasets cannot be deleted in V1';
end;
$$;

create or replace function public.guard_pnl_reporting_ingestion_identity()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if row(
        new.id, new.idempotency_actor, new.idempotency_key,
        new.request_fingerprint, new.dataset_type, new.reporting_year,
        new.actual_through_month, new.template_version, new.source_sha256,
        new.reserved_dataset_id, new.source_path, new.created_at
    ) is distinct from row(
        old.id, old.idempotency_actor, old.idempotency_key,
        old.request_fingerprint, old.dataset_type, old.reporting_year,
        old.actual_through_month, old.template_version, old.source_sha256,
        old.reserved_dataset_id, old.source_path, old.created_at
    ) then
        raise exception 'pnl reporting ingestion identity is immutable';
    end if;
    if old.status = 'COMPLETED' then
        raise exception 'terminal pnl reporting ingestion cannot be changed';
    end if;
    if old.status = 'CLEANUP_REQUIRED'
       and not (
            new.status = 'FAILED'
            and new.safe_failure_classification = 'ADMIN_CLEANUP_CONFIRMED'
       ) then
        raise exception 'cleanup-required pnl reporting ingestion needs confirmation';
    end if;
    if old.status = 'FAILED' and new.status <> 'RESERVED' then
        raise exception 'failed pnl reporting ingestion can only be retried';
    end if;
    new.updated_at := pg_catalog.now();
    return new;
end;
$$;

create trigger pnl_reporting_datasets_guard_immutable
before update on public.pnl_reporting_datasets
for each row execute function public.guard_pnl_reporting_dataset_immutability();

create trigger pnl_reporting_datasets_prevent_delete
before delete on public.pnl_reporting_datasets
for each row execute function public.prevent_pnl_reporting_dataset_delete();

create trigger pnl_reporting_ingestion_guard_identity
before update on public.pnl_reporting_ingestion_requests
for each row execute function public.guard_pnl_reporting_ingestion_identity();

create trigger pnl_reporting_datasets_audit
after insert or update or delete on public.pnl_reporting_datasets
for each row execute function public.append_row_audit_log();

create trigger pnl_reporting_active_datasets_audit
after insert or update or delete on public.pnl_reporting_active_datasets
for each row execute function public.append_row_audit_log();

create trigger pnl_reporting_ingestion_audit
after insert or update or delete on public.pnl_reporting_ingestion_requests
for each row execute function public.append_row_audit_log();

create or replace function public.reserve_pnl_reporting_ingestion(
    p_idempotency_actor text,
    p_idempotency_key text,
    p_request_fingerprint text,
    p_dataset_type text,
    p_reporting_year integer,
    p_actual_through_month integer,
    p_template_version text,
    p_source_sha256 text
) returns table (
    ingestion_id uuid,
    dataset_id uuid,
    ingestion_status text,
    lease_token uuid,
    idempotency_replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_existing public.pnl_reporting_ingestion_requests%rowtype;
    v_ingestion_id uuid := gen_random_uuid();
    v_dataset_id uuid := gen_random_uuid();
    v_lease uuid := gen_random_uuid();
begin
    if p_idempotency_actor is null
       or pg_catalog.length(pg_catalog.btrim(p_idempotency_actor)) not between 1 and 256
       or p_idempotency_key is null
       or p_idempotency_key !~ '^[A-Za-z0-9._:-]{1,128}$'
       or p_request_fingerprint is null
       or p_request_fingerprint !~ '^[0-9a-f]{64}$'
       or p_dataset_type is null
       or p_dataset_type not in ('PLAN', 'ACTUAL')
       or p_reporting_year is null
       or p_reporting_year not between 2000 and 2200
       or not (
            (p_dataset_type = 'PLAN' and p_actual_through_month is null)
            or
            (p_dataset_type = 'ACTUAL'
                and p_actual_through_month is not null
                and p_actual_through_month between 1 and 12)
       )
       or p_template_version is distinct from 'PNL_REPORTING_V1'
       or p_source_sha256 is null
       or p_source_sha256 !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid pnl reporting ingestion request';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            p_idempotency_actor || pg_catalog.chr(31) || p_idempotency_key,
            0
        )
    );

    select * into v_existing
      from public.pnl_reporting_ingestion_requests request_row
     where request_row.idempotency_actor = p_idempotency_actor
       and request_row.idempotency_key = p_idempotency_key
     for update;

    if found then
        if v_existing.request_fingerprint <> p_request_fingerprint
           or v_existing.dataset_type <> p_dataset_type
           or v_existing.reporting_year <> p_reporting_year
           or v_existing.actual_through_month is distinct from p_actual_through_month
           or v_existing.template_version <> p_template_version
           or v_existing.source_sha256 <> p_source_sha256 then
            raise exception 'IDEMPOTENCY_CONFLICT';
        end if;
        if v_existing.status = 'COMPLETED' then
            return query select v_existing.id, v_existing.reserved_dataset_id,
                'COMPLETED'::text, null::uuid, true;
            return;
        end if;
        if v_existing.status = 'CLEANUP_REQUIRED' then
            return query select v_existing.id, v_existing.reserved_dataset_id,
                'CLEANUP_REQUIRED'::text, null::uuid, true;
            return;
        end if;
        if v_existing.status = 'RESERVED' then
            if v_existing.lease_expires_at <= pg_catalog.now() then
                update public.pnl_reporting_ingestion_requests request_row
                   set status = 'CLEANUP_REQUIRED',
                       lease_token = null,
                       lease_expires_at = null,
                       safe_failure_classification = 'LEASE_EXPIRED_SOURCE_STATE_UNKNOWN',
                       failure_detail = '{}'::jsonb
                 where request_row.id = v_existing.id;
                return query select v_existing.id, v_existing.reserved_dataset_id,
                    'CLEANUP_REQUIRED'::text, null::uuid, true;
            else
                return query select v_existing.id, v_existing.reserved_dataset_id,
                    'IN_PROGRESS'::text, null::uuid, true;
            end if;
            return;
        end if;
        update public.pnl_reporting_ingestion_requests request_row
           set status = 'RESERVED',
               lease_token = v_lease,
               lease_expires_at = pg_catalog.now() + interval '30 minutes',
               safe_failure_classification = null,
               failure_detail = '{}'::jsonb
         where request_row.id = v_existing.id;
        return query select v_existing.id, v_existing.reserved_dataset_id,
            'RESERVED'::text, v_lease, true;
        return;
    end if;

    insert into public.pnl_reporting_ingestion_requests (
        id, idempotency_actor, idempotency_key, request_fingerprint,
        dataset_type, reporting_year, actual_through_month, template_version,
        source_sha256, reserved_dataset_id, source_path, status,
        lease_token, lease_expires_at
    ) values (
        v_ingestion_id, p_idempotency_actor, p_idempotency_key,
        p_request_fingerprint, p_dataset_type, p_reporting_year,
        p_actual_through_month, p_template_version, p_source_sha256,
        v_dataset_id, 'reporting/' || v_dataset_id::text || '/source.xlsx',
        'RESERVED', v_lease, pg_catalog.now() + interval '30 minutes'
    );
    return query select v_ingestion_id, v_dataset_id, 'RESERVED'::text,
        v_lease, false;
end;
$$;

create or replace function public.heartbeat_pnl_reporting_ingestion(
    p_ingestion_id uuid,
    p_lease_token uuid
) returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.pnl_reporting_ingestion_requests request_row
       set lease_expires_at = pg_catalog.now() + interval '30 minutes'
     where request_row.id = p_ingestion_id
       and request_row.status = 'RESERVED'
       and request_row.lease_token is not distinct from p_lease_token
       and request_row.lease_expires_at > pg_catalog.now();
    if not found then
        raise exception 'pnl reporting ingestion claim is invalid';
    end if;
end;
$$;

create or replace function public.finalize_pnl_reporting_ingestion(
    p_ingestion_id uuid,
    p_lease_token uuid,
    p_canonical_schema_version text,
    p_parser_version text,
    p_canonical_payload jsonb,
    p_original_filename text,
    p_validation_summary jsonb
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_request public.pnl_reporting_ingestion_requests%rowtype;
    v_dataset public.pnl_reporting_datasets%rowtype;
    v_previous_dataset_id uuid;
    v_response jsonb;
    v_activated_at timestamptz;
begin
    select * into v_request
      from public.pnl_reporting_ingestion_requests request_row
     where request_row.id = p_ingestion_id
     for update;
    if not found
       or v_request.status <> 'RESERVED'
       or v_request.lease_token is distinct from p_lease_token
       or v_request.lease_expires_at <= pg_catalog.now() then
        raise exception 'pnl reporting ingestion claim is invalid';
    end if;
    if p_canonical_schema_version is distinct from 'PNL_REPORTING_CANONICAL_V1'
       or p_parser_version is distinct from 'PNL_REPORTING_PARSER_V1'
       or coalesce(pg_catalog.jsonb_typeof(p_canonical_payload), '') <> 'object'
       or coalesce(pg_catalog.jsonb_typeof(p_validation_summary), '') <> 'object'
       or p_original_filename is null
       or pg_catalog.length(pg_catalog.btrim(p_original_filename)) not between 1 and 255
       or p_original_filename <> pg_catalog.btrim(p_original_filename)
       or p_original_filename ~ '[/\\]'
       or p_original_filename ~ '[[:cntrl:]]'
       or pg_catalog.lower(pg_catalog.right(p_original_filename, 5)) <> '.xlsx'
       or not (p_canonical_payload ? 'template_version')
       or not (p_canonical_payload ? 'dataset_type')
       or not (p_canonical_payload ? 'reporting_year')
       or not (p_canonical_payload ? 'actual_through_month')
       or p_canonical_payload ->> 'template_version'
            is distinct from v_request.template_version
       or p_canonical_payload ->> 'dataset_type'
            is distinct from v_request.dataset_type
       or coalesce(pg_catalog.jsonb_typeof(
            p_canonical_payload -> 'reporting_year'
       ), '') <> 'number'
       or (p_canonical_payload ->> 'reporting_year')::integer
            is distinct from v_request.reporting_year
       or (
            v_request.actual_through_month is null
            and p_canonical_payload -> 'actual_through_month'
                is distinct from 'null'::jsonb
       )
       or (
            v_request.actual_through_month is not null
            and (
                coalesce(pg_catalog.jsonb_typeof(
                    p_canonical_payload -> 'actual_through_month'
                ), '') <> 'number'
                or (p_canonical_payload ->> 'actual_through_month')::integer
                    is distinct from v_request.actual_through_month
            )
       ) then
        raise exception 'invalid pnl reporting finalization payload';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'pnl-reporting:' || v_request.reporting_year::text || ':'
                || v_request.dataset_type,
            0
        )
    );
    -- clock_timestamp is sampled after the year/type lock. Unlike now(), it
    -- preserves the real serialized activation order across concurrent RPCs.
    v_activated_at := pg_catalog.clock_timestamp();

    select active_row.dataset_id into v_previous_dataset_id
      from public.pnl_reporting_active_datasets active_row
     where active_row.reporting_year = v_request.reporting_year
       and active_row.dataset_type = v_request.dataset_type
     for update;

    insert into public.pnl_reporting_datasets (
        id, dataset_type, reporting_year, template_version,
        canonical_schema_version, actual_through_month, canonical_payload,
        source_bucket, source_path, source_sha256, original_filename,
        uploaded_by_actor, uploaded_at, parser_version, validation_summary
    ) values (
        v_request.reserved_dataset_id, v_request.dataset_type,
        v_request.reporting_year, v_request.template_version,
        p_canonical_schema_version, v_request.actual_through_month,
        p_canonical_payload, 'pnl-models', v_request.source_path,
        v_request.source_sha256, p_original_filename,
        v_request.idempotency_actor, v_activated_at, p_parser_version,
        p_validation_summary
    ) returning * into v_dataset;

    insert into public.pnl_reporting_active_datasets (
        reporting_year, dataset_type, dataset_id, activated_at,
        activated_by_actor
    ) values (
        v_request.reporting_year, v_request.dataset_type, v_dataset.id,
        v_dataset.uploaded_at, v_request.idempotency_actor
    )
    on conflict (reporting_year, dataset_type) do update
       set dataset_id = excluded.dataset_id,
           activated_at = excluded.activated_at,
           activated_by_actor = excluded.activated_by_actor;

    if v_previous_dataset_id is not null then
        update public.pnl_reporting_datasets dataset_row
           set superseded_at = v_dataset.uploaded_at,
               superseded_by_dataset_id = v_dataset.id
         where dataset_row.id = v_previous_dataset_id
           and dataset_row.reporting_year = v_request.reporting_year
           and dataset_row.dataset_type = v_request.dataset_type
           and dataset_row.superseded_at is null
           and dataset_row.superseded_by_dataset_id is null;
        if not found then
            raise exception 'pnl reporting supersession chain is inconsistent';
        end if;
    end if;

    v_response := pg_catalog.jsonb_build_object(
        'datasetId', v_dataset.id,
        'datasetType', v_dataset.dataset_type,
        'reportingYear', v_dataset.reporting_year,
        'actualThroughMonth', v_dataset.actual_through_month,
        'templateVersion', v_dataset.template_version,
        'sourceSha256', v_dataset.source_sha256,
        'uploadedAt', v_dataset.uploaded_at,
        'warnings', coalesce(p_validation_summary -> 'warnings', '[]'::jsonb),
        'supersededDatasetId', v_previous_dataset_id,
        'replayed', false
    );

    update public.pnl_reporting_ingestion_requests request_row
       set status = 'COMPLETED',
           lease_token = null,
           lease_expires_at = null,
           dataset_id = v_dataset.id,
           response_payload = v_response,
           safe_failure_classification = null,
           failure_detail = '{}'::jsonb,
           completed_at = pg_catalog.clock_timestamp()
     where request_row.id = v_request.id;

    return v_response;
end;
$$;

create or replace function public.get_completed_pnl_reporting_ingestion(
    p_ingestion_id uuid
) returns jsonb
language sql
security definer
set search_path = ''
as $$
    select request_row.response_payload
      from public.pnl_reporting_ingestion_requests request_row
      join public.pnl_reporting_datasets dataset_row
        on dataset_row.id = request_row.dataset_id
       and dataset_row.id = request_row.reserved_dataset_id
       and dataset_row.dataset_type = request_row.dataset_type
       and dataset_row.reporting_year = request_row.reporting_year
       and dataset_row.source_sha256 = request_row.source_sha256
       and dataset_row.source_path = request_row.source_path
     where request_row.id = p_ingestion_id
       and request_row.status = 'COMPLETED';
$$;

create or replace function public.record_pnl_reporting_ingestion_failure(
    p_ingestion_id uuid,
    p_lease_token uuid,
    p_cleanup_succeeded boolean,
    p_safe_failure_classification text,
    p_failure_detail jsonb default '{}'::jsonb
) returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.pnl_reporting_ingestion_requests request_row
       set status = case when p_cleanup_succeeded then 'FAILED' else 'CLEANUP_REQUIRED' end,
           lease_token = null,
           lease_expires_at = null,
           safe_failure_classification = pg_catalog.left(
               coalesce(
                   nullif(pg_catalog.btrim(p_safe_failure_classification), ''),
                   'INGESTION_FAILED'
               ),
               128
           ),
           failure_detail = case
               when pg_catalog.jsonb_typeof(coalesce(p_failure_detail, '{}'::jsonb)) = 'object'
               then coalesce(p_failure_detail, '{}'::jsonb)
               else '{}'::jsonb
           end
     where request_row.id = p_ingestion_id
       and request_row.status = 'RESERVED'
       and request_row.lease_token is not distinct from p_lease_token;
    if not found then
        raise exception 'pnl reporting ingestion claim is invalid';
    end if;
end;
$$;

create or replace function public.get_pnl_reporting_ingestion_recovery_queue()
returns table (
    ingestion_id uuid,
    dataset_id uuid,
    ingestion_status text,
    source_path text,
    source_sha256 text,
    safe_failure_classification text,
    failure_detail jsonb,
    created_at timestamptz,
    updated_at timestamptz
)
language sql
security definer
set search_path = ''
as $$
    select request_row.id, request_row.reserved_dataset_id,
           request_row.status, request_row.source_path,
           request_row.source_sha256, request_row.safe_failure_classification,
           request_row.failure_detail, request_row.created_at,
           request_row.updated_at
      from public.pnl_reporting_ingestion_requests request_row
     where request_row.status = 'CLEANUP_REQUIRED'
        or (
            request_row.status = 'RESERVED'
            and request_row.lease_expires_at <= pg_catalog.now()
        )
     order by request_row.created_at;
$$;

create or replace function public.acknowledge_pnl_reporting_ingestion_cleanup(
    p_ingestion_id uuid,
    p_storage_cleanup_confirmed boolean
) returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    if not coalesce(p_storage_cleanup_confirmed, false) then
        raise exception 'storage cleanup confirmation is required';
    end if;
    update public.pnl_reporting_ingestion_requests request_row
       set status = 'FAILED',
           lease_token = null,
           lease_expires_at = null,
           safe_failure_classification = 'ADMIN_CLEANUP_CONFIRMED',
           failure_detail = request_row.failure_detail
               || pg_catalog.jsonb_build_object('cleanup_confirmed_at', pg_catalog.now())
     where request_row.id = p_ingestion_id
       and (
            request_row.status = 'CLEANUP_REQUIRED'
            or (
                request_row.status = 'RESERVED'
                and request_row.lease_expires_at <= pg_catalog.now()
            )
       );
    if not found then
        raise exception 'pnl reporting recovery item is not eligible';
    end if;
end;
$$;

revoke all on function public.guard_pnl_reporting_dataset_immutability()
    from public, anon, authenticated, service_role;
revoke all on function public.prevent_pnl_reporting_dataset_delete()
    from public, anon, authenticated, service_role;
revoke all on function public.guard_pnl_reporting_ingestion_identity()
    from public, anon, authenticated, service_role;
revoke all on function public.reserve_pnl_reporting_ingestion(
    text, text, text, text, integer, integer, text, text
) from public, anon, authenticated, service_role;
revoke all on function public.heartbeat_pnl_reporting_ingestion(uuid, uuid)
    from public, anon, authenticated, service_role;
revoke all on function public.finalize_pnl_reporting_ingestion(
    uuid, uuid, text, text, jsonb, text, jsonb
) from public, anon, authenticated, service_role;
revoke all on function public.get_completed_pnl_reporting_ingestion(uuid)
    from public, anon, authenticated, service_role;
revoke all on function public.record_pnl_reporting_ingestion_failure(
    uuid, uuid, boolean, text, jsonb
) from public, anon, authenticated, service_role;
revoke all on function public.get_pnl_reporting_ingestion_recovery_queue()
    from public, anon, authenticated, service_role;
revoke all on function public.acknowledge_pnl_reporting_ingestion_cleanup(uuid, boolean)
    from public, anon, authenticated, service_role;

grant execute on function public.reserve_pnl_reporting_ingestion(
    text, text, text, text, integer, integer, text, text
) to service_role;
grant execute on function public.heartbeat_pnl_reporting_ingestion(uuid, uuid)
    to service_role;
grant execute on function public.finalize_pnl_reporting_ingestion(
    uuid, uuid, text, text, jsonb, text, jsonb
) to service_role;
grant execute on function public.get_completed_pnl_reporting_ingestion(uuid)
    to service_role;
grant execute on function public.record_pnl_reporting_ingestion_failure(
    uuid, uuid, boolean, text, jsonb
) to service_role;
grant execute on function public.get_pnl_reporting_ingestion_recovery_queue()
    to service_role;
grant execute on function public.acknowledge_pnl_reporting_ingestion_cleanup(uuid, boolean)
    to service_role;

commit;

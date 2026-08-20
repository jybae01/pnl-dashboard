begin;

-- Keep the original finalization RPC intact for existing callers. The v1.1
-- variant derives its narrowly scoped tariff provenance from the immutable
-- reserved request, calls the original finalizer, and updates the inserted
-- Model inside the same transaction.
create function public.finalize_forecast_generation_v11(
    p_generation_id uuid, p_lease_token uuid, p_generated_workbook_sha256 text,
    p_name text, p_model_year integer, p_version text, p_file_name text,
    p_period_types jsonb, p_mapping_version text, p_mapping_hash text,
    p_engine_version text
) returns public.models
language plpgsql security definer set search_path = '' as $$
declare
    v_request public.forecast_generation_requests%rowtype;
    v_model public.models%rowtype;
    v_regional_sales_monthly jsonb;
    v_month_count integer;
    v_distinct_month_count integer;
begin
    select * into v_request
      from public.forecast_generation_requests request_row
     where request_row.id = p_generation_id;

    if not found
       or jsonb_typeof(v_request.request_payload #> '{request,months}') is distinct from 'array'
       or coalesce(jsonb_array_length(v_request.request_payload #> '{request,months}'), 0) = 0 then
        raise exception 'forecast generation tariff metadata is invalid';
    end if;

    if exists (
        select 1
          from jsonb_array_elements(
              v_request.request_payload #> '{request,months}'
          ) with ordinality as month_item(value, ordinal)
         where jsonb_typeof(month_item.value) is distinct from 'object'
            or jsonb_typeof(month_item.value -> 'month') is distinct from 'number'
            or jsonb_typeof(month_item.value -> 'na_sa_sales') is distinct from 'number'
            or case
                when jsonb_typeof(month_item.value -> 'month') = 'number'
                then (month_item.value ->> 'month')::numeric <> trunc((month_item.value ->> 'month')::numeric)
                  or (month_item.value ->> 'month')::integer not between 1 and 12
                  or (month_item.value ->> 'month')::integer
                     <> (v_request.request_payload #>> '{request,start_month}')::integer
                        + month_item.ordinal::integer - 1
                else true
               end
            or case
                when jsonb_typeof(month_item.value -> 'na_sa_sales') = 'number'
                then (month_item.value ->> 'na_sa_sales')::numeric < 0
                else true
               end
    ) then
        raise exception 'forecast generation tariff metadata is invalid';
    end if;

    select count(*), count(distinct month_item.value ->> 'month')
      into v_month_count, v_distinct_month_count
      from jsonb_array_elements(
          v_request.request_payload #> '{request,months}'
      ) as month_item(value);

    if v_month_count <> v_distinct_month_count
       or v_month_count <> jsonb_array_length(
           v_request.request_payload #> '{request,months}'
       ) then
        raise exception 'forecast generation tariff metadata is invalid';
    end if;

    select jsonb_object_agg(
               (month_item.value ->> 'month')::integer::text,
               to_jsonb((month_item.value ->> 'na_sa_sales')::numeric)
               order by month_item.ordinal
           )
      into v_regional_sales_monthly
      from jsonb_array_elements(
          v_request.request_payload #> '{request,months}'
      ) with ordinality as month_item(value, ordinal);

    select * into v_model
      from public.finalize_forecast_generation(
        p_generation_id,
        p_lease_token,
        p_generated_workbook_sha256,
        p_name,
        p_model_year,
        p_version,
        p_file_name,
        p_period_types,
        p_mapping_version,
        p_mapping_hash,
        p_engine_version
    );

    update public.models model_row
       set regional_sales_monthly = v_regional_sales_monthly,
           tariff_applicable_rate = 0.85,
           tariff_rate = 0.10,
           tariff_adjustment_monthly = '{}'::jsonb,
           tariff_in_workbook = true
     where model_row.id = v_model.id
       and model_row.forecast_generation_id = p_generation_id
       and model_row.source_kind = 'forecast_generated'
    returning * into v_model;

    if not found then
        raise exception 'forecast generation tariff metadata persistence failed';
    end if;

    return v_model;
end;
$$;

revoke all on function public.finalize_forecast_generation_v11(
    uuid, uuid, text, text, integer, text, text, jsonb, text, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.finalize_forecast_generation_v11(
    uuid, uuid, text, text, integer, text, text, jsonb, text, text, text
) to service_role;

commit;

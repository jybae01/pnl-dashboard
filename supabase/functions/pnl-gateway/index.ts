import { createClient, User } from "@supabase/supabase-js";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const ENGINE_VERSION = Deno.env.get("ENGINE_VERSION") ?? "phase1-unconfigured";
const RESULT_SCHEMA_VERSION = Deno.env.get("RESULT_SCHEMA_VERSION") ?? "1";
const STORAGE_BUCKET = "pnl-models";
const MAPPING_CONFIG_KEY = "model_mapping";
const UUID_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const JOB_ROUTE = new RegExp(`/jobs/(${UUID_PATTERN})(?:/(uploaded))?$`);

const service = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

function corsHeaders(request: Request): Record<string, string> {
  const allowed = (Deno.env.get("ALLOWED_ORIGINS") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const origin = request.headers.get("origin") ?? "";
  return {
    "access-control-allow-origin": allowed.includes(origin) ? origin : allowed[0] ?? "null",
    "access-control-allow-headers": "authorization, content-type, x-request-id",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "vary": "Origin",
  };
}

function json(request: Request, status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(request), "content-type": "application/json; charset=utf-8" },
  });
}

async function authenticatedUser(request: Request): Promise<User | null> {
  const authorization = request.headers.get("authorization") ?? "";
  if (!authorization.toLowerCase().startsWith("bearer ")) return null;
  const client = createClient(SUPABASE_URL, ANON_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
    global: { headers: { Authorization: authorization } },
  });
  const { data, error } = await client.auth.getUser();
  return error ? null : data.user;
}

function isAdmin(user: User): boolean {
  const role = user.app_metadata?.role;
  const roles = user.app_metadata?.roles;
  return role === "admin" || (Array.isArray(roles) && roles.includes("admin"));
}

async function readJson(request: Request): Promise<Record<string, unknown>> {
  try {
    return await request.json();
  } catch {
    throw new Error("invalid_json");
  }
}

function requiredText(body: Record<string, unknown>, key: string): string {
  const value = typeof body[key] === "string" ? body[key].trim() : "";
  if (!value) throw new Error(`missing_${key}`);
  return value;
}

async function publishedMapping() {
  const { data, error } = await service
    .from("app_config")
    .select("version,content_hash")
    .eq("config_key", MAPPING_CONFIG_KEY)
    .eq("status", "published")
    .order("is_default", { ascending: false })
    .order("published_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  if (!data) throw new Error("published_mapping_not_found");
  return data;
}

async function initializeUpload(request: Request, user: User): Promise<Response> {
  const body = await readJson(request);
  const name = requiredText(body, "name");
  const modelType = requiredText(body, "modelType");
  const fileName = requiredText(body, "fileName");
  const version = typeof body.version === "string" && body.version.trim() ? body.version.trim() : "V1";
  const modelYear = Number(body.modelYear);
  if (!fileName.toLowerCase().endsWith(".xlsx")) return json(request, 400, { error: "xlsx_required" });
  if (!Number.isInteger(modelYear) || modelYear < 2000 || modelYear > 2200) {
    return json(request, 400, { error: "invalid_model_year" });
  }
  const baselineModelId = typeof body.baselineModelId === "string"
    ? body.baselineModelId.trim().toLowerCase()
    : "";
  if (baselineModelId && !(new RegExp(`^${UUID_PATTERN}$`, "i")).test(baselineModelId)) {
    return json(request, 400, { error: "invalid_baseline_model_id" });
  }
  const rawMonths = body.months === undefined ? [] : body.months;
  if (!Array.isArray(rawMonths)) return json(request, 400, { error: "invalid_months" });
  const months = rawMonths.map(Number).sort((left, right) => left - right);
  if (
    months.some((month) => !Number.isInteger(month) || month < 1 || month > 12) ||
    new Set(months).size !== months.length ||
    months.some((month, index) => index > 0 && month !== months[index - 1] + 1)
  ) {
    return json(request, 400, { error: "invalid_months" });
  }
  const baselineSalesFx = Number(body.baselineSalesFx ?? 1480);
  const comparisonSalesFx = Number(body.comparisonSalesFx ?? 1480);
  if (!(baselineSalesFx > 0) || !(comparisonSalesFx > 0)) {
    return json(request, 400, { error: "invalid_sales_fx" });
  }
  const publish = Boolean(body.publish);
  const makeDefault = Boolean(body.makeDefault);
  if (makeDefault && !publish) {
    return json(request, 400, { error: "default_requires_publication" });
  }

  if (baselineModelId) {
    const { data: baseline, error: baselineError } = await service
      .from("models")
      .select("id,model_year,is_published")
      .eq("id", baselineModelId)
      .maybeSingle();
    if (baselineError) throw baselineError;
    if (!baseline?.is_published) return json(request, 409, { error: "published_baseline_not_found" });
    if (baseline.model_year !== modelYear) {
      return json(request, 409, { error: "baseline_year_mismatch" });
    }
  }

  const mapping = await publishedMapping();
  const modelId = crypto.randomUUID();
  const jobId = crypto.randomUUID();
  const storagePath = `models/${modelId}/source.xlsx`;

  // The signed token is created first but returned only after the DB RPC has
  // atomically created both rows. Failed DB initialization therefore exposes
  // neither a usable path nor a token to the caller.
  const { data: signed, error: signError } = await service.storage
    .from(STORAGE_BUCKET)
    .createSignedUploadUrl(storagePath, { upsert: false });
  if (signError || !signed) throw signError ?? new Error("signed_upload_failed");

  const { data: job, error: initializeError } = await service.rpc("initialize_calculation_upload", {
    p_model_id: modelId,
    p_job_id: jobId,
    p_name: name,
    p_model_type: modelType,
    p_model_year: modelYear,
    p_created_date: typeof body.createdDate === "string" ? body.createdDate : new Date().toISOString().slice(0, 10),
    p_version: version,
    p_file_name: fileName,
    p_storage_bucket: STORAGE_BUCKET,
    p_storage_path: storagePath,
    p_engine_version: ENGINE_VERSION,
    p_mapping_version: mapping.version,
    p_mapping_hash: mapping.content_hash,
    p_result_schema_version: RESULT_SCHEMA_VERSION,
    p_created_by: user.id,
    p_max_attempts: 3,
    p_analysis_request: {
      ...(baselineModelId ? { baseline_model_id: baselineModelId } : {}),
      months,
      baseline_sales_fx: baselineSalesFx,
      comparison_sales_fx: comparisonSalesFx,
      publish,
      make_default: makeDefault,
    },
  });
  if (initializeError) throw initializeError;

  return json(request, 201, {
    modelId,
    jobId,
    status: Array.isArray(job) ? job[0]?.status : job?.status ?? "pending",
    bucket: STORAGE_BUCKET,
    path: storagePath,
    signedUrl: signed.signedUrl,
    token: signed.token,
    provenance: {
      engineVersion: ENGINE_VERSION,
      mappingVersion: mapping.version,
      mappingHash: mapping.content_hash,
      resultSchemaVersion: RESULT_SCHEMA_VERSION,
    },
    analysisRequest: {
      baselineModelId: baselineModelId || null,
      months,
      baselineSalesFx,
      comparisonSalesFx,
      publish,
      makeDefault,
    },
  });
}

async function jobStatus(request: Request, user: User, jobId: string): Promise<Response> {
  const { data, error } = await service
    .from("calculation_jobs")
    .select("id,model_id,status,upload_completed_at,attempt,max_attempts,heartbeat_at,error_code,error_message,created_by,created_at,updated_at,completed_at")
    .eq("id", jobId)
    .maybeSingle();
  if (error) throw error;
  if (!data) return json(request, 404, { error: "job_not_found" });
  if (!isAdmin(user) && data.created_by !== user.id) return json(request, 403, { error: "forbidden" });
  const { created_by: _owner, ...visible } = data;
  return json(request, 200, visible);
}

async function markUploadCompleted(request: Request, user: User, jobId: string): Promise<Response> {
  const { data: job, error: jobError } = await service
    .from("calculation_jobs")
    .select("id,model_id,status,storage_bucket,storage_path,created_by")
    .eq("id", jobId)
    .maybeSingle();
  if (jobError) throw jobError;
  if (!job) return json(request, 404, { error: "job_not_found" });
  if (!isAdmin(user) && job.created_by !== user.id) return json(request, 403, { error: "forbidden" });
  const prefix = `models/${job.model_id}`;
  const { data: objects, error: listError } = await service.storage
    .from(job.storage_bucket)
    .list(prefix, { search: "source.xlsx", limit: 2 });
  if (listError) throw listError;
  if (!objects?.some((object) => `${prefix}/${object.name}` === job.storage_path)) {
    return json(request, 409, { error: "source_upload_not_found" });
  }
  const { data, error } = await service.rpc("mark_calculation_upload_completed", {
    p_job_id: jobId,
    p_created_by: job.created_by,
  });
  if (error) throw error;
  const updated = Array.isArray(data) ? data[0] : data;
  return json(request, 200, {
    status: updated?.status,
    uploadCompleted: true,
    queueMessageId: updated?.queue_message_id,
  });
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(request) });
  try {
    const path = new URL(request.url).pathname;
    if (request.method === "POST" && path.endsWith("/uploads/init")) {
      const user = await authenticatedUser(request);
      if (!user) return json(request, 401, { error: "unauthorized" });
      if (!isAdmin(user)) return json(request, 403, { error: "admin_required" });
      return await initializeUpload(request, user);
    }
    const match = path.match(JOB_ROUTE);
    if (match && request.method === "GET" && !match[2]) {
      const user = await authenticatedUser(request);
      if (!user) return json(request, 401, { error: "unauthorized" });
      return await jobStatus(request, user, match[1]);
    }
    if (match && request.method === "POST" && match[2] === "uploaded") {
      const user = await authenticatedUser(request);
      if (!user) return json(request, 401, { error: "unauthorized" });
      return await markUploadCompleted(request, user, match[1]);
    }
    return json(request, 404, { error: "not_found" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "gateway_error";
    const status = message === "published_mapping_not_found" ? 409 : 400;
    return json(request, status, { error: message });
  }
});

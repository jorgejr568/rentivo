import createClient, { defaultBodySerializer } from "openapi-fetch";

import type { paths } from "./schema";

export interface ApiResult<T> {
  data: T;
  requestId: string;
  response: Response;
}

interface ProblemDetails {
  code?: string;
  detail?: string;
  fields?: Record<string, string>;
  request_id?: string;
  status?: number;
}

interface UnauthorizedEvent {
  code: string;
  schemaPath: string;
}

type ApiFetchResult =
  | { data: unknown; error?: never; response: Response }
  | { data?: never; error: unknown; response: Response };
type ApiResponseData<TPending> = Extract<Awaited<TPending>, { data: unknown }>["data"];
type UnauthorizedHandler = ((event: UnauthorizedEvent) => void) | null;

const PUBLIC_AUTH_PATHS = new Set([
  "/api/v1/auth/config",
  "/api/v1/auth/google/callback",
  "/api/v1/auth/google/start",
  "/api/v1/auth/login",
  "/api/v1/auth/mfa/passkeys/begin",
  "/api/v1/auth/mfa/passkeys/complete",
  "/api/v1/auth/mfa/recovery/verify",
  "/api/v1/auth/mfa/totp/verify",
  "/api/v1/auth/password/forgot",
  "/api/v1/auth/password/reset",
  "/api/v1/auth/signup"
]);
const SESSION_INVALID_CODES = new Set(["authentication_required", "invalid_credentials"]);

let csrfToken = "";
let unauthorizedHandler: UnauthorizedHandler = null;

export class ApiError extends Error {
  readonly code: string;
  readonly fields: Record<string, string>;
  readonly requestId: string;
  readonly response: Response;
  readonly status: number;

  constructor(response: Response, problem?: ProblemDetails) {
    super(problem?.detail ?? "Não foi possível concluir a solicitação. Tente novamente.");
    this.name = "ApiError";
    this.code = problem?.code ?? "request_failed";
    this.fields = problem?.fields ?? {};
    this.requestId = problem?.request_id ?? response.headers.get("X-Request-ID") ?? "";
    this.response = response;
    this.status = problem?.status ?? response.status;
  }
}

export function setCsrfToken(value: string) {
  csrfToken = value;
}

export function setUnauthorizedHandler(handler: UnauthorizedHandler) {
  unauthorizedHandler = handler;
}

function asProblemDetails(value: unknown): ProblemDetails | undefined {
  return typeof value === "object" && value !== null ? (value as ProblemDetails) : undefined;
}

class SameOriginRequest extends Request {
  readonly sourceBody: BodyInit | null | undefined;
  readonly sourceSignal: AbortSignal | null | undefined;

  constructor(input: RequestInfo | URL, init?: RequestInit) {
    const { signal, ...compatibleInit } = Object(init) as RequestInit;
    super(input, compatibleInit);
    this.sourceBody = init?.body;
    this.sourceSignal = signal;
  }
}

async function sameOriginFetch(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const canHaveBody = request.method !== "GET" && request.method !== "HEAD";
  const sourceBody = (request as SameOriginRequest).sourceBody;
  const body = !canHaveBody
    ? undefined
    : sourceBody ?? await request.clone().arrayBuffer();
  const headers = new Headers(request.headers);
  if (body instanceof FormData) {
    headers.delete("Content-Type");
  }
  return globalThis.fetch(`${url.pathname}${url.search}`, {
    body,
    credentials: "same-origin",
    headers: Object.fromEntries(headers.entries()),
    method: request.method,
    signal: (request as SameOriginRequest).sourceSignal
  });
}

function hasBinaryValue(body: unknown): body is Record<string, unknown> {
  return typeof body === "object" && body !== null && Object.values(body).some((value) => value instanceof Blob);
}

function apiBodySerializer(body: unknown): BodyInit {
  if (!hasBinaryValue(body)) {
    return defaultBodySerializer(body);
  }
  const form = new FormData();
  Object.entries(body).forEach(([key, value]) => {
    if (value !== undefined) {
      form.append(key, value instanceof Blob ? value : String(value));
    }
  });
  return form;
}

export const apiClient = createClient<paths>({
  baseUrl: window.location.origin,
  bodySerializer: apiBodySerializer,
  credentials: "same-origin",
  fetch: sameOriginFetch,
  Request: SameOriginRequest
});

apiClient.use({
  onRequest({ request, schemaPath }) {
    request.headers.set("Accept", "application/json");
    if (
      csrfToken &&
      !["GET", "HEAD", "OPTIONS"].includes(request.method) &&
      !PUBLIC_AUTH_PATHS.has(schemaPath)
    ) {
      request.headers.set("X-CSRF-Token", csrfToken);
    }
  },
  async onResponse({ response, schemaPath }) {
    if (response.status !== 401 || PUBLIC_AUTH_PATHS.has(schemaPath)) {
      return;
    }
    const problem = asProblemDetails(await response.clone().json().catch(() => undefined));
    if (problem?.code && SESSION_INVALID_CODES.has(problem.code)) {
      unauthorizedHandler?.({ code: problem.code, schemaPath });
    }
  }
});

export async function apiRequest<TPending extends Promise<ApiFetchResult>>(
  pending: TPending
): Promise<ApiResult<ApiResponseData<TPending>>> {
  const result = await pending;
  if ("error" in result) {
    throw new ApiError(result.response, asProblemDetails(result.error));
  }
  return {
    data: result.data as ApiResponseData<TPending>,
    requestId: result.response.headers.get("X-Request-ID") ?? "",
    response: result.response
  };
}

import type { components } from "../lib/api/schema";

export type AuthConfig = components["schemas"]["AuthConfigResponse"];
export type AuthenticatedResponse = components["schemas"]["AuthenticatedResponse"];
export type BillingCapabilities = components["schemas"]["BillingCapabilitiesResponse"] & {
  can_manage_theme: boolean;
  can_read_theme: boolean;
  can_upload_bill_receipts: boolean;
};

export const BILLING_CAPABILITIES_ALL: BillingCapabilities = {
  can_create_bills: true,
  can_create_exports: true,
  can_delete: true,
  can_edit: true,
  can_manage_bills: true,
  can_manage_theme: true,
  can_read_attachments: true,
  can_read_bills: true,
  can_read_expenses: true,
  can_read_theme: true,
  can_transfer: true,
  can_upload_bill_receipts: true,
  can_write_attachments: true,
  can_write_expenses: true
};

export const BILLING_CAPABILITIES_NONE: BillingCapabilities = {
  can_create_bills: false,
  can_create_exports: false,
  can_delete: false,
  can_edit: false,
  can_manage_bills: false,
  can_manage_theme: false,
  can_read_attachments: false,
  can_read_bills: false,
  can_read_expenses: false,
  can_read_theme: false,
  can_transfer: false,
  can_upload_bill_receipts: false,
  can_write_attachments: false,
  can_write_expenses: false
};

export const AUTH_CONFIG: AuthConfig = {
  analytics: { gtm_container_id: "GTM-TEST" },
  feature_flags: {
    google_auth: true,
    turnstile: true,
    turnstile_site_key: "turnstile-site-key"
  }
};

export const AUTHENTICATED_RESPONSE: AuthenticatedResponse = {
  bootstrap: {
    analytics: { events: [], gtm_container_id: "GTM-TEST" },
    capabilities: { mfa_setup_required: false, scopes: ["profile:read"] },
    csrf_token: "csrf-token",
    feature_flags: AUTH_CONFIG.feature_flags,
    pending_invite_count: 2,
    user: { email: "user@example.com", id: 42 }
  },
  credential_transport: "cookie",
  status: "authenticated"
};

export const AUTHENTICATED_WITH_EVENT: AuthenticatedResponse = {
  ...AUTHENTICATED_RESPONSE,
  bootstrap: {
    ...AUTHENTICATED_RESPONSE.bootstrap,
    analytics: {
      events: [{ event: "rentivo_login_success", reason: null, via: "password" }],
      gtm_container_id: "GTM-TEST"
    }
  }
};

export const PROBLEM_401 = {
  code: "authentication_required",
  detail: "Autenticação necessária.",
  fields: {},
  request_id: "request-id",
  status: 401,
  title: "Não autenticado",
  type: "https://rentivo.com.br/problems/authentication_required"
};

export function jsonResponse(body: unknown, status = 200, headers: HeadersInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json", ...Object.fromEntries(new Headers(headers)) },
    status
  });
}

export function problemResponse(body = PROBLEM_401, headers: HeadersInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/problem+json",
      ...Object.fromEntries(new Headers(headers))
    },
    status: body.status
  });
}

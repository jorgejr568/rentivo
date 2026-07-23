import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { saveMfaChallenge } from "../features/auth/authStorage";
import { apiClient, apiRequest } from "../lib/api/client";
import { AUTH_CONFIG, AUTHENTICATED_RESPONSE, jsonResponse, problemResponse } from "../test/auth";
import { createAppRouter } from "./router";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/v1/auth/config") {
        return jsonResponse({
          ...AUTH_CONFIG,
          analytics: { gtm_container_id: "" },
          feature_flags: {
            google_auth: false,
            turnstile: false,
            turnstile_site_key: ""
          }
        });
      }
      if (String(input) === "/api/v1/auth/session") {
        return problemResponse();
      }
      if (String(input).startsWith("/api/v1/auth/google/callback?")) {
        return new Promise<Response>(() => undefined);
      }
      throw new Error(`Unexpected request: ${String(input)}`);
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.pushState({}, "", "/");
  delete window.dataLayer;
  delete window.turnstile;
  document.head
    .querySelectorAll("script[data-rentivo-gtm], script[data-rentivo-turnstile]")
    .forEach((script) => script.remove());
});

it.each([
  ["/login", "Entrar"],
  ["/mobile-logout?state=native-state", "Sessão encerrada"],
  ["/signup", "Criar Conta"],
  ["/forgot-password", "Enviar link"],
  ["/reset-password", "Link inválido ou expirado. Solicite uma nova redefinição."],
  ["/auth/google/callback?code=code&state=state", "Entrando com o Google..."]
])("routes the legacy authentication URL %s outside the shell", async (path, expectedCopy) => {
  window.history.pushState({}, "", path);
  const router = createAppRouter();
  const view = render(<RouterProvider router={router} />);

  expect(await screen.findByText(expectedCopy)).toBeVisible();
  expect(screen.getByRole("main")).toHaveClass("wrapper", "main-content");
  expect(screen.getByText(expectedCopy).closest("main")).toBe(screen.getByRole("main"));
  view.unmount();
  router.dispose();
});

it.each([
  ["/privacy", "Política de Privacidade"],
  ["/terms", "Termos de Uso"]
])("renders the public legal page %s inside the public shell", async (path, heading) => {
  window.history.pushState({}, "", path);
  const router = createAppRouter();
  const view = render(<RouterProvider router={router} />);

  expect(
    await screen.findByRole("heading", { level: 2, name: heading })
  ).toBeVisible();
  expect(screen.getByRole("main")).toHaveClass("wrapper", "main-content");

  view.unmount();
  router.dispose();
});

it("renders the public support page inside the public shell", async () => {
  window.history.pushState({}, "", "/support");
  const router = createAppRouter();
  const view = render(<RouterProvider router={router} />);

  expect(
    await screen.findByRole("heading", { level: 2, name: "Suporte" })
  ).toBeVisible();
  expect(screen.getByRole("main")).toHaveClass("wrapper", "main-content");

  view.unmount();
  router.dispose();
});

it("does not render or request private content until session authentication succeeds", async () => {
  const NativeRequest = globalThis.Request;
  class CompatibleNavigationRequest extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      const compatibleInit = { ...init };
      delete compatibleInit.signal;
      super(input, compatibleInit);
    }
  }
  vi.stubGlobal("Request", CompatibleNavigationRequest);
  let resolveSession!: (response: Response) => void;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (url === "/api/v1/auth/session") {
      return new Promise<Response>((resolve) => {
        resolveSession = resolve;
      });
    }
    if (url === "/api/v1/profile") return jsonResponse({ email: "user@example.com" });
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  function PrivateProbe() {
    useEffect(() => {
      void apiRequest(apiClient.GET("/api/v1/profile"));
    }, []);
    return <p>private-screen</p>;
  }

  window.history.pushState({}, "", "/private");
  const router = createAppRouter([{ element: <PrivateProbe />, path: "/private" }]);
  const view = render(<RouterProvider router={router} />);

  await waitFor(() => expect(resolveSession).toBeTypeOf("function"));
  expect(screen.getByRole("status")).toHaveTextContent("Carregando sessão...");
  expect(screen.queryByText("private-screen")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => String(url) === "/api/v1/profile")).toBe(false);

  await act(async () => resolveSession(problemResponse()));

  await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  expect(screen.queryByText("private-screen")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => String(url) === "/api/v1/profile")).toBe(false);
  view.unmount();
  router.dispose();
});

it("redirects direct protected navigation when live bootstrap requires MFA setup", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (url === "/api/v1/auth/session") return jsonResponse({
      ...AUTHENTICATED_RESPONSE,
      bootstrap: {
        ...AUTHENTICATED_RESPONSE.bootstrap,
        capabilities: {
          ...AUTHENTICATED_RESPONSE.bootstrap.capabilities,
          mfa_setup_required: true
        }
      }
    });
    throw new Error(`Unexpected request: ${url}`);
  }));
  window.history.pushState({}, "", "/private");
  const router = createAppRouter([
    { element: <h1>Conteúdo privado</h1>, path: "/private" },
    { element: <h1>Configuração MFA</h1>, path: "/security/totp/setup" }
  ]);
  const view = render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: "Configuração MFA" })).toBeVisible();
  expect(router.state.location.pathname).toBe("/security/totp/setup");
  expect(screen.queryByRole("heading", { name: "Conteúdo privado" })).not.toBeInTheDocument();

  view.unmount();
  router.dispose();
});

it("offers an in-place retry when protected-session validation is temporarily unavailable", async () => {
  const user = userEvent.setup();
  let sessionAttempts = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (url === "/api/v1/auth/session") {
      sessionAttempts += 1;
      return sessionAttempts === 1
        ? new Response(null, { status: 503 })
        : jsonResponse(AUTHENTICATED_RESPONSE);
    }
    if (url === "/api/v1/security") return jsonResponse({
      mfa: { organization_enforced: false, setup_required: false },
      passkeys: [],
      profile: { email: "user@example.com", pix_key: "pix", pix_merchant_city: "SP", pix_merchant_name: "User" },
      totp: { enabled: false, recovery_codes_remaining: 0 }
    });
    if (url === "/api/v1/api-keys") return jsonResponse({ items: [] });
    if (url === "/api/v1/api-keys/options") return jsonResponse({ default_expiration_days: 90, max_expiration_days: 365, organizations: [], personal_workspace: { resource_id: "personal", resource_type: "user" }, scopes: ["profile:read"] });
    throw new Error(`Unexpected request: ${url}`);
  }));
  window.history.pushState({}, "", "/security");
  const router = createAppRouter();
  const view = render(<RouterProvider router={router} />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível validar sua sessão.");
  expect(router.state.location.pathname).toBe("/security");
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByRole("heading", { name: "Segurança" })).toBeVisible();

  view.unmount();
  router.dispose();
});

it("routes an active MFA challenge at its legacy URL", async () => {
  saveMfaChallenge({ challengeId: "challenge", methods: ["totp"] });
  window.history.pushState({}, "", "/mfa-verify?challenge=challenge");
  const router = createAppRouter();
  const view = render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: "Verificação MFA" })).toBeVisible();
  expect(screen.getByRole("main")).toHaveClass("wrapper", "main-content");

  view.unmount();
  router.dispose();
});

it.each([
  ["/security", "Segurança"],
  ["/security/totp/setup", "Configurar Autenticação TOTP"],
  ["/security/recovery-codes", "Códigos de Recuperação"]
])("routes the authenticated security URL %s through the shell", async (path, heading) => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (url === "/api/v1/auth/session") return jsonResponse(AUTHENTICATED_RESPONSE);
    if (url === "/api/v1/security") return jsonResponse({
      mfa: { organization_enforced: false, setup_required: false },
      passkeys: [],
      profile: { email: "user@example.com", pix_key: "pix", pix_merchant_city: "SP", pix_merchant_name: "User" },
      totp: { enabled: false, recovery_codes_remaining: 0 }
    });
    if (url === "/api/v1/security/totp/setup") return jsonResponse({ provisioning_uri: "otpauth://totp/test", qr_code_base64: "cXI=", secret: "SECRET" });
    if (url === "/api/v1/api-keys") return jsonResponse({ items: [] });
    if (url === "/api/v1/api-keys/options") return jsonResponse({ default_expiration_days: 90, max_expiration_days: 365, organizations: [], personal_workspace: { resource_id: "personal", resource_type: "user" }, scopes: ["profile:read"] });
    throw new Error(`Unexpected request: ${url}`);
  }));
  window.history.pushState(path.endsWith("recovery-codes") ? { usr: { recoveryCodes: ["one"] } } : {}, "", path);
  const router = createAppRouter();
  const view = render(<RouterProvider router={router} />);
  expect(await screen.findByRole("heading", { name: heading })).toBeVisible();
  expect(screen.getByRole("main")).toContainElement(screen.getByRole("heading", { name: heading }));
  view.unmount();
  router.dispose();
});

it("redirects the authenticated home URL to billings", async () => {
  const NativeRequest = globalThis.Request;
  class CompatibleNavigationRequest extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      const compatibleInit = { ...init };
      delete compatibleInit.signal;
      super(input, compatibleInit);
    }
  }
  vi.stubGlobal("Request", CompatibleNavigationRequest);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (url === "/api/v1/auth/session") return jsonResponse(AUTHENTICATED_RESPONSE);
    throw new Error(`Unexpected request: ${url}`);
  }));
  window.history.pushState({}, "", "/");
  const router = createAppRouter([
    { element: <h1>Minhas Cobranças</h1>, path: "/billings/" }
  ]);
  const view = render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: "Minhas Cobranças" })).toBeVisible();
  expect(router.state.location.pathname).toBe("/billings/");

  view.unmount();
  router.dispose();
});

it("renders the public landing page at the anonymous home URL without the authenticated shell", async () => {
  window.history.pushState({}, "", "/");
  const router = createAppRouter();
  const view = render(<RouterProvider router={router} />);

  expect(
    await screen.findByRole("heading", { level: 1, name: /cobranças de aluguel.*pix em segundos/i })
  ).toBeVisible();
  expect(screen.getByRole("link", { name: "Criar conta gratuita" })).toHaveAttribute("href", "/signup");
  expect(screen.queryByRole("button", { name: "Sair" })).not.toBeInTheDocument();

  view.unmount();
  router.dispose();
});

it("renders the fresh-account billing state instead of an authenticated catch-all", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (url === "/api/v1/auth/session") return jsonResponse(AUTHENTICATED_RESPONSE);
    if (url === "/api/v1/billings") return jsonResponse({
      items: [],
      stats: {
        active_count: 0,
        billed_count: 0,
        expected: 0,
        net_income: 0,
        overdue: 0,
        overdue_count: 0,
        paid_count: 0,
        pending: 0,
        pending_count: 0,
        received: 0,
        total_expenses: 0,
        year: 2026
      },
      user_pix_incomplete: true
    });
    throw new Error(`Unexpected request: ${url}`);
  }));
  window.history.pushState({}, "", "/billings/");
  const router = createAppRouter();
  const view = render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: "Minhas Cobranças" })).toBeVisible();
  expect(screen.getByText("Nenhuma cobrança cadastrada.")).toBeVisible();
  expect(screen.getByRole("main")).toContainElement(
    screen.getByRole("heading", { name: "Minhas Cobranças" })
  );

  view.unmount();
  router.dispose();
});

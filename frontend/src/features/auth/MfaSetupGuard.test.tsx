import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { createAppRouter } from "../../app/router";
import { AUTH_CONFIG, AUTHENTICATED_RESPONSE, jsonResponse } from "../../test/auth";

const MFA_REQUIRED_RESPONSE = {
  ...AUTHENTICATED_RESPONSE,
  bootstrap: {
    ...AUTHENTICATED_RESPONSE.bootstrap,
    capabilities: {
      ...AUTHENTICATED_RESPONSE.bootstrap.capabilities,
      mfa_setup_required: true
    }
  }
};

function installSessionSequence(...sessions: typeof AUTHENTICATED_RESPONSE[]) {
  let sessionIndex = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (url === "/api/v1/auth/session") {
      const session = sessions[Math.min(sessionIndex, sessions.length - 1)];
      sessionIndex += 1;
      return jsonResponse(session);
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function installTotpCompletionFlow(
  ...sessions: Array<typeof AUTHENTICATED_RESPONSE | Response>
) {
  let sessionIndex = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (url === "/api/v1/auth/session") {
      const session = sessions[Math.min(sessionIndex, sessions.length - 1)];
      sessionIndex += 1;
      return session instanceof Response ? session : jsonResponse(session);
    }
    if (url === "/api/v1/security/totp/setup") {
      return jsonResponse({
        provisioning_uri: "otpauth://totp/test",
        qr_code_base64: "cXI=",
        secret: "SECRET"
      });
    }
    if (url === "/api/v1/security/totp/confirm") {
      return jsonResponse({ recovery_codes: ["code-one"] });
    }
    if (url === "/api/v1/security") {
      return jsonResponse({
        mfa: { organization_enforced: true, setup_required: false },
        passkeys: [],
        profile: {
          email: "user@example.com",
          pix_key: "pix",
          pix_merchant_city: "SP",
          pix_merchant_name: "User"
        },
        totp: { enabled: true, recovery_codes_remaining: 1 }
      });
    }
    if (url === "/api/v1/api-keys") return jsonResponse({ items: [] });
    if (url === "/api/v1/api-keys/options") {
      return jsonResponse({
        default_expiration_days: 90,
        max_expiration_days: 365,
        organizations: [],
        personal_workspace: { resource_id: "personal", resource_type: "user" },
        scopes: ["profile:read"]
      });
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

it("guards direct navigation while preserving setup, recovery, and logout access", async () => {
  const user = userEvent.setup();
  installSessionSequence(MFA_REQUIRED_RESPONSE);
  window.history.pushState({}, "", "/private");
  const router = createAppRouter([
    { element: <h1>Conteúdo privado</h1>, path: "/private" },
    { element: <h1>Configuração permitida</h1>, path: "/security/totp/setup" },
    { element: <h1>Recuperação permitida</h1>, path: "/security/recovery-codes" }
  ]);

  const view = render(<RouterProvider router={router} />);

  await waitFor(() => expect(router.state.location.pathname).toBe("/security/totp/setup"));
  expect(screen.getByRole("heading", { name: "Configuração permitida" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "user@example.com" }));
  expect(screen.getByRole("button", { name: "Sair" })).toBeVisible();

  await act(async () => router.navigate("/security/recovery-codes"));
  expect(screen.getByRole("heading", { name: "Recuperação permitida" })).toBeVisible();

  view.unmount();
  router.dispose();
});

it("refreshes the bootstrap across the production setup, recovery, and Continue flow", async () => {
  const user = userEvent.setup();
  const fetchMock = installTotpCompletionFlow(
    MFA_REQUIRED_RESPONSE,
    AUTHENTICATED_RESPONSE,
    AUTHENTICATED_RESPONSE
  );
  window.history.pushState({}, "", "/security/totp/setup");
  const router = createAppRouter();

  const view = render(<RouterProvider router={router} />);

  expect(await screen.findByAltText("QR Code TOTP")).toBeVisible();
  await user.type(screen.getByLabelText("Código de verificação"), "123456");
  await user.click(screen.getByRole("button", { name: "Confirmar e Ativar" }));
  expect(await screen.findByRole("heading", { name: "Códigos de Recuperação" })).toBeVisible();
  await waitFor(() => {
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === "/api/v1/auth/session")).toHaveLength(2);
  });
  await user.click(screen.getByRole("button", { name: "Continuar" }));
  expect(await screen.findByRole("heading", { name: "Segurança" })).toBeVisible();
  expect(router.state.location.pathname).toBe("/security");
  expect(fetchMock.mock.calls.filter(([url]) => String(url) === "/api/v1/auth/session")).toHaveLength(3);

  view.unmount();
  router.dispose();
});

it("keeps recovery codes through failed refreshes and retries before Continue", async () => {
  const user = userEvent.setup();
  const fetchMock = installTotpCompletionFlow(
    MFA_REQUIRED_RESPONSE,
    new Response(null, { status: 503 }),
    new Response(null, { status: 503 }),
    AUTHENTICATED_RESPONSE
  );
  window.history.pushState({}, "", "/security/totp/setup");
  const router = createAppRouter();

  const view = render(<RouterProvider router={router} />);

  expect(await screen.findByAltText("QR Code TOTP")).toBeVisible();
  await user.type(screen.getByLabelText("Código de verificação"), "123456");
  await user.click(screen.getByRole("button", { name: "Confirmar e Ativar" }));

  expect(await screen.findByRole("heading", { name: "Códigos de Recuperação" })).toBeVisible();
  expect(screen.getByText("code-one")).toBeVisible();
  expect(screen.queryByText("Não foi possível confirmar o código.")).not.toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/security/recovery-codes");

  await user.click(screen.getByRole("button", { name: "Continuar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível atualizar sua sessão.");
  expect(screen.getByText("code-one")).toBeVisible();
  expect(router.state.location.pathname).toBe("/security/recovery-codes");

  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByRole("heading", { name: "Segurança" })).toBeVisible();
  expect(router.state.location.pathname).toBe("/security");
  expect(fetchMock.mock.calls.filter(([url]) => String(url) === "/api/v1/auth/session")).toHaveLength(4);

  view.unmount();
  router.dispose();
});

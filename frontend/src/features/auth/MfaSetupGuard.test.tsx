import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { createAppRouter } from "../../app/router";
import { AUTH_CONFIG, AUTHENTICATED_RESPONSE, jsonResponse } from "../../test/auth";
import { useAuth } from "./AuthProvider";

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

function SetupProbe() {
  const { retrySession } = useAuth();
  return <button onClick={retrySession}>atualizar sessão</button>;
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

it("removes the redirect after a refreshed bootstrap reports MFA complete", async () => {
  const user = userEvent.setup();
  const fetchMock = installSessionSequence(MFA_REQUIRED_RESPONSE, AUTHENTICATED_RESPONSE);
  window.history.pushState({}, "", "/security/totp/setup");
  const router = createAppRouter([
    { element: <h1>Conteúdo privado</h1>, path: "/private" },
    { element: <SetupProbe />, path: "/security/totp/setup" }
  ]);

  const view = render(<RouterProvider router={router} />);

  await user.click(await screen.findByRole("button", { name: "atualizar sessão" }));
  await waitFor(() => {
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === "/api/v1/auth/session")).toHaveLength(2);
  });
  await screen.findByRole("button", { name: "atualizar sessão" });
  await act(async () => router.navigate("/private"));
  expect(await screen.findByRole("heading", { name: "Conteúdo privado" })).toBeVisible();
  expect(router.state.location.pathname).toBe("/private");

  view.unmount();
  router.dispose();
});

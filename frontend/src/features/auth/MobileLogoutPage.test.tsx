import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../../test/auth";
import { renderAuth } from "../../test/renderAuth";
import { MobileLogoutPage } from "./MobileLogoutPage";

const { openMobileAuthorizationCallback } = vi.hoisted(() => ({
  openMobileAuthorizationCallback: vi.fn()
}));

vi.mock("./mobileAuthorization", () => ({ openMobileAuthorizationCallback }));

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("MobileLogoutPage", () => {
  it("logs out the authenticated browser session before returning to the app", async () => {
    let resolveLogout!: (response: Response) => void;
    const logoutResponse = new Promise<Response>((resolve) => {
      resolveLogout = resolve;
    });
    const { fetchMock } = renderAuth(<MobileLogoutPage />, {
      handlers: { "/api/v1/auth/logout": () => logoutResponse },
      path: "/mobile-logout?state=native%20state",
      session: "authenticated"
    });

    expect(await screen.findByRole("heading", { name: "Saindo do Rentivo" })).toBeVisible();
    expect(openMobileAuthorizationCallback).not.toHaveBeenCalled();

    await act(async () => resolveLogout(new Response(null, { status: 204 })));

    expect(await screen.findByRole("heading", { name: "Sessão encerrada" })).toBeVisible();
    expect(openMobileAuthorizationCallback).toHaveBeenCalledOnce();
    expect(openMobileAuthorizationCallback).toHaveBeenCalledWith(
      "rentivo://auth/logout?state=native%20state"
    );
    const logoutCall = fetchMock.mock.calls.find(([url]) => url === "/api/v1/auth/logout");
    expect(new Headers(logoutCall?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-token");
  });

  it("returns immediately when the browser session is already anonymous", async () => {
    const { fetchMock } = renderAuth(<MobileLogoutPage />, {
      path: "/mobile-logout?state=native-state"
    });

    expect(await screen.findByRole("heading", { name: "Sessão encerrada" })).toBeVisible();
    expect(openMobileAuthorizationCallback).toHaveBeenCalledWith(
      "rentivo://auth/logout?state=native-state"
    );
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/auth/logout")).toBe(false);
  });

  it("treats an expired session during logout as already signed out", async () => {
    renderAuth(<MobileLogoutPage />, {
      handlers: {
        "/api/v1/auth/logout": () =>
          jsonResponse(
            {
              code: "authentication_required",
              detail: "Autenticação necessária.",
              status: 401
            },
            401,
            { "Content-Type": "application/problem+json" }
          )
      },
      path: "/mobile-logout?state=native-state",
      session: "authenticated"
    });

    expect(await screen.findByRole("heading", { name: "Sessão encerrada" })).toBeVisible();
    expect(openMobileAuthorizationCallback).toHaveBeenCalledWith(
      "rentivo://auth/logout?state=native-state"
    );
  });

  it("keeps the browser open and retries when logout fails", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderAuth(<MobileLogoutPage />, {
      handlers: {
        "/api/v1/auth/logout": () => {
          attempts += 1;
          return attempts === 1
            ? new Response(null, { status: 503 })
            : new Response(null, { status: 204 });
        }
      },
      path: "/mobile-logout?state=native-state",
      session: "authenticated"
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível encerrar a sessão no site."
    );
    expect(openMobileAuthorizationCallback).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("heading", { name: "Sessão encerrada" })).toBeVisible();
    expect(openMobileAuthorizationCallback).toHaveBeenCalledOnce();
    expect(attempts).toBe(2);
  });

  it("shows the retry state for a network failure", async () => {
    renderAuth(<MobileLogoutPage />, {
      handlers: {
        "/api/v1/auth/logout": () => {
          throw new TypeError("network unavailable");
        }
      },
      path: "/mobile-logout?state=native-state",
      session: "authenticated"
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível encerrar a sessão no site."
    );
    expect(openMobileAuthorizationCallback).not.toHaveBeenCalled();
  });

  it.each([204, 503])("ignores a late logout response after unmounting (%s)", async (status) => {
    let resolveLogout!: (response: Response) => void;
    const logoutResponse = new Promise<Response>((resolve) => {
      resolveLogout = resolve;
    });
    const view = renderAuth(<MobileLogoutPage />, {
      handlers: { "/api/v1/auth/logout": () => logoutResponse },
      path: "/mobile-logout?state=native-state",
      session: "authenticated"
    });

    await screen.findByRole("heading", { name: "Saindo do Rentivo" });
    await waitFor(() =>
      expect(view.fetchMock.mock.calls.some(([url]) => url === "/api/v1/auth/logout")).toBe(true)
    );
    view.unmount();
    await act(async () => resolveLogout(new Response(null, { status })));

    expect(openMobileAuthorizationCallback).not.toHaveBeenCalled();
  });

  it("retries session validation before attempting logout", async () => {
    const user = userEvent.setup();
    let sessionAttempts = 0;
    renderAuth(<MobileLogoutPage />, {
      handlers: { "/api/v1/auth/logout": () => new Response(null, { status: 204 }) },
      path: "/mobile-logout?state=native-state",
      sessionHandler: () => {
        sessionAttempts += 1;
        return sessionAttempts === 1
          ? new Response(null, { status: 503 })
          : jsonResponse({
              bootstrap: {
                analytics: { events: [], gtm_container_id: "" },
                capabilities: { mfa_setup_required: false, scopes: ["profile:read"] },
                csrf_token: "csrf-token",
                feature_flags: {
                  google_auth: false,
                  turnstile: false,
                  turnstile_site_key: ""
                },
                pending_invite_count: 0,
                user: { email: "user@example.com", id: 42 }
              },
              credential_transport: "cookie",
              status: "authenticated"
            })
      }
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível verificar a sessão do site."
    );
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("heading", { name: "Sessão encerrada" })).toBeVisible();
    expect(sessionAttempts).toBe(2);
  });

  it("rejects a missing state and lets the user reopen a completed callback", async () => {
    const user = userEvent.setup();
    const view = renderAuth(<MobileLogoutPage />, { path: "/mobile-logout" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível validar a solicitação do aplicativo."
    );
    expect(openMobileAuthorizationCallback).not.toHaveBeenCalled();

    view.unmount();
    renderAuth(<MobileLogoutPage />, { path: "/mobile-logout?state=native-state" });
    await screen.findByRole("heading", { name: "Sessão encerrada" });
    openMobileAuthorizationCallback.mockClear();
    await user.click(screen.getByRole("button", { name: "Voltar para o app agora" }));
    expect(openMobileAuthorizationCallback).toHaveBeenCalledWith(
      "rentivo://auth/logout?state=native-state"
    );
  });
});

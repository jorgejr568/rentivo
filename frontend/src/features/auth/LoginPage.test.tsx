import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AUTHENTICATED_WITH_EVENT,
  jsonResponse,
  problemResponse
} from "../../test/auth";
import { renderAuth } from "../../test/renderAuth";
import { setAuthFlash } from "./authStorage";
import { LoginPage } from "./LoginPage";

const { openMobileAuthorizationCallback } = vi.hoisted(() => ({
  openMobileAuthorizationCallback: vi.fn()
}));

vi.mock("./mobileAuthorization", () => ({ openMobileAuthorizationCallback }));

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  delete window.dataLayer;
  delete window.turnstile;
  document.head.querySelectorAll("script[data-rentivo-gtm], script[data-rentivo-turnstile]").forEach((script) => script.remove());
});

describe("LoginPage", () => {
  it("preserves the legacy PT-BR form, Google option, Turnstile, focus, and title", async () => {
    renderAuth(<LoginPage />);

    const email = await screen.findByLabelText("E-mail");
    expect(email).toHaveFocus();
    expect(screen.getByLabelText("Senha")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Entrar" })).toHaveClass("btn--lg");
    expect(screen.getByRole("link", { name: "Esqueceu sua senha?" })).toHaveAttribute(
      "href",
      "/forgot-password"
    );
    expect(screen.getByRole("link", { name: "Continuar com Google" })).toBeVisible();
    expect(screen.getByTestId("turnstile")).toBeVisible();
    expect(document.title).toBe("Entrar - Rentivo");
  });

  it("shows loading and completes password login at the legacy destination", async () => {
    const user = userEvent.setup();
    let resolveLogin!: (response: Response) => void;
    const loginResponse = new Promise<Response>((resolve) => {
      resolveLogin = resolve;
    });
    renderAuth(<LoginPage />, {
      handlers: {
        "/api/v1/auth/login": (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({
            credential_transport: "cookie",
            email: "user@example.com",
            password: "correct-password",
            turnstile_token: ""
          });
          return loginResponse;
        }
      }
    });

    await user.type(await screen.findByLabelText("E-mail"), " user@example.com ");
    await user.type(screen.getByLabelText("Senha"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(screen.getByRole("button", { name: "Entrar" })).toBeDisabled();
    await act(async () => resolveLogin(jsonResponse(AUTHENTICATED_WITH_EVENT)));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
    expect(window.dataLayer?.at(-1)).toEqual({
      event: "rentivo_login_success",
      reason: null,
      via: "password"
    });
  });

  it("persists public MFA progress and navigates to verification", async () => {
    const user = userEvent.setup();
    renderAuth(<LoginPage />, {
      handlers: {
        "/api/v1/auth/login": () =>
          jsonResponse(
            {
              challenge_id: "challenge/id",
              methods: ["totp", "recovery", "passkey"],
              status: "mfa_required"
            },
            202
          )
      }
    });

    await user.type(await screen.findByLabelText("E-mail"), "user@example.com");
    await user.type(screen.getByLabelText("Senha"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/mfa-verify?challenge=challenge%2Fid"
      )
    );
    expect(sessionStorage.getItem("rentivo.auth.mfa")).toContain("passkey");
  });

  it("shows API errors, restores focus, resets Turnstile, and forwards analytics", async () => {
    const user = userEvent.setup();
    const reset = vi.fn();
    window.turnstile = { render: vi.fn().mockReturnValue("widget"), reset };
    renderAuth(<LoginPage />, {
      handlers: {
        "/api/v1/auth/login": () =>
          problemResponse(
            {
              code: "invalid_credentials",
              detail: "E-mail ou senha inválidos.",
              fields: {},
              request_id: "request-id",
              status: 401,
              title: "Não autenticado",
              type: "https://rentivo.com.br/problems/invalid_credentials"
            },
            {
              "X-Rentivo-Analytics-Event": "rentivo_login_failed",
              "X-Rentivo-Analytics-Reason": "bad_credentials"
            }
          )
      }
    });

    await user.type(await screen.findByLabelText("E-mail"), "user@example.com");
    await user.type(screen.getByLabelText("Senha"), "wrong");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha inválidos.");
    expect(screen.getByLabelText("E-mail")).toHaveFocus();
    expect(reset).toHaveBeenCalledWith("widget");
    expect(window.dataLayer?.at(-1)).toEqual({
      event: "rentivo_login_failed",
      reason: "bad_credentials"
    });
  });

  it("shows Google callback errors and a one-shot reset success message", async () => {
    setAuthFlash("Senha redefinida com sucesso. Faça login com a nova senha.");

    renderAuth(<LoginPage />, { path: "/login?error=google_auth_failed" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível entrar com o Google. Tente novamente."
    );
    expect(
      screen.getByText("Senha redefinida com sucesso. Faça login com a nova senha.")
    ).toHaveAttribute("role", "status");
    expect(sessionStorage.getItem("rentivo.auth.flash")).toBeNull();
  });

  it("retries authentication configuration and redirects an existing session", async () => {
    const user = userEvent.setup();
    let configCalls = 0;
    renderAuth(<LoginPage />, {
      configHandler: () => {
        configCalls += 1;
        return configCalls === 1
          ? new Response(null, { status: 503 })
          : jsonResponse({
              analytics: { gtm_container_id: "" },
              feature_flags: {
                google_auth: false,
                turnstile: false,
                turnstile_site_key: ""
              }
            });
      },
      session: "authenticated"
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar as opções de autenticação. Tente novamente."
    );
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
  });

  it("exchanges an existing web session for a mobile callback instead of opening the dashboard", async () => {
    const { fetchMock } = renderAuth(<LoginPage />, {
      path: "/login?mobile_state=native-state",
      session: "authenticated",
      handlers: {
        "/api/v1/auth/mobile/authorize": (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({ state: "native-state" });
          return jsonResponse({ authorization_code: "one-time-code", state: "native-state" });
        }
      }
    });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/auth/mobile/authorize",
        expect.objectContaining({ method: "POST" })
      )
    );
    expect(openMobileAuthorizationCallback).toHaveBeenCalledWith(
      "rentivo://auth/callback?code=one-time-code&state=native-state"
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/login?mobile_state=native-state");
  });

  it("shows the generic request error when no API response is available", async () => {
    const user = userEvent.setup();
    renderAuth(<LoginPage />, {
      handlers: {
        "/api/v1/auth/login": () => {
          throw new TypeError("network unavailable");
        }
      }
    });

    await user.type(await screen.findByLabelText("E-mail"), "user@example.com");
    await user.type(screen.getByLabelText("Senha"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível concluir a solicitação. Tente novamente."
    );
  });
});

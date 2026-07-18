import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AUTHENTICATED_RESPONSE, jsonResponse, problemResponse } from "../../test/auth";
import { renderAuth } from "../../test/renderAuth";
import { loadMfaChallenge } from "./authStorage";
import { GoogleCallbackPage } from "./GoogleCallbackPage";

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  delete window.dataLayer;
  document.head.querySelectorAll("script[data-rentivo-gtm]").forEach((script) => script.remove());
});

describe("GoogleCallbackPage", () => {
  it("forwards the callback query as JSON and completes authentication", async () => {
    let callbackCalls = 0;
    renderAuth(<GoogleCallbackPage />, {
      handlers: {
        "/api/v1/auth/google/callback?code=auth-code&state=oauth-state": (init) => {
          callbackCalls += 1;
          expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
          expect(init?.credentials).toBe("same-origin");
          return jsonResponse(AUTHENTICATED_RESPONSE);
        }
      },
      path: "/auth/google/callback?code=auth-code&state=oauth-state"
    });

    expect(screen.getByText("Entrando com o Google...")).toHaveAttribute("role", "status");
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
    expect(callbackCalls).toBe(1);
    expect(document.title).toBe("Entrar com Google - Rentivo");
  });

  it("stores the returned MFA challenge and opens verification", async () => {
    renderAuth(<GoogleCallbackPage />, {
      handlers: {
        "/api/v1/auth/google/callback?code=auth-code&state=oauth-state": () =>
          jsonResponse(
            {
              challenge_id: "google/challenge",
              methods: ["totp", "passkey"],
              status: "mfa_required"
            },
            202
          )
      },
      path: "/auth/google/callback?code=auth-code&state=oauth-state"
    });

    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/mfa-verify?challenge=google%2Fchallenge"
      )
    );
    expect(loadMfaChallenge("google/challenge")).toEqual({
      challengeId: "google/challenge",
      methods: ["totp", "passkey"]
    });
  });

  it("returns callback failures to the legacy login error URL", async () => {
    renderAuth(<GoogleCallbackPage />, {
      handlers: {
        "/api/v1/auth/google/callback?error=access_denied&state=oauth-state": () =>
          problemResponse({
            code: "google_auth_failed",
            detail: "Não foi possível entrar com o Google. Tente novamente.",
            fields: {},
            request_id: "request-id",
            status: 401,
            title: "Não autenticado",
            type: "https://rentivo.app/problems/google_auth_failed"
          })
      },
      path: "/auth/google/callback?error=access_denied&state=oauth-state"
    });

    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("/login?error=google_auth_failed")
    );
  });

  it("uses the same failure path for an unavailable callback request", async () => {
    renderAuth(<GoogleCallbackPage />, {
      handlers: {
        "/api/v1/auth/google/callback?code=auth-code": () => {
          throw new TypeError("network unavailable");
        }
      },
      path: "/auth/google/callback?code=auth-code"
    });

    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("/login?error=google_auth_failed")
    );
  });
});

import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AUTHENTICATED_RESPONSE, jsonResponse, problemResponse } from "../../test/auth";
import { renderAuth } from "../../test/renderAuth";
import { saveMfaChallenge } from "./authStorage";
import { MfaVerifyPage } from "./MfaVerifyPage";

function storeChallenge(methods = ["totp", "recovery", "passkey"]) {
  saveMfaChallenge({ challengeId: "challenge-1", methods });
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  delete window.dataLayer;
  document.head.querySelectorAll("script[data-rentivo-gtm]").forEach((script) => script.remove());
});

describe("MfaVerifyPage", () => {
  it("returns to login when public challenge progress is unavailable", async () => {
    renderAuth(<MfaVerifyPage />, { path: "/mfa-verify?challenge=missing" });

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
  });

  it("preserves the legacy TOTP, recovery, and passkey choices", async () => {
    storeChallenge();
    renderAuth(<MfaVerifyPage />, { path: "/mfa-verify?challenge=challenge-1" });

    const code = await screen.findByLabelText("Código de autenticação");
    expect(code).toHaveFocus();
    expect(code).toHaveAttribute("autocomplete", "one-time-code");
    expect(code).toHaveAttribute("maxlength", "8");
    expect(screen.getByRole("button", { name: "Usar Passkey" })).toBeVisible();
    expect(screen.getByText("Usar código de recuperação")).toBeVisible();
    expect(document.title).toBe("Verificação MFA - Rentivo");
  });

  it("verifies TOTP with the generated request and authenticates", async () => {
    const user = userEvent.setup();
    storeChallenge();
    renderAuth(<MfaVerifyPage />, {
      handlers: {
        "/api/v1/auth/mfa/totp/verify": (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({
            challenge_id: "challenge-1",
            code: "123456",
            credential_transport: "cookie"
          });
          return jsonResponse(AUTHENTICATED_RESPONSE);
        }
      },
      path: "/mfa-verify?challenge=challenge-1"
    });

    await user.type(await screen.findByLabelText("Código de autenticação"), "123456");
    await user.click(screen.getByRole("button", { name: "Verificar" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
    expect(sessionStorage.getItem("rentivo.auth.mfa")).toBeNull();
  });

  it("switches to the recovery-code endpoint", async () => {
    const user = userEvent.setup();
    storeChallenge();
    renderAuth(<MfaVerifyPage />, {
      handlers: {
        "/api/v1/auth/mfa/recovery/verify": (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({
            challenge_id: "challenge-1",
            code: "recovery-code",
            credential_transport: "cookie"
          });
          return jsonResponse(AUTHENTICATED_RESPONSE);
        }
      },
      path: "/mfa-verify?challenge=challenge-1"
    });

    await screen.findByLabelText("Código de autenticação");
    await user.click(screen.getByText("Usar código de recuperação"));
    await user.type(screen.getByPlaceholderText("Código de recuperação"), "recovery-code");
    await user.click(
      screen.getByRole("button", { name: "Verificar com código de recuperação" })
    );

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
  });

  it("maps invalid-code and rate-limit problems to legacy copy and focus", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    storeChallenge(["totp", "recovery"]);
    renderAuth(<MfaVerifyPage />, {
      handlers: {
        "/api/v1/auth/mfa/totp/verify": () => {
          attempts += 1;
          return problemResponse(
            attempts === 1
              ? {
                  code: "invalid_mfa_code",
                  detail: "Código de verificação inválido.",
                  fields: {},
                  request_id: "request-id",
                  status: 401,
                  title: "Não autenticado",
                  type: "https://rentivo.app/problems/invalid_mfa_code"
                }
              : {
                  code: "mfa_rate_limited",
                  detail: "Muitas tentativas. Aguarde um momento antes de tentar novamente.",
                  fields: {},
                  request_id: "request-id",
                  status: 429,
                  title: "Muitas tentativas",
                  type: "https://rentivo.app/problems/mfa_rate_limited"
                }
          );
        }
      },
      path: "/mfa-verify?challenge=challenge-1"
    });

    const code = await screen.findByLabelText("Código de autenticação");
    await user.type(code, "000000");
    await user.click(screen.getByRole("button", { name: "Verificar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Código inválido. Tente novamente.");
    expect(code).toHaveFocus();
    expect(window.dataLayer?.at(-1)).toEqual({ event: "rentivo_mfa_verify_failed" });

    await user.click(screen.getByRole("button", { name: "Verificar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Muitas tentativas. Aguarde alguns minutos."
    );
  });

  it("completes passkey authentication with typed WebAuthn JSON", async () => {
    const user = userEvent.setup();
    const credential = {
      id: "credential-id",
      rawId: "AQI",
      response: {
        authenticatorData: "Aw",
        clientDataJSON: "BA",
        signature: "BQ"
      },
      type: "public-key"
    };
    vi.stubGlobal("PublicKeyCredential", {
      parseRequestOptionsFromJSON: vi.fn().mockReturnValue({ challenge: new ArrayBuffer(0) })
    });
    vi.stubGlobal("navigator", {
      credentials: { get: vi.fn().mockResolvedValue({ toJSON: () => credential }) }
    });
    storeChallenge(["passkey"]);
    renderAuth(<MfaVerifyPage />, {
      handlers: {
        "/api/v1/auth/mfa/passkeys/begin": (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({
            challenge_id: "challenge-1",
            credential_transport: "cookie"
          });
          return jsonResponse({
            allowCredentials: [{ id: "AQI", type: "public-key" }],
            challenge: "AwQ",
            rpId: "rentivo.app",
            timeout: 60000,
            userVerification: "preferred"
          });
        },
        "/api/v1/auth/mfa/passkeys/complete": (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({
            challenge_id: "challenge-1",
            credential,
            credential_transport: "cookie"
          });
          return jsonResponse(AUTHENTICATED_RESPONSE);
        }
      },
      path: "/mfa-verify?challenge=challenge-1"
    });

    await user.click(await screen.findByRole("button", { name: "Usar Passkey" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
  });

  it("treats passkey cancellation as silent and reports other browser errors", async () => {
    const user = userEvent.setup();
    const get = vi
      .fn()
      .mockRejectedValueOnce(Object.assign(new Error("cancelled"), { name: "NotAllowedError" }))
      .mockRejectedValueOnce(new Error("browser failure"));
    vi.stubGlobal("PublicKeyCredential", {
      parseRequestOptionsFromJSON: vi.fn().mockReturnValue({ challenge: new ArrayBuffer(0) })
    });
    vi.stubGlobal("navigator", { credentials: { get } });
    storeChallenge(["passkey"]);
    renderAuth(<MfaVerifyPage />, {
      handlers: {
        "/api/v1/auth/mfa/passkeys/begin": () =>
          jsonResponse({
            allowCredentials: [],
            challenge: "AwQ",
            rpId: "rentivo.app",
            timeout: 60000,
            userVerification: "preferred"
          })
      },
      path: "/mfa-verify?challenge=challenge-1"
    });

    const passkeyButton = await screen.findByRole("button", { name: "Usar Passkey" });
    await user.click(passkeyButton);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await user.click(passkeyButton);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Erro na autenticação com passkey. Tente novamente."
    );
    expect(passkeyButton).toHaveFocus();
  });

  it("shows unknown recovery API problems and restores recovery focus", async () => {
    const user = userEvent.setup();
    storeChallenge(["recovery"]);
    renderAuth(<MfaVerifyPage />, {
      handlers: {
        "/api/v1/auth/mfa/recovery/verify": () =>
          problemResponse({
            code: "challenge_expired",
            detail: "A verificação expirou. Entre novamente.",
            fields: {},
            request_id: "request-id",
            status: 401,
            title: "Não autenticado",
            type: "https://rentivo.app/problems/challenge_expired"
          })
      },
      path: "/mfa-verify?challenge=challenge-1"
    });

    await user.click(await screen.findByText("Usar código de recuperação"));
    const recovery = screen.getByLabelText("Código de recuperação");
    await user.type(recovery, "recovery-code");
    await user.click(
      screen.getByRole("button", { name: "Verificar com código de recuperação" })
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A verificação expirou. Entre novamente."
    );
    expect(recovery).toHaveFocus();
  });

  it("shows the generic request error when code verification has no API response", async () => {
    const user = userEvent.setup();
    storeChallenge(["totp"]);
    renderAuth(<MfaVerifyPage />, {
      handlers: {
        "/api/v1/auth/mfa/totp/verify": () => {
          throw new TypeError("network unavailable");
        }
      },
      path: "/mfa-verify?challenge=challenge-1"
    });

    await user.type(await screen.findByLabelText("Código de autenticação"), "123456");
    await user.click(screen.getByRole("button", { name: "Verificar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível concluir a solicitação. Tente novamente."
    );
  });

  it("handles an empty passkey selection and a later passkey API problem", async () => {
    const user = userEvent.setup();
    const credential = {
      id: "credential-id",
      rawId: "AQI",
      response: {
        authenticatorData: "Aw",
        clientDataJSON: "BA",
        signature: "BQ"
      },
      type: "public-key"
    };
    vi.stubGlobal("PublicKeyCredential", {
      parseRequestOptionsFromJSON: vi.fn().mockReturnValue({ challenge: new ArrayBuffer(0) })
    });
    vi.stubGlobal("navigator", {
      credentials: {
        get: vi
          .fn()
          .mockResolvedValueOnce(null)
          .mockResolvedValueOnce({ toJSON: () => credential })
      }
    });
    let beginCalls = 0;
    storeChallenge(["passkey"]);
    renderAuth(<MfaVerifyPage />, {
      handlers: {
        "/api/v1/auth/mfa/passkeys/begin": () => {
          beginCalls += 1;
          return jsonResponse({
            allowCredentials: [],
            challenge: "AwQ",
            rpId: "rentivo.app",
            timeout: 60000,
            userVerification: "preferred"
          });
        },
        "/api/v1/auth/mfa/passkeys/complete": () =>
          problemResponse({
            code: "passkey_verification_failed",
            detail: "Não foi possível verificar esta passkey.",
            fields: {},
            request_id: "request-id",
            status: 401,
            title: "Não autenticado",
            type: "https://rentivo.app/problems/passkey_verification_failed"
          })
      },
      path: "/mfa-verify?challenge=challenge-1"
    });

    const passkeyButton = await screen.findByRole("button", { name: "Usar Passkey" });
    await user.click(passkeyButton);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await user.click(passkeyButton);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível verificar esta passkey."
    );
    expect(beginCalls).toBe(2);
  });

  it("locks every MFA method while a verification request is active", async () => {
    const user = userEvent.setup();
    let resolveVerification!: (response: Response) => void;
    const verification = new Promise<Response>((resolve) => {
      resolveVerification = resolve;
    });
    storeChallenge();
    renderAuth(<MfaVerifyPage />, {
      handlers: {
        "/api/v1/auth/mfa/totp/verify": () => verification
      },
      path: "/mfa-verify?challenge=challenge-1"
    });

    await user.click(await screen.findByText("Usar código de recuperação"));
    await user.type(screen.getByLabelText("Código de autenticação"), "123456");
    await user.click(screen.getByRole("button", { name: "Verificar" }));

    expect(screen.getByRole("button", { name: "Verificar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Usar Passkey" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Verificar com código de recuperação" })
    ).toBeDisabled();

    await act(async () => resolveVerification(jsonResponse(AUTHENTICATED_RESPONSE)));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
  });
});

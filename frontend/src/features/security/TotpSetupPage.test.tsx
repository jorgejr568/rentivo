import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { AUTHENTICATED_RESPONSE, jsonResponse, problemResponse } from "../../test/auth";
import { renderAuth } from "../../test/renderAuth";
import { TotpSetupPage } from "./TotpSetupPage";

afterEach(() => vi.unstubAllGlobals());

it("starts setup with POST and routes confirmed codes to the one-time screen", async () => {
  const user = userEvent.setup();
  const { fetchMock } = renderAuth(<TotpSetupPage />, {
    handlers: {
      "/api/v1/security/totp/confirm": () => jsonResponse({ recovery_codes: ["code-one"] }),
      "/api/v1/security/totp/setup": () =>
        jsonResponse({ provisioning_uri: "otpauth://totp/test", qr_code_base64: "cXI=", secret: "SECRET" })
    },
    path: "/security/totp/setup",
    session: "authenticated"
  });

  expect(await screen.findByAltText("QR Code TOTP")).toBeVisible();
  await user.type(screen.getByLabelText("Código de verificação"), "123456");
  await user.click(screen.getByRole("button", { name: "Confirmar e Ativar" }));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/security/recovery-codes"));
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/security/totp/setup",
    expect.objectContaining({ headers: expect.objectContaining({ "x-csrf-token": "csrf-token" }), method: "POST" })
  );
});

it("shows enforced MFA, retries setup errors, and links back to passkeys", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  renderAuth(<TotpSetupPage />, {
    handlers: {
      "/api/v1/security/totp/setup": () => {
        attempts += 1;
        return attempts === 1
          ? problemResponse({ code: "totp", detail: "TOTP já está ativado.", fields: {}, request_id: "id", status: 409, title: "Conflito", type: "problem" })
          : jsonResponse({ provisioning_uri: "otpauth://totp/test", qr_code_base64: "cXI=", secret: "SECRET" });
      }
    },
    path: "/security/totp/setup",
    sessionHandler: () => jsonResponse({
      ...AUTHENTICATED_RESPONSE,
      bootstrap: { ...AUTHENTICATED_RESPONSE.bootstrap, capabilities: { ...AUTHENTICATED_RESPONSE.bootstrap.capabilities, mfa_setup_required: true } }
    })
  });
  expect(await screen.findByText("TOTP já está ativado.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText(/Sua organização exige/)).toBeVisible();
  expect(screen.getByRole("link", { name: "Ou cadastrar uma Passkey" })).toHaveAttribute("href", "/security");
});

it("reports confirmation API and network failures and restores focus", async () => {
  const user = userEvent.setup();
  let confirms = 0;
  renderAuth(<TotpSetupPage />, {
    handlers: {
      "/api/v1/security/totp/confirm": () => {
        confirms += 1;
        if (confirms === 1) return problemResponse({ code: "invalid", detail: "Código inválido.", fields: {}, request_id: "id", status: 400, title: "Inválido", type: "problem" });
        throw new Error("offline");
      },
      "/api/v1/security/totp/setup": () => jsonResponse({ provisioning_uri: "otpauth://totp/test", qr_code_base64: "cXI=", secret: "SECRET" })
    },
    path: "/security/totp/setup",
    session: "authenticated"
  });
  const code = await screen.findByLabelText("Código de verificação");
  await user.type(code, "123456");
  await user.click(screen.getByRole("button", { name: "Confirmar e Ativar" }));
  expect(await screen.findByText("Código inválido.")).toBeVisible();
  expect(code).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Confirmar e Ativar" }));
  expect(await screen.findByText("Não foi possível confirmar o código.")).toBeVisible();
});

it("reports a generic setup failure", async () => {
  renderAuth(<TotpSetupPage />, {
    handlers: { "/api/v1/security/totp/setup": () => { throw new Error("offline"); } },
    path: "/security/totp/setup",
    session: "authenticated"
  });
  expect(await screen.findByText("Não foi possível iniciar a configuração TOTP.")).toBeVisible();
});

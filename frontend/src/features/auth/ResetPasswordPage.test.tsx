import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { problemResponse } from "../../test/auth";
import { renderAuth } from "../../test/renderAuth";
import { ResetPasswordPage } from "./ResetPasswordPage";

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  delete window.dataLayer;
  document.head.querySelectorAll("script[data-rentivo-gtm]").forEach((script) => script.remove());
});

describe("ResetPasswordPage", () => {
  it("shows the exact invalid-link state when the token is missing", async () => {
    renderAuth(<ResetPasswordPage />, { path: "/reset-password" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Link inválido ou expirado. Solicite uma nova redefinição."
    );
    expect(screen.getByRole("link", { name: "Pedir novo link" })).toHaveAttribute(
      "href",
      "/forgot-password"
    );
    expect(screen.queryByLabelText("Nova senha")).not.toBeInTheDocument();
    expect(document.title).toBe("Redefinir senha - Rentivo");
  });

  it("renders the token form and validates password confirmation locally", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderAuth(<ResetPasswordPage />, {
      path: "/reset-password?token=reset-token"
    });

    expect(await screen.findByLabelText("Nova senha")).toHaveFocus();
    await user.type(screen.getByLabelText("Nova senha"), "password-one");
    await user.type(screen.getByLabelText("Confirmar nova senha"), "password-two");
    await user.click(screen.getByRole("button", { name: "Redefinir senha" }));

    expect(screen.getByRole("alert")).toHaveTextContent("As senhas não coincidem.");
    expect(screen.getByLabelText("Nova senha")).toHaveFocus();
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/auth/password/reset")).toBe(
      false
    );
  });

  it("submits the generated contract, forwards analytics, and flashes login", async () => {
    const user = userEvent.setup();
    renderAuth(<ResetPasswordPage />, {
      handlers: {
        "/api/v1/auth/password/reset": (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({
            confirm_password: "new-password",
            password: "new-password",
            token: "reset-token"
          });
          return new Response(null, {
            headers: { "X-Rentivo-Analytics-Event": "rentivo_password_reset_completed" },
            status: 204
          });
        }
      },
      path: "/reset-password?token=reset-token"
    });

    await user.type(await screen.findByLabelText("Nova senha"), "new-password");
    await user.type(screen.getByLabelText("Confirmar nova senha"), "new-password");
    await user.click(screen.getByRole("button", { name: "Redefinir senha" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(sessionStorage.getItem("rentivo.auth.flash")).toBe(
      "Senha redefinida com sucesso. Faça login com a nova senha."
    );
    expect(window.dataLayer?.at(-1)).toEqual({
      event: "rentivo_password_reset_completed"
    });
  });

  it("turns an invalid or expired API token into the same link state", async () => {
    const user = userEvent.setup();
    renderAuth(<ResetPasswordPage />, {
      handlers: {
        "/api/v1/auth/password/reset": () =>
          problemResponse({
            code: "invalid_or_expired_reset_token",
            detail: "Token de redefinição inválido ou expirado.",
            fields: {},
            request_id: "request-id",
            status: 400,
            title: "Requisição inválida",
            type: "https://rentivo.com.br/problems/invalid_or_expired_reset_token"
          })
      },
      path: "/reset-password?token=expired-token"
    });

    await user.type(await screen.findByLabelText("Nova senha"), "new-password");
    await user.type(screen.getByLabelText("Confirmar nova senha"), "new-password");
    await user.click(screen.getByRole("button", { name: "Redefinir senha" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Link inválido ou expirado. Solicite uma nova redefinição."
    );
    expect(screen.queryByLabelText("Nova senha")).not.toBeInTheDocument();
  });

  it("shows specific and generic errors for other reset failures", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderAuth(<ResetPasswordPage />, {
      handlers: {
        "/api/v1/auth/password/reset": () => {
          attempts += 1;
          if (attempts === 1) {
            return problemResponse({
              code: "password_rejected",
              detail: "Escolha uma senha diferente.",
              fields: {},
              request_id: "request-id",
              status: 400,
              title: "Requisição inválida",
              type: "https://rentivo.com.br/problems/password_rejected"
            });
          }
          throw new TypeError("network unavailable");
        }
      },
      path: "/reset-password?token=reset-token"
    });

    await user.type(await screen.findByLabelText("Nova senha"), "new-password");
    await user.type(screen.getByLabelText("Confirmar nova senha"), "new-password");
    await user.click(screen.getByRole("button", { name: "Redefinir senha" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Escolha uma senha diferente.");

    await user.click(screen.getByRole("button", { name: "Redefinir senha" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível concluir a solicitação. Tente novamente."
    );
  });
});

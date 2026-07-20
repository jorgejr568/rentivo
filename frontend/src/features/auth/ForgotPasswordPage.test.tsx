import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, problemResponse } from "../../test/auth";
import { renderAuth } from "../../test/renderAuth";
import { ForgotPasswordPage } from "./ForgotPasswordPage";

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  delete window.dataLayer;
  delete window.turnstile;
  document.head.querySelectorAll("script[data-rentivo-gtm], script[data-rentivo-turnstile]").forEach((script) => script.remove());
});

describe("ForgotPasswordPage", () => {
  it("preserves the legacy guidance, form, focus, Turnstile, and title", async () => {
    renderAuth(<ForgotPasswordPage />, { path: "/forgot-password" });

    expect(
      await screen.findByText(
        "Informe o e-mail da sua conta. Se ele estiver cadastrado, enviaremos um link para redefinir a senha."
      )
    ).toBeVisible();
    expect(screen.getByLabelText("E-mail")).toHaveFocus();
    expect(screen.getByRole("button", { name: "Enviar link" })).toBeVisible();
    expect(screen.getByTestId("turnstile")).toBeVisible();
    expect(screen.getByRole("link", { name: "Voltar para o login" })).toHaveAttribute(
      "href",
      "/login"
    );
    expect(document.title).toBe("Esqueci minha senha - Rentivo");
  });

  it("uses the generated contract and shows the same non-enumerating success state", async () => {
    const user = userEvent.setup();
    renderAuth(<ForgotPasswordPage />, {
      handlers: {
        "/api/v1/auth/password/forgot": (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({
            email: "user@example.com",
            turnstile_token: ""
          });
          return jsonResponse(
            {
              analytics_events: [
                { event: "rentivo_password_reset_requested", reason: null, via: null }
              ],
              status: "accepted"
            },
            202
          );
        }
      },
      path: "/forgot-password"
    });

    await user.type(await screen.findByLabelText("E-mail"), " USER@EXAMPLE.COM ");
    await user.click(screen.getByRole("button", { name: "Enviar link" }));

    expect(
      await screen.findByText(
        "Se o e-mail estiver cadastrado, em instantes você receberá uma mensagem com instruções."
      )
    ).toHaveAttribute("role", "status");
    expect(screen.queryByRole("button", { name: "Enviar link" })).not.toBeInTheDocument();
    expect(window.dataLayer?.at(-1)).toEqual({
      event: "rentivo_password_reset_requested",
      reason: null,
      via: null
    });
  });

  it("shows security errors, restores focus, and resets Turnstile", async () => {
    const user = userEvent.setup();
    const reset = vi.fn();
    window.turnstile = { render: vi.fn().mockReturnValue("widget"), reset };
    renderAuth(<ForgotPasswordPage />, {
      handlers: {
        "/api/v1/auth/password/forgot": () =>
          problemResponse({
            code: "turnstile_failed",
            detail: "Verificação de segurança falhou. Tente novamente.",
            fields: {},
            request_id: "request-id",
            status: 400,
            title: "Requisição inválida",
            type: "https://rentivo.com.br/problems/turnstile_failed"
          })
      },
      path: "/forgot-password"
    });

    await user.type(await screen.findByLabelText("E-mail"), "user@example.com");
    await user.click(screen.getByRole("button", { name: "Enviar link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Verificação de segurança falhou. Tente novamente."
    );
    expect(screen.getByLabelText("E-mail")).toHaveFocus();
    expect(reset).toHaveBeenCalledWith("widget");
  });

  it("uses the generic message when the request fails before an API response", async () => {
    const user = userEvent.setup();
    renderAuth(<ForgotPasswordPage />, {
      handlers: {
        "/api/v1/auth/password/forgot": () => {
          throw new TypeError("network unavailable");
        }
      },
      path: "/forgot-password"
    });

    await user.type(await screen.findByLabelText("E-mail"), "user@example.com");
    await user.click(screen.getByRole("button", { name: "Enviar link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível concluir a solicitação. Tente novamente."
    );
  });

  it("redirects an existing authenticated session", async () => {
    renderAuth(<ForgotPasswordPage />, {
      path: "/forgot-password",
      session: "authenticated"
    });

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
  });
});

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AUTHENTICATED_RESPONSE, jsonResponse, problemResponse } from "../../test/auth";
import { renderAuth } from "../../test/renderAuth";
import { SignupPage } from "./SignupPage";

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  delete window.dataLayer;
  delete window.turnstile;
  document.head.querySelectorAll("script[data-rentivo-gtm], script[data-rentivo-turnstile]").forEach((script) => script.remove());
});

describe("SignupPage", () => {
  it("preserves the signup form, Google option, Turnstile, focus, and title", async () => {
    renderAuth(<SignupPage />, { path: "/signup" });

    expect(await screen.findByLabelText("E-mail")).toHaveFocus();
    expect(screen.getByLabelText("Senha")).toHaveClass("field-input");
    expect(screen.getByLabelText("Confirmar Senha")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Criar Conta" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Continuar com Google" })).toBeVisible();
    expect(screen.getByTestId("turnstile")).toBeVisible();
    expect(document.title).toBe("Criar Conta - Rentivo");
  });

  it("rejects mismatched passwords before calling the API", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderAuth(<SignupPage />, { path: "/signup" });

    await user.type(await screen.findByLabelText("E-mail"), "user@example.com");
    await user.type(screen.getByLabelText("Senha"), "password-one");
    await user.type(screen.getByLabelText("Confirmar Senha"), "password-two");
    await user.click(screen.getByRole("button", { name: "Criar Conta" }));

    expect(screen.getByRole("alert")).toHaveTextContent("As senhas não coincidem.");
    expect(screen.getByLabelText("E-mail")).toHaveFocus();
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/auth/signup")).toBe(false);
  });

  it("submits the generated signup contract and authenticates", async () => {
    const user = userEvent.setup();
    renderAuth(<SignupPage />, {
      handlers: {
        "/api/v1/auth/signup": (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({
            confirm_password: "correct-password",
            credential_transport: "cookie",
            email: "user@example.com",
            password: "correct-password",
            turnstile_token: ""
          });
          return jsonResponse(AUTHENTICATED_RESPONSE);
        }
      },
      path: "/signup"
    });

    await user.type(await screen.findByLabelText("E-mail"), " user@example.com ");
    await user.type(screen.getByLabelText("Senha"), "correct-password");
    await user.type(screen.getByLabelText("Confirmar Senha"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Criar Conta" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
  });

  it("shows duplicate-email errors, restores focus, and resets Turnstile", async () => {
    const user = userEvent.setup();
    const reset = vi.fn();
    window.turnstile = { render: vi.fn().mockReturnValue("widget"), reset };
    renderAuth(<SignupPage />, {
      handlers: {
        "/api/v1/auth/signup": () =>
          problemResponse({
            code: "email_already_registered",
            detail: "E-mail já cadastrado.",
            fields: {},
            request_id: "request-id",
            status: 400,
            title: "Requisição inválida",
            type: "https://rentivo.app/problems/email_already_registered"
          })
      },
      path: "/signup"
    });

    await user.type(await screen.findByLabelText("E-mail"), "user@example.com");
    await user.type(screen.getByLabelText("Senha"), "correct-password");
    await user.type(screen.getByLabelText("Confirmar Senha"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Criar Conta" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail já cadastrado.");
    expect(screen.getByLabelText("E-mail")).toHaveFocus();
    expect(reset).toHaveBeenCalledWith("widget");
  });

  it("shows the generic request error when no API response is available", async () => {
    const user = userEvent.setup();
    renderAuth(<SignupPage />, {
      handlers: {
        "/api/v1/auth/signup": () => {
          throw new TypeError("network unavailable");
        }
      },
      path: "/signup"
    });

    await user.type(await screen.findByLabelText("E-mail"), "user@example.com");
    await user.type(screen.getByLabelText("Senha"), "correct-password");
    await user.type(screen.getByLabelText("Confirmar Senha"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Criar Conta" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível concluir a solicitação. Tente novamente."
    );
  });
});

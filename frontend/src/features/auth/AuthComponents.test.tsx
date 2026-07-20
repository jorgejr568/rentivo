import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  AuthError,
  GoogleAuthLink,
  LoginAuthHeader,
  RentivoTitle,
  StandardAuthPanel,
  SubmitButton
} from "./AuthComponents";

describe("authentication components", () => {
  it("preserves the standard legacy panel and Rentivo title", () => {
    render(
      <StandardAuthPanel>
        <RentivoTitle />
        <p>Conteúdo</p>
      </StandardAuthPanel>
    );

    expect(screen.getByText("Conteúdo").closest(".panel-body")).toHaveStyle({
      padding: "2rem"
    });
    expect(screen.getByRole("heading", { name: /Ren\s*tivo/ })).toHaveClass("login-title");
  });

  it("preserves the dedicated login header", () => {
    render(<LoginAuthHeader />);

    expect(screen.getByText("R")).toHaveClass("auth-mark");
    expect(screen.getByRole("heading", { name: /Entrar no rent\s*ivo/ })).toBeVisible();
    expect(screen.getByText("Bem-vindo de volta.")).toBeVisible();
  });

  it("renders errors only when present", () => {
    const view = render(<AuthError message={null} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    view.rerender(<AuthError message="E-mail ou senha inválidos." />);
    expect(screen.getByRole("alert")).toHaveTextContent("E-mail ou senha inválidos.");
  });

  it("keeps submit labels stable while exposing loading state", () => {
    const view = render(<SubmitButton loading={false}>Entrar</SubmitButton>);
    expect(screen.getByRole("button", { name: "Entrar" })).toBeEnabled();

    view.rerender(<SubmitButton loading>Entrar</SubmitButton>);
    expect(screen.getByRole("button", { name: "Entrar" })).toBeDisabled();
    expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true");
  });

  it("uses the Google API start endpoint and legacy button copy", () => {
    render(<GoogleAuthLink />);

    expect(screen.getByRole("link", { name: "Continuar com Google" })).toHaveAttribute(
      "href",
      "/api/v1/auth/google/start"
    );
    expect(document.querySelector(".google-icon")).toBeInTheDocument();
  });
});

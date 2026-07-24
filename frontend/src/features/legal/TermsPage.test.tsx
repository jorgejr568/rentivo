import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";

import { TermsPage } from "./TermsPage";

it("renders the terms sections, contact address, and page title", () => {
  render(
    <MemoryRouter>
      <TermsPage />
    </MemoryRouter>
  );

  expect(
    screen.getByRole("heading", { level: 2, name: "Termos de Uso" })
  ).toBeVisible();
  expect(screen.getByRole("heading", { name: "Pagamentos" })).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Política de Privacidade" })
  ).toHaveAttribute("href", "/privacy");
  expect(
    screen.getByRole("link", { name: "suporte@rentivo.com.br" })
  ).toHaveAttribute("href", "mailto:suporte@rentivo.com.br");
  expect(document.title).toBe("Termos de Uso - Rentivo");
});

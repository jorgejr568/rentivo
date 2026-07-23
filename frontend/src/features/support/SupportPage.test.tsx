import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";

import { SupportPage } from "./SupportPage";

it("renders the support contact, legal links, and page title", () => {
  render(
    <MemoryRouter>
      <SupportPage />
    </MemoryRouter>
  );

  expect(screen.getByRole("heading", { level: 2, name: "Suporte" })).toBeVisible();
  expect(
    screen.getByRole("link", { name: "suporte@rentivo.com.br" })
  ).toHaveAttribute("href", "mailto:suporte@rentivo.com.br");
  expect(
    screen.getByRole("link", { name: "Política de Privacidade" })
  ).toHaveAttribute("href", "/privacy");
  expect(screen.getByRole("link", { name: "Termos de Uso" })).toHaveAttribute(
    "href",
    "/terms"
  );
  expect(document.title).toBe("Suporte - Rentivo");
});

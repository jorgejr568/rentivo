import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";

import { PrivacyPolicyPage } from "./PrivacyPolicyPage";

it("renders the privacy policy sections, contact address, and page title", () => {
  render(
    <MemoryRouter>
      <PrivacyPolicyPage />
    </MemoryRouter>
  );

  expect(
    screen.getByRole("heading", { level: 2, name: "Política de Privacidade" })
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Dados que coletamos" })
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Seus direitos (LGPD)" })
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "suporte@rentivo.com.br" })
  ).toHaveAttribute("href", "mailto:suporte@rentivo.com.br");
  expect(screen.getByRole("link", { name: "Termos de Uso" })).toHaveAttribute(
    "href",
    "/terms"
  );
  expect(document.title).toBe("Política de Privacidade - Rentivo");
});

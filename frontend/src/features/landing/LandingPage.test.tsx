import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { LandingPage } from "./LandingPage";

it("renders the public landing content and its primary paths", () => {
  render(<LandingPage />);

  expect(
    screen.getByRole("heading", { level: 1, name: /cobranças de aluguel.*pix em segundos/i })
  ).toBeVisible();
  expect(screen.getByRole("link", { name: "Criar conta gratuita" })).toHaveAttribute(
    "href",
    "/signup"
  );
  expect(screen.getAllByRole("link", { name: "GitHub" })[0]).toHaveAttribute(
    "href",
    "https://github.com/jorgejr568/rentivo"
  );
  expect(screen.getByRole("heading", { name: "Tudo que um locador precisa" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Três passos por mês" })).toBeVisible();
  expect(screen.getByRole("contentinfo")).toHaveTextContent(
    "Gestão de cobranças para imóveis."
  );
});

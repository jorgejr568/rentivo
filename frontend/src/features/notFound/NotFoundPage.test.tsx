import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { NotFoundPage } from "./NotFoundPage";

it("preserves the authenticated legacy not-found content", () => {
  render(
    <MemoryRouter>
      <NotFoundPage />
    </MemoryRouter>
  );

  expect(screen.getByText("404")).toBeVisible();
  expect(screen.getByRole("heading", { name: "Página não encontrada" })).toBeVisible();
  expect(screen.getByText("A página que você procura não existe ou foi movida.")).toBeVisible();
  expect(screen.getByRole("link", { name: "Voltar ao início" })).toHaveAttribute("href", "/billings/");
});

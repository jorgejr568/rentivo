import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { EmptyState, LoadError, LoadingState } from "./PageState";

describe("PageState", () => {
  it("announces a stable loading state", () => {
    render(<LoadingState label="Carregando cobranças..." />);

    expect(screen.getByRole("status")).toHaveTextContent("Carregando cobranças...");
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });

  it("shows a retryable load failure", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<LoadError message="Não foi possível carregar." onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível carregar.");
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders empty-state copy and an optional primary action", () => {
    render(
      <MemoryRouter>
        <EmptyState
          action={<Link className="btn btn--primary" to="/billings/create">Criar primeira cobrança</Link>}
          body="Você ainda não cadastrou nenhuma cobrança."
          title="Nenhuma cobrança"
        />
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Nenhuma cobrança" })).toBeVisible();
    expect(screen.getByText("Você ainda não cadastrou nenhuma cobrança.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Criar primeira cobrança" })).toHaveAttribute(
      "href",
      "/billings/create"
    );
  });

  it("supports informational empty states without an action", () => {
    render(<EmptyState body="Não há convites pendentes." title="Tudo certo" />);

    expect(screen.getByRole("heading", { name: "Tudo certo" })).toBeVisible();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

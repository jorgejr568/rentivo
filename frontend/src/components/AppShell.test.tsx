import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { AppShell } from "./AppShell";

describe("AppShell", () => {
  it("opens and closes the account menu with focus restored", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <AppShell currentPath="/billings/active" currentUser={{ email: "user@example.com" }} />
      </MemoryRouter>
    );

    const trigger = screen.getByRole("button", { name: /user@example.com/i });
    expect(screen.getByRole("link", { name: "Minhas Cobranças" })).toHaveClass("is-active");
    await user.click(trigger);

    expect(screen.getByRole("link", { name: "Segurança" })).toBeVisible();
    expect(trigger.closest(".topbar-dropdown")).toHaveClass("open");

    await user.keyboard("{Escape}");

    expect(trigger).toHaveFocus();
    expect(trigger.closest(".topbar-dropdown")).not.toHaveClass("open");
  });

  it("uses the browser location when no current path is supplied", () => {
    render(
      <MemoryRouter initialEntries={["/organizations/browser-path"]}>
        <AppShell currentUser={{ email: "user@example.com" }} />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: "Organizações" })).toHaveClass("is-active");
  });

  it("closes navigation menus after client-side route changes", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <AppShell currentUser={{ email: "user@example.com" }} />
      </MemoryRouter>
    );

    const mobileTrigger = screen.getByRole("button", { name: "Menu" });
    await user.click(mobileTrigger);
    await user.click(screen.getByRole("link", { name: "Minhas Cobranças" }));
    expect(mobileTrigger).toHaveAttribute("aria-expanded", "false");

    const accountTrigger = screen.getByRole("button", { name: /user@example.com/i });
    await user.click(accountTrigger);
    await user.click(screen.getByRole("link", { name: "Segurança" }));
    expect(accountTrigger).toHaveAttribute("aria-expanded", "false");
  });

  it("handles mobile navigation, outside menu closure, invites, toasts, and logout", async () => {
    const user = userEvent.setup();
    const onLogout = vi.fn();

    render(
      <MemoryRouter>
        <AppShell
          currentPath="/organizations/acme"
          currentUser={{ email: "user@example.com" }}
          pendingInviteCount={2}
          onLogout={onLogout}
          toasts={[{ category: "info", id: "saved", message: "Alterações salvas" }]}
        >
          <p>Conteúdo da página</p>
        </AppShell>
      </MemoryRouter>
    );

    await user.click(screen.getByRole("button", { name: "Menu" }));
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Organizações" })).toHaveClass("is-active");
    expect(screen.getByRole("link", { name: "Minhas Cobranças" })).not.toHaveClass("is-active");
    expect(screen.getByRole("alert")).toHaveClass("toast--info");

    const accountTrigger = screen.getByRole("button", { name: /user@example.com/i });
    await user.click(accountTrigger);
    expect(screen.getByText("2")).toBeVisible();
    await user.click(screen.getByText("Conteúdo da página"));
    expect(screen.queryByRole("link", { name: "Segurança" })).not.toBeInTheDocument();

    await user.click(accountTrigger);
    await user.click(screen.getByRole("button", { name: "Sair" }));
    expect(onLogout).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders its page content without authenticated navigation", () => {
    render(
      <MemoryRouter>
        <AppShell>
          <h1>Boas-vindas</h1>
        </AppShell>
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Boas-vindas" })).toBeVisible();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});

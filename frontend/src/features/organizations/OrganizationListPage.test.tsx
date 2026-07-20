import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { jsonResponse, problemResponse } from "../../test/auth";
import { OrganizationListPage } from "./OrganizationListPage";

type Organization = components["schemas"]["OrganizationResponse"];

const organization: Organization = {
  capabilities: { can_create_billing: false, can_invite: false, can_manage: false, can_view_billing_stats: false },
  created_at: "2026-07-18T10:00:00Z",
  current_role: "admin",
  enforce_mfa: true,
  name: "Ribeiro Imóveis",
  updated_at: "2026-07-18T11:00:00Z",
  uuid: "org-public-uuid"
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function installList(items: Organization[]) {
  vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ items })));
  return render(<MemoryRouter><OrganizationListPage /></MemoryRouter>);
}

it("renders the exact fresh-account organization state and restores the legacy title", async () => {
  document.title = "Anterior";
  let resolvePending!: (response: Response) => void;
  const pending = new Promise<Response>((resolve) => {
    resolvePending = resolve;
  });
  vi.stubGlobal("fetch", vi.fn(() => pending));
  const view = render(<MemoryRouter><OrganizationListPage /></MemoryRouter>);

  expect(screen.getByText("Carregando organizações...")).toBeVisible();
  resolvePending(jsonResponse({ items: [] }));

  expect(await screen.findByRole("heading", { name: "Organizações" })).toHaveClass("pagehead__title");
  expect(screen.getByText("Você não faz parte de nenhuma organização.")).toBeVisible();
  expect(screen.getByRole("link", { name: "Criar organização" })).toHaveAttribute("href", "/organizations/create");
  await waitFor(() => expect(document.title).toBe("Organizações - Rentivo"));
  view.unmount();
  expect(document.title).toBe("Anterior");
});

it("renders populated legacy cards without deriving controls from current_role", async () => {
  installList([organization]);

  const card = await screen.findByRole("link", { name: /Ribeiro Imóveis/ });
  expect(card).toHaveClass("org-card");
  expect(card).toHaveAttribute("href", "/organizations/org-public-uuid");
  expect(card.querySelector(".org-card__mark")).toHaveTextContent("R");
  expect(screen.getByText("Abrir organização")).toHaveClass("org-card__mfa");
  expect(screen.getByRole("link", { name: /Nova organização/ })).toHaveClass("btn--primary");
});

it("retries API and network failures", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  vi.stubGlobal("fetch", vi.fn(() => {
    attempts += 1;
    if (attempts === 1) {
      return problemResponse({
        code: "organizations_unavailable",
        detail: "Organizações indisponíveis.",
        fields: {},
        request_id: "request-id",
        status: 503,
        title: "Indisponível",
        type: "problem"
      });
    }
    if (attempts === 2) {
      throw new Error("offline");
    }
    return jsonResponse({ items: [organization] });
  }));
  render(<MemoryRouter><OrganizationListPage /></MemoryRouter>);

  expect(await screen.findByText("Organizações indisponíveis.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText("Não foi possível carregar as organizações.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  await waitFor(() => expect(screen.getByText("Ribeiro Imóveis")).toBeVisible());
});

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { BILLING_CAPABILITIES_ALL, jsonResponse, problemResponse } from "../../test/auth";
import { BillingCreatePage } from "./BillingCreatePage";

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
vi.mock("../auth/analytics", () => analytics);

type Billing = components["schemas"]["BillingResponse"];
type OrganizationList = components["schemas"]["OrganizationListResponse"];

const stats: components["schemas"]["BillingStatsResponse"] = {
  active_count: 0, billed_count: 0, expected: 0, net_income: 0, overdue: 0, overdue_count: 0,
  paid_count: 0, pending: 0, pending_count: 0, received: 0, total_expenses: 0, year: 2026
};
const organizationList: OrganizationList = {
  items: [{
    capabilities: { can_create_billing: true, can_invite: true, can_manage: true, can_view_billing_stats: true }, created_at: null,
    current_role: "admin", enforce_mfa: false, name: "Ribeiro Imóveis", updated_at: null, uuid: "org-public"
  }]
};
const created: Billing = {
  capabilities: BILLING_CAPABILITIES_ALL,
  communication_templates: [], created_at: "2026-07-18T12:00:00Z", description: "",
  items: [{ amount: 285_000, description: "Aluguel", item_type: "fixed", uuid: "item-created" }], name: "Apartamento 302",
  owner: { name: null, type: "user", uuid: null }, pix_key: "", pix_merchant_city: "", pix_merchant_name: "",
  pix_needs_setup: true, recipients: [], reply_to: [], stats, updated_at: "2026-07-18T12:00:00Z", uuid: "billing-created"
};

afterEach(() => {
  cleanup();
  analytics.pushAnalyticsFromResponse.mockReset();
  vi.unstubAllGlobals();
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

function installFetch(handlers: Record<string, (init?: RequestInit) => Response | Promise<Response>>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`Unexpected request: ${key}`);
    return handler(init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/billings/create"]}>
      <Routes>
        <Route element={<><BillingCreatePage /><LocationProbe /></>} path="/billings/create" />
        <Route element={<LocationProbe />} path="/billings/:billingUuid" />
      </Routes>
    </MemoryRouter>
  );
}

it("creates an integer-centavo personal billing while omitting untouched contact collections", async () => {
  const user = userEvent.setup();
  const fetchMock = installFetch({
    "GET /api/v1/organizations": () => jsonResponse(organizationList),
    "POST /api/v1/billings": (init) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toEqual({
        description: "", items: [{ amount: 285_000, description: "Aluguel", item_type: "fixed" }],
        name: "Apartamento 302", owner: { type: "user" }, pix_key: "", pix_merchant_city: "", pix_merchant_name: ""
      });
      expect(body).not.toHaveProperty("recipients");
      expect(body).not.toHaveProperty("reply_to");
      return jsonResponse(created, 201, { "X-Rentivo-Analytics-Event": "rentivo_billing_created" });
    }
  });
  document.title = "Anterior";
  const view = renderPage();

  expect(screen.getByText("Carregando formulário...")).toBeVisible();
  expect(await screen.findByRole("heading", { name: "Nova cobrança" })).toHaveClass("pagehead__title");
  expect(screen.getByRole("link", { name: "Minhas Cobranças" })).toHaveClass("crumb");
  expect(document.title).toBe("Nova cobrança - Rentivo");
  await user.type(screen.getByLabelText("Nome do imóvel"), "Apartamento 302");
  await user.type(screen.getByLabelText("Descrição do item 1"), "Aluguel");
  await user.type(screen.getByLabelText("Valor do item 1 (R$)"), "2.850,00");
  const createButton = screen.getByRole("button", { name: "Criar cobrança" });
  act(() => {
    createButton.click();
    createButton.click();
  });

  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-created"));
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(document.title).toBe("Anterior");
  view.unmount();
  expect(document.title).toBe("Anterior");
});

it("selects an organization and sends populated recipient, reply-to, fixed and variable rows", async () => {
  const user = userEvent.setup();
  installFetch({
    "GET /api/v1/organizations": () => jsonResponse(organizationList),
    "POST /api/v1/billings": (init) => {
      expect(JSON.parse(String(init?.body))).toEqual({
        description: "", items: [
          { amount: 0, description: "Água", item_type: "variable" },
          { amount: 100_050, description: "Condomínio", item_type: "fixed" }
        ], name: "Casa", owner: { type: "organization", uuid: "org-public" },
        pix_key: "", pix_merchant_city: "", pix_merchant_name: "",
        recipients: [{ email: "joao@example.com", name: "João" }],
        reply_to: [{ email: "ana@example.com", name: "Ana" }]
      });
      return jsonResponse({ ...created, uuid: "billing-org" }, 201);
    }
  });
  renderPage();
  await screen.findByLabelText("Nome do imóvel");
  await user.type(screen.getByLabelText("Nome do imóvel"), "Casa");
  await user.selectOptions(screen.getByLabelText("Proprietário"), "org-public");
  await user.type(screen.getByLabelText("Descrição do item 1"), "Água");
  await user.selectOptions(screen.getByLabelText("Tipo do item 1"), "variable");
  await user.click(screen.getByRole("button", { name: "Adicionar item" }));
  await user.type(screen.getByLabelText("Descrição do item 2"), "Condomínio");
  await user.type(screen.getByLabelText("Valor do item 2 (R$)"), "1.000,50");
  await user.click(screen.getByRole("button", { name: "Adicionar destinatário" }));
  await user.type(screen.getByLabelText("Nome do destinatário 1"), "João");
  await user.type(screen.getByLabelText("E-mail do destinatário 1"), "joao@example.com");
  await user.click(screen.getByRole("button", { name: "Adicionar Reply-To" }));
  await user.type(screen.getByLabelText("Nome do Reply-To 1"), "Ana");
  await user.type(screen.getByLabelText("E-mail do Reply-To 1"), "ana@example.com");
  await user.click(screen.getByRole("button", { name: "Criar cobrança" }));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-org"));
});

it("retries organization loading and normalizes body field errors with focus", async () => {
  const user = userEvent.setup();
  let gets = 0;
  let posts = 0;
  installFetch({
    "GET /api/v1/organizations": () => {
      gets += 1;
      if (gets === 1) throw new Error("offline");
      return jsonResponse(organizationList);
    },
    "POST /api/v1/billings": () => {
      posts += 1;
      if (posts === 1) return problemResponse({
        code: "validation_error", detail: "Confira os campos.",
        fields: { "body.items.0.amount": "Valor inválido.", "body.name": "Nome inválido." },
        request_id: "request-id", status: 422, title: "Dados inválidos", type: "problem"
      });
      if (posts === 2) return problemResponse({
        code: "invalid_billing", detail: "Cobrança recusada.", fields: {}, request_id: "request-id",
        status: 422, title: "Dados inválidos", type: "problem"
      });
      throw new Error("offline");
    }
  });
  renderPage();

  expect(await screen.findByText("Não foi possível carregar as organizações.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  await user.type(await screen.findByLabelText("Nome do imóvel"), "Casa");
  await user.type(screen.getByLabelText("Descrição do item 1"), "Aluguel");
  await user.click(screen.getByRole("button", { name: "Criar cobrança" }));
  expect(await screen.findByText("Nome inválido.")).toBeVisible();
  expect(screen.getByText("Valor inválido.")).toBeVisible();
  expect(screen.getByLabelText("Nome do imóvel")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Criar cobrança" }));
  expect(await screen.findByText("Cobrança recusada.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Criar cobrança" }));
  expect(await screen.findByText("Não foi possível criar a cobrança.")).toBeVisible();
  expect(screen.getByLabelText("Nome do imóvel")).toHaveFocus();
});

it("aborts a pending create and ignores its late response after cancellation", async () => {
  const user = userEvent.setup();
  let createCalls = 0;
  let createSignal: AbortSignal | undefined;
  let resolveCreate: ((response: Response) => void) | undefined;
  installFetch({
    "GET /api/v1/organizations": () => jsonResponse(organizationList),
    "POST /api/v1/billings": (init) => {
      createCalls += 1;
      createSignal = init?.signal as AbortSignal | undefined;
      return new Promise<Response>((resolve) => { resolveCreate = resolve; });
    }
  });
  render(<MemoryRouter initialEntries={["/billings/create"]}><Routes>
    <Route element={<><BillingCreatePage /><LocationProbe /></>} path="/billings/create" />
    <Route element={<LocationProbe />} path="/billings/" />
    <Route element={<LocationProbe />} path="/billings/:billingUuid" />
  </Routes></MemoryRouter>);

  await user.type(await screen.findByLabelText("Nome do imóvel"), "Casa");
  await user.type(screen.getByLabelText("Descrição do item 1"), "Aluguel");
  await user.click(screen.getByRole("button", { name: "Criar cobrança" }));
  await waitFor(() => expect(createCalls).toBe(1));
  await user.click(screen.getByRole("link", { name: "Cancelar" }));

  expect(screen.getByTestId("location")).toHaveTextContent("/billings/");
  expect(createSignal).toBeDefined();
  expect(createSignal?.aborted).toBe(true);
  await act(async () => { resolveCreate?.(jsonResponse(created, 201, { "X-Rentivo-Analytics-Event": "rentivo_billing_created" })); });
  expect(screen.getByTestId("location")).toHaveTextContent("/billings/");
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("ignores a late create failure after the page unmounts", async () => {
  const user = userEvent.setup();
  let rejectCreate: ((reason?: unknown) => void) | undefined;
  installFetch({
    "GET /api/v1/organizations": () => jsonResponse(organizationList),
    "POST /api/v1/billings": () => new Promise<Response>((_resolve, reject) => { rejectCreate = reject; })
  });
  render(<MemoryRouter initialEntries={["/billings/create"]}><Routes>
    <Route element={<><BillingCreatePage /><LocationProbe /></>} path="/billings/create" />
    <Route element={<LocationProbe />} path="/billings/" />
  </Routes></MemoryRouter>);

  await user.type(await screen.findByLabelText("Nome do imóvel"), "Casa");
  await user.type(screen.getByLabelText("Descrição do item 1"), "Aluguel");
  await user.click(screen.getByRole("button", { name: "Criar cobrança" }));
  await user.click(screen.getByRole("link", { name: "Cancelar" }));
  await act(async () => { rejectCreate?.(new Error("late failure")); });

  expect(screen.getByTestId("location")).toHaveTextContent("/billings/");
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

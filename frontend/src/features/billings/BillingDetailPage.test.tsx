import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { jsonResponse, problemResponse } from "../../test/auth";
import { BillingDetailPage } from "./BillingDetailPage";

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
vi.mock("../auth/analytics", () => analytics);

type Attachment = components["schemas"]["AttachmentResponse"];
type Bill = components["schemas"]["BillResponse"];
type ScopedBillingCapabilities = components["schemas"]["BillingCapabilitiesResponse"] & {
  can_create_bills: boolean;
  can_create_exports: boolean;
  can_manage_theme: boolean;
  can_read_attachments: boolean;
  can_read_bills: boolean;
  can_read_expenses: boolean;
  can_read_theme: boolean;
  can_upload_bill_receipts: boolean;
  can_write_attachments: boolean;
  can_write_expenses: boolean;
};
type Billing = Omit<components["schemas"]["BillingResponse"], "capabilities"> & { capabilities: ScopedBillingCapabilities };
type Expense = components["schemas"]["ExpenseResponse"];
type Organization = components["schemas"]["OrganizationResponse"];

const stats: components["schemas"]["BillingStatsResponse"] = {
  active_count: 2, billed_count: 6, expected: 900_000, net_income: 250_000, overdue: 100_000,
  overdue_count: 1, paid_count: 1, pending: 500_000, pending_count: 2, received: 300_000,
  total_expenses: 50_000, year: 2026
};
const billing: Billing = {
  capabilities: {
    can_create_bills: true, can_create_exports: true, can_delete: true, can_edit: true,
    can_manage_bills: true, can_manage_theme: true, can_read_attachments: true, can_read_bills: true,
    can_read_expenses: true, can_read_theme: true, can_transfer: true, can_upload_bill_receipts: true,
    can_write_attachments: true, can_write_expenses: true
  },
  communication_templates: [], created_at: null, description: "Inquilino atual",
  items: [{ amount: 285_000, description: "Aluguel", item_type: "fixed", uuid: "item-rent" }, { amount: 0, description: "Água", item_type: "variable", uuid: "item-water" }],
  name: "Apartamento 302", owner: { name: null, type: "user", uuid: null }, pix_key: "pix@example.com",
  pix_merchant_city: "SALVADOR", pix_merchant_name: "MARIA", pix_needs_setup: true,
  recipients: [], reply_to: [], stats, updated_at: null, uuid: "billing-public"
};
const billCapabilities: components["schemas"]["BillCapabilitiesResponse"] = {
  can_compose: true, can_delete: true, can_delete_receipts: true, can_download_invoice: true, can_download_recibo: true,
  can_edit: true, can_regenerate: true, can_reorder_receipts: true, can_send_invoice: true, can_send_recibo: true,
  can_transition: true, can_upload_receipts: true
};
function makeBill(status: string, index: number): Bill {
  return {
    available_transitions: [], capabilities: billCapabilities, created_at: null, due_date: index === 1 ? null : `2026-0${index + 1}-10`,
    has_invoice: true, has_recibo: false, line_items: [], notes: "", pdf_render_status: "ready",
    reference_month: `2026-0${index + 1}`, status, status_updated_at: null, total_amount: index * 10_000, uuid: `bill-${status}`
  };
}
const bills = ["draft", "published", "sent", "paid", "cancelled", "delayed_payment"].map(makeBill);
const expense: Expense = { amount: 120_000, category: "iptu", created_at: null, description: "IPTU 2026", incurred_on: "2026-01-10", uuid: "expense-public" };
const attachment: Attachment = { content_type: "application/pdf", created_at: null, file_size: 2048, filename: "contrato.pdf", name: "Contrato", sort_order: 0, uuid: "attachment-public" };
const organization: Organization = {
  capabilities: { can_create_billing: false, can_invite: false, can_manage: false, can_view_billing_stats: false }, created_at: null,
  current_role: "viewer", enforce_mfa: false, name: "Ribeiro Imóveis", updated_at: null, uuid: "org-public"
};

afterEach(() => {
  cleanup(); analytics.pushAnalyticsFromResponse.mockReset(); vi.unstubAllGlobals();
});

function LocationProbe() { const location = useLocation(); return <output data-testid="location">{location.pathname}</output>; }
function RouteSwitcher() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/billings/billing-second")} type="button">Trocar cobrança</button>;
}
function installFetch(handler: (key: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => handler(`${init?.method ?? "GET"} ${String(input)}`, init));
  vi.stubGlobal("fetch", fetchMock); return fetchMock;
}
function dataResponse(key: string, currentBilling = billing, currentBills = bills, currentExpenses = [expense], currentAttachments = [attachment], currentOrganizations = [organization]) {
  if (key === "GET /api/v1/billings/billing-public") return jsonResponse(currentBilling);
  if (key === "GET /api/v1/billings/billing-public/bills") return jsonResponse({ items: currentBills });
  if (key === "GET /api/v1/billings/billing-public/expenses") return jsonResponse({ items: currentExpenses });
  if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: currentAttachments });
  if (key === "GET /api/v1/organizations") return jsonResponse({ items: currentOrganizations });
  throw new Error(`Unexpected request: ${key}`);
}
function renderPage() {
  return render(<MemoryRouter initialEntries={["/billings/billing-public"]}><Routes>
    <Route element={<><BillingDetailPage /><LocationProbe /></>} path="/billings/:billingUuid" />
    <Route element={<LocationProbe />} path="/billings/" />
  </Routes></MemoryRouter>);
}

it("renders the populated legacy detail with PIX warning, every status, stats, expenses and downloads", async () => {
  installFetch((key) => dataResponse(key));
  document.title = "Anterior";
  const view = renderPage();

  expect(screen.getByText("Carregando cobrança...")).toBeVisible();
  expect(await screen.findByRole("heading", { name: "Apartamento 302" })).toHaveClass("pagehead__title");
  expect(screen.getByText("Inquilino atual")).toBeVisible();
  expect(screen.getByRole("button", { name: "Gerar fatura" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Gerar fatura" })).toHaveAttribute("title", "Configure os dados do PIX primeiro");
  expect(screen.getByRole("link", { name: "Tema" })).toHaveAttribute("href", "/themes/billing/billing-public");
  expect(screen.getByRole("link", { name: "Editar" })).toHaveAttribute("href", "/billings/billing-public/edit");
  expect(screen.getByText(/Os dados do PIX não estão configurados/)).toBeVisible();
  expect(screen.getByRole("link", { name: "Segurança" })).toHaveAttribute("href", "/security");
  expect(screen.getAllByText("R$ 2.850,00")).toHaveLength(2);
  expect(screen.getByText("por fatura")).toBeVisible();
  expect(screen.getByText("pix@example.com")).toBeVisible();
  expect(screen.getByText("PIX pendente")).toHaveClass("tag--draft");
  for (const status of ["Rascunho", "Publicado", "Enviado", "Pago", "Cancelado", "Pag. Atrasado"]) expect(screen.getByText(status)).toBeVisible();
  expect(screen.getByText("6 geradas")).toBeVisible();
  expect(screen.getByText("Recebido (ano)").nextSibling).toHaveTextContent("R$ 3.000,00");
  expect(screen.getByText("IPTU 2026")).toBeVisible();
  expect(screen.getByText("IPTU", { selector: "td" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Baixar" })).toHaveAttribute("href", "/api/v1/billings/billing-public/attachments/attachment-public");
  expect(screen.getByRole("heading", { name: "Transferir para organização" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Zona de perigo" })).toBeVisible();
  await waitFor(() => expect(document.title).toBe("Apartamento 302 - Rentivo"));
  view.unmount();
  expect(document.title).toBe("Anterior");
});

it("renders configured personal PIX fallbacks, first-invoice action, partial overrides and singular history", async () => {
  const configured: Billing = {
    ...billing,
    description: "",
    pix_key: "",
    pix_merchant_city: "",
    pix_merchant_name: "",
    pix_needs_setup: false
  };
  installFetch((key) => dataResponse(key, configured, [], [], [], []));
  renderPage();
  expect(await screen.findByText("Modelo de cobrança recorrente")).toBeVisible();
  expect(screen.getByRole("link", { name: "Gerar fatura" })).toHaveAttribute("href", "/billings/billing-public/bills/generate");
  expect(screen.getByRole("link", { name: "Gerar primeira fatura" })).toBeVisible();
  expect(screen.getByText("Sem override nesta cobrança — usa a configuração do proprietário (sua conta).")).toBeVisible();
  expect(screen.getByText("PIX configurado")).toHaveClass("tag--paid");

  cleanup();
  const partial = { ...configured, pix_merchant_name: "MARIA" };
  installFetch((key) => dataResponse(key, partial, [makeBill("paid", 0)], [], [], []));
  renderPage();
  expect(await screen.findByText("1 gerada")).toBeVisible();
  expect(screen.queryByText("Chave PIX (override)")).not.toBeInTheDocument();
  expect(screen.getByText("MARIA")).toBeVisible();
  expect(screen.getByText("Cidade").parentElement).toHaveTextContent("—");

  cleanup();
  const keyOnly = { ...configured, pix_key: "pix@example.com" };
  installFetch((key) => dataResponse(key, keyOnly, [], [], [], []));
  renderPage();
  expect(await screen.findByText("pix@example.com")).toBeVisible();
  expect(screen.getByText("Recebedor").parentElement).toHaveTextContent("—");
});

it("exports, creates and removes centavo expenses, forwards analytics and refreshes domain data", async () => {
  const user = userEvent.setup();
  let billingGets = 0;
  let expenseCreateCalls = 0;
  let expenseDeleteCalls = 0;
  let currentExpenses = [expense];
  let resolveExpenseCreate: ((response: Response) => void) | undefined;
  let resolveExpenseDelete: ((response: Response) => void) | undefined;
  installFetch((key, init) => {
    if (key === "GET /api/v1/billings/billing-public") { billingGets += 1; return jsonResponse(billing); }
    if (key === "GET /api/v1/billings/billing-public/bills") return jsonResponse({ items: bills });
    if (key === "GET /api/v1/billings/billing-public/expenses") return jsonResponse({ items: currentExpenses });
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [attachment] });
    if (key === "GET /api/v1/organizations") return jsonResponse({ items: [organization] });
    if (key === "POST /api/v1/billings/billing-public/exports") {
      const format = JSON.parse(String(init?.body)).format;
      return jsonResponse({ format, status: "queued" }, 202, { "X-Rentivo-Analytics-Event": "rentivo_data_exported" });
    }
    if (key === "POST /api/v1/billings/billing-public/expenses") {
      expenseCreateCalls += 1;
      expect(JSON.parse(String(init?.body))).toEqual({ amount: 12_050, category: "manutencao", description: "Pintura", incurred_on: "2026-07-18" });
      return new Promise<Response>((resolve) => { resolveExpenseCreate = resolve; });
    }
    if (key === "DELETE /api/v1/billings/billing-public/expenses/expense-new") {
      expenseDeleteCalls += 1;
      return new Promise<Response>((resolve) => { resolveExpenseDelete = resolve; });
    }
    throw new Error(`Unexpected request: ${key}`);
  });
  renderPage();
  await screen.findByText("IPTU 2026");

  await user.click(screen.getByRole("button", { name: "Exportar CSV" }));
  expect(await screen.findByText("Exportação CSV solicitada. O arquivo será enviado para o seu e-mail.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Exportar Excel" }));
  expect(await screen.findByText("Exportação XLSX solicitada. O arquivo será enviado para o seu e-mail.")).toBeVisible();
  await user.type(screen.getByLabelText("Descrição da despesa"), "Pintura");
  await user.selectOptions(screen.getByLabelText("Categoria da despesa"), "manutencao");
  fireEvent.change(screen.getByLabelText("Data da despesa"), { target: { value: "2026-07-18" } });
  await user.type(screen.getByLabelText("Valor da despesa (R$)"), "120,50");
  fireEvent.click(screen.getByRole("button", { name: "Adicionar despesa" }));
  fireEvent.click(screen.getByRole("button", { name: "Adicionar despesa" }));
  await waitFor(() => expect(expenseCreateCalls).toBe(1));
  expect(screen.getByRole("button", { name: "Adicionar despesa" })).toBeDisabled();
  currentExpenses = [...currentExpenses, { ...expense, amount: 12_050, category: "manutencao", description: "Pintura", incurred_on: "2026-07-18", uuid: "expense-new" }];
  await act(async () => {
    resolveExpenseCreate?.(jsonResponse(currentExpenses[1], 201, { "X-Rentivo-Analytics-Event": "rentivo_expense_created" }));
  });
  expect(await screen.findByText("Pintura")).toBeVisible();
  const row = screen.getByText("Pintura").closest("tr");
  expect(row).not.toBeNull();
  await user.click(within(row as HTMLElement).getByRole("button", { name: "Remover despesa Pintura" }));
  expect(screen.getByRole("dialog", { name: "Remover esta despesa?" })).toBeVisible();
  const confirmRemove = screen.getByRole("button", { name: "Remover" });
  fireEvent.click(confirmRemove);
  fireEvent.click(confirmRemove);
  await waitFor(() => expect(expenseDeleteCalls).toBe(1));
  expect(within(row as HTMLElement).getByRole("button", { name: "Remover despesa Pintura" })).toBeDisabled();
  currentExpenses = [expense];
  await act(async () => {
    resolveExpenseDelete?.(new Response(null, { status: 204, headers: { "X-Rentivo-Analytics-Event": "rentivo_expense_deleted" } }));
  });
  await waitFor(() => expect(screen.queryByText("Pintura")).not.toBeInTheDocument());
  expect(screen.getByText("Despesa removida.", { selector: '[role="status"]' })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Despesas" })).toHaveFocus();
  expect(billingGets).toBe(3);
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledTimes(4);
});

it("confirms transfer and uses the public organization UUID before navigating", async () => {
  const user = userEvent.setup();
  let transferCalls = 0;
  let resolveTransfer: ((response: Response) => void) | undefined;
  installFetch((key, init) => {
    if (key === "POST /api/v1/billings/billing-public/transfer") {
      expect(JSON.parse(String(init?.body))).toEqual({ organization_uuid: "org-public" });
      transferCalls += 1;
      return new Promise<Response>((resolve) => { resolveTransfer = resolve; });
    }
    return dataResponse(key);
  });
  renderPage();
  await screen.findByLabelText("Organização de destino");
  await user.selectOptions(screen.getByLabelText("Organização de destino"), "org-public");
  await user.click(screen.getByRole("button", { name: "Transferir" }));
  expect(screen.getByRole("dialog", { name: "Transferir cobrança?" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Voltar" }));
  expect(transferCalls).toBe(0);
  await user.click(screen.getByRole("button", { name: "Transferir" }));
  const confirmTransfer = screen.getByRole("button", { name: "Confirmar transferência" });
  fireEvent.click(confirmTransfer);
  fireEvent.click(confirmTransfer);
  await waitFor(() => expect(transferCalls).toBe(1));
  expect(screen.getByRole("button", { name: "Transferir" })).toBeDisabled();
  await act(async () => {
    resolveTransfer?.(new Response(null, { status: 204, headers: { "X-Rentivo-Analytics-Event": "rentivo_billing_transferred" } }));
  });
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("confirms destructive billing deletion and reports mutation failures", async () => {
  const user = userEvent.setup();
  let deleteAttempts = 0;
  let resolveDelete: ((response: Response) => void) | undefined;
  installFetch((key) => {
    if (key === "DELETE /api/v1/billings/billing-public") {
      deleteAttempts += 1;
      if (deleteAttempts === 1) throw new Error("offline");
      return new Promise<Response>((resolve) => { resolveDelete = resolve; });
    }
    return dataResponse(key);
  });
  renderPage();
  await screen.findByRole("button", { name: "Excluir cobrança" });
  await user.click(screen.getByRole("button", { name: "Excluir cobrança" }));
  expect(screen.getByRole("dialog", { name: "Excluir cobrança?" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Excluir cobrança permanentemente" }));
  expect(await screen.findByText("Não foi possível excluir a cobrança.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Excluir cobrança" }));
  const confirmDelete = screen.getByRole("button", { name: "Excluir cobrança permanentemente" });
  fireEvent.click(confirmDelete);
  fireEvent.click(confirmDelete);
  await waitFor(() => expect(deleteAttempts).toBe(2));
  expect(screen.getByRole("button", { name: "Excluir cobrança" })).toBeDisabled();
  await act(async () => {
    resolveDelete?.(new Response(null, { status: 204, headers: { "X-Rentivo-Analytics-Event": "rentivo_billing_deleted" } }));
  });
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/"));
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("reports export, expense-removal and transfer failures without forwarding analytics", async () => {
  const user = userEvent.setup();
  installFetch((key) => {
    if (key === "POST /api/v1/billings/billing-public/exports") throw new Error("offline");
    if (key === "DELETE /api/v1/billings/billing-public/expenses/expense-public") throw new Error("offline");
    if (key === "POST /api/v1/billings/billing-public/transfer") throw new Error("offline");
    return dataResponse(key);
  });
  renderPage();
  await screen.findByText("IPTU 2026");

  await user.click(screen.getByRole("button", { name: "Exportar CSV" }));
  expect(await screen.findByText("Não foi possível solicitar a exportação.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Remover despesa IPTU 2026" }));
  await user.click(screen.getByRole("button", { name: "Remover" }));
  expect(await screen.findByText("Não foi possível remover a despesa.")).toBeVisible();
  await user.selectOptions(screen.getByLabelText("Organização de destino"), "org-public");
  await user.click(screen.getByRole("button", { name: "Transferir" }));
  await user.click(screen.getByRole("button", { name: "Confirmar transferência" }));
  expect(await screen.findByText("Não foi possível transferir a cobrança.")).toBeVisible();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("retries loading, focuses expense field errors, and honors every denied capability in empty organization state", async () => {
  const user = userEvent.setup();
  let billingGets = 0;
  let expensePosts = 0;
  const denied: Billing = {
    ...billing,
    capabilities: {
      can_create_bills: false, can_create_exports: false, can_delete: false, can_edit: false,
      can_manage_bills: false, can_manage_theme: false, can_read_attachments: true, can_read_bills: true,
      can_read_expenses: true, can_read_theme: false, can_transfer: false, can_upload_bill_receipts: false,
      can_write_attachments: false, can_write_expenses: false
    },
    description: "", items: [{ amount: 0, description: "Água", item_type: "variable", uuid: "item-water" }],
    owner: { name: "Ribeiro Imóveis", type: "organization", uuid: "org-public" },
    pix_key: "", pix_merchant_city: "", pix_merchant_name: "", pix_needs_setup: true, stats: { ...stats, received: 0, total_expenses: 0, net_income: 0 }
  };
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") {
      billingGets += 1;
      if (billingGets === 1) throw new Error("offline");
      return jsonResponse(billingGets === 2 ? billing : denied);
    }
    if (key === "GET /api/v1/billings/billing-public/bills") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-public/expenses") return jsonResponse({ items: billingGets >= 3 ? [expense] : [] });
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/organizations") return jsonResponse({ items: [] });
    if (key === "POST /api/v1/billings/billing-public/expenses") {
      expensePosts += 1;
      if (expensePosts === 1) return problemResponse({ code: "validation_error", detail: "Valor inválido.", fields: { "body.amount": "Informe um valor válido." }, request_id: "request-id", status: 422, title: "Dados inválidos", type: "problem" });
      throw new Error("offline");
    }
    throw new Error(`Unexpected request: ${key}`);
  });
  renderPage();
  expect(await screen.findByText("Não foi possível carregar a cobrança.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  await screen.findByLabelText("Valor da despesa (R$)");
  await user.type(screen.getByLabelText("Descrição da despesa"), "Pintura");
  fireEvent.change(screen.getByLabelText("Data da despesa"), { target: { value: "2026-07-18" } });
  await user.type(screen.getByLabelText("Valor da despesa (R$)"), "abc");
  await user.click(screen.getByRole("button", { name: "Adicionar despesa" }));
  expect(await screen.findByText("Informe um valor válido.")).toBeVisible();
  expect(screen.getByLabelText("Valor da despesa (R$)")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Adicionar despesa" }));
  expect(await screen.findByText("Não foi possível adicionar a despesa.")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText("Modelo de cobrança recorrente · Organização")).toBeVisible();
  expect(screen.getByText("Sem override nesta cobrança — usa a configuração do proprietário (organização).")).toBeVisible();
  expect(screen.getByText("Nenhuma fatura gerada para este imóvel.")).toBeVisible();
  expect(screen.getByText("IPTU 2026")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Remover despesa IPTU 2026" })).not.toBeInTheDocument();
  expect(screen.getByText("Nenhum documento anexado.")).toBeVisible();
  expect(screen.queryByRole("link", { name: "Gerar primeira fatura" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Tema" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Editar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Adicionar despesa" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Transferir para organização" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Zona de perigo" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Organizações" })).toHaveAttribute("href", "/organizations/");
});

it("requests and renders each billing domain only when its precise capability allows it", async () => {
  const restricted: Billing = {
    ...billing,
    capabilities: {
      can_create_bills: false, can_create_exports: false, can_delete: false, can_edit: false,
      can_manage_bills: false, can_manage_theme: false, can_read_attachments: true, can_read_bills: false,
      can_read_expenses: false, can_read_theme: true, can_transfer: false, can_upload_bill_receipts: false,
      can_write_attachments: false, can_write_expenses: false
    },
    pix_needs_setup: false
  };
  const requests: string[] = [];
  installFetch((key) => {
    requests.push(key);
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(restricted);
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [attachment] });
    throw new Error(`Unexpected request: ${key}`);
  });

  renderPage();

  expect(await screen.findByRole("heading", { name: "Apartamento 302" })).toBeVisible();
  expect(requests).toEqual([
    "GET /api/v1/billings/billing-public",
    "GET /api/v1/billings/billing-public/attachments"
  ]);
  expect(screen.getByRole("link", { name: "Baixar" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Tema" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Faturas" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Despesas" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Exportar CSV" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Adicionar despesa" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Transferir para organização" })).not.toBeInTheDocument();

  cleanup();
  const writeOnly: Billing = {
    ...restricted,
    capabilities: {
      ...restricted.capabilities,
      can_create_bills: true,
      can_create_exports: true,
      can_manage_theme: true,
      can_read_attachments: false,
      can_read_theme: false,
      can_upload_bill_receipts: true,
      can_write_attachments: true,
      can_write_expenses: true
    }
  };
  requests.length = 0;
  installFetch((key) => {
    requests.push(key);
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(writeOnly);
    throw new Error(`Unexpected request: ${key}`);
  });

  renderPage();

  expect(await screen.findByRole("heading", { name: "Apartamento 302" })).toBeVisible();
  expect(requests).toEqual(["GET /api/v1/billings/billing-public"]);
  expect(screen.getByRole("link", { name: "Gerar fatura" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Exportar CSV" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Adicionar despesa" })).toBeVisible();
  expect(screen.queryByRole("link", { name: "Baixar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Tema" })).not.toBeInTheDocument();
});

it("hides route A immediately and rejects its late load after navigating to route B", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa B", uuid: "billing-second" };
  let resolveSecondBilling: ((response: Response) => void) | undefined;
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-second") return new Promise<Response>((resolve) => { resolveSecondBilling = resolve; });
    if (key === "GET /api/v1/billings/billing-second/bills") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/expenses") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    return dataResponse(key);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public"]}><Routes>
    <Route element={<><BillingDetailPage /><RouteSwitcher /></>} path="/billings/:billingUuid" />
  </Routes></MemoryRouter>);

  expect(await screen.findByRole("heading", { name: "Apartamento 302" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(screen.getByText("Carregando cobrança...")).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Apartamento 302" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Exportar CSV" })).not.toBeInTheDocument();

  resolveSecondBilling?.(jsonResponse(secondBilling));
  expect(await screen.findByRole("heading", { name: "Casa B" })).toBeVisible();
});

it("aborts a route A mutation and ignores its response after route B becomes active", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa B", uuid: "billing-second" };
  let exportSignal: AbortSignal | undefined;
  let resolveExport: ((response: Response) => void) | undefined;
  installFetch((key, init) => {
    if (key === "POST /api/v1/billings/billing-public/exports") {
      exportSignal = init?.signal as AbortSignal | undefined;
      return new Promise<Response>((resolve) => { resolveExport = resolve; });
    }
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/bills") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/expenses") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    return dataResponse(key);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public"]}><Routes>
    <Route element={<><BillingDetailPage /><RouteSwitcher /></>} path="/billings/:billingUuid" />
  </Routes></MemoryRouter>);

  await screen.findByRole("heading", { name: "Apartamento 302" });
  await user.click(screen.getByRole("button", { name: "Exportar CSV" }));
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByRole("heading", { name: "Casa B" })).toBeVisible();
  expect(exportSignal).toBeDefined();
  expect(exportSignal?.aborted).toBe(true);

  await act(async () => {
    resolveExport?.(jsonResponse({ format: "csv", status: "queued" }, 202, { "X-Rentivo-Analytics-Event": "rentivo_data_exported" }));
  });
  expect(screen.queryByText(/Exportação CSV solicitada/)).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("does not navigate or emit analytics when a transfer resolves after the route changes", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa B", uuid: "billing-second" };
  let transferSignal: AbortSignal | undefined;
  let resolveTransfer: ((response: Response) => void) | undefined;
  installFetch((key, init) => {
    if (key === "POST /api/v1/billings/billing-public/transfer") {
      transferSignal = init?.signal as AbortSignal | undefined;
      return new Promise<Response>((resolve) => { resolveTransfer = resolve; });
    }
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/bills") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/expenses") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    return dataResponse(key);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public"]}><Routes>
    <Route element={<><BillingDetailPage /><RouteSwitcher /><LocationProbe /></>} path="/billings/:billingUuid" />
    <Route element={<LocationProbe />} path="/billings/" />
  </Routes></MemoryRouter>);

  await screen.findByRole("heading", { name: "Apartamento 302" });
  await user.selectOptions(screen.getByLabelText("Organização de destino"), "org-public");
  await user.click(screen.getByRole("button", { name: "Transferir" }));
  await user.click(screen.getByRole("button", { name: "Confirmar transferência" }));
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByRole("heading", { name: "Casa B" })).toBeVisible();
  expect(transferSignal?.aborted).toBe(true);

  await act(async () => {
    resolveTransfer?.(new Response(null, { status: 204, headers: { "X-Rentivo-Analytics-Event": "rentivo_billing_transferred" } }));
  });
  expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-second");
  expect(screen.queryByRole("dialog", { name: "Transferir cobrança?" })).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("deduplicates exports and disables every domain mutation while one is pending", async () => {
  let exportCalls = 0;
  let resolveExport: ((response: Response) => void) | undefined;
  installFetch((key) => {
    if (key === "POST /api/v1/billings/billing-public/exports") {
      exportCalls += 1;
      return new Promise<Response>((resolve) => { resolveExport = resolve; });
    }
    return dataResponse(key);
  });
  renderPage();
  await screen.findByRole("button", { name: "Exportar CSV" });

  fireEvent.click(screen.getByRole("button", { name: "Remover despesa IPTU 2026" }));
  fireEvent.change(screen.getByLabelText("Organização de destino"), { target: { value: "org-public" } });
  fireEvent.click(screen.getByRole("button", { name: "Transferir" }));
  fireEvent.click(screen.getByRole("button", { name: "Excluir cobrança" }));
  const exportCsv = screen.getByRole("button", { name: "Exportar CSV" });
  const exportXlsx = screen.getByRole("button", { name: "Exportar Excel" });
  act(() => {
    exportCsv.click();
    exportXlsx.click();
  });

  await waitFor(() => expect(exportCalls).toBe(1));
  expect(screen.getByRole("button", { name: "Exportar CSV" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Exportar Excel" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Adicionar despesa" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Remover despesa IPTU 2026" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Transferir" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Excluir cobrança" })).toBeDisabled();
  fireEvent.submit(screen.getByRole("button", { name: "Adicionar despesa" }).closest("form")!);
  fireEvent.click(screen.getByRole("button", { name: "Remover" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirmar transferência" }));
  fireEvent.click(screen.getByRole("button", { name: "Excluir cobrança permanentemente" }));

  await act(async () => {
    resolveExport?.(jsonResponse({ format: "csv", status: "queued" }, 202));
  });
  await waitFor(() => expect(screen.getByRole("button", { name: "Exportar CSV" })).toBeEnabled());
});

it("ignores an expense creation response after the billing route changes", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa B", uuid: "billing-second" };
  let resolveCreate: ((response: Response) => void) | undefined;
  installFetch((key) => {
    if (key === "POST /api/v1/billings/billing-public/expenses") return new Promise<Response>((resolve) => { resolveCreate = resolve; });
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/bills") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/expenses") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    return dataResponse(key);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public"]}><Routes>
    <Route element={<><BillingDetailPage /><RouteSwitcher /></>} path="/billings/:billingUuid" />
  </Routes></MemoryRouter>);

  await screen.findByRole("button", { name: "Adicionar despesa" });
  fireEvent.submit(screen.getByRole("button", { name: "Adicionar despesa" }).closest("form")!);
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByRole("heading", { name: "Casa B" })).toBeVisible();
  await act(async () => { resolveCreate?.(jsonResponse(expense, 201)); });

  expect(screen.getByRole("heading", { name: "Casa B" })).toBeVisible();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("ignores an expense removal response after the billing route changes", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa B", uuid: "billing-second" };
  let resolveRemoval: ((response: Response) => void) | undefined;
  installFetch((key) => {
    if (key === "DELETE /api/v1/billings/billing-public/expenses/expense-public") return new Promise<Response>((resolve) => { resolveRemoval = resolve; });
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/bills") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/expenses") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    return dataResponse(key);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public"]}><Routes>
    <Route element={<><BillingDetailPage /><RouteSwitcher /></>} path="/billings/:billingUuid" />
  </Routes></MemoryRouter>);

  await screen.findByRole("button", { name: "Remover despesa IPTU 2026" });
  await user.click(screen.getByRole("button", { name: "Remover despesa IPTU 2026" }));
  await user.click(screen.getByRole("button", { name: "Remover" }));
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByRole("heading", { name: "Casa B" })).toBeVisible();
  await act(async () => { resolveRemoval?.(new Response(null, { status: 204 })); });

  expect(screen.queryByText("Despesa removida.")).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("ignores an expense removal after its refresh becomes stale", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa B", uuid: "billing-second" };
  let billingGets = 0;
  let resolveRefresh: ((response: Response) => void) | undefined;
  installFetch((key) => {
    if (key === "DELETE /api/v1/billings/billing-public/expenses/expense-public") return new Response(null, { status: 204 });
    if (key === "GET /api/v1/billings/billing-public") {
      billingGets += 1;
      if (billingGets === 2) return new Promise<Response>((resolve) => { resolveRefresh = resolve; });
      return jsonResponse(billing);
    }
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/bills") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/expenses") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    return dataResponse(key);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public"]}><Routes>
    <Route element={<><BillingDetailPage /><RouteSwitcher /></>} path="/billings/:billingUuid" />
  </Routes></MemoryRouter>);

  await screen.findByRole("button", { name: "Remover despesa IPTU 2026" });
  await user.click(screen.getByRole("button", { name: "Remover despesa IPTU 2026" }));
  await user.click(screen.getByRole("button", { name: "Remover" }));
  await waitFor(() => expect(billingGets).toBe(2));
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByRole("heading", { name: "Casa B" })).toBeVisible();
  await act(async () => { resolveRefresh?.(jsonResponse(billing)); });

  expect(screen.queryByText("Despesa removida.")).not.toBeInTheDocument();
});

it("does not navigate when billing deletion resolves after the route changes", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa B", uuid: "billing-second" };
  let resolveDelete: ((response: Response) => void) | undefined;
  installFetch((key) => {
    if (key === "DELETE /api/v1/billings/billing-public") return new Promise<Response>((resolve) => { resolveDelete = resolve; });
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/bills") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/expenses") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    return dataResponse(key);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public"]}><Routes>
    <Route element={<><BillingDetailPage /><RouteSwitcher /><LocationProbe /></>} path="/billings/:billingUuid" />
    <Route element={<LocationProbe />} path="/billings/" />
  </Routes></MemoryRouter>);

  await screen.findByRole("button", { name: "Excluir cobrança" });
  await user.click(screen.getByRole("button", { name: "Excluir cobrança" }));
  await user.click(screen.getByRole("button", { name: "Excluir cobrança permanentemente" }));
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByRole("heading", { name: "Casa B" })).toBeVisible();
  await act(async () => { resolveDelete?.(new Response(null, { status: 204 })); });

  expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-second");
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("rejects a late manual retry from route A after route B has loaded", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa B", uuid: "billing-second" };
  let publicBillingGets = 0;
  let resolvePublicRetry: ((response: Response) => void) | undefined;
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") {
      publicBillingGets += 1;
      if (publicBillingGets === 1) throw new Error("offline");
      return new Promise<Response>((resolve) => { resolvePublicRetry = resolve; });
    }
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/bills") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/expenses") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    return dataResponse(key);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public"]}><Routes>
    <Route element={<><BillingDetailPage /><RouteSwitcher /></>} path="/billings/:billingUuid" />
  </Routes></MemoryRouter>);

  expect(await screen.findByText("Não foi possível carregar a cobrança.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  await waitFor(() => expect(publicBillingGets).toBe(2));
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByRole("heading", { name: "Casa B" })).toBeVisible();

  await act(async () => {
    resolvePublicRetry?.(jsonResponse(billing));
  });
  expect(screen.getByRole("heading", { name: "Casa B" })).toBeVisible();
  expect(screen.queryByText("Carregando cobrança...")).not.toBeInTheDocument();
});

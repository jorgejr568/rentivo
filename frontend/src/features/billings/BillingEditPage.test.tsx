import { StrictMode } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { BILLING_CAPABILITIES_ALL, jsonResponse, problemResponse } from "../../test/auth";
import { BillingEditPage } from "./BillingEditPage";

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
vi.mock("../auth/analytics", () => analytics);

type Billing = components["schemas"]["BillingResponse"];
const stats: components["schemas"]["BillingStatsResponse"] = {
  active_count: 1, billed_count: 1, expected: 285_000, net_income: 0, overdue: 0, overdue_count: 0,
  paid_count: 0, pending: 285_000, pending_count: 1, received: 0, total_expenses: 0, year: 2026
};
const billing: Billing = {
  capabilities: BILLING_CAPABILITIES_ALL,
  communication_templates: [], created_at: null, description: "Inquilino atual",
  items: [{ amount: 285_000, description: "Aluguel", item_type: "fixed", uuid: "item-rent" }, { amount: 0, description: "Água", item_type: "variable", uuid: "item-water" }],
  name: "Apartamento 302", owner: { name: null, type: "user", uuid: null }, pix_key: "chave",
  pix_merchant_city: "SALVADOR", pix_merchant_name: "MARIA", pix_needs_setup: false,
  recipients: [{ email: "joao@example.com", name: "João", uuid: "recipient-full" }, { uuid: "recipient-reference" }],
  reply_to: [{ email: "ana@example.com", name: "Ana", uuid: "reply-full" }], stats, updated_at: null, uuid: "billing-public"
};
const attachment: components["schemas"]["AttachmentResponse"] = {
  content_type: "application/pdf", created_at: null, file_size: 1024, filename: "contrato.pdf",
  name: "Contrato", sort_order: 0, uuid: "attachment-public"
};

afterEach(() => {
  cleanup();
  analytics.pushAnalyticsFromResponse.mockReset();
  vi.unstubAllGlobals();
});

function LocationProbe() { const location = useLocation(); return <output data-testid="location">{location.pathname}</output>; }
function RouteSwitcher() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/billings/billing-second/edit")} type="button">Trocar cobrança</button>;
}
function installFetch(handler: (key: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => handler(`${init?.method ?? "GET"} ${String(input)}`, init));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
function renderPage() {
  return render(<MemoryRouter initialEntries={["/billings/billing-public/edit"]}><Routes>
    <Route element={<><BillingEditPage /><LocationProbe /></>} path="/billings/:billingUuid/edit" />
    <Route element={<LocationProbe />} path="/billings/:billingUuid" />
  </Routes></MemoryRouter>);
}

it("preserves opaque recipient references while explicitly replacing a fully visible reply-to collection", async () => {
  const user = userEvent.setup();
  let attachmentGets = 0;
  const fetchMock = installFetch((key, init) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(billing);
    if (key === "GET /api/v1/billings/billing-public/attachments") {
      attachmentGets += 1;
      return jsonResponse({ items: attachmentGets === 1 ? [] : [attachment] });
    }
    if (key === "POST /api/v1/billings/billing-public/attachments") return jsonResponse(attachment, 201);
    if (key === "PATCH /api/v1/billings/billing-public") {
      expect(JSON.parse(String(init?.body))).toEqual({
        description: "Inquilino atual", items: [
          { amount: 285_000, description: "Aluguel", item_type: "fixed", uuid: "item-rent" },
          { amount: 0, description: "Água", item_type: "variable", uuid: "item-water" },
          { amount: 50_000, description: "Garagem", item_type: "fixed" }
        ], name: "Apartamento 302", pix_key: "chave", pix_merchant_city: "SALVADOR", pix_merchant_name: "MARIA",
        reply_to: []
      });
      return jsonResponse({ ...billing, recipients: [], reply_to: [] }, 200, { "X-Rentivo-Analytics-Event": "rentivo_billing_edited" });
    }
    throw new Error(`Unexpected request: ${key}`);
  });
  document.title = "Anterior";
  const view = renderPage();

  expect(screen.getByText("Carregando cobrança...")).toBeVisible();
  expect(await screen.findByRole("heading", { name: "Editar cobrança" })).toHaveClass("pagehead__title");
  expect(screen.getByLabelText("Nome do imóvel")).toHaveValue("Apartamento 302");
  expect(screen.getAllByLabelText(/Nome do destinatário/)).toHaveLength(1);
  expect(screen.getByLabelText("Nome do destinatário 1")).toBeDisabled();
  expect(screen.getByText("Alguns destinatários estão ocultos. Esta lista não pode ser alterada com segurança.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Adicionar destinatário" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Remover destinatário 1" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Valor do item 1 (R$)")).toHaveValue("2.850,00");
  expect(screen.getByLabelText("Valor do item 2 (R$)")).toBeDisabled();
  await waitFor(() => expect(document.title).toBe("Editar Apartamento 302 - Rentivo"));
  await user.upload(screen.getByLabelText("Arquivo"), new File(["pdf"], "contrato.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar" }));
  expect(await screen.findByText("Contrato")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Adicionar item" }));
  await user.type(screen.getByLabelText("Descrição do item 3"), "Garagem");
  await user.type(screen.getByLabelText("Valor do item 3 (R$)"), "500,00");
  await user.click(screen.getByRole("button", { name: "Remover Reply-To 1" }));
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-public"));
  const requestKeys = fetchMock.mock.calls.map(([input, init]) => `${init?.method ?? "GET"} ${String(input)}`);
  expect(requestKeys.filter((key) => key === "GET /api/v1/billings/billing-public")).toHaveLength(1);
  expect(requestKeys.filter((key) => key === "GET /api/v1/billings/billing-public/attachments")).toHaveLength(2);
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledTimes(2);
  await waitFor(() => expect(document.title).toBe("Anterior"));
  view.unmount();
  expect(document.title).toBe("Anterior");
});

it("retries loading, normalizes edit errors, focuses controls and handles offline save", async () => {
  const user = userEvent.setup();
  let billingGets = 0;
  let patches = 0;
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") {
      billingGets += 1;
      if (billingGets === 1) throw new Error("offline");
      return jsonResponse(billing);
    }
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [] });
    if (key === "PATCH /api/v1/billings/billing-public") {
      patches += 1;
      if (patches === 1) return problemResponse({
        code: "validation_error", detail: "PIX inválido.", fields: { "body.pix_key": "Chave PIX inválida." },
        request_id: "request-id", status: 422, title: "Dados inválidos", type: "problem"
      });
      if (patches === 2) return problemResponse({
        code: "invalid_billing", detail: "Cobrança recusada.", fields: {}, request_id: "request-id",
        status: 422, title: "Dados inválidos", type: "problem"
      });
      throw new Error("offline");
    }
    throw new Error(`Unexpected request: ${key}`);
  });
  renderPage();
  expect(await screen.findByText("Não foi possível carregar a cobrança.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  await screen.findByLabelText("Chave PIX");
  await user.clear(screen.getByLabelText("Valor do item 1 (R$)"));
  await user.type(screen.getByLabelText("Valor do item 1 (R$)"), "abc");
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
  expect(await screen.findByText("Chave PIX inválida.")).toBeVisible();
  expect(screen.getByLabelText("Chave PIX")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
  expect(await screen.findByText("Cobrança recusada.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
  expect(await screen.findByText("Não foi possível atualizar a cobrança.")).toBeVisible();
  expect(screen.getByLabelText("Nome do imóvel")).toHaveFocus();
});

it("hides the edit form from a role-looking payload when capability denies editing", async () => {
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse({ ...billing, capabilities: { ...billing.capabilities, can_edit: false } });
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [] });
    throw new Error(`Unexpected request: ${key}`);
  });
  renderPage();
  expect(await screen.findByText("Você não tem permissão para editar esta cobrança.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Salvar alterações" })).not.toBeInTheDocument();
});

it("edits without requesting attachments and hides file controls when file scopes are absent", async () => {
  const fetchMock = installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse({
      ...billing,
      capabilities: {
        ...billing.capabilities,
        can_read_attachments: false,
        can_write_attachments: false
      }
    });
    throw new Error(`Unexpected request: ${key}`);
  });

  renderPage();

  expect(await screen.findByRole("heading", { name: "Editar cobrança" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Salvar alterações" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Documentos" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Arquivo")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledOnce();
});

it("shows readable attachments without upload or delete controls when files are read-only", async () => {
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse({
      ...billing,
      capabilities: { ...billing.capabilities, can_write_attachments: false }
    });
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [attachment] });
    throw new Error(`Unexpected request: ${key}`);
  });

  renderPage();

  expect(await screen.findByText("Contrato")).toBeVisible();
  expect(screen.getByRole("link", { name: "Ver" })).toBeVisible();
  expect(screen.queryByLabelText("Arquivo")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Remover documento Contrato" })).not.toBeInTheDocument();
});

it("uploads with files:write without attempting a forbidden attachment read", async () => {
  const user = userEvent.setup();
  const fetchMock = installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse({
      ...billing,
      capabilities: {
        ...billing.capabilities,
        can_read_attachments: false,
        can_write_attachments: true
      }
    });
    if (key === "POST /api/v1/billings/billing-public/attachments") return jsonResponse(attachment, 201);
    throw new Error(`Unexpected request: ${key}`);
  });

  renderPage();

  await user.upload(await screen.findByLabelText("Arquivo"), new File(["pdf"], "contrato.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar" }));

  expect(await screen.findByText("Documento enviado.")).toBeVisible();
  expect(fetchMock.mock.calls.map(([input, init]) => `${init?.method ?? "GET"} ${String(input)}`)).toEqual([
    "GET /api/v1/billings/billing-public",
    "POST /api/v1/billings/billing-public/attachments"
  ]);
});

it("discards StrictMode mount work and returns to loading when the billing route changes", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa 2", uuid: "billing-second" };
  let resolveSecondBilling: ((response: Response) => void) | undefined;
  const fetchMock = installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(billing);
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [] });
    if (key === "GET /api/v1/billings/billing-second") return new Promise<Response>((resolve) => { resolveSecondBilling = resolve; });
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    throw new Error(`Unexpected request: ${key}`);
  });

  render(<StrictMode><MemoryRouter initialEntries={["/billings/billing-public/edit"]}><Routes>
    <Route element={<><BillingEditPage /><RouteSwitcher /></>} path="/billings/:billingUuid/edit" />
  </Routes></MemoryRouter></StrictMode>);

  expect(await screen.findByDisplayValue("Apartamento 302")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(screen.getByText("Carregando cobrança...")).toBeVisible();
  await act(async () => { resolveSecondBilling?.(jsonResponse(secondBilling)); });
  expect(await screen.findByDisplayValue("Casa 2")).toBeVisible();

  const requestKeys = fetchMock.mock.calls.map(([input, init]) => `${init?.method ?? "GET"} ${String(input)}`);
  expect(requestKeys.filter((key) => key === "GET /api/v1/billings/billing-public")).toHaveLength(2);
  expect(requestKeys.filter((key) => key === "GET /api/v1/billings/billing-second")).toHaveLength(1);
});

it("keeps generic attachment errors out of billing-form focus handling", async () => {
  const user = userEvent.setup();
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(billing);
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [] });
    if (key === "POST /api/v1/billings/billing-public/attachments") throw new Error("offline");
    throw new Error(`Unexpected request: ${key}`);
  });
  renderPage();
  await screen.findByLabelText("Arquivo");

  await user.upload(screen.getByLabelText("Arquivo"), new File(["pdf"], "contrato.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar" }));

  expect(await screen.findByText("Não foi possível enviar o documento.")).toBeVisible();
  expect(screen.getByLabelText("Nome do imóvel")).not.toHaveFocus();
});

it("omits an opaque reply-to collection while preserving editable recipients", async () => {
  const user = userEvent.setup();
  const opaqueReplyBilling: Billing = {
    ...billing,
    recipients: [{ email: "joao@example.com", name: "João", uuid: "recipient-full" }],
    reply_to: [{ email: "ana@example.com", name: "Ana", uuid: "reply-full" }, { uuid: "reply-reference" }]
  };
  installFetch((key, init) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(opaqueReplyBilling);
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [] });
    if (key === "PATCH /api/v1/billings/billing-public") {
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      expect(body.recipients).toEqual([{ email: "joao@example.com", name: "João" }]);
      expect(body).not.toHaveProperty("reply_to");
      return jsonResponse(opaqueReplyBilling);
    }
    throw new Error(`Unexpected request: ${key}`);
  });
  renderPage();

  expect(await screen.findByText("Alguns endereços Reply-To estão ocultos. Esta lista não pode ser alterada com segurança.")).toBeVisible();
  expect(screen.getByLabelText("Nome do Reply-To 1")).toBeDisabled();
  expect(screen.getByLabelText("Nome do destinatário 1")).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-public"));
});

it("aborts a pending save and ignores its late response after switching billing routes", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa 2", uuid: "billing-second" };
  let patchCalls = 0;
  let patchSignal: AbortSignal | undefined;
  let resolvePatch: ((response: Response) => void) | undefined;
  installFetch((key, init) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(billing);
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [] });
    if (key === "PATCH /api/v1/billings/billing-public") {
      patchCalls += 1;
      patchSignal = init?.signal as AbortSignal | undefined;
      return new Promise<Response>((resolve) => { resolvePatch = resolve; });
    }
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    throw new Error(`Unexpected request: ${key}`);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public/edit"]}><Routes>
    <Route element={<><BillingEditPage /><RouteSwitcher /><LocationProbe /></>} path="/billings/:billingUuid/edit" />
    <Route element={<LocationProbe />} path="/billings/:billingUuid" />
  </Routes></MemoryRouter>);

  const saveButton = await screen.findByRole("button", { name: "Salvar alterações" });
  act(() => {
    saveButton.click();
    saveButton.click();
  });
  await waitFor(() => expect(patchCalls).toBe(1));
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByDisplayValue("Casa 2")).toBeVisible();
  expect(patchSignal).toBeDefined();
  expect(patchSignal?.aborted).toBe(true);

  await act(async () => { resolvePatch?.(jsonResponse(billing, 200, { "X-Rentivo-Analytics-Event": "rentivo_billing_edited" })); });
  expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-second/edit");
  expect(screen.getByDisplayValue("Casa 2")).toBeVisible();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("ignores a late save failure after switching billing routes", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa 2", uuid: "billing-second" };
  let rejectPatch: ((reason?: unknown) => void) | undefined;
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(billing);
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [] });
    if (key === "PATCH /api/v1/billings/billing-public") return new Promise<Response>((_resolve, reject) => { rejectPatch = reject; });
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    throw new Error(`Unexpected request: ${key}`);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public/edit"]}><Routes>
    <Route element={<><BillingEditPage /><RouteSwitcher /></>} path="/billings/:billingUuid/edit" />
  </Routes></MemoryRouter>);

  await user.click(await screen.findByRole("button", { name: "Salvar alterações" }));
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByDisplayValue("Casa 2")).toBeVisible();
  await act(async () => { rejectPatch?.(new Error("late failure")); });

  expect(screen.queryByText("Não foi possível atualizar a cobrança.")).not.toBeInTheDocument();
  expect(screen.getByDisplayValue("Casa 2")).toBeVisible();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("aborts an attachment refresh and rejects its late route-A payload on route B", async () => {
  const user = userEvent.setup();
  const secondBilling = { ...billing, name: "Casa 2", uuid: "billing-second" };
  let attachmentGets = 0;
  let refreshSignal: AbortSignal | undefined;
  let resolveRefresh: ((response: Response) => void) | undefined;
  installFetch((key, init) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(billing);
    if (key === "GET /api/v1/billings/billing-public/attachments") {
      attachmentGets += 1;
      if (attachmentGets === 1) return jsonResponse({ items: [] });
      refreshSignal = init?.signal as AbortSignal | undefined;
      return new Promise<Response>((resolve) => { resolveRefresh = resolve; });
    }
    if (key === "POST /api/v1/billings/billing-public/attachments") return jsonResponse(attachment, 201);
    if (key === "GET /api/v1/billings/billing-second") return jsonResponse(secondBilling);
    if (key === "GET /api/v1/billings/billing-second/attachments") return jsonResponse({ items: [] });
    throw new Error(`Unexpected request: ${key}`);
  });
  render(<MemoryRouter initialEntries={["/billings/billing-public/edit"]}><Routes>
    <Route element={<><BillingEditPage /><RouteSwitcher /></>} path="/billings/:billingUuid/edit" />
  </Routes></MemoryRouter>);

  await user.upload(await screen.findByLabelText("Arquivo"), new File(["pdf"], "contrato.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar" }));
  await waitFor(() => expect(attachmentGets).toBe(2));
  await user.click(screen.getByRole("button", { name: "Trocar cobrança" }));
  expect(await screen.findByDisplayValue("Casa 2")).toBeVisible();
  expect(refreshSignal).toBeDefined();
  expect(refreshSignal?.aborted).toBe(true);

  await act(async () => { resolveRefresh?.(jsonResponse({ items: [attachment] })); });
  expect(screen.queryByText("Contrato")).not.toBeInTheDocument();
  expect(screen.queryByText("Não foi possível atualizar a lista de documentos.")).not.toBeInTheDocument();
});

it("normalizes item UUID errors, renders them in the row and focuses that row", async () => {
  const user = userEvent.setup();
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(billing);
    if (key === "GET /api/v1/billings/billing-public/attachments") return jsonResponse({ items: [] });
    if (key === "PATCH /api/v1/billings/billing-public") return problemResponse({
      code: "stale_billing_item", detail: "Item desatualizado.",
      fields: { "body.items.1.uuid": "Este item foi alterado ou removido." },
      request_id: "request-id", status: 409, title: "Conflito", type: "problem"
    });
    throw new Error(`Unexpected request: ${key}`);
  });
  renderPage();

  await user.click(await screen.findByRole("button", { name: "Salvar alterações" }));
  expect(await screen.findByText("Este item foi alterado ou removido.")).toBeVisible();
  expect(screen.getByLabelText("Descrição do item 2")).toHaveFocus();
  expect(screen.getByLabelText("Descrição do item 2")).toHaveAccessibleDescription("Este item foi alterado ou removido.");
});

it("reports an attachment refresh failure while the edit route remains current", async () => {
  const user = userEvent.setup();
  let attachmentGets = 0;
  installFetch((key) => {
    if (key === "GET /api/v1/billings/billing-public") return jsonResponse(billing);
    if (key === "GET /api/v1/billings/billing-public/attachments") {
      attachmentGets += 1;
      if (attachmentGets === 1) return jsonResponse({ items: [] });
      throw new Error("refresh offline");
    }
    if (key === "POST /api/v1/billings/billing-public/attachments") return jsonResponse(attachment, 201);
    throw new Error(`Unexpected request: ${key}`);
  });
  renderPage();

  await user.upload(await screen.findByLabelText("Arquivo"), new File(["pdf"], "contrato.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar" }));

  expect(await screen.findByText("Não foi possível atualizar a lista de documentos.")).toBeVisible();
  expect(screen.getByText("Documento enviado.", { selector: '[role="status"]' })).toBeVisible();
});

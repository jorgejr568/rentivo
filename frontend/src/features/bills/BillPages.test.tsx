import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { BILLING_CAPABILITIES_ALL, jsonResponse, problemResponse } from "../../test/auth";
import { BillDetailPage } from "./BillDetailPage";
import { BillEditPage } from "./BillEditPage";
import { CommunicationComposePage } from "./CommunicationComposePage";

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
vi.mock("../auth/analytics", () => analytics);

type Billing = components["schemas"]["BillingResponse"];
type Bill = components["schemas"]["BillDetailResponse"];

const capabilities: components["schemas"]["BillCapabilitiesResponse"] = {
  can_compose: true,
  can_delete: true, can_delete_receipts: true, can_download_invoice: true,
  can_download_recibo: true, can_edit: true, can_regenerate: true,
  can_reorder_receipts: true, can_send_invoice: true, can_send_recibo: true,
  can_transition: true, can_upload_receipts: true
};
const billing: Billing = {
  capabilities: { ...BILLING_CAPABILITIES_ALL, can_transfer: false },
  communication_templates: [
    { body: "Olá {{nome_inquilino}}", comm_type: "bill_ready", subject: "Fatura de julho" },
    { body: "Segue recibo", comm_type: "payment_receipt", subject: "Recibo de julho" }
  ],
  created_at: null, description: "Apartamento 302",
  items: [{ amount: 250000, description: "Aluguel", item_type: "fixed", uuid: "01J00000000000000000000010" }],
  name: "Residencial Sol", owner: { type: "organization", uuid: "org-uuid", name: "Sol Imóveis" },
  pix_key: "financeiro@example.com", pix_merchant_city: "SALVADOR", pix_merchant_name: "SOL IMOVEIS",
  pix_needs_setup: false,
  recipients: [
    { email: "ana@example.com", name: "Ana", uuid: "recipient-ana" },
    { uuid: "recipient-redacted" }
  ],
  reply_to: [],
  stats: { active_count: 1, billed_count: 1, expected: 250000, net_income: 250000, overdue: 0, overdue_count: 0, paid_count: 1, pending: 0, pending_count: 0, received: 250000, total_expenses: 0, year: 2026 },
  updated_at: null, uuid: "billing-public-uuid"
};
const bill: Bill = {
  available_transitions: [], capabilities,
  communications: [
    { comm_type: "bill_ready", created_at: "2026-07-18T10:00:00Z", recipient_email: "ana@example.com", recipient_name: "Ana", sent_at: "2026-07-18T10:01:00Z", status: "sent", subject: "Fatura", uuid: "comm-full" },
    { comm_type: "bill_ready", created_at: "2026-07-18T11:00:00Z", sent_at: null, status: "queued", uuid: "comm-redacted" },
    { comm_type: "bill_ready", created_at: null, recipient_email: "bia@example.com", recipient_name: "Bia", sent_at: null, status: "failed", subject: "Falha", uuid: "comm-failed" }
  ],
  created_at: "2026-07-18T09:00:00Z", due_date: "2026-08-10", has_invoice: true, has_recibo: true,
  line_items: [
    { amount: 250000, description: "Aluguel", item_type: "fixed", sort_order: 0 },
    { amount: 1250, description: "Gás", item_type: "extra", sort_order: 1 }
  ],
  notes: "Obrigado", pdf_render_status: null, receipts: [], reference_month: "2026-07",
  status: "paid", status_updated_at: "2026-07-18T10:00:00Z", total_amount: 251250,
  uuid: "bill-public-uuid"
};
const secondBilling: Billing = { ...billing, name: "Residencial Lua", uuid: "billing-second" };
const secondBill: Bill = { ...bill, reference_month: "2026-08", uuid: "bill-second" };

afterEach(() => {
  cleanup();
  analytics.pushAnalyticsFromResponse.mockReset();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function ComposeRouteSwitch() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/billings/billing-second/bills/bill-second/communications/compose?type=bill_ready")} type="button">Trocar comunicação</button>;
}

function BillRouteSwitch({ edit = false }: { edit?: boolean }) {
  const navigate = useNavigate();
  return <button onClick={() => navigate(`/billings/billing-second/bills/bill-second${edit ? "/edit" : ""}`)} type="button">Trocar fatura</button>;
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

function renderAt(element: React.ReactElement, path: string, routePath: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<>{element}<LocationProbe /></>} path={routePath} />
        <Route element={<LocationProbe />} path="/billings/:billingUuid" />
        <Route element={<LocationProbe />} path="/billings/:billingUuid/bills/:billUuid" />
      </Routes>
    </MemoryRouter>
  );
}

const detailHandlers = () => ({
  "GET /api/v1/billings/billing-public-uuid": () => jsonResponse(billing),
  "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => jsonResponse(bill)
});

const secondDetailHandlers = () => ({
  "GET /api/v1/billings/billing-second": () => jsonResponse(secondBilling),
  "GET /api/v1/billings/billing-second/bills/bill-second": () => jsonResponse(secondBill)
});

it("renders invoice detail, item types, QR/PDF/recibo links, capabilities, and redacted history", async () => {
  installFetch(detailHandlers());
  document.title = "Anterior";
  const view = renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");

  expect(screen.getByText("Carregando fatura...")).toBeVisible();
  expect(await screen.findByRole("heading", { name: "Fatura · Julho/2026" })).toHaveClass("pagehead__title");
  expect(screen.getByRole("link", { name: "Residencial Sol" })).toHaveClass("crumb");
  expect(screen.getAllByText("R$ 2.512,50")).toHaveLength(2);
  expect(screen.getByText("Extra")).toHaveClass("tag--extra");
  expect(screen.getByRole("link", { name: "Abrir PDF com QR" })).toHaveAttribute("href", "/api/v1/billings/billing-public-uuid/bills/bill-public-uuid/invoice");
  expect(screen.getByRole("link", { name: "Baixar recibo" })).toHaveAttribute("href", "/api/v1/billings/billing-public-uuid/bills/bill-public-uuid/recibo/download");
  expect(screen.getByRole("button", { name: /Baixar/ })).toHaveClass("btn-dropdown-toggle");
  expect(screen.getByRole("button", { name: /Enviar comunicação/ })).toHaveClass("btn-dropdown-toggle");
  expect(screen.getByRole("link", { name: "Enviar fatura" })).toHaveAttribute("href", "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready");
  expect(screen.getByRole("link", { name: "Enviar recibo" })).toHaveAttribute("href", "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=payment_receipt");
  expect(screen.getByRole("link", { name: "Editar" })).toHaveAttribute("href", "/billings/billing-public-uuid/bills/bill-public-uuid/edit");
  expect(screen.getByText("Ana <ana@example.com>")).toBeVisible();
  expect(screen.getByText("Dados do destinatário protegidos")).toBeVisible();
  expect(screen.getByText("Falhou")).toHaveClass("tag--cancelled");
  await waitFor(() => expect(document.title).toBe("Fatura Julho/2026 - Rentivo"));
  view.unmount();
  expect(document.title).toBe("Anterior");
});

it("toggles one legacy action dropdown at a time and closes it accessibly", async () => {
  const user = userEvent.setup();
  installFetch(detailHandlers());
  renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });

  const download = screen.getByRole("button", { name: /Baixar/ });
  const communication = screen.getByRole("button", { name: /Enviar comunicação/ });
  const downloadDropdown = download.closest(".btn-dropdown")!;
  const communicationDropdown = communication.closest(".btn-dropdown")!;
  expect(download).toHaveAttribute("aria-expanded", "false");
  expect(download).toHaveAttribute("aria-controls", "bill-download-menu");
  expect(download).not.toHaveAttribute("aria-haspopup");
  expect(communication).not.toHaveAttribute("aria-haspopup");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(screen.queryByRole("menuitem")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Baixar fatura" })).toBeInTheDocument();

  await user.click(download);
  expect(downloadDropdown).toHaveClass("open");
  expect(download).toHaveAttribute("aria-expanded", "true");
  fireEvent.keyDown(document, { key: "ArrowDown" });
  expect(downloadDropdown).toHaveClass("open");
  await user.click(download);
  expect(downloadDropdown).not.toHaveClass("open");
  await user.click(download);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(downloadDropdown).not.toHaveClass("open");
  expect(download).toHaveFocus();

  await user.click(download);
  await user.click(communication);
  expect(downloadDropdown).not.toHaveClass("open");
  expect(download).toHaveAttribute("aria-expanded", "false");
  expect(communicationDropdown).toHaveClass("open");
  expect(communication).toHaveAttribute("aria-expanded", "true");
  await user.click(communication);
  expect(communicationDropdown).not.toHaveClass("open");
  await user.click(communication);

  fireEvent.keyDown(document, { key: "Escape" });
  expect(communicationDropdown).not.toHaveClass("open");
  expect(communication).toHaveAttribute("aria-expanded", "false");
  expect(communication).toHaveFocus();

  await user.click(download);
  fireEvent.click(document.body);
  expect(downloadDropdown).not.toHaveClass("open");
});

it.each([
  ["signed S3", "https://storage.example.com/private/signed-recibo.pdf"],
  ["same-origin content", "/api/v1/billings/billing-public-uuid/bills/bill-public-uuid/recibo/content"]
] as const)("downloads a %s recibo URL through one typed handshake", async (_kind, downloadUrl) => {
  const user = userEvent.setup();
  const clicked: Array<{ download: string; href: string }> = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push({ download: this.download, href: this.href });
  });
  const fetchMock = installFetch({
    ...detailHandlers(),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/recibo/download": () => jsonResponse(
      { download_url: downloadUrl, filename: "recibo-julho.pdf" },
      200,
      {
        "X-Rentivo-Analytics-Event": "rentivo_recibo_downloaded",
        "X-Rentivo-Analytics-Bill-Uuid-Hash": "bill-hash"
      }
    )
  });
  renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });
  const createElement = vi.spyOn(document, "createElement");

  await user.click(screen.getByRole("link", { name: "Baixar recibo" }));

  await waitFor(() => expect(clicked).toEqual([{
    download: "recibo-julho.pdf",
    href: new URL(downloadUrl, window.location.href).href
  }]));
  expect(createElement.mock.calls.filter(([tagName]) => tagName === "a")).toHaveLength(1);
  const receiptRequests = fetchMock.mock.calls
    .map(([input]) => String(input))
    .filter((url) => url.includes("/recibo"));
  expect(receiptRequests).toEqual([
    "/api/v1/billings/billing-public-uuid/bills/bill-public-uuid/recibo/download"
  ]);
  expect(receiptRequests).not.toContain(
    "/api/v1/billings/billing-public-uuid/bills/bill-public-uuid/recibo"
  );
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("reports a failed recibo handshake and restores the download control", async () => {
  const user = userEvent.setup();
  let settle!: (response: Response) => void;
  const pending = new Promise<Response>((resolve) => { settle = resolve; });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  installFetch({
    ...detailHandlers(),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/recibo/download": () => pending
  });
  renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });
  const download = screen.getByRole("link", { name: "Baixar recibo" });

  await user.click(download);
  expect(download).toHaveAttribute("aria-disabled", "true");
  settle(problemResponse({ code: "download_failed", detail: "Recibo indisponível.", fields: {}, request_id: "req", status: 503, title: "Erro", type: "problem" }));

  expect(await screen.findByText("Não foi possível baixar o recibo.")).toBeVisible();
  await waitFor(() => expect(download).not.toHaveAttribute("aria-disabled"));
  expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it.each(["resolve", "reject"] as const)("discards a recibo download that %s after the route changes", async (outcome) => {
  const user = userEvent.setup();
  const mutation = { signal: null as AbortSignal | null };
  let settle!: () => void;
  const pending = new Promise<Response>((resolve, reject) => {
    settle = outcome === "resolve"
      ? () => resolve(jsonResponse(
        { download_url: "https://storage.example.com/private/stale.pdf", filename: "stale.pdf" },
        200,
        { "X-Rentivo-Analytics-Event": "stale_download" }
      ))
      : () => reject(new Error("stale download"));
  });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  installFetch({
    ...detailHandlers(),
    ...secondDetailHandlers(),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/recibo/download": (init) => {
      mutation.signal = init?.signal ?? null;
      return pending;
    }
  });
  renderAt(<><BillDetailPage /><BillRouteSwitch /></>, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });
  await user.click(screen.getByRole("link", { name: "Baixar recibo" }));
  await user.click(screen.getByRole("button", { name: "Trocar fatura" }));
  expect(await screen.findByRole("heading", { name: "Fatura · Agosto/2026" })).toBeVisible();
  expect(mutation.signal?.aborted).toBe(true);

  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.queryByText("Não foi possível baixar o recibo.")).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
  expect(click).not.toHaveBeenCalled();
});

it("uses communication capabilities directly and keeps a paid rendering receipt disabled", async () => {
  installFetch({
    ...detailHandlers(),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => jsonResponse({
      ...bill,
      capabilities: {
        ...capabilities,
        can_download_recibo: false,
        can_send_recibo: false
      },
      has_recibo: false,
      pdf_render_status: "pending"
    })
  });
  renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });

  expect(screen.getByRole("link", { name: "Enviar fatura" })).toBeVisible();
  expect(screen.getByText("Baixar recibo")).toHaveAttribute("aria-disabled", "true");
  expect(screen.getByText("Baixar recibo")).toHaveAttribute("title", "O recibo ainda está sendo gerado.");
  expect(screen.queryByRole("link", { name: "Baixar recibo" })).not.toBeInTheDocument();
  expect(screen.getByText("Enviar recibo")).toHaveAttribute("aria-disabled", "true");
  expect(screen.getByText("Enviar recibo")).toHaveAttribute("title", "O recibo ainda está sendo gerado.");
  expect(screen.queryByRole("link", { name: "Enviar recibo" })).not.toBeInTheDocument();
});

it("keeps legacy draft download and communication options visible but disabled from capabilities", async () => {
  installFetch({
    ...detailHandlers(),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => jsonResponse({
      ...bill,
      capabilities: {
        ...capabilities,
        can_download_recibo: false,
        can_send_invoice: false,
        can_send_recibo: false
      },
      status: "draft"
    })
  });
  renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });

  expect(screen.getByText("Baixar recibo")).toHaveAttribute("title", "O recibo fica disponível quando a fatura está paga.");
  expect(screen.getByText("Enviar fatura")).toHaveAttribute("title", "A fatura ainda está sendo gerada.");
  expect(screen.getByText("Enviar recibo")).toHaveAttribute("title", "O recibo fica disponível quando a fatura está paga.");
});

it("edits line items and extras, regenerates, deletes, and forwards mutation analytics", async () => {
  const user = userEvent.setup();
  let patchBody: unknown;
  installFetch({
    ...detailHandlers(),
    "PATCH /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": (init) => {
      patchBody = JSON.parse(String(init?.body));
      return jsonResponse({ ...bill, notes: "Atualizado" }, 200, { "X-Rentivo-Analytics-Event": "rentivo_bill_edited" });
    },
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/regenerate": () => jsonResponse({ ...bill, pdf_render_status: "pending" }, 202, { "X-Rentivo-Analytics-Event": "rentivo_bill_regenerated" }),
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts": () => jsonResponse({ attached: 1, items: [{ content_type: "application/pdf", created_at: null, file_size: 3, filename: "edit.pdf", sort_order: 0, uuid: "01J00000000000000000000003" }], skipped: 0, total_bytes: 3 }, 201, { "X-Rentivo-Analytics-Event": "rentivo_receipt_uploaded" }),
    "DELETE /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => new Response(null, { headers: { "X-Rentivo-Analytics-Event": "rentivo_bill_deleted" }, status: 204 })
  });
  renderAt(<BillEditPage />, "/billings/billing-public-uuid/bills/bill-public-uuid/edit", "/billings/:billingUuid/bills/:billUuid/edit");

  await screen.findByRole("heading", { name: "Editar Fatura" });
  expect(screen.getByLabelText("Vencimento")).toHaveValue("10/08/2026");
  expect(screen.getAllByLabelText("Tipo")[0]).toBeDisabled();
  await user.upload(screen.getByLabelText("Anexar comprovantes"), new File(["pdf"], "edit.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar comprovantes" }));
  expect(await screen.findByText("edit.pdf")).toBeVisible();
  await user.clear(screen.getByLabelText("Observações"));
  await user.type(screen.getByLabelText("Observações"), "Atualizado");
  await user.click(screen.getByRole("button", { name: "Adicionar despesa extra" }));
  const descriptions = screen.getAllByLabelText("Descrição");
  const amounts = screen.getAllByLabelText("Valor (R$)");
  await user.type(descriptions.at(-1)!, "Energia");
  await user.type(amounts.at(-1)!, "50,00");
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(patchBody).toEqual({
    due_date: "2026-08-10",
    line_items: [
      { amount: 250000, description: "Aluguel", item_type: "fixed" },
      { amount: 1250, description: "Gás", item_type: "extra" },
      { amount: 5000, description: "Energia", item_type: "extra" }
    ],
    notes: "Atualizado"
  }));

  await user.click(screen.getByRole("button", { name: "Regenerar PDF" }));
  expect(await screen.findByText("O PDF será regenerado em segundo plano.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Excluir fatura" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Excluir fatura" }));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-public-uuid"));
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledTimes(4);
});

it("previews moderation, requires acknowledgement, sends selected recipients, and applies templates", async () => {
  const user = userEvent.setup();
  let previewCount = 0;
  let sendBody: unknown;
  installFetch({
    ...detailHandlers(),
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => {
      previewCount += 1;
      return jsonResponse(previewCount === 1
        ? { html: "<p>Prévia inicial</p>", mild: [], severe: [] }
        : { html: "<p>Prévia revista</p>", mild: ["droga"], severe: [] });
    },
    "POST /api/v1/billings/billing-public-uuid/communications/send": (init) => {
      sendBody = JSON.parse(String(init?.body));
      return jsonResponse({ queued_count: 2 }, 202, { "X-Rentivo-Analytics-Event": "rentivo_communication_queued" });
    }
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");

  expect(await screen.findByRole("heading", { name: "Enviar fatura" })).toHaveClass("pagehead__title");
  expect(await screen.findByText("Prévia inicial")).toBeVisible();
  expect(screen.getByLabelText("Ana <ana@example.com>")).toBeChecked();
  expect(screen.getByLabelText("Destinatário protegido")).toBeChecked();
  expect(screen.getByLabelText("Assunto")).toHaveValue("Fatura de julho");
  await user.click(screen.getByRole("button", { name: "Atualizar pré-visualização" }));
  expect(await screen.findByText("Linguagem possivelmente ofensiva: droga.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Enviar fatura" })).toBeDisabled();
  await user.click(screen.getByLabelText("Reconheço o aviso e quero enviar mesmo assim."));
  await user.selectOptions(screen.getByLabelText("Salvar modelo"), "billing");
  await user.click(screen.getByRole("button", { name: "Enviar fatura" }));

  await waitFor(() => expect(sendBody).toEqual({
    acknowledge_warning: true, bill_uuid: "bill-public-uuid", body: "Olá {{nome_inquilino}}",
    comm_type: "bill_ready", recipient_uuids: ["recipient-ana", "recipient-redacted"],
    save_scope: "billing", subject: "Fatura de julho"
  }));
  expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-public-uuid/bills/bill-public-uuid");
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("shows compose empty, severe moderation, load retry, and body field errors", async () => {
  const user = userEvent.setup();
  let billLoads = 0;
  let sends = 0;
  installFetch({
    "GET /api/v1/billings/billing-public-uuid": () => jsonResponse({ ...billing, recipients: [] }),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => {
      billLoads += 1;
      return billLoads === 1 ? problemResponse({ code: "offline", detail: "Falha ao carregar.", fields: {}, request_id: "req", status: 503, title: "Erro", type: "problem" }) : jsonResponse(bill);
    },
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => jsonResponse({ html: "<p>Bloqueada</p>", mild: [], severe: ["ameaça"] }),
    "POST /api/v1/billings/billing-public-uuid/communications/send": () => {
      sends += 1;
      return problemResponse({ code: "validation_error", detail: "Confira os campos.", fields: { "body.subject": "Assunto obrigatório." }, request_id: "req", status: 422, title: "Dados inválidos", type: "problem" });
    }
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  expect(await screen.findByText("Falha ao carregar.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText(/Nenhum destinatário cadastrado/)).toBeVisible();
  expect(screen.getByRole("link", { name: "Adicione destinatários" })).toHaveAttribute("href", "/billings/billing-public-uuid/edit");
  expect(sends).toBe(0);
});

it("retries invoice detail and renders denied, failed-PDF, and empty nested states", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  const deniedBill: Bill = {
    ...bill,
    capabilities: {
      can_compose: false, can_delete: false, can_delete_receipts: false,
      can_download_invoice: false, can_download_recibo: false, can_edit: false,
      can_regenerate: false, can_reorder_receipts: false, can_send_invoice: false,
      can_send_recibo: false, can_transition: false, can_upload_receipts: false
    },
    communications: [], due_date: null, has_invoice: false, has_recibo: false,
    line_items: [{ amount: 1000, description: "Consumo", item_type: "variable", sort_order: 0 }],
    notes: "", pdf_render_status: "failed", status: "unknown", status_updated_at: null
  };
  installFetch({
    "GET /api/v1/billings/billing-public-uuid": () => jsonResponse({
      ...billing,
      capabilities: { ...billing.capabilities, can_manage_bills: false },
      description: "", pix_key: "", pix_merchant_city: "", pix_merchant_name: ""
    }),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => {
      attempts += 1;
      return attempts === 1
        ? problemResponse({ code: "offline", detail: "Falha ao carregar detalhe.", fields: {}, request_id: "req", status: 503, title: "Erro", type: "problem" })
        : jsonResponse(deniedBill);
    }
  });
  renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  expect(await screen.findByText("Falha ao carregar detalhe.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText("Falha no PDF")).toBeVisible();
  expect(screen.getByText("Variável")).toHaveClass("tag--variable");
  expect(screen.getByText("Nenhum comprovante anexado.")).toBeVisible();
  expect(screen.getByText("Nenhuma comunicação enviada.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Baixar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Editar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Enviar comunicação" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Observações" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Gerenciar fatura" })).not.toBeInTheDocument();
});

it("regenerates and deletes from detail using backend capabilities", async () => {
  const user = userEvent.setup();
  installFetch({
    ...detailHandlers(),
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/regenerate": () => jsonResponse({ ...bill, pdf_render_status: "pending" }, 202, { "X-Rentivo-Analytics-Event": "rentivo_bill_regenerated" }),
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts": () => jsonResponse({ attached: 1, items: [{ content_type: "application/pdf", created_at: null, file_size: 3, filename: "detail.pdf", sort_order: 0, uuid: "01J00000000000000000000004" }], skipped: 0, total_bytes: 3 }, 201, { "X-Rentivo-Analytics-Event": "rentivo_receipt_uploaded" }),
    "DELETE /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => new Response(null, { headers: { "X-Rentivo-Analytics-Event": "rentivo_bill_deleted" }, status: 204 })
  });
  renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });
  await user.upload(screen.getByLabelText("Anexar comprovantes"), new File(["pdf"], "detail.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar comprovantes" }));
  expect(await screen.findByText("detail.pdf")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Regenerar PDF" }));
  expect(await screen.findByText("O PDF será regenerado em segundo plano.")).toBeVisible();
  expect(screen.getByText("Renderizando…")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Excluir fatura" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Excluir fatura" }));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-public-uuid"));
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledTimes(3);
});

it("keeps detail visible and reports regeneration and deletion failures", async () => {
  const user = userEvent.setup();
  installFetch({
    ...detailHandlers(),
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/regenerate": () => problemResponse({ code: "render_failed", detail: "Falha ao regenerar.", fields: {}, request_id: "req", status: 503, title: "Erro", type: "problem" }),
    "DELETE /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => problemResponse({ code: "delete_failed", detail: "Falha ao excluir.", fields: {}, request_id: "req", status: 409, title: "Erro", type: "problem" })
  });
  renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });
  await user.click(screen.getByRole("button", { name: "Regenerar PDF" }));
  expect(await screen.findByText("Falha ao regenerar.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Excluir fatura" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Excluir fatura" }));
  expect(await screen.findByText("Falha ao excluir.")).toBeVisible();
  expect(screen.getByRole("heading", { name: "Fatura · Julho/2026" })).toBeVisible();
});

it.each(["resolve", "reject"] as const)("discards a detail regeneration that %s after the route changes", async (outcome) => {
  const user = userEvent.setup();
  const mutation = { signal: null as AbortSignal | null };
  let settle!: () => void;
  const pending = new Promise<Response>((resolve, reject) => {
    settle = outcome === "resolve"
      ? () => resolve(jsonResponse({ ...bill, pdf_render_status: "pending" }, 202, { "X-Rentivo-Analytics-Event": "stale_regenerate" }))
      : () => reject(new Error("stale regeneration"));
  });
  installFetch({
    ...detailHandlers(),
    ...secondDetailHandlers(),
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/regenerate": (init) => {
      mutation.signal = init?.signal ?? null;
      return pending;
    }
  });
  renderAt(<><BillDetailPage /><BillRouteSwitch /></>, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });
  await user.click(screen.getByRole("button", { name: "Regenerar PDF" }));
  await user.click(screen.getByRole("button", { name: "Trocar fatura" }));
  expect(await screen.findByRole("heading", { name: "Fatura · Agosto/2026" })).toBeVisible();
  expect(mutation.signal?.aborted).toBe(true);

  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.queryByText("O PDF será regenerado em segundo plano.")).not.toBeInTheDocument();
  expect(screen.queryByText("Não foi possível regenerar o PDF.")).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it.each(["resolve", "reject"] as const)("does not navigate when a stale detail deletion %s", async (outcome) => {
  const user = userEvent.setup();
  let settle!: () => void;
  const pending = new Promise<Response>((resolve, reject) => {
    settle = outcome === "resolve"
      ? () => resolve(new Response(null, { headers: { "X-Rentivo-Analytics-Event": "stale_delete" }, status: 204 }))
      : () => reject(new Error("stale delete"));
  });
  installFetch({
    ...detailHandlers(),
    ...secondDetailHandlers(),
    "DELETE /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => pending
  });
  renderAt(<><BillDetailPage /><BillRouteSwitch /></>, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });
  await user.click(screen.getByRole("button", { name: "Excluir fatura" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Excluir fatura" }));
  await user.click(screen.getByRole("button", { name: "Trocar fatura" }));
  expect(await screen.findByRole("heading", { name: "Fatura · Agosto/2026" })).toBeVisible();

  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-second/bills/bill-second");
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("retries edit loading and obeys denied edit and file capabilities", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  const denied = {
    ...bill,
    capabilities: { ...capabilities, can_delete: false, can_edit: false, can_regenerate: false, can_upload_receipts: false },
    due_date: null,
    pdf_render_status: "failed"
  };
  installFetch({
    "GET /api/v1/billings/billing-public-uuid": () => jsonResponse(billing),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => {
      attempts += 1;
      return attempts === 1
        ? problemResponse({ code: "offline", detail: "Falha ao abrir edição.", fields: {}, request_id: "req", status: 503, title: "Erro", type: "problem" })
        : jsonResponse(denied);
    }
  });
  renderAt(<BillEditPage />, "/billings/billing-public-uuid/bills/bill-public-uuid/edit", "/billings/:billingUuid/bills/:billUuid/edit");
  expect(await screen.findByText("Falha ao abrir edição.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText(/a última tentativa de gerar o PDF falhou/)).toBeVisible();
  expect(screen.getByText("Você não possui permissão para editar esta fatura.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Salvar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Regenerar PDF" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Excluir fatura" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Anexar comprovantes")).not.toBeInTheDocument();
});

it("validates edit rows and dates, removes extras, and focuses nested API errors", async () => {
  const user = userEvent.setup();
  let saves = 0;
  installFetch({
    ...detailHandlers(),
    "PATCH /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => {
      saves += 1;
      if (saves === 1) return problemResponse({
        code: "validation_error", detail: "Confira os campos.", fields: { "body.notes": "Observação não permitida." },
        request_id: "req", status: 422, title: "Dados inválidos", type: "problem"
      });
      throw new Error("offline");
    }
  });
  renderAt(<BillEditPage />, "/billings/billing-public-uuid/bills/bill-public-uuid/edit", "/billings/:billingUuid/bills/:billUuid/edit");
  await screen.findByRole("heading", { name: "Editar Fatura" });
  await user.click(screen.getByRole("button", { name: "Remover Gás" }));
  expect(screen.queryByDisplayValue("Gás")).not.toBeInTheDocument();
  const description = screen.getByLabelText("Descrição");
  const amount = screen.getByLabelText("Valor (R$)");
  await user.clear(description);
  await user.clear(amount);
  await user.clear(screen.getByLabelText("Vencimento"));
  await user.type(screen.getByLabelText("Vencimento"), "31/02/2026");
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Informe a descrição.")).toBeVisible();
  expect(screen.getByText("Informe um valor válido.")).toBeVisible();
  expect(screen.getByText("Informe uma data válida.")).toBeVisible();
  expect(screen.getByLabelText("Vencimento")).toHaveFocus();

  await user.type(description, "Aluguel");
  await user.type(amount, "2.500,00");
  await user.clear(screen.getByLabelText("Vencimento"));
  await user.type(screen.getByLabelText("Vencimento"), "10/08/2026");
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Observação não permitida.")).toBeVisible();
  await waitFor(() => expect(screen.getByLabelText("Observações")).toHaveFocus());
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Não foi possível atualizar a fatura.")).toBeVisible();
});

it("reports edit regeneration and deletion failures", async () => {
  const user = userEvent.setup();
  installFetch({
    ...detailHandlers(),
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/regenerate": () => problemResponse({ code: "render_failed", detail: "Regeneração indisponível.", fields: {}, request_id: "req", status: 503, title: "Erro", type: "problem" }),
    "DELETE /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => problemResponse({ code: "delete_failed", detail: "Exclusão indisponível.", fields: {}, request_id: "req", status: 409, title: "Erro", type: "problem" })
  });
  renderAt(<BillEditPage />, "/billings/billing-public-uuid/bills/bill-public-uuid/edit", "/billings/:billingUuid/bills/:billUuid/edit");
  await screen.findByRole("heading", { name: "Editar Fatura" });
  await user.click(screen.getByRole("button", { name: "Regenerar PDF" }));
  expect(await screen.findByText("Regeneração indisponível.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Excluir fatura" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Excluir fatura" }));
  expect(await screen.findByText("Exclusão indisponível.")).toBeVisible();
});

it.each(["resolve", "reject"] as const)("discards an edit save that %s after the route changes", async (outcome) => {
  const user = userEvent.setup();
  const mutation = { signal: null as AbortSignal | null };
  let settle!: () => void;
  const pending = new Promise<Response>((resolve, reject) => {
    settle = outcome === "resolve"
      ? () => resolve(jsonResponse({ ...bill, notes: "stale" }, 200, { "X-Rentivo-Analytics-Event": "stale_edit" }))
      : () => reject(new Error("stale edit"));
  });
  installFetch({
    ...detailHandlers(),
    ...secondDetailHandlers(),
    "PATCH /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": (init) => {
      mutation.signal = init?.signal ?? null;
      return pending;
    }
  });
  renderAt(<><BillEditPage /><BillRouteSwitch edit /></>, "/billings/billing-public-uuid/bills/bill-public-uuid/edit", "/billings/:billingUuid/bills/:billUuid/edit");
  await screen.findByRole("heading", { name: "Editar Fatura" });
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await user.click(screen.getByRole("button", { name: "Trocar fatura" }));
  await waitFor(() => expect(screen.getByText(/Referencia:/)).toHaveTextContent("Agosto/2026"));
  expect(mutation.signal?.aborted).toBe(true);

  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.queryByText("Fatura atualizada com sucesso.")).not.toBeInTheDocument();
  expect(screen.queryByText("Não foi possível atualizar a fatura.")).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it.each([
  ["regenerate", "resolve"],
  ["regenerate", "reject"],
  ["delete", "resolve"],
  ["delete", "reject"]
] as const)("discards a stale edit %s completion that %s", async (action, outcome) => {
  const user = userEvent.setup();
  const mutation = { signal: null as AbortSignal | null };
  let settle!: () => void;
  const pending = new Promise<Response>((resolve, reject) => {
    settle = outcome === "resolve"
      ? () => resolve(action === "regenerate"
        ? jsonResponse({ ...bill, pdf_render_status: "pending" }, 202, { "X-Rentivo-Analytics-Event": "stale_regenerate" })
        : new Response(null, { headers: { "X-Rentivo-Analytics-Event": "stale_delete" }, status: 204 }))
      : () => reject(new Error(`stale ${action}`));
  });
  const endpoint = action === "regenerate"
    ? "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/regenerate"
    : "DELETE /api/v1/billings/billing-public-uuid/bills/bill-public-uuid";
  installFetch({
    ...detailHandlers(),
    ...secondDetailHandlers(),
    [endpoint]: (init) => {
      mutation.signal = init?.signal ?? null;
      return pending;
    }
  });
  renderAt(<><BillEditPage /><BillRouteSwitch edit /></>, "/billings/billing-public-uuid/bills/bill-public-uuid/edit", "/billings/:billingUuid/bills/:billUuid/edit");
  await screen.findByRole("heading", { name: "Editar Fatura" });
  if (action === "regenerate") {
    await user.click(screen.getByRole("button", { name: "Regenerar PDF" }));
  } else {
    await user.click(screen.getByRole("button", { name: "Excluir fatura" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Excluir fatura" }));
  }
  await user.click(screen.getByRole("button", { name: "Trocar fatura" }));
  await waitFor(() => expect(screen.getByText(/Referencia:/)).toHaveTextContent("Agosto/2026"));
  expect(mutation.signal?.aborted).toBe(true);

  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.getByTestId("location")).toHaveTextContent("/billings/billing-second/bills/bill-second/edit");
  expect(screen.queryByText("O PDF será regenerado em segundo plano.")).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it.each([
  ["ausente", ""],
  ["desconhecido", "?type=unsupported"]
])("rejects a %s communication type without loading invoice resources", async (_label, search) => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  renderAt(
    <CommunicationComposePage />,
    `/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose${search}`,
    "/billings/:billingUuid/bills/:billUuid/communications/compose"
  );

  expect(screen.getByText("Tipo de comunicação inválido.")).toBeVisible();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(document.title).toBe("Enviar comunicação - Rentivo");
});

it("blocks severe communication content and reports preview failures", async () => {
  const user = userEvent.setup();
  let previews = 0;
  installFetch({
    ...detailHandlers(),
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => {
      previews += 1;
      return previews === 1
        ? jsonResponse({ html: "<p>Bloqueada</p>", mild: [], severe: ["ameaça"] })
        : problemResponse({ code: "preview_failed", detail: "Prévia indisponível.", fields: {}, request_id: "req", status: 503, title: "Erro", type: "problem" });
    }
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  expect(await screen.findByText(/Conteúdo não permitido.*ameaça/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Enviar fatura" })).toBeDisabled();
  expect(screen.queryByLabelText("Reconheço o aviso e quero enviar mesmo assim.")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Atualizar pré-visualização" }));
  expect(await screen.findByText("Prévia indisponível.")).toBeVisible();
});

it("keeps only the latest preview and invalidates preview acknowledgement after editing", async () => {
  const user = userEvent.setup();
  let rejectFirst!: (error: Error) => void;
  let resolveSecond!: (response: Response) => void;
  let previews = 0;
  installFetch({
    ...detailHandlers(),
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => {
      previews += 1;
      if (previews === 1) return jsonResponse({ html: "<p>Prévia inicial</p>", mild: [], severe: [] });
      return new Promise<Response>((resolve, reject) => {
        if (previews === 2) rejectFirst = reject;
        else resolveSecond = resolve;
      });
    }
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  await screen.findByText("Prévia inicial");
  await user.click(screen.getByRole("button", { name: "Atualizar pré-visualização" }));
  await user.type(screen.getByLabelText("Assunto"), " revisado");
  expect(screen.getByText("A pré-visualização aparecerá aqui.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Atualizar pré-visualização" })).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Atualizar pré-visualização" }));
  resolveSecond(jsonResponse({ html: "<p>Prévia mais nova</p>", mild: ["droga"], severe: [] }));
  expect(await screen.findByText("Prévia mais nova")).toBeVisible();
  await user.click(screen.getByLabelText("Reconheço o aviso e quero enviar mesmo assim."));

  await user.type(screen.getByLabelText("Corpo (Markdown — HTML não é permitido)"), " revisado");
  expect(screen.getByText("A pré-visualização aparecerá aqui.")).toBeVisible();
  expect(screen.queryByLabelText("Reconheço o aviso e quero enviar mesmo assim.")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Enviar fatura" })).toBeDisabled();

  rejectFirst(new Error("prévia antiga falhou"));
  await waitFor(() => expect(screen.queryByText("Não foi possível atualizar a pré-visualização.")).not.toBeInTheDocument());
});

it("resets compose resources and previews when route parameters change", async () => {
  const user = userEvent.setup();
  let resolveOldPreview!: (response: Response) => void;
  installFetch({
    ...detailHandlers(),
    "GET /api/v1/billings/billing-second": () => jsonResponse({
      ...billing,
      communication_templates: [{ body: "Corpo da segunda", comm_type: "bill_ready", subject: "Segunda cobrança" }],
      name: "Residencial Lua",
      recipients: [{ email: "bia@example.com", name: "Bia", uuid: "recipient-bia" }],
      uuid: "billing-second"
    }),
    "GET /api/v1/billings/billing-second/bills/bill-second": () => jsonResponse({ ...bill, uuid: "bill-second" }),
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => new Promise<Response>((resolve) => { resolveOldPreview = resolve; }),
    "POST /api/v1/billings/billing-second/communications/preview": () => jsonResponse({ html: "<p>Prévia da segunda</p>", mild: [], severe: [] })
  });
  renderAt(<><CommunicationComposePage /><ComposeRouteSwitch /></>, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  await screen.findByRole("heading", { name: "Enviar fatura" });
  await user.type(screen.getByLabelText("Assunto"), " temporário");
  await user.click(screen.getByRole("button", { name: "Trocar comunicação" }));

  expect(await screen.findByText("Residencial Lua · Julho/2026. Cada destinatário recebe um e-mail separado com o PDF da fatura anexado.")).toBeVisible();
  expect(screen.getByLabelText("Assunto")).toHaveValue("Segunda cobrança");
  expect(screen.getByLabelText("Corpo (Markdown — HTML não é permitido)")).toHaveValue("Corpo da segunda");
  expect(await screen.findByText("Prévia da segunda")).toBeVisible();
  resolveOldPreview(jsonResponse({ html: "<p>Prévia vazada</p>", mild: [], severe: [] }));
  await waitFor(() => expect(screen.queryByText("Prévia vazada")).not.toBeInTheDocument());
});

it("blocks direct compose access from typed capabilities before previewing", async () => {
  installFetch({
    ...detailHandlers(),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => jsonResponse({
      ...bill,
      capabilities: { ...capabilities, can_compose: false, can_send_invoice: false }
    })
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");

  expect(await screen.findByText("Você não possui permissão para enviar esta comunicação.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Enviar fatura" })).not.toBeInTheDocument();
});

it("blocks a direct invoice compose URL when its artifact is not ready", async () => {
  installFetch({
    ...detailHandlers(),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => jsonResponse({
      ...bill,
      capabilities: { ...capabilities, can_send_invoice: false }
    })
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  expect(await screen.findByText("A fatura ainda está sendo gerada.")).toBeVisible();
});

it.each(["resolve", "reject"] as const)("discards a pending send that %s after a route change", async (outcome) => {
  const user = userEvent.setup();
  let settleSend!: () => void;
  const pendingSend = new Promise<Response>((resolve, reject) => {
    settleSend = outcome === "resolve"
      ? () => resolve(jsonResponse({ queued_count: 2 }, 202, { "X-Rentivo-Analytics-Event": "stale_send" }))
      : () => reject(new Error("stale send failed"));
  });
  installFetch({
    ...detailHandlers(),
    "GET /api/v1/billings/billing-second": () => jsonResponse({
      ...billing,
      communication_templates: [{ body: "Corpo da segunda", comm_type: "bill_ready", subject: "Segunda cobrança" }],
      name: "Residencial Lua",
      recipients: [{ email: "bia@example.com", name: "Bia", uuid: "recipient-bia" }],
      uuid: "billing-second"
    }),
    "GET /api/v1/billings/billing-second/bills/bill-second": () => jsonResponse({ ...bill, uuid: "bill-second" }),
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => jsonResponse({ html: "<p>Pronta</p>", mild: [], severe: [] }),
    "POST /api/v1/billings/billing-second/communications/preview": () => jsonResponse({ html: "<p>Segunda pronta</p>", mild: [], severe: [] }),
    "POST /api/v1/billings/billing-public-uuid/communications/send": () => pendingSend
  });
  renderAt(<><CommunicationComposePage /><ComposeRouteSwitch /></>, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  await screen.findByText("Pronta");
  await user.click(screen.getByRole("button", { name: "Enviar fatura" }));
  expect(screen.getByRole("button", { name: "Enviando..." })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Trocar comunicação" }));
  expect(await screen.findByText("Segunda pronta")).toBeVisible();

  settleSend();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.queryByText("Não foi possível enviar a comunicação.")).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("requires recipients and focuses subject and body API errors", async () => {
  const user = userEvent.setup();
  let sends = 0;
  installFetch({
    ...detailHandlers(),
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => jsonResponse({ html: "<p>Ok</p>", mild: [], severe: [] }),
    "POST /api/v1/billings/billing-public-uuid/communications/send": () => {
      sends += 1;
      return problemResponse({
        code: "validation_error", detail: "Confira os campos.",
        fields: sends === 1
          ? { "body.subject": "Assunto obrigatório." }
          : sends === 2
            ? { "body.body": "Corpo obrigatório." }
            : sends === 3
              ? { "body.recipient_uuids": "Destinatário desatualizado." }
              : { "body.save_scope": "Modelo indisponível." },
        request_id: "req", status: 422, title: "Dados inválidos", type: "problem"
      });
    }
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  await screen.findByRole("heading", { name: "Enviar fatura" });
  await user.clear(screen.getByLabelText("Assunto"));
  await user.type(screen.getByLabelText("Assunto"), "Novo assunto");
  await user.clear(screen.getByLabelText("Corpo (Markdown — HTML não é permitido)"));
  await user.type(screen.getByLabelText("Corpo (Markdown — HTML não é permitido)"), "Novo corpo");
  await user.click(screen.getByRole("button", { name: "Atualizar pré-visualização" }));
  await screen.findByText("Ok");
  await user.click(screen.getByLabelText("Ana <ana@example.com>"));
  await user.click(screen.getByLabelText("Destinatário protegido"));
  fireEvent.submit(document.getElementById("comm-form")!);
  expect(await screen.findByText("Selecione ao menos um destinatário.")).toBeVisible();
  expect(screen.getByLabelText("Ana <ana@example.com>")).toHaveFocus();
  expect(sends).toBe(0);

  await user.click(screen.getByLabelText("Ana <ana@example.com>"));
  await user.click(screen.getByRole("button", { name: "Enviar fatura" }));
  expect(await screen.findByText("Assunto obrigatório.")).toBeVisible();
  await waitFor(() => expect(screen.getByLabelText("Assunto")).toHaveFocus());
  await user.click(screen.getByRole("button", { name: "Enviar fatura" }));
  expect(await screen.findByText("Corpo obrigatório.")).toBeVisible();
  await waitFor(() => expect(screen.getByLabelText("Corpo (Markdown — HTML não é permitido)")).toHaveFocus());
  await user.click(screen.getByRole("button", { name: "Enviar fatura" }));
  expect(await screen.findByText("Destinatário desatualizado.")).toBeVisible();
  await waitFor(() => expect(screen.getByLabelText("Ana <ana@example.com>")).toHaveFocus());
  await user.selectOptions(screen.getByLabelText("Salvar modelo"), "billing");
  await user.click(screen.getByRole("button", { name: "Enviar fatura" }));
  expect(await screen.findByText("Modelo indisponível.")).toBeVisible();
  await waitFor(() => expect(screen.getByLabelText("Salvar modelo")).toHaveFocus());
});

it("targets moderation acknowledgement field errors", async () => {
  installFetch({
    ...detailHandlers(),
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => jsonResponse({ html: "<p>Revisar</p>", mild: ["droga"], severe: [] }),
    "POST /api/v1/billings/billing-public-uuid/communications/send": () => problemResponse({
      code: "communication_warning_unacknowledged", detail: "Reconheça o aviso.",
      fields: { "body.acknowledge_warning": "Confirme antes de enviar." }, request_id: "req",
      status: 422, title: "Dados inválidos", type: "problem"
    })
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  await screen.findByText("Linguagem possivelmente ofensiva: droga.");
  fireEvent.submit(document.getElementById("comm-form")!);
  expect(await screen.findByText("Confirme antes de enviar.")).toBeVisible();
  await waitFor(() => expect(screen.getByLabelText("Reconheço o aviso e quero enviar mesmo assim.")).toHaveFocus());
});

it("renders the payment-receipt variant with an empty template and capability-driven owner scope", async () => {
  installFetch({
    "GET /api/v1/billings/billing-public-uuid": () => jsonResponse({
      ...billing,
      capabilities: { ...billing.capabilities, can_edit: false },
      communication_templates: billing.communication_templates.filter((item) => item.comm_type !== "payment_receipt"),
      owner: { type: "user", uuid: null }
    }),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => jsonResponse(bill),
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => jsonResponse({ html: "", mild: [], severe: [] })
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=payment_receipt", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  expect(await screen.findByRole("heading", { name: "Enviar recibo de pagamento" })).toBeVisible();
  expect(screen.getByText(/Cada destinatário recebe.*recibo anexado/)).toBeVisible();
  expect(screen.getByLabelText("Assunto")).toHaveValue("");
  expect(screen.getByLabelText("Corpo (Markdown — HTML não é permitido)")).toHaveValue("");
  expect(screen.queryByRole("option", { name: /minha conta|organização/ })).not.toBeInTheDocument();
  expect(document.title).toBe("Enviar recibo de pagamento - Rentivo");
});

it("blocks unavailable recibos and shows a pending preview with user-owner template scope", async () => {
  installFetch({
    ...detailHandlers(),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => jsonResponse({ ...bill, capabilities: { ...capabilities, can_download_recibo: true, can_send_recibo: false } })
  });
  const blocked = renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=payment_receipt", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  expect(await screen.findByText("O recibo ainda está sendo gerado.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Enviar recibo de pagamento" })).not.toBeInTheDocument();
  blocked.unmount();

  let resolvePreview!: (response: Response) => void;
  const pendingPreview = new Promise<Response>((resolve) => { resolvePreview = resolve; });
  installFetch({
    "GET /api/v1/billings/billing-public-uuid": () => jsonResponse({ ...billing, owner: { type: "user", uuid: null } }),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => jsonResponse(bill),
    "POST /api/v1/billings/billing-public-uuid/communications/preview": () => pendingPreview
  });
  renderAt(<CommunicationComposePage />, "/billings/billing-public-uuid/bills/bill-public-uuid/communications/compose?type=bill_ready", "/billings/:billingUuid/bills/:billUuid/communications/compose");
  expect(await screen.findByText("A pré-visualização aparecerá aqui.")).toBeVisible();
  expect(screen.getByRole("option", { name: "Salvar para minha conta" })).toBeVisible();
  resolvePreview(jsonResponse({ html: "<p>Pronta</p>", mild: [], severe: [] }));
  expect(await screen.findByText("Pronta")).toBeVisible();
});

it("refreshes invoice detail after a stale status conflict", async () => {
  const user = userEvent.setup();
  let billLoads = 0;
  installFetch({
    "GET /api/v1/billings/billing-public-uuid": () => jsonResponse(billing),
    "GET /api/v1/billings/billing-public-uuid/bills/bill-public-uuid": () => {
      billLoads += 1;
      return jsonResponse({
        ...bill,
        available_transitions: [{ label: "Cancelar fatura", requires_confirmation: true, style: "danger", target: "cancelled" }]
      });
    },
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/transitions": () => problemResponse({
      code: "stale_bill_status", detail: "O status da fatura foi alterado.", fields: {}, request_id: "req",
      status: 409, title: "Conflito", type: "problem"
    })
  });
  renderAt(<BillDetailPage />, "/billings/billing-public-uuid/bills/bill-public-uuid", "/billings/:billingUuid/bills/:billUuid");
  await screen.findByRole("heading", { name: "Fatura · Julho/2026" });
  await user.click(screen.getByRole("button", { name: "Cancelar fatura" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancelar fatura" }));
  await waitFor(() => expect(billLoads).toBe(2));
});

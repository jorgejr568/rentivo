import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { jsonResponse, problemResponse } from "../../test/auth";
import { BillStatusActions } from "./BillStatusActions";

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
vi.mock("../auth/analytics", () => analytics);

type Bill = components["schemas"]["BillDetailResponse"];
const bill: Bill = {
  available_transitions: [
    { label: "Marcar como pago", requires_confirmation: true, style: "primary", target: "paid" },
    { label: "Cancelar fatura", requires_confirmation: true, style: "danger", target: "cancelled" }
  ],
  capabilities: {
    can_compose: true,
    can_delete: true, can_delete_receipts: true, can_download_invoice: true,
    can_download_recibo: false, can_edit: true, can_regenerate: true,
    can_reorder_receipts: true, can_send_invoice: true, can_send_recibo: false,
    can_transition: true, can_upload_receipts: true
  },
  communications: [], created_at: "2026-07-18T10:00:00Z", due_date: "2026-08-10",
  has_invoice: true, has_recibo: false, line_items: [], notes: "", pdf_render_status: null,
  receipts: [], reference_month: "2026-07", status: "sent", status_updated_at: null,
  total_amount: 250000, uuid: "bill-public-uuid"
};

afterEach(() => {
  cleanup();
  analytics.pushAnalyticsFromResponse.mockReset();
  vi.unstubAllGlobals();
});

function installFetch(handler: (init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    expect(String(input)).toBe("/api/v1/billings/billing-public-uuid/bills/bill-public-uuid/transitions");
    return handler(init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

it("uses backend transitions and confirms a strict compare-and-swap status change", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  let body: unknown;
  installFetch((init) => {
    body = JSON.parse(String(init?.body));
    return jsonResponse({ ...bill, status: "paid", available_transitions: [] }, 200, {
      "X-Rentivo-Analytics-Event": "rentivo_bill_status_changed"
    });
  });
  render(<BillStatusActions billingUuid="billing-public-uuid" bill={bill} onChange={onChange} onStale={vi.fn()} />);

  await user.click(screen.getByRole("button", { name: "Marcar como pago" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("Marcar fatura como paga?");
  expect(screen.getByRole("dialog")).toHaveTextContent("libera o recibo");
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Marcar como pago" }));

  await waitFor(() => expect(body).toEqual({ current_status: "sent", target: "paid" }));
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ status: "paid" }));
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("refreshes on stale 409 and never reconstructs transitions when capability is absent", async () => {
  const user = userEvent.setup();
  const onStale = vi.fn();
  installFetch(() => problemResponse({
    code: "stale_bill_status", detail: "O status da fatura foi alterado.", fields: {}, request_id: "req",
    status: 409, title: "Conflito", type: "problem"
  }));
  const view = render(<BillStatusActions billingUuid="billing-public-uuid" bill={bill} onChange={vi.fn()} onStale={onStale} />);
  await user.click(screen.getByRole("button", { name: "Cancelar fatura" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancelar fatura" }));
  expect(await screen.findByText("O status da fatura foi alterado.")).toBeVisible();
  expect(onStale).toHaveBeenCalledOnce();

  view.rerender(<BillStatusActions
    billingUuid="billing-public-uuid"
    bill={{ ...bill, available_transitions: [], capabilities: { ...bill.capabilities, can_transition: false } }}
    onChange={vi.fn()}
    onStale={vi.fn()}
  />);
  expect(screen.queryByRole("button", { name: /status|pago|cancelar/i })).not.toBeInTheDocument();
});

it("submits an unconfirmed backend transition and reports non-conflict failures", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  installFetch(() => {
    attempts += 1;
    return attempts === 1
      ? jsonResponse({ ...bill, status: "published" })
      : problemResponse({ code: "offline", detail: "Falha temporária.", fields: {}, request_id: "req", status: 503, title: "Erro", type: "problem" });
  });
  const unconfirmed: Bill = {
    ...bill,
    available_transitions: [{ label: "Publicar fatura", requires_confirmation: false, style: "primary", target: "published" }],
    status: "draft"
  };
  const onChange = vi.fn();
  const onStale = vi.fn();
  const view = render(<BillStatusActions billingUuid="billing-public-uuid" bill={unconfirmed} onChange={onChange} onStale={onStale} />);

  await user.click(screen.getByRole("button", { name: "Publicar fatura" }));
  await waitFor(() => expect(onChange).toHaveBeenCalledOnce());
  view.rerender(<BillStatusActions billingUuid="billing-public-uuid" bill={unconfirmed} onChange={onChange} onStale={onStale} />);
  await user.click(screen.getByRole("button", { name: "Publicar fatura" }));
  expect(await screen.findByText("Falha temporária.")).toBeVisible();
  expect(onStale).not.toHaveBeenCalled();
});

it("uses a generic confirmation for a new backend transition", async () => {
  const user = userEvent.setup();
  installFetch(() => jsonResponse({ ...bill, status: "draft" }));
  render(<BillStatusActions
    billingUuid="billing-public-uuid"
    bill={{ ...bill, available_transitions: [
      { label: "Publicar fatura", requires_confirmation: false, style: "primary", target: "published" },
      { label: "Nova transição", requires_confirmation: true, style: "other", target: "archived" }
    ] }}
    onChange={vi.fn()}
    onStale={vi.fn()}
  />);
  await user.click(screen.getByRole("button", { name: "Nova transição" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("Alterar status da fatura?");
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Nova transição" }));
  await waitFor(() => expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce());
});

it.each(["resolve", "reject"] as const)("discards a status transition that %s after the bill route changes", async (outcome) => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const onStale = vi.fn();
  const mutation = { signal: null as AbortSignal | null };
  let settle!: () => void;
  const pending = new Promise<Response>((resolve, reject) => {
    settle = outcome === "resolve"
      ? () => resolve(jsonResponse({ ...bill, status: "paid" }, 200, { "X-Rentivo-Analytics-Event": "stale_transition" }))
      : () => reject(new Error("stale transition"));
  });
  installFetch((init) => {
    mutation.signal = init?.signal ?? null;
    return pending;
  });
  const view = render(<BillStatusActions billingUuid="billing-public-uuid" bill={bill} onChange={onChange} onStale={onStale} />);
  await user.click(screen.getByRole("button", { name: "Marcar como pago" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Marcar como pago" }));

  view.rerender(<BillStatusActions
    billingUuid="billing-second"
    bill={{ ...bill, reference_month: "2026-08", uuid: "bill-second" }}
    onChange={onChange}
    onStale={onStale}
  />);
  expect(mutation.signal?.aborted).toBe(true);
  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(onChange).not.toHaveBeenCalled();
  expect(onStale).not.toHaveBeenCalled();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

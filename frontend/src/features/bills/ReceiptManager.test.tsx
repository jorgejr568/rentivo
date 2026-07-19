import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { jsonResponse, problemResponse } from "../../test/auth";
import { ReceiptManager } from "./ReceiptManager";

interface SortableOptionsStub {
  animation?: number;
  disabled?: boolean;
  ghostClass?: string;
  handle?: string;
  onEnd?: () => void;
}

interface SortableInstanceStub {
  destroy: ReturnType<typeof vi.fn>;
  option: ReturnType<typeof vi.fn>;
}

interface SortableRecord {
  element: HTMLElement;
  instance: SortableInstanceStub;
  options: SortableOptionsStub;
}

const sortable = vi.hoisted(() => ({
  create: vi.fn<(element: HTMLElement, options: SortableOptionsStub) => SortableInstanceStub>(),
  instances: [] as SortableRecord[]
}));
vi.mock("sortablejs", () => ({ default: { create: sortable.create } }));

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
vi.mock("../auth/analytics", () => analytics);

type Receipt = components["schemas"]["ReceiptResponse"];
const receipts: Receipt[] = [
  { content_type: "application/pdf", created_at: "2026-07-18T10:00:00Z", file_size: 1536, filename: "julho.pdf", sort_order: 0, uuid: "01J00000000000000000000000" },
  { content_type: "image/png", created_at: null, file_size: 2048, filename: "pix.png", sort_order: 1, uuid: "01J00000000000000000000001" }
];
const capabilities = {
  can_compose: true,
  can_delete: true, can_delete_receipts: true, can_download_invoice: true,
  can_download_recibo: false, can_edit: true, can_regenerate: true,
  can_reorder_receipts: true, can_send_invoice: true, can_send_recibo: false,
  can_transition: true, can_upload_receipts: true
};

beforeEach(() => {
  sortable.instances.length = 0;
  sortable.create.mockReset();
  sortable.create.mockImplementation((element, options) => {
    const instance = { destroy: vi.fn(), option: vi.fn() };
    sortable.instances.push({ element, instance, options });
    return instance;
  });
});

afterEach(() => {
  cleanup();
  analytics.pushAnalyticsFromResponse.mockReset();
  vi.unstubAllGlobals();
});

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

it("renders same-origin downloads and uploads, deletes, and reorders receipts from capabilities", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const uploaded: Receipt = { ...receipts[0], filename: "novo.pdf", uuid: "01J00000000000000000000002" };
  let uploadBody: FormData | undefined;
  let orderBody: unknown;
  installFetch({
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts": (init) => {
      uploadBody = init?.body as FormData;
      return jsonResponse({ attached: 1, items: [uploaded], skipped: 0, total_bytes: 3 }, 201, {
        "X-Rentivo-Analytics-Event": "rentivo_receipt_uploaded"
      });
    },
    "DELETE /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts/01J00000000000000000000000": () => new Response(null, {
      headers: { "X-Rentivo-Analytics-Event": "rentivo_receipt_deleted" }, status: 204
    }),
    "PUT /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipt-order": (init) => {
      orderBody = JSON.parse(String(init?.body));
      return jsonResponse({ items: [uploaded, receipts[1]] });
    }
  });
  render(<ReceiptManager
    billingUuid="billing-public-uuid" billUuid="bill-public-uuid"
    capabilities={capabilities} onChange={onChange} receipts={receipts}
  />);

  expect(screen.getByRole("link", { name: "Ver julho.pdf" })).toHaveAttribute(
    "href", "/api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts/01J00000000000000000000000"
  );
  expect(screen.getByText("1.5 KB")).toBeVisible();
  const file = new File(["pdf"], "novo.pdf", { type: "application/pdf" });
  await user.upload(screen.getByLabelText("Anexar comprovantes"), file);
  await user.click(screen.getByRole("button", { name: "Enviar comprovantes" }));
  await waitFor(() => expect(uploadBody?.getAll("receipt_files")).toEqual([file]));
  expect(onChange).toHaveBeenCalledWith([...receipts, uploaded]);

  await user.click(screen.getByRole("button", { name: "Remover julho.pdf" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("Remover comprovante?");
  await user.click(screen.getByRole("button", { name: "Remover", hidden: true }));
  await waitFor(() => expect(onChange).toHaveBeenCalledWith([receipts[1], uploaded]));

  expect(screen.queryAllByRole("button", { name: /Mover .* para (cima|baixo)/ })).toHaveLength(0);
  const handle = screen.getByRole("button", { name: "Reordenar novo.pdf" });
  handle.focus();
  await user.keyboard("{ArrowUp}");
  await waitFor(() => expect(orderBody).toEqual({ order: [uploaded.uuid, receipts[1].uuid] }));
  expect(onChange).toHaveBeenLastCalledWith([uploaded, receipts[1]]);
  expect(screen.getByText("novo.pdf movido para cima.")).toHaveAttribute("aria-live", "polite");
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledTimes(2);
});

it("shows a fresh empty state and omits every action denied by backend capabilities", () => {
  render(<ReceiptManager
    billingUuid="billing-public-uuid" billUuid="bill-public-uuid"
    capabilities={{ ...capabilities, can_delete_receipts: false, can_reorder_receipts: false, can_upload_receipts: false }}
    onChange={vi.fn()} receipts={[]}
  />);
  expect(screen.getByText("Nenhum comprovante anexado.")).toBeVisible();
  expect(screen.queryByLabelText("Anexar comprovantes")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /remover|mover/i })).not.toBeInTheDocument();
  expect(sortable.create).not.toHaveBeenCalled();
});

it("focuses empty uploads and surfaces upload, delete, and reorder failures", async () => {
  const user = userEvent.setup();
  installFetch({
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts": () => problemResponse({ code: "upload_failed", detail: "Arquivo inválido.", fields: {}, request_id: "req", status: 422, title: "Erro", type: "problem" }),
    "DELETE /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts/01J00000000000000000000000": () => problemResponse({ code: "delete_failed", detail: "Falha ao remover.", fields: {}, request_id: "req", status: 503, title: "Erro", type: "problem" }),
    "PUT /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipt-order": () => problemResponse({ code: "order_failed", detail: "Falha ao ordenar.", fields: {}, request_id: "req", status: 409, title: "Erro", type: "problem" })
  });
  render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={vi.fn()} receipts={receipts} />);

  const input = screen.getByLabelText("Anexar comprovantes");
  fireEvent.change(input, { target: { files: null } });
  await user.click(screen.getByRole("button", { name: "Enviar comprovantes" }));
  expect(await screen.findByText("Selecione ao menos um comprovante.")).toBeVisible();
  expect(input).toHaveFocus();

  await user.upload(input, new File(["bad"], "bad.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar comprovantes" }));
  expect(await screen.findByText("Arquivo inválido.")).toBeVisible();
  expect(input).toHaveFocus();

  await user.click(screen.getByRole("button", { name: "Remover julho.pdf" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remover" }));
  expect(await screen.findByText("Falha ao remover.")).toBeVisible();

  const handle = screen.getByRole("button", { name: "Reordenar julho.pdf" });
  handle.focus();
  await user.keyboard("{ArrowDown}");
  expect(await screen.findByText("Falha ao ordenar.")).toBeVisible();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("deduplicates uploads, shows progress and skipped counts, merges latest state, and focuses success", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const external: Receipt = { ...receipts[0], filename: "externo.pdf", uuid: "01J00000000000000000000003" };
  const uploaded: Receipt = { ...receipts[0], filename: "novo.pdf", uuid: "01J00000000000000000000004" };
  let uploadBody: FormData | undefined;
  let resolveUpload!: (response: Response) => void;
  installFetch({
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts": (init) => {
      uploadBody = init?.body as FormData;
      return new Promise<Response>((resolve) => { resolveUpload = resolve; });
    }
  });
  const view = render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={onChange} receipts={receipts} />);
  const file = new File(["pdf"], "novo.pdf", { lastModified: 123, type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Anexar comprovantes"), { target: { files: [file, file] } });
  await user.click(screen.getByRole("button", { name: "Enviar comprovantes" }));

  expect(screen.getByRole("progressbar", { name: "Progresso do envio" })).toBeVisible();
  expect(uploadBody?.getAll("receipt_files")).toEqual([file]);
  view.rerender(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={onChange} receipts={[...receipts, external]} />);
  resolveUpload(jsonResponse({ attached: 1, items: [uploaded], skipped: 1, total_bytes: 3 }, 201, {
    "X-Rentivo-Analytics-Event": "rentivo_receipt_uploaded"
  }));

  const success = await screen.findByRole("status");
  expect(success).toHaveTextContent("1 comprovante(s) anexado(s). 1 arquivo(s) ignorado(s).");
  await waitFor(() => expect(success).toHaveFocus());
  expect(onChange).toHaveBeenLastCalledWith([...receipts, external, uploaded]);
});

it("initializes legacy SortableJS options, persists onEnd order, and disables sorting while pending", async () => {
  const onChange = vi.fn();
  let orderBody: unknown;
  let resolveOrder!: (response: Response) => void;
  installFetch({
    "PUT /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipt-order": (init) => {
      orderBody = JSON.parse(String(init?.body));
      return new Promise<Response>((resolve) => { resolveOrder = resolve; });
    }
  });
  render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={onChange} receipts={receipts} />);

  expect(sortable.create).toHaveBeenCalledOnce();
  const record = sortable.instances[0];
  expect(record.element).toHaveAttribute("id", "receipt-list");
  expect(record.options).toMatchObject({
    animation: 150,
    disabled: false,
    ghostClass: "sortable-ghost",
    handle: ".drag-handle",
    onEnd: expect.any(Function)
  });
  expect(screen.getAllByRole("button", { name: /Reordenar/ })).toHaveLength(2);
  expect(screen.queryAllByRole("button", { name: /Mover .* para (cima|baixo)/ })).toHaveLength(0);
  expect(screen.getByRole("button", { name: "Reordenar julho.pdf" })).not.toHaveAttribute("draggable");

  const list = record.element;
  list.append(list.querySelector("tr[data-uuid]")!);
  act(() => record.options.onEnd?.());

  await waitFor(() => expect(orderBody).toEqual({ order: [receipts[1].uuid, receipts[0].uuid] }));
  expect(record.instance.option).toHaveBeenCalledWith("disabled", true);
  expect(screen.getByRole("button", { name: "Reordenar julho.pdf" })).toBeDisabled();
  const external = { ...receipts[0], uuid: "01J00000000000000000000099" };
  await act(async () => resolveOrder(jsonResponse({ items: [external, ...receipts].reverse() })));
  await waitFor(() => expect(onChange).toHaveBeenCalledWith([...receipts].reverse()));
  expect(record.instance.option).toHaveBeenLastCalledWith("disabled", false);
});

it("rolls a failed SortableJS onEnd back to the latest persisted order", async () => {
  installFetch({
    "PUT /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipt-order": () => problemResponse({
      code: "order_failed", detail: "Falha ao ordenar.", fields: {}, request_id: "req", status: 409, title: "Erro", type: "problem"
    })
  });
  render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={vi.fn()} receipts={receipts} />);
  const record = sortable.instances[0];
  record.element.append(record.element.querySelector("tr[data-uuid]")!);

  act(() => record.options.onEnd?.());

  expect(await screen.findByText("Falha ao ordenar.")).toBeVisible();
  expect(Array.from(record.element.querySelectorAll("tr[data-uuid]"), (row) => row.getAttribute("data-uuid"))).toEqual(
    receipts.map((receipt) => receipt.uuid)
  );
});

it("rejects malformed SortableJS DOM orders and restores persisted rows", () => {
  const fetchMock = installFetch({});
  render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={vi.fn()} receipts={receipts} />);
  const record = sortable.instances[0];
  const unknown = document.createElement("tr");
  unknown.dataset.uuid = "unknown-receipt";
  record.element.append(unknown);

  act(() => record.options.onEnd?.());

  expect(fetchMock).not.toHaveBeenCalled();
  expect(unknown.isConnected).toBe(false);
  expect(Array.from(record.element.querySelectorAll("tr[data-uuid]"), (row) => row.getAttribute("data-uuid"))).toEqual(
    receipts.map((receipt) => receipt.uuid)
  );
});

it("destroys and reinitializes SortableJS across route, capability, and unmount lifecycles", () => {
  const view = render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={vi.fn()} receipts={receipts} />);
  const first = sortable.instances[0].instance;

  view.rerender(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-second" capabilities={capabilities} onChange={vi.fn()} receipts={receipts} />);
  expect(first.destroy).toHaveBeenCalledOnce();
  expect(sortable.create).toHaveBeenCalledTimes(2);
  const second = sortable.instances[1].instance;

  view.rerender(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-second" capabilities={{ ...capabilities, can_reorder_receipts: false }} onChange={vi.fn()} receipts={receipts} />);
  expect(second.destroy).toHaveBeenCalledOnce();
  expect(sortable.create).toHaveBeenCalledTimes(2);

  view.rerender(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-second" capabilities={capabilities} onChange={vi.fn()} receipts={receipts} />);
  expect(sortable.create).toHaveBeenCalledTimes(3);
  const third = sortable.instances[2].instance;
  view.unmount();
  expect(third.destroy).toHaveBeenCalledOnce();
});

it("reorders from the single handle keyboard controls and announces the move", async () => {
  const user = userEvent.setup();
  const fetchMock = installFetch({
    "PUT /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipt-order": () => jsonResponse({ items: [...receipts].reverse() })
  });
  render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={vi.fn()} receipts={receipts} />);
  const handle = screen.getByRole("button", { name: "Reordenar julho.pdf" });
  handle.focus();

  await user.keyboard("{ArrowUp}");
  expect(fetchMock).not.toHaveBeenCalled();
  await user.keyboard("{Enter}");
  expect(fetchMock).not.toHaveBeenCalled();
  await user.keyboard("{ArrowDown}");

  expect(await screen.findByText("julho.pdf movido para baixo.")).toHaveAttribute("aria-live", "polite");
  expect(fetchMock).toHaveBeenCalledOnce();
});

it.each(["resolve", "reject"] as const)("ignores a stale upload that %s after the bill changes", async (outcome) => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  let settle!: () => void;
  const pending = new Promise<Response>((resolve, reject) => {
    settle = outcome === "resolve"
      ? () => resolve(jsonResponse({ attached: 1, items: [receipts[0]], skipped: 0, total_bytes: 3 }, 201))
      : () => reject(new Error("stale upload"));
  });
  installFetch({
    "POST /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts": () => pending
  });
  const view = render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={onChange} receipts={receipts} />);
  await user.upload(screen.getByLabelText("Anexar comprovantes"), new File(["pdf"], "novo.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar comprovantes" }));
  view.rerender(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-second" capabilities={capabilities} onChange={onChange} receipts={[]} />);
  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it.each(["resolve", "reject"] as const)("ignores a stale delete that %s after the bill changes", async (outcome) => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  let settle!: () => void;
  const pending = new Promise<Response>((resolve, reject) => {
    settle = outcome === "resolve" ? () => resolve(new Response(null, { status: 204 })) : () => reject(new Error("stale delete"));
  });
  installFetch({
    "DELETE /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipts/01J00000000000000000000000": () => pending
  });
  const view = render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={onChange} receipts={receipts} />);
  await user.click(screen.getByRole("button", { name: "Remover julho.pdf" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remover" }));
  view.rerender(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-second" capabilities={capabilities} onChange={onChange} receipts={[]} />);
  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it.each(["resolve", "reject"] as const)("ignores a stale reorder that %s after the bill changes", async (outcome) => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  let settle!: () => void;
  const pending = new Promise<Response>((resolve, reject) => {
    settle = outcome === "resolve" ? () => resolve(jsonResponse({ items: [...receipts].reverse() })) : () => reject(new Error("stale reorder"));
  });
  installFetch({
    "PUT /api/v1/billings/billing-public-uuid/bills/bill-public-uuid/receipt-order": () => pending
  });
  const view = render(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-public-uuid" capabilities={capabilities} onChange={onChange} receipts={receipts} />);
  screen.getByRole("button", { name: "Reordenar julho.pdf" }).focus();
  await user.keyboard("{ArrowDown}");
  view.rerender(<ReceiptManager billingUuid="billing-public-uuid" billUuid="bill-second" capabilities={capabilities} onChange={onChange} receipts={[]} />);
  settle();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

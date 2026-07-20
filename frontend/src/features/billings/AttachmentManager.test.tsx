import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { jsonResponse, problemResponse } from "../../test/auth";
import { AttachmentManager } from "./AttachmentManager";

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
vi.mock("../auth/analytics", () => analytics);

type Attachment = components["schemas"]["AttachmentResponse"];
const attachment: Attachment = {
  content_type: "application/pdf", created_at: "2026-07-18T12:00:00Z", file_size: 1536,
  filename: "contrato.pdf", name: "Contrato", sort_order: 0, uuid: "attachment-public"
};

afterEach(() => {
  cleanup();
  analytics.pushAnalyticsFromResponse.mockReset();
  vi.unstubAllGlobals();
});

function installFetch(handler: (method: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => handler(`${init?.method ?? "GET"} ${String(input)}`, init));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

it("uploads a real File through typed multipart, forwards analytics and refreshes", async () => {
  const user = userEvent.setup();
  const onChanged = vi.fn();
  const onError = vi.fn();
  let attempts = 0;
  installFetch((request, init) => {
    expect(request).toBe("POST /api/v1/billings/billing-public/attachments");
    attempts += 1;
    expect(init?.body).toBeInstanceOf(FormData);
    const form = init?.body as FormData;
    expect(form.get("name")).toBe("Contrato de locação");
    expect(form.get("file")).toBeInstanceOf(File);
    if (attempts === 1) return problemResponse({
      code: "invalid_attachment", detail: "Arquivo inválido.", fields: { "body.file": "Selecione um PDF." },
      request_id: "request-id", status: 422, title: "Dados inválidos", type: "problem"
    });
    return jsonResponse(attachment, 201, { "X-Rentivo-Analytics-Event": "rentivo_billing_attachment_uploaded" });
  });
  render(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-public" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);

  const file = new File([new Uint8Array([37, 80, 68, 70])], "contrato.pdf", { type: "application/pdf" });
  await user.type(screen.getByLabelText("Nome do documento"), "Contrato de locação");
  await user.upload(screen.getByLabelText("Arquivo"), file);
  await user.click(screen.getByRole("button", { name: "Enviar" }));
  expect(await screen.findByText("Selecione um PDF.")).toBeVisible();
  expect(screen.getByLabelText("Arquivo")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Enviar" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
  expect(onError).not.toHaveBeenCalled();
});

it("keeps successful upload status when refreshing the attachment list fails", async () => {
  const user = userEvent.setup();
  const onChanged = vi.fn().mockRejectedValue(new Error("refresh offline"));
  const onError = vi.fn();
  installFetch(() => jsonResponse(attachment, 201, { "X-Rentivo-Analytics-Event": "rentivo_billing_attachment_uploaded" }));
  render(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-public" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);

  await user.upload(screen.getByLabelText("Arquivo"), new File(["pdf"], "contrato.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Documento enviado.");
  expect(onError).toHaveBeenCalledWith("Não foi possível atualizar a lista de documentos.");
  expect(onError).not.toHaveBeenCalledWith("Não foi possível enviar o documento.");
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("renders downloads and confirms attachment deletion before refreshing", async () => {
  const user = userEvent.setup();
  const onChanged = vi.fn();
  const onError = vi.fn();
  installFetch((request) => {
    expect(request).toBe("DELETE /api/v1/billings/billing-public/attachments/attachment-public");
    return new Response(null, { status: 204, headers: { "X-Rentivo-Analytics-Event": "rentivo_billing_attachment_deleted" } });
  });
  render(<MemoryRouter><AttachmentManager attachments={[attachment]} billingUuid="billing-public" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);

  expect(screen.getByText("1.5 KB")).toBeVisible();
  expect(screen.getByRole("link", { name: "Ver" })).toHaveAttribute("href", "/api/v1/billings/billing-public/attachments/attachment-public");
  await user.click(screen.getByRole("button", { name: "Remover documento Contrato" }));
  expect(screen.getByRole("dialog", { name: "Remover documento?" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Voltar" }));
  expect(onChanged).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Remover documento Contrato" }));
  await user.click(screen.getByRole("button", { name: "Remover" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  expect(screen.getByRole("status")).toHaveTextContent("Documento removido.");
  expect(screen.getByRole("heading", { name: "Documentos" })).toHaveFocus();
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
  expect(onError).not.toHaveBeenCalled();
});

it("keeps successful removal status and focus when refreshing the attachment list fails", async () => {
  const user = userEvent.setup();
  const onChanged = vi.fn().mockRejectedValue(new Error("refresh offline"));
  const onError = vi.fn();
  installFetch(() => new Response(null, { status: 204, headers: { "X-Rentivo-Analytics-Event": "rentivo_billing_attachment_deleted" } }));
  render(<MemoryRouter><AttachmentManager attachments={[attachment]} billingUuid="billing-public" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);

  await user.click(screen.getByRole("button", { name: "Remover documento Contrato" }));
  await user.click(screen.getByRole("button", { name: "Remover" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Documento removido.");
  expect(onError).toHaveBeenCalledWith("Não foi possível atualizar a lista de documentos.");
  expect(onError).not.toHaveBeenCalledWith("Não foi possível remover o documento.");
  expect(screen.getByRole("heading", { name: "Documentos" })).toHaveFocus();
});

it("shows exact empty detail copy, capability-aware actions and generic mutation failures", async () => {
  const user = userEvent.setup();
  const onError = vi.fn();
  installFetch(() => { throw new Error("offline"); });
  const view = render(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-public" canEdit mode="detail" onChanged={vi.fn()} onError={onError} /></MemoryRouter>);
  expect(screen.getByText("Nenhum documento anexado.")).toBeVisible();
  expect(screen.getByRole("link", { name: "Anexar documento" })).toHaveAttribute("href", "/billings/billing-public/edit");

  view.rerender(<MemoryRouter><AttachmentManager attachments={[attachment]} billingUuid="billing-public" canEdit mode="edit" onChanged={vi.fn()} onError={onError} /></MemoryRouter>);
  await user.click(screen.getByRole("button", { name: "Remover documento Contrato" }));
  await user.click(screen.getByRole("button", { name: "Remover" }));
  await waitFor(() => expect(onError).toHaveBeenCalledWith("Não foi possível remover o documento."));

  view.rerender(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-public" canEdit={false} mode="detail" onChanged={vi.fn()} onError={onError} /></MemoryRouter>);
  expect(screen.queryByRole("link", { name: "Anexar documento" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Enviar" })).not.toBeInTheDocument();

  view.rerender(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-public" canEdit={false} mode="edit" onChanged={vi.fn()} onError={onError} /></MemoryRouter>);
  expect(screen.getByText("Nenhum documento anexado.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Enviar" })).not.toBeInTheDocument();
});

it("validates missing files and reports structured, offline and pending upload states", async () => {
  const user = userEvent.setup();
  const onChanged = vi.fn();
  const onError = vi.fn();
  let attempt = 0;
  let resolveUpload: ((response: Response) => void) | undefined;
  installFetch(() => {
    attempt += 1;
    if (attempt === 1) return problemResponse({
      code: "invalid_attachment", detail: "Arquivo recusado.", fields: {}, request_id: "request-id",
      status: 422, title: "Dados inválidos", type: "problem"
    });
    if (attempt === 2) throw new Error("offline");
    return new Promise<Response>((resolve) => { resolveUpload = resolve; });
  });
  render(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-public" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);

  await user.click(screen.getByRole("button", { name: "Enviar" }));
  expect(screen.getByText("Selecione um arquivo.")).toBeVisible();
  expect(screen.getByLabelText("Arquivo")).toHaveFocus();
  const file = new File(["pdf"], "contrato.pdf", { type: "application/pdf" });
  await user.upload(screen.getByLabelText("Arquivo"), file);
  await user.click(screen.getByRole("button", { name: "Enviar" }));
  await waitFor(() => expect(onError).toHaveBeenCalledWith("Arquivo recusado."));
  await user.click(screen.getByRole("button", { name: "Enviar" }));
  await waitFor(() => expect(onError).toHaveBeenCalledWith("Não foi possível enviar o documento."));
  await user.click(screen.getByRole("button", { name: "Enviar" }));
  expect(screen.getByRole("button", { name: "Enviando..." })).toBeDisabled();
  resolveUpload?.(jsonResponse(attachment, 201));
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
});

it("aborts and ignores an attachment mutation when the billing UUID changes", async () => {
  const user = userEvent.setup();
  const onChanged = vi.fn();
  const onError = vi.fn();
  let uploadSignal: AbortSignal | undefined;
  let resolveUpload: ((response: Response) => void) | undefined;
  installFetch((_request, init) => {
    uploadSignal = init?.signal as AbortSignal | undefined;
    return new Promise<Response>((resolve) => { resolveUpload = resolve; });
  });
  const view = render(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-public" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);

  await user.upload(screen.getByLabelText("Arquivo"), new File(["pdf"], "contrato.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar" }));
  await waitFor(() => expect(uploadSignal).toBeDefined());
  view.rerender(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-second" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);
  expect(uploadSignal?.aborted).toBe(true);

  await act(async () => {
    resolveUpload?.(jsonResponse(attachment, 201, { "X-Rentivo-Analytics-Event": "rentivo_billing_attachment_uploaded" }));
  });
  expect(onChanged).not.toHaveBeenCalled();
  expect(onError).not.toHaveBeenCalled();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("ignores stale upload failures and stale attachment removals after the billing UUID changes", async () => {
  const user = userEvent.setup();
  const onChanged = vi.fn();
  const onError = vi.fn();
  let rejectUpload: ((reason?: unknown) => void) | undefined;
  let removeSignal: AbortSignal | undefined;
  let resolveRemove: ((response: Response) => void) | undefined;
  installFetch((request, init) => {
    if (request === "POST /api/v1/billings/billing-public/attachments") {
      return new Promise<Response>((_resolve, reject) => { rejectUpload = reject; });
    }
    if (request === "DELETE /api/v1/billings/billing-second/attachments/attachment-public") {
      removeSignal = init?.signal as AbortSignal | undefined;
      return new Promise<Response>((resolve) => { resolveRemove = resolve; });
    }
    throw new Error(`Unexpected request: ${request}`);
  });
  const view = render(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-public" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);

  await user.upload(screen.getByLabelText("Arquivo"), new File(["pdf"], "contrato.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar" }));
  view.rerender(<MemoryRouter><AttachmentManager attachments={[attachment]} billingUuid="billing-second" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);
  await act(async () => { rejectUpload?.(new Error("late failure")); });

  await user.click(screen.getByRole("button", { name: "Remover documento Contrato" }));
  await user.click(screen.getByRole("button", { name: "Remover" }));
  await waitFor(() => expect(removeSignal).toBeDefined());
  view.rerender(<MemoryRouter><AttachmentManager attachments={[]} billingUuid="billing-third" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);
  expect(removeSignal?.aborted).toBe(true);
  await act(async () => { resolveRemove?.(new Response(null, { status: 204 })); });

  expect(onChanged).not.toHaveBeenCalled();
  expect(onError).not.toHaveBeenCalled();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("deduplicates attachment deletion and keeps upload and delete in one refresh lock", async () => {
  const user = userEvent.setup();
  let deleteCalls = 0;
  let uploadCalls = 0;
  let resolveRefresh: (() => void) | undefined;
  const onChanged = vi.fn(() => new Promise<void>((resolve) => { resolveRefresh = resolve; }));
  const onError = vi.fn();
  installFetch((request) => {
    if (request === "DELETE /api/v1/billings/billing-public/attachments/attachment-public") {
      deleteCalls += 1;
      return new Response(null, { status: 204 });
    }
    if (request === "POST /api/v1/billings/billing-public/attachments") {
      uploadCalls += 1;
      return jsonResponse(attachment, 201);
    }
    throw new Error(`Unexpected request: ${request}`);
  });
  render(<MemoryRouter><AttachmentManager attachments={[attachment]} billingUuid="billing-public" canEdit mode="edit" onChanged={onChanged} onError={onError} /></MemoryRouter>);

  await user.upload(screen.getByLabelText("Arquivo"), new File(["pdf"], "contrato.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Remover documento Contrato" }));
  const confirmDelete = screen.getByRole("button", { name: "Remover" });
  act(() => {
    confirmDelete.click();
    confirmDelete.click();
  });

  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  expect(deleteCalls).toBe(1);
  expect(screen.getByRole("button", { name: "Enviar" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Remover documento Contrato" })).toBeDisabled();
  fireEvent.submit(screen.getByRole("button", { name: "Enviar" }).closest("form")!);
  expect(uploadCalls).toBe(0);

  await act(async () => { resolveRefresh?.(); });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enviar" })).toBeEnabled());
  expect(screen.getByRole("button", { name: "Remover documento Contrato" })).toBeEnabled();
  expect(onError).not.toHaveBeenCalled();
});

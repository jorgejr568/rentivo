import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { jsonResponse, problemResponse } from "../../test/auth";
import { ApiKeySection } from "./ApiKeySection";

const options = {
  default_expiration_days: 90,
  max_expiration_days: 365,
  organizations: [{ name: "Acme", resource_id: "org-uuid", resource_type: "organization" }],
  personal_workspace: { resource_id: "personal", resource_type: "user" },
  scopes: ["profile:read"]
};

const key = {
  created_at: "2026-07-17T10:00:00Z",
  expires_at: "2026-10-17T10:00:00Z",
  grants: [{ available: true, resource_id: "personal", resource_type: "user" }],
  hint: "rntv-v1-abcd••••yz",
  last_used_at: null,
  name: "Produção",
  revoked_at: null,
  scopes: ["profile:read"],
  uuid: "key-uuid"
};

afterEach(() => vi.unstubAllGlobals());

it("creates an integration key and gates its one-time secret", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/api-keys/options") return jsonResponse(options);
    if (url === "/api/v1/api-keys" && init?.method === "POST") return jsonResponse({ ...key, secret: "rntv-v1-secret" }, 201);
    if (url === "/api/v1/api-keys") return jsonResponse({ items: [] });
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(<ApiKeySection />);

  await user.click(await screen.findByRole("button", { name: "Criar chave" }));
  await user.type(screen.getByLabelText("Nome"), "Produção");
  await user.click(screen.getByLabelText("Consultar perfil"));
  await user.click(screen.getByLabelText("Pessoal"));
  await user.click(screen.getByRole("button", { name: "Criar chave" }));
  expect(await screen.findByText("rntv-v1-secret")).toBeVisible();
  await user.click(screen.getByRole("checkbox", { name: /guardei esta chave/i }));
  await user.click(screen.getByRole("button", { name: "Concluir" }));
  expect(await screen.findByText("Chave de integração criada.")).toBeVisible();
});

it("edits and idempotently revokes an active key", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/api-keys/options") return jsonResponse(options);
    if (url === "/api/v1/api-keys/key-uuid" && init?.method === "PATCH") return jsonResponse({ ...key, name: "Atualizada" });
    if (url === "/api/v1/api-keys/key-uuid" && init?.method === "DELETE") return new Response(null, { status: 204 });
    if (url === "/api/v1/api-keys") return jsonResponse({ items: [key, { ...key, name: "Outra", uuid: "other-uuid" }] });
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(<ApiKeySection />);

  await user.click(await screen.findByRole("button", { name: "Editar Produção" }));
  await user.clear(screen.getByLabelText("Nome"));
  await user.type(screen.getByLabelText("Nome"), "Atualizada");
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
  expect(await screen.findByText("Chave de integração atualizada.")).toBeVisible();
  expect(screen.getByText("Outra")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Revogar Atualizada" }));
  await user.click(screen.getByRole("button", { name: "Revogar chave" }));
  expect(await screen.findByText("Chave de integração revogada.")).toBeVisible();
  expect(screen.getByText("Revogada")).toBeVisible();
});

it("retries load failures and reports API and network mutation errors", async () => {
  const user = userEvent.setup();
  let listAttempts = 0;
  let createAttempts = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/api-keys/options") return jsonResponse(options);
    if (url === "/api/v1/api-keys" && init?.method === "POST") {
      createAttempts += 1;
      if (createAttempts === 1) return problemResponse({ code: "invalid", detail: "Chave inválida.", fields: {}, request_id: "id", status: 422, title: "Inválida", type: "problem" });
      throw new Error("offline");
    }
    if (url === "/api/v1/api-keys") {
      listAttempts += 1;
      if (listAttempts === 1) throw new Error("offline");
      return jsonResponse({ items: [] });
    }
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(<ApiKeySection />);

  expect(await screen.findByText("Não foi possível carregar as chaves de integração.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  await user.click(await screen.findByRole("button", { name: "Criar chave" }));
  await user.type(screen.getByLabelText("Nome"), "Teste");
  await user.click(screen.getByLabelText("Consultar perfil"));
  await user.click(screen.getByLabelText("Pessoal"));
  await user.click(screen.getByRole("button", { name: "Criar chave" }));
  expect(await screen.findByText("Chave inválida.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Criar chave" }));
  expect(await screen.findByText("Não foi possível salvar a chave de integração.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Cancelar" }));
  await waitFor(() => expect(screen.getByText("Nenhuma chave de integração cadastrada.")).toBeVisible());
});

it("keeps the key active when revocation fails", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/api-keys/options") return jsonResponse(options);
    if (url === "/api/v1/api-keys/key-uuid" && init?.method === "DELETE") throw new Error("offline");
    if (url === "/api/v1/api-keys") return jsonResponse({ items: [key] });
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(<ApiKeySection />);
  await user.click(await screen.findByRole("button", { name: "Revogar Produção" }));
  await user.click(screen.getByRole("button", { name: "Revogar chave" }));
  expect(await screen.findByText("Não foi possível revogar a chave de integração.")).toBeVisible();
  expect(screen.queryByText("Revogada")).not.toBeInTheDocument();
});

it("shows server load and revoke problems and leaves unrelated keys unchanged", async () => {
  const user = userEvent.setup();
  let loads = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/api-keys/options") return jsonResponse(options);
    if (url === "/api/v1/api-keys/key-uuid" && init?.method === "DELETE") return problemResponse({ code: "revoke", detail: "Revogação bloqueada.", fields: {}, request_id: "id", status: 409, title: "Conflito", type: "problem" });
    if (url === "/api/v1/api-keys") {
      loads += 1;
      if (loads === 1) return problemResponse({ code: "load", detail: "Acesso negado.", fields: {}, request_id: "id", status: 403, title: "Negado", type: "problem" });
      return jsonResponse({ items: [key, { ...key, name: "Outra", uuid: "other-uuid" }] });
    }
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(<ApiKeySection />);
  expect(await screen.findByText("Acesso negado.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  await user.click(await screen.findByRole("button", { name: "Revogar Produção" }));
  await user.click(screen.getByRole("button", { name: "Revogar chave" }));
  expect(await screen.findByText("Revogação bloqueada.")).toBeVisible();
  expect(screen.getByText("Outra")).toBeVisible();
});

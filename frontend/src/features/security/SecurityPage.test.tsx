import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { jsonResponse, problemResponse } from "../../test/auth";
import { renderAuth } from "../../test/renderAuth";
import type { components } from "../../lib/api/schema";
import { SecurityPage } from "./SecurityPage";
import { createPasskey } from "./webauthn";

vi.mock("./webauthn", () => ({ createPasskey: vi.fn() }));

const summary: components["schemas"]["SecuritySummaryResponse"] = {
  mfa: { organization_enforced: false, setup_required: false },
  passkeys: [],
  profile: { email: "user@example.com", pix_key: "pix", pix_merchant_city: "SP", pix_merchant_name: "User" },
  totp: { enabled: true, recovery_codes_remaining: 8 }
};

const apiKeyOptions = { default_expiration_days: 90, max_expiration_days: 365, organizations: [], personal_workspace: { resource_id: "personal", resource_type: "user" }, scopes: ["profile:read"] };

function renderPage(handlers: Record<string, (init?: RequestInit) => Response | Promise<Response>> = {}, value: components["schemas"]["SecuritySummaryResponse"] = summary) {
  return renderAuth(<SecurityPage />, {
    handlers: {
      "/api/v1/api-keys": () => jsonResponse({ items: [] }),
      "/api/v1/api-keys/options": () => jsonResponse(apiKeyOptions),
      "/api/v1/auth/logout": () => new Response(null, { status: 204 }),
      "/api/v1/security": () => jsonResponse(value),
      ...handlers
    },
    path: "/security",
    session: "authenticated"
  });
}

afterEach(() => {
  vi.mocked(createPasskey).mockReset();
  vi.unstubAllGlobals();
});

it("ports the security summary and clears authentication after disabling TOTP", async () => {
  const user = userEvent.setup();
  renderPage({ "/api/v1/security/totp/disable": () => new Response(null, { status: 204 }) });

  expect(await screen.findByRole("heading", { name: "Segurança" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Desativar TOTP" }));
  await user.type(screen.getByLabelText("Confirme sua senha para desativar"), "password");
  await user.click(screen.getByRole("button", { name: "Confirmar Desativação" }));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
});

it("shows incomplete PIX, enforced MFA, disabled TOTP, and low recovery warnings", async () => {
  const value = {
    ...summary,
    mfa: { organization_enforced: true, setup_required: true },
    profile: { ...summary.profile, pix_key: "", pix_merchant_city: "", pix_merchant_name: "" },
    totp: { enabled: false, recovery_codes_remaining: 0 }
  };
  renderPage({}, value);
  expect(await screen.findByText(/Preencha todos os campos/)).toBeVisible();
  expect(screen.getAllByText(/Sua organização exige/).length).toBeGreaterThan(0);
  expect(screen.getByRole("link", { name: "Configurar TOTP" })).toHaveAttribute("href", "/security/totp/setup");
});

it("updates PIX and changes the password atomically", async () => {
  const user = userEvent.setup();
  renderPage({
    "/api/v1/security/change-password": () => new Response(null, { headers: { "X-Rentivo-Analytics-Event": "rentivo_password_changed" }, status: 204 }),
    "/api/v1/security/pix": (init) => jsonResponse({ profile: { ...summary.profile, pix_key: JSON.parse(String(init?.body)).pix_key } })
  });
  await screen.findByRole("heading", { name: "Segurança" });
  await user.clear(screen.getByLabelText("Chave PIX"));
  await user.type(screen.getByLabelText("Chave PIX"), "nova-chave");
  await user.clear(screen.getByLabelText("Nome do recebedor"));
  await user.type(screen.getByLabelText("Nome do recebedor"), "Novo Nome");
  await user.clear(screen.getByLabelText("Cidade do recebedor"));
  await user.type(screen.getByLabelText("Cidade do recebedor"), "Rio");
  await user.click(screen.getByRole("button", { name: "Salvar Dados PIX" }));
  expect(await screen.findByText("Dados do PIX atualizados.")).toBeVisible();
  await user.type(screen.getByLabelText("Senha atual"), "current");
  await user.type(screen.getByLabelText("Nova senha"), "new-password");
  await user.type(screen.getByLabelText("Confirmar nova senha"), "different");
  await user.click(screen.getByRole("button", { name: "Alterar Senha" }));
  expect(await screen.findByText("As senhas não coincidem.")).toBeVisible();
  await user.clear(screen.getByLabelText("Confirmar nova senha"));
  await user.type(screen.getByLabelText("Confirmar nova senha"), "new-password");
  await user.click(screen.getByRole("button", { name: "Alterar Senha" }));
  expect(await screen.findByText("Senha alterada com sucesso!")).toBeVisible();
  expect(screen.getByLabelText("Senha atual")).toHaveValue("");
});

it("routes regenerated recovery codes to their one-time screen", async () => {
  const user = userEvent.setup();
  renderPage({ "/api/v1/security/recovery-codes/regenerate": () => jsonResponse({ recovery_codes: ["one"] }, 200, { "X-Rentivo-Analytics-Event": "rentivo_recovery_codes_regenerated" }) });
  await user.click(await screen.findByRole("button", { name: "Regenerar Códigos de Recuperação" }));
  expect(await screen.findByTestId("location")).toHaveTextContent("/security/recovery-codes");
});

it("registers a passkey with typed WebAuthn data", async () => {
  const user = userEvent.setup();
  vi.mocked(createPasskey).mockResolvedValue({
    clientExtensionResults: {}, id: "credential", rawId: "raw", response: { attestationObject: "attestation", clientDataJSON: "client" }, type: "public-key"
  });
  renderPage({
    "/api/v1/security/passkeys/register/begin": () => jsonResponse({ challenge_id: "challenge", options: { challenge: "challenge", excludeCredentials: [], hints: [], pubKeyCredParams: [], rp: { name: "Rentivo" }, user: { displayName: "User", id: "id", name: "user@example.com" } } }),
    "/api/v1/security/passkeys/register/complete": () => jsonResponse({ created_at: "2026-07-17T10:00:00Z", last_used_at: null, name: "Notebook", uuid: "pk-uuid" }, 200, { "X-Rentivo-Analytics-Event": "rentivo_passkey_added" })
  });
  await user.type(await screen.findByLabelText("Nome da passkey"), "Notebook");
  await user.click(screen.getByRole("button", { name: /Adicionar Passkey/ }));
  expect(await screen.findByText("Passkey cadastrada.")).toBeVisible();
  expect(screen.getByText("Notebook")).toBeVisible();
  vi.mocked(createPasskey).mockResolvedValueOnce(null);
  await user.click(screen.getByRole("button", { name: /Adicionar Passkey/ }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});

it("logs out after deleting a passkey and preserves the session when deletion is rejected", async () => {
  const user = userEvent.setup();
  let deletions = 0;
  const value = { ...summary, passkeys: [{ created_at: "2026-07-17T10:00:00Z", last_used_at: null, name: "Notebook", uuid: "pk-uuid" }] };
  renderPage({
    "/api/v1/security/passkeys/pk-uuid": () => {
      deletions += 1;
      return deletions === 1
        ? problemResponse({ code: "mfa_required_by_organization", detail: "Mantenha um fator ativo.", fields: {}, request_id: "id", status: 409, title: "Conflito", type: "problem" })
        : new Response(null, { status: 204 });
    }
  }, value);
  await user.click(await screen.findByRole("button", { name: "Remover Notebook" }));
  await user.click(screen.getByRole("button", { name: "Remover passkey" }));
  expect(await screen.findByText("Mantenha um fator ativo.")).toBeVisible();
  expect(screen.getByTestId("location")).toHaveTextContent("/security");
  await user.click(screen.getByRole("button", { name: "Remover Notebook" }));
  await user.click(screen.getByRole("button", { name: "Remover passkey" }));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
});

it("surfaces API and network action failures", async () => {
  const user = userEvent.setup();
  let pixAttempts = 0;
  let passwordAttempts = 0;
  let recoveryAttempts = 0;
  renderPage({
    "/api/v1/security/change-password": () => {
      passwordAttempts += 1;
      if (passwordAttempts === 1) return problemResponse({ code: "password", detail: "Senha atual incorreta.", fields: {}, request_id: "id", status: 400, title: "Inválida", type: "problem" });
      throw new Error("offline");
    },
    "/api/v1/security/pix": () => {
      pixAttempts += 1;
      if (pixAttempts === 1) return problemResponse({ code: "pix", detail: "PIX inválido.", fields: {}, request_id: "id", status: 422, title: "Inválido", type: "problem" });
      throw new Error("offline");
    },
    "/api/v1/security/recovery-codes/regenerate": () => {
      recoveryAttempts += 1;
      if (recoveryAttempts === 1) return problemResponse({ code: "recovery", detail: "Não disponível.", fields: {}, request_id: "id", status: 409, title: "Conflito", type: "problem" });
      throw new Error("offline");
    },
    "/api/v1/security/totp/disable": () => problemResponse({ code: "totp", detail: "TOTP protegido.", fields: {}, request_id: "id", status: 409, title: "Conflito", type: "problem" })
  });
  await screen.findByRole("heading", { name: "Segurança" });
  await user.click(screen.getByRole("button", { name: "Salvar Dados PIX" }));
  expect(await screen.findByText("PIX inválido.")).toBeVisible();
  expect(screen.getByLabelText("Chave PIX")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Salvar Dados PIX" }));
  expect(await screen.findByText("Não foi possível atualizar os dados do PIX.")).toBeVisible();
  await user.type(screen.getByLabelText("Senha atual"), "current");
  await user.type(screen.getByLabelText("Nova senha"), "new");
  await user.type(screen.getByLabelText("Confirmar nova senha"), "new");
  await user.click(screen.getByRole("button", { name: "Alterar Senha" }));
  expect(await screen.findByText("Senha atual incorreta.")).toBeVisible();
  expect(screen.getByLabelText("Senha atual")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Alterar Senha" }));
  expect(await screen.findByText("Não foi possível alterar a senha.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Regenerar Códigos de Recuperação" }));
  expect(await screen.findByText("Não disponível.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Regenerar Códigos de Recuperação" })).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Regenerar Códigos de Recuperação" }));
  expect(await screen.findByText("Não foi possível regenerar os códigos de recuperação.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Desativar TOTP" }));
  await user.type(screen.getByLabelText("Confirme sua senha para desativar"), "password");
  await user.click(screen.getByRole("button", { name: "Confirmar Desativação" }));
  expect(await screen.findByText("TOTP protegido.")).toBeVisible();
  expect(screen.getByLabelText("Confirme sua senha para desativar")).toHaveFocus();
});

it("retries a failed security-summary request", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  renderPage({
    "/api/v1/security": () => {
      attempts += 1;
      if (attempts === 1) throw new Error("offline");
      return jsonResponse({ ...summary, totp: { enabled: true, recovery_codes_remaining: 2 } });
    }
  });
  expect(await screen.findByText("Não foi possível carregar as configurações de segurança.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText(/Recomendamos regenerar/)).toBeVisible();
  await waitFor(() => expect(screen.getByRole("heading", { name: "Segurança" })).toBeVisible());
});

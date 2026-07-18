import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { ApiKeyForm, scopeLabel } from "./ApiKeyForm";

const options: components["schemas"]["APIKeyOptionsResponse"] = {
  default_expiration_days: 90,
  max_expiration_days: 365,
  organizations: [{ name: "Acme", resource_id: "org-uuid", resource_type: "organization" }],
  personal_workspace: { resource_id: "personal", resource_type: "user" },
  scopes: ["profile:read", "billings:read"]
};

it("requires a name, scope, and at least one personal or organization workspace", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(<ApiKeyForm onCancel={vi.fn()} onSubmit={onSubmit} options={options} />);

  await user.click(screen.getByRole("button", { name: "Criar chave" }));
  expect(screen.getByText("Informe um nome para a chave.")).toBeVisible();
  expect(screen.getByText("Selecione pelo menos um escopo.")).toBeVisible();
  expect(screen.getByText("Selecione pelo menos um espaço de trabalho.")).toBeVisible();
  expect(onSubmit).not.toHaveBeenCalled();
});

it("submits selected safe scopes and public workspace identifiers", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  render(<ApiKeyForm onCancel={onCancel} onSubmit={onSubmit} options={options} />);

  await user.type(screen.getByLabelText("Nome"), "Automação");
  await user.clear(screen.getByLabelText("Expira em"));
  await user.type(screen.getByLabelText("Expira em"), "2026-12-31");
  await user.click(screen.getByLabelText("Consultar perfil"));
  await user.click(screen.getByLabelText("Pessoal"));
  await user.click(screen.getByLabelText("Acme"));
  await user.click(screen.getByRole("button", { name: "Criar chave" }));

  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    grants: [
      { resource_id: "personal", resource_type: "user" },
      { resource_id: "org-uuid", resource_type: "organization" }
    ],
    name: "Automação",
    scopes: ["profile:read"]
  }));
  expect(onSubmit.mock.calls[0][0].expires_at).toMatch(/T23:59:59\.999Z$/);
  await user.click(screen.getByRole("button", { name: "Cancelar" }));
  expect(onCancel).toHaveBeenCalledOnce();
});

it("lets the backend apply the exact default expiration", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(<ApiKeyForm onCancel={vi.fn()} onSubmit={onSubmit} options={options} />);

  await user.type(screen.getByLabelText("Nome"), "Padrão");
  await user.click(screen.getByLabelText("Consultar perfil"));
  await user.click(screen.getByLabelText("Pessoal"));
  await user.click(screen.getByRole("button", { name: "Criar chave" }));

  expect(onSubmit).toHaveBeenCalledOnce();
  expect(onSubmit.mock.calls[0][0]).not.toHaveProperty("expires_at");
});

it("never serializes the maximum date beyond the backend duration cap", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(<ApiKeyForm onCancel={vi.fn()} onSubmit={onSubmit} options={options} />);

  await user.type(screen.getByLabelText("Nome"), "Máximo");
  await user.click(screen.getByLabelText("Consultar perfil"));
  await user.click(screen.getByLabelText("Pessoal"));
  const expiration = screen.getByLabelText("Expira em");
  await user.clear(expiration);
  await user.type(expiration, expiration.getAttribute("max")!);
  const submittedAfter = Date.now();
  await user.click(screen.getByRole("button", { name: "Criar chave" }));

  const submittedExpiration = new Date(onSubmit.mock.calls[0][0].expires_at).getTime();
  expect(submittedExpiration).toBeLessThanOrEqual(
    submittedAfter + options.max_expiration_days * 24 * 60 * 60 * 1000
  );
});

it("evaluates each validation independently and supports organization-only access", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(<ApiKeyForm onCancel={vi.fn()} onSubmit={onSubmit} options={options} />);
  await user.type(screen.getByLabelText("Nome"), "Teste");
  await user.click(screen.getByRole("button", { name: "Criar chave" }));
  expect(screen.getByText("Selecione pelo menos um escopo.")).toBeVisible();
  await user.click(screen.getByLabelText("Consultar perfil"));
  await user.click(screen.getByRole("button", { name: "Criar chave" }));
  expect(screen.getByText("Selecione pelo menos um espaço de trabalho.")).toBeVisible();
  await user.click(screen.getByLabelText("Acme"));
  await user.click(screen.getByRole("button", { name: "Criar chave" }));
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ grants: [{ resource_id: "org-uuid", resource_type: "organization" }] }));
  await user.click(screen.getByLabelText("Consultar perfil"));
  expect(screen.getByLabelText("Consultar perfil")).not.toBeChecked();
});

it("hydrates an existing key without changing expiration", () => {
  const onSubmit = vi.fn();
  render(
    <ApiKeyForm
      initialKey={{
        created_at: "2026-01-01T00:00:00Z",
        expires_at: "2026-12-01T00:00:00Z",
        grants: [
          { available: true, resource_id: "personal", resource_type: "user" },
          { available: true, resource_id: "org-uuid", resource_type: "organization" },
          { available: false, resource_id: null, resource_type: "organization" }
        ],
        hint: "rntv-v1-abcd••••yz",
        last_used_at: null,
        name: "Atual",
        revoked_at: null,
        scopes: ["profile:read"],
        uuid: "key-uuid"
      }}
      loading
      onCancel={vi.fn()}
      onSubmit={onSubmit}
      options={options}
    />
  );

  expect(screen.queryByLabelText("Expira em")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Salvar alterações" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
});

it("uses readable known scope labels and preserves an unknown safe scope", () => {
  expect(scopeLabel("billings:read")).toBe("Consultar cobranças");
  expect(scopeLabel("future:read")).toBe("future:read");
});

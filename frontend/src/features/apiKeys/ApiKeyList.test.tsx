import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { ApiKeyList, formatDate } from "./ApiKeyList";

const options: components["schemas"]["APIKeyOptionsResponse"] = {
  default_expiration_days: 90,
  max_expiration_days: 365,
  organizations: [{ name: "Acme", resource_id: "org-uuid", resource_type: "organization" }],
  personal_workspace: { resource_id: "personal", resource_type: "user" },
  scopes: ["profile:read"]
};

it("renders the empty integration-key state", () => {
  render(<ApiKeyList items={[]} onEdit={vi.fn()} onRevoke={vi.fn()} options={options} />);
  expect(screen.getByText("Nenhuma chave de integração cadastrada.")).toBeVisible();
  expect(formatDate(null)).toBe("Nunca");
});

it("renders masked metadata and exposes actions only for active keys", async () => {
  const user = userEvent.setup();
  const onEdit = vi.fn();
  const onRevoke = vi.fn();
  const active = {
    created_at: "2026-07-17T10:00:00Z",
    expires_at: "2026-10-17T10:00:00Z",
    grants: [
      { available: true, resource_id: "personal", resource_type: "user" as const },
      { available: true, resource_id: "org-uuid", resource_type: "organization" as const },
      { available: true, resource_id: "missing-org", resource_type: "organization" as const },
      { available: false, resource_id: null, resource_type: "organization" as const }
    ],
    hint: "rntv-v1-abcd••••yz",
    last_used_at: null,
    name: "Produção",
    revoked_at: null,
    scopes: ["profile:read"],
    uuid: "active"
  };
  render(<ApiKeyList items={[active, { ...active, name: "Antiga", revoked_at: "2026-07-18T10:00:00Z", uuid: "revoked" }]} onEdit={onEdit} onRevoke={onRevoke} options={options} />);

  expect(screen.getAllByText("rntv-v1-abcd••••yz")).toHaveLength(2);
  expect(screen.getAllByText(/Pessoal, Acme, Organização, Espaço indisponível/)).toHaveLength(2);
  expect(screen.getByText("Revogada")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Editar Produção" }));
  await user.click(screen.getByRole("button", { name: "Revogar Produção" }));
  expect(onEdit).toHaveBeenCalledWith(active);
  expect(onRevoke).toHaveBeenCalledWith(active);
  expect(screen.getByRole("button", { name: "Editar Antiga" })).toBeDisabled();
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { PasskeyManager } from "./PasskeyManager";

it("confirms passkey deletion and reports that the login was revoked", async () => {
  const user = userEvent.setup();
  const onDelete = vi.fn().mockResolvedValue(undefined);
  const onSessionRevoked = vi.fn();
  render(
    <PasskeyManager
      onDelete={onDelete}
      onRegister={vi.fn()}
      onSessionRevoked={onSessionRevoked}
      organizationEnforced={false}
      passkeys={[{ created_at: "2026-07-17T10:00:00Z", last_used_at: null, name: "Notebook", uuid: "pk-uuid" }]}
    />
  );

  await user.click(screen.getByRole("button", { name: "Remover Notebook" }));
  await user.click(screen.getByRole("button", { name: "Remover passkey" }));
  expect(onDelete).toHaveBeenCalledWith("pk-uuid");
  expect(onSessionRevoked).toHaveBeenCalledOnce();
});

it("registers a named passkey and uses the legacy default for a blank name", async () => {
  const user = userEvent.setup();
  const onRegister = vi.fn().mockResolvedValue(undefined);
  render(<PasskeyManager onDelete={vi.fn()} onRegister={onRegister} onSessionRevoked={vi.fn()} organizationEnforced passkeys={[]} />);
  expect(screen.getByText(/Sua organização exige/)).toBeVisible();
  expect(screen.getByText("Nenhuma passkey cadastrada.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: /Adicionar Passkey/ }));
  expect(onRegister).toHaveBeenCalledWith("Minha Passkey");
  await user.type(screen.getByLabelText("Nome da passkey"), "Celular");
  await user.click(screen.getByRole("button", { name: /Adicionar Passkey/ }));
  expect(onRegister).toHaveBeenLastCalledWith("Celular");
  expect(screen.getByLabelText("Nome da passkey")).toHaveValue("");
});

it("silently handles a canceled passkey prompt and focuses other failures", async () => {
  const user = userEvent.setup();
  const onRegister = vi.fn()
    .mockRejectedValueOnce(new DOMException("cancel", "NotAllowedError"))
    .mockRejectedValueOnce(new Error("Falha do navegador."))
    .mockRejectedValueOnce("unknown");
  render(<PasskeyManager onDelete={vi.fn()} onRegister={onRegister} onSessionRevoked={vi.fn()} organizationEnforced={false} passkeys={[]} />);
  const button = screen.getByRole("button", { name: /Adicionar Passkey/ });
  await user.click(button);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await user.click(button);
  expect(await screen.findByText("Falha do navegador.")).toBeVisible();
  expect(screen.getByLabelText("Nome da passkey")).toHaveFocus();
  await user.click(button);
  expect(await screen.findByText("Não foi possível cadastrar a passkey.")).toBeVisible();
});

it("keeps the session when passkey deletion is rejected", async () => {
  const user = userEvent.setup();
  const onSessionRevoked = vi.fn();
  render(<PasskeyManager onDelete={vi.fn().mockRejectedValue("unknown")} onRegister={vi.fn()} onSessionRevoked={onSessionRevoked} organizationEnforced={false} passkeys={[{ created_at: "2026-07-17T10:00:00Z", last_used_at: "2026-07-18T10:00:00Z", name: "", uuid: "pk-uuid" }]} />);
  expect(screen.getByText("Sem nome")).toBeVisible();
  expect(screen.queryByText("Nunca")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Remover" }));
  await user.click(screen.getByRole("button", { name: "Remover passkey" }));
  expect(await screen.findByText("Não foi possível remover a passkey.")).toBeVisible();
  expect(onSessionRevoked).not.toHaveBeenCalled();
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ApiKeySecretDialog } from "./ApiKeySecretDialog";

it("shows the integration secret once and requires acknowledgement before closing", async () => {
  const user = userEvent.setup();
  const onClose = vi.fn();
  render(<ApiKeySecretDialog onClose={onClose} open secret="rntv-v1-secret" />);

  expect(screen.getByText("rntv-v1-secret")).toBeVisible();
  expect(screen.getByRole("button", { name: "Concluir" })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: /guardei esta chave/i })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(onClose).not.toHaveBeenCalled();
  await user.keyboard("{Tab}");
  expect(screen.getByRole("button", { name: "Copiar chave" })).toHaveFocus();
  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(screen.getByRole("checkbox", { name: /guardei esta chave/i })).toHaveFocus();
  await user.click(screen.getByRole("checkbox", { name: /guardei esta chave/i }));
  await user.keyboard("{Tab}");
  expect(screen.getByRole("button", { name: "Concluir" })).toHaveFocus();
  await user.keyboard("{Tab}");
  expect(screen.getByRole("button", { name: "Copiar chave" })).toHaveFocus();
  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(screen.getByRole("button", { name: "Concluir" })).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Concluir" }));
  expect(onClose).toHaveBeenCalledOnce();
});

it("copies the secret and resets its state after being closed", async () => {
  const user = userEvent.setup();
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
  const { rerender } = render(<ApiKeySecretDialog onClose={vi.fn()} open secret="rntv-v1-secret" />);
  await user.click(screen.getByRole("button", { name: "Copiar chave" }));
  expect(writeText).toHaveBeenCalledWith("rntv-v1-secret");
  expect(screen.getByRole("button", { name: "Copiada!" })).toBeVisible();
  rerender(<ApiKeySecretDialog onClose={vi.fn()} open={false} secret="rntv-v1-secret" />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

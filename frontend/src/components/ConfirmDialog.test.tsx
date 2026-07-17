import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("traps focus in a destructive confirmation", async () => {
    const user = userEvent.setup();

    render(
      <ConfirmDialog
        open
        title="Revogar chave"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    );

    await user.tab();
    await user.tab();

    expect(screen.getByRole("button", { name: "Voltar" })).toHaveFocus();

    await user.tab({ shift: true });

    expect(screen.getByRole("button", { name: "Confirmar" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "ArrowDown" });
  });

  it("closes on Escape and restores focus to its trigger", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const trigger = document.createElement("button");
    trigger.textContent = "Abrir confirmação";
    document.body.append(trigger);
    trigger.focus();

    render(
      <ConfirmDialog open title="Revogar chave" onConfirm={vi.fn()} onClose={onClose} />
    );

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledOnce();
    expect(trigger).toHaveFocus();
    trigger.remove();
  });

  it("confirms, closes, and supports the primary variant", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onClose = vi.fn();

    render(
      <ConfirmDialog
        acceptLabel="Marcar como pago"
        body="Esta cobrança será atualizada."
        onConfirm={onConfirm}
        onClose={onClose}
        open
        title="Confirmar pagamento"
        variant="primary"
      />
    );

    expect(screen.getByText("Esta cobrança será atualizada.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Marcar como pago" }));

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("does not render while closed", () => {
    render(<ConfirmDialog open={false} title="Revogar chave" onConfirm={vi.fn()} onClose={vi.fn()} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes when its backdrop is pressed", () => {
    const onClose = vi.fn();

    render(<ConfirmDialog open title="Revogar chave" onConfirm={vi.fn()} onClose={onClose} />);

    fireEvent.mouseDown(screen.getByRole("dialog").parentElement!);

    expect(onClose).toHaveBeenCalledOnce();
  });
});

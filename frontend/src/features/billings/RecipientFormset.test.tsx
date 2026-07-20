import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";

import { RecipientFormset, type ContactValue } from "./RecipientFormset";

afterEach(cleanup);

it("adds, edits and removes recipients with the legacy row classes", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const values: ContactValue[] = [{ id: "recipient-1", email: "joao@example.com", name: "João" }];
  function Harness({ kind }: { kind: "recipients" | "reply_to" }) {
    const [contacts, setContacts] = useState(values);
    return <RecipientFormset kind={kind} onChange={(next) => { onChange(next); setContacts(next); }} values={contacts} />;
  }
  const view = render(<Harness kind="recipients" />);

  expect(screen.getByRole("heading", { name: "Destinatários" })).toBeVisible();
  expect(screen.getByLabelText("Nome do destinatário 1").closest(".item-grid")).not.toBeNull();
  await user.clear(screen.getByLabelText("Nome do destinatário 1"));
  await user.type(screen.getByLabelText("Nome do destinatário 1"), "José");
  expect(onChange).toHaveBeenLastCalledWith([{ ...values[0], name: "José" }]);

  await user.click(screen.getByRole("button", { name: "Adicionar destinatário" }));
  expect(onChange).toHaveBeenLastCalledWith([
    { ...values[0], name: "José" },
    expect.objectContaining({ email: "", name: "" })
  ]);
  await user.type(screen.getByLabelText("Nome do destinatário 2"), "Ana");

  await user.click(screen.getByRole("button", { name: "Remover destinatário 2" }));
  await user.click(screen.getByRole("button", { name: "Remover destinatário 1" }));
  expect(onChange).toHaveBeenLastCalledWith([]);
  view.unmount();
  render(<Harness kind="reply_to" />);
  expect(screen.getByRole("heading", { name: "Responder para (Reply-To)" })).toBeVisible();
  await user.type(screen.getByLabelText("E-mail do Reply-To 1"), "x");
  expect(onChange).toHaveBeenLastCalledWith([{ ...values[0], email: "joao@example.comx" }]);
  await user.click(screen.getByRole("button", { name: "Remover Reply-To 1" }));
  expect(onChange).toHaveBeenLastCalledWith([]);
});

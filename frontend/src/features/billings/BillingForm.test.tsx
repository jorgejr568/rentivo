import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { BillingForm, type BillingFormValues } from "./BillingForm";
import { emptyBillingValues } from "./billingFormValues";

type Organization = components["schemas"]["OrganizationResponse"];

const organizations: Organization[] = [
  {
    capabilities: { can_create_billing: true, can_invite: false, can_manage: false, can_view_billing_stats: true },
    created_at: null,
    current_role: "viewer",
    enforce_mfa: false,
    name: "Permitida por capability",
    updated_at: null,
    uuid: "org-allowed"
  },
  {
    capabilities: { can_create_billing: false, can_invite: true, can_manage: true, can_view_billing_stats: false },
    created_at: null,
    current_role: "admin",
    enforce_mfa: false,
    name: "Negada por capability",
    updated_at: null,
    uuid: "org-denied"
  }
];

afterEach(cleanup);

function Harness({ fieldErrors = {} }: { fieldErrors?: Record<string, string> }) {
  const values = emptyBillingValues();
  values.recipients = [{ email: "", id: "recipient-error", name: "" }];
  const onSubmit = vi.fn();
  return <MemoryRouter><BillingForm error="" fieldErrors={fieldErrors} mode="create" onSubmit={onSubmit} organizations={organizations} saving={false} values={values} /></MemoryRouter>;
}

function renderForm(element: React.ReactNode) {
  return render(<MemoryRouter>{element}</MemoryRouter>);
}

it("preserves the create form structure and filters owners by capability instead of role", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  const values = emptyBillingValues();
  renderForm(<BillingForm error="" fieldErrors={{}} mode="create" onSubmit={onSubmit} organizations={organizations} saving={false} values={values} />);

  expect(screen.getByLabelText("Nome do imóvel")).toHaveFocus();
  expect(screen.getByRole("heading", { name: "Detalhes" }).closest(".panel")).not.toBeNull();
  expect(screen.getByRole("option", { name: "Minha conta" })).toBeVisible();
  expect(screen.getByRole("option", { name: "Permitida por capability" })).toBeVisible();
  expect(screen.queryByRole("option", { name: "Negada por capability" })).not.toBeInTheDocument();
  expect(screen.getByText("R$ 0,00")).toHaveAttribute("id", "fixed-subtotal");

  await user.type(screen.getByLabelText("Nome do imóvel"), "Apartamento 302");
  await user.type(screen.getByRole("textbox", { name: /^Descrição$/ }), "Inquilino atual");
  await user.type(screen.getByLabelText("Chave PIX"), "pix@example.com");
  await user.type(screen.getByLabelText("Nome do recebedor"), "MARIA");
  await user.type(screen.getByLabelText("Cidade do recebedor"), "SALVADOR");
  await user.type(screen.getByLabelText("Descrição do item 1"), "Aluguel");
  await user.type(screen.getByLabelText("Valor do item 1 (R$)"), "2.850,00");
  expect(screen.getByText("R$ 2.850,00")).toBeVisible();
  await user.selectOptions(screen.getByLabelText("Tipo do item 1"), "variable");
  expect(screen.getByLabelText("Valor do item 1 (R$)")).toBeDisabled();
  expect(screen.getByLabelText("Valor do item 1 (R$)")).toHaveClass("input--disabled");
  expect(screen.getByText("R$ 0,00")).toBeVisible();
  await user.selectOptions(screen.getByLabelText("Tipo do item 1"), "fixed");
  await user.selectOptions(screen.getByLabelText("Tipo do item 1"), "variable");

  await user.click(screen.getByRole("button", { name: "Adicionar item" }));
  expect(screen.getByLabelText("Descrição do item 2")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Remover item 2" }));
  expect(screen.queryByLabelText("Descrição do item 2")).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Proprietário"), "org-allowed");
  await user.selectOptions(screen.getByLabelText("Proprietário"), "");
  await user.selectOptions(screen.getByLabelText("Proprietário"), "org-allowed");
  await user.click(screen.getByRole("button", { name: "Criar cobrança" }));

  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    name: "Apartamento 302",
    ownerType: "organization",
    ownerUuid: "org-allowed"
  }));
});

it("renders field and form errors, focuses normalized controls and supports edit copy", async () => {
  const user = userEvent.setup();
  const values: BillingFormValues = {
    ...emptyBillingValues(),
    description: "Inquilino",
    items: [{ amount: "1.000,00", description: "Aluguel", id: "item-a", itemType: "fixed" }],
    name: "Casa",
    pixKey: "chave",
    pixMerchantCity: "SALVADOR",
    pixMerchantName: "MARIA",
    recipients: [{ email: "maria@example.com", id: "recipient-a", name: "Maria" }],
    replyTo: [{ email: "ana@example.com", id: "reply-a", name: "Ana" }]
  };
  const onSubmit = vi.fn();
  const view = renderForm(<BillingForm error="Falha geral." fieldErrors={{ "items.0.amount": "Valor inválido.", name: "Nome inválido." }} mode="edit" onSubmit={onSubmit} organizations={[]} saving values={values} />);

  expect(screen.getByText("Falha geral.")).toHaveAttribute("role", "alert");
  expect(screen.getByText("Nome inválido.")).toBeVisible();
  expect(screen.getByText("Valor inválido.")).toBeVisible();
  expect(screen.getByLabelText("Nome do imóvel")).toHaveFocus();
  expect(screen.queryByLabelText("Proprietário")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Salvando..." })).toBeDisabled();

  view.rerender(<MemoryRouter><BillingForm error="" fieldErrors={{ "items.0.amount": "Valor inválido." }} mode="edit" onSubmit={onSubmit} organizations={[]} saving={false} values={values} /></MemoryRouter>);
  expect(screen.getByLabelText("Valor do item 1 (R$)")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
  expect(onSubmit).toHaveBeenCalled();
});

it("keeps invalid currency visible and prevents removing the final item row", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  renderForm(<BillingForm error="" fieldErrors={{}} mode="create" onSubmit={onSubmit} organizations={[]} saving={false} values={emptyBillingValues()} />);

  await user.type(screen.getByLabelText("Valor do item 1 (R$)"), "abc");
  expect(screen.getByText("R$ 0,00")).toBeVisible();
  expect(screen.getByRole("button", { name: "Remover item 1" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Adicionar item" }));
  expect(screen.getByRole("button", { name: "Remover item 1" })).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Remover item 2" }));
  expect(screen.getByRole("button", { name: "Remover item 1" })).toBeDisabled();
});

it("renders an aggregate items error and focuses the first item description", () => {
  renderForm(<BillingForm error="" fieldErrors={{ items: "Adicione pelo menos um item." }} mode="create" onSubmit={vi.fn()} organizations={[]} saving={false} values={emptyBillingValues()} />);

  expect(screen.getByText("Adicione pelo menos um item.")).toBeVisible();
  expect(screen.getByLabelText("Descrição do item 1")).toHaveFocus();
});

it("focuses the add action for an aggregate items error without rows and describes row errors", () => {
  const valuesWithoutItems = emptyBillingValues();
  valuesWithoutItems.items = [];
  const view = renderForm(<BillingForm error="" fieldErrors={{ items: "Adicione pelo menos um item." }} mode="create" onSubmit={vi.fn()} organizations={[]} saving={false} values={valuesWithoutItems} />);

  expect(screen.getByRole("button", { name: "Adicionar item" })).toHaveFocus();
  view.unmount();

  renderForm(<BillingForm error="" fieldErrors={{ "items.0.description": "Informe a descrição." }} mode="create" onSubmit={vi.fn()} organizations={[]} saving={false} values={emptyBillingValues()} />);
  expect(screen.getByText("Informe a descrição.")).toBeVisible();
  expect(screen.getByLabelText("Descrição do item 1")).toHaveAttribute("aria-describedby", expect.stringContaining("description-error"));
});

it("focuses PIX and contact fields when their server errors change", () => {
  const view = render(<Harness fieldErrors={{ pix_key: "PIX inválido." }} />);
  expect(screen.getByLabelText("Chave PIX")).toHaveFocus();
  view.rerender(<Harness fieldErrors={{ "recipients.0.email": "E-mail inválido." }} />);
  expect(screen.getByText("E-mail inválido.")).toBeVisible();
  view.rerender(<Harness fieldErrors={{ "recipients.0.name": "Nome inválido." }} />);
  expect(screen.getByText("Nome inválido.")).toBeVisible();
  view.rerender(<Harness fieldErrors={{ description: "Descrição inválida." }} />);
  expect(screen.getByText("Descrição inválida.")).toBeVisible();
  view.rerender(<Harness fieldErrors={{ unexpected: "Erro inesperado." }} />);
});

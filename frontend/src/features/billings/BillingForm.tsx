import { QrCode, Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { FieldError } from "../../components/FieldError";
import { formatBrl, parseBrl } from "../../lib/format";
import type { components } from "../../lib/api/schema";
import { RecipientFormset, type ContactValue } from "./RecipientFormset";

type Organization = components["schemas"]["OrganizationResponse"];

export interface BillingItemValue {
  amount: string;
  description: string;
  id: string;
  itemType: "fixed" | "variable";
  uuid?: string;
}

export interface BillingFormValues {
  description: string;
  items: BillingItemValue[];
  name: string;
  ownerType: "user" | "organization";
  ownerUuid: string;
  pixKey: string;
  pixMerchantCity: string;
  pixMerchantName: string;
  recipients: ContactValue[];
  replyTo: ContactValue[];
}

interface BillingFormProps {
  cancelTo?: string;
  error: string;
  fieldErrors: Record<string, string>;
  mode: "create" | "edit";
  lockedContacts?: { recipients: boolean; replyTo: boolean };
  onSubmit: (values: BillingFormValues) => void;
  organizations: Organization[];
  saving: boolean;
  values: BillingFormValues;
}

let itemSequence = 0;

function newItem(description = "", amount = "", itemType: "fixed" | "variable" = "fixed"): BillingItemValue {
  itemSequence += 1;
  return { amount, description, id: `billing-item-${itemSequence}`, itemType };
}

function controlNameFor(field: string): string {
  const itemMatch = /^items\.(\d+)\.(description|item_type|amount|uuid)$/.exec(field);
  if (itemMatch) return itemMatch[2] === "uuid" ? `items-${itemMatch[1]}-description` : `items-${itemMatch[1]}-${itemMatch[2]}`;
  const contactMatch = /^(recipients|reply_to)\.(\d+)\.(name|email)$/.exec(field);
  if (contactMatch) return `${contactMatch[1]}-${contactMatch[2]}-${contactMatch[3]}`;
  const names: Record<string, string> = {
    description: "description",
    name: "name",
    owner: "owner",
    pix_key: "pix_key",
    pix_merchant_city: "pix_merchant_city",
    pix_merchant_name: "pix_merchant_name"
  };
  return names[field] ?? field;
}

export function BillingForm({ cancelTo, error, fieldErrors, lockedContacts, mode, onSubmit, organizations, saving, values }: BillingFormProps) {
  const [form, setForm] = useState(values);
  const allowedOrganizations = organizations.filter((organization) => organization.capabilities.can_create_billing);
  const fixedSubtotal = useMemo(() => form.items.reduce((sum, item) => {
    if (item.itemType === "variable") return sum;
    return sum + (parseBrl(item.amount) ?? 0);
  }, 0), [form.items]);

  useEffect(() => {
    const fields = Object.keys(fieldErrors);
    const firstField = ["name", "description", "owner", "pix_key", "pix_merchant_name", "pix_merchant_city"]
      .find((field) => fields.includes(field)) ?? fields[0];
    if (!firstField) return;
    const control = firstField === "items"
      ? document.querySelector<HTMLElement>('[name="items-0-description"]') ?? document.querySelector<HTMLElement>('[name="items-add"]')
      : document.querySelector<HTMLElement>(`[name="${controlNameFor(firstField)}"]`);
    control?.focus();
  }, [fieldErrors]);

  useEffect(() => {
    if (error) document.querySelector<HTMLElement>('[name="name"]')?.focus();
  }, [error]);

  const setField = <K extends keyof BillingFormValues>(field: K, value: BillingFormValues[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
  };
  const updateItem = (index: number, changes: Partial<BillingItemValue>) => {
    setForm((current) => ({
      ...current,
      items: current.items.map((item, currentIndex) => currentIndex === index ? { ...item, ...changes } : item)
    }));
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(form);
  };

  return (
    <form id="billing-form" onSubmit={submit}>
      {error ? <div className="toast toast--error" role="alert">{error}</div> : null}
      <div className="panel">
        <div className="panel__head"><h3>Detalhes</h3><span className="panel__title-eyebrow">Obrigatório</span></div>
        <div className="panel__body">
          {mode === "create" ? (
            <div className="field field--full">
              <label className="field__label" htmlFor="owner">Proprietário</label>
              <select
                className="select"
                id="owner"
                name="owner"
                onChange={(event) => setForm((current) => ({
                  ...current,
                  ownerType: event.target.value ? "organization" : "user",
                  ownerUuid: event.target.value
                }))}
                value={form.ownerType === "organization" ? form.ownerUuid : ""}
              >
                <option value="">Minha conta</option>
                {allowedOrganizations.map((organization) => <option key={organization.uuid} value={organization.uuid}>{organization.name}</option>)}
              </select>
              <FieldError id="owner-error" message={fieldErrors.owner} />
            </div>
          ) : null}
          <div className="form-grid">
            <div className="field field--full">
              <label className="field__label" htmlFor="name">Nome do imóvel</label>
              <input aria-describedby={fieldErrors.name ? "name-error" : undefined} autoFocus className="input" id="name" name="name" onChange={(event) => setField("name", event.target.value)} placeholder="Ex.: Apartamento 302 — Ed. Aurora" required type="text" value={form.name} />
              <FieldError id="name-error" message={fieldErrors.name} />
            </div>
            <div className="field field--full">
              <label className="field__label" htmlFor="description">Descrição</label>
              <input aria-describedby={fieldErrors.description ? "description-error" : undefined} className="input" id="description" name="description" onChange={(event) => setField("description", event.target.value)} placeholder="Inquilino, endereço ou nota interna" type="text" value={form.description} />
              <FieldError id="description-error" message={fieldErrors.description} />
            </div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel__head">
          <div><h3>Recebimento PIX</h3><p className="panel__desc">Opcional — em branco usa a chave configurada na sua conta ou organização.</p></div>
          <QrCode aria-hidden="true" size={20} />
        </div>
        <div className="panel__body">
          <div className="field">
            <label className="field__label" htmlFor="pix_key">Chave PIX</label>
            <input aria-describedby="pix-key-hint pix-key-error" className="input mono" id="pix_key" name="pix_key" onChange={(event) => setField("pixKey", event.target.value)} placeholder="e-mail, CPF/CNPJ, telefone (+55) ou aleatória" type="text" value={form.pixKey} />
            <span className="field__hint" id="pix-key-hint">Para celular inclua +55, caso contrário 11 dígitos são tratados como CPF.</span>
            <FieldError id="pix-key-error" message={fieldErrors.pix_key} />
          </div>
          <div className="form-grid">
            <div className="field">
              <label className="field__label" htmlFor="pix_merchant_name">Nome do recebedor</label>
              <input className="input" id="pix_merchant_name" maxLength={25} name="pix_merchant_name" onChange={(event) => setField("pixMerchantName", event.target.value)} placeholder="Até 25 caracteres" type="text" value={form.pixMerchantName} />
              <span className="field__hint">Até 25 caracteres.</span>
              <FieldError id="pix-name-error" message={fieldErrors.pix_merchant_name} />
            </div>
            <div className="field">
              <label className="field__label" htmlFor="pix_merchant_city">Cidade do recebedor</label>
              <input className="input mono" id="pix_merchant_city" maxLength={15} name="pix_merchant_city" onChange={(event) => setField("pixMerchantCity", event.target.value)} placeholder="SEM ACENTOS" type="text" value={form.pixMerchantCity} />
              <span className="field__hint">Até 15 caracteres, sem acentos.</span>
              <FieldError id="pix-city-error" message={fieldErrors.pix_merchant_city} />
            </div>
          </div>
        </div>
      </div>

      <RecipientFormset fieldErrors={fieldErrors} kind="recipients" locked={lockedContacts?.recipients} onChange={(contacts) => setField("recipients", contacts)} values={form.recipients} />
      <RecipientFormset fieldErrors={fieldErrors} kind="reply_to" locked={lockedContacts?.replyTo} onChange={(contacts) => setField("replyTo", contacts)} values={form.replyTo} />

      <div className="panel">
        <div className="panel__head">
          <div><h3>Itens da cobrança</h3><p className="panel__desc">Fixos têm valor definido. Variáveis (água, luz) você preenche a cada fatura.</p></div>
          <button aria-label="Adicionar item" className="btn btn--sm btn--primary" name="items-add" onClick={() => setField("items", [...form.items, newItem()])} type="button">+ Adicionar <span className="sr-only">item</span></button>
        </div>
        <div className="panel__body">
          <FieldError id="items-error" message={fieldErrors.items} />
          <input id="id_items-TOTAL_FORMS" name="items-TOTAL_FORMS" type="hidden" value={form.items.length} />
          <div id="items-container">
            {form.items.map((item, index) => {
              const descriptionError = fieldErrors[`items.${index}.description`];
              const uuidError = fieldErrors[`items.${index}.uuid`];
              const typeError = fieldErrors[`items.${index}.item_type`];
              const amountError = fieldErrors[`items.${index}.amount`];
              return (
                <div className="formset-row" id={`items-row-${index}`} key={item.id}>
                  <div className="item-grid">
                    <div className="field mb-0">
                      <label className="field__label" htmlFor={`${item.id}-description`}>Descrição</label>
                      <input aria-describedby={[descriptionError ? `${item.id}-description-error` : "", uuidError ? `${item.id}-uuid-error` : "", index === 0 && fieldErrors.items ? "items-error" : ""].filter(Boolean).join(" ") || undefined} aria-label={`Descrição do item ${index + 1}`} className="input" id={`${item.id}-description`} name={`items-${index}-description`} onChange={(event) => updateItem(index, { description: event.target.value })} placeholder={index === 0 ? "Ex.: Aluguel" : "Ex.: Condomínio"} required type="text" value={item.description} />
                      <FieldError id={`${item.id}-description-error`} message={descriptionError} />
                      <FieldError id={`${item.id}-uuid-error`} message={uuidError} />
                    </div>
                    <div className="field mb-0">
                      <label className="field__label" htmlFor={`${item.id}-type`}>Tipo</label>
                      <select aria-label={`Tipo do item ${index + 1}`} className="select" id={`${item.id}-type`} name={`items-${index}-item_type`} onChange={(event) => updateItem(index, { amount: event.target.value === "variable" ? "" : item.amount, itemType: event.target.value as BillingItemValue["itemType"] })} value={item.itemType}>
                        <option value="fixed">Fixo</option><option value="variable">Variável</option>
                      </select>
                      <FieldError id={`${item.id}-type-error`} message={typeError} />
                    </div>
                    <div className="field mb-0">
                      <label className="field__label" htmlFor={`${item.id}-amount`}>Valor (R$)</label>
                      <input aria-label={`Valor do item ${index + 1} (R$)`} className={`input mono${item.itemType === "variable" ? " input--disabled" : ""}`} disabled={item.itemType === "variable"} id={`${item.id}-amount`} inputMode="decimal" name={`items-${index}-amount`} onChange={(event) => updateItem(index, { amount: event.target.value })} placeholder="0,00" type="text" value={item.amount} />
                      <FieldError id={`${item.id}-amount-error`} message={amountError} />
                    </div>
                    <div className="field mb-0">
                      <span className="field__label sr-only">Remover</span>
                      <button aria-label={`Remover item ${index + 1}`} className="icon-btn" disabled={form.items.length === 1} onClick={() => setField("items", form.items.filter((_, current) => current !== index))} title={form.items.length === 1 ? "A cobrança precisa de pelo menos um item" : "Remover item"} type="button"><Trash2 aria-hidden="true" size={16} /></button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="actionbar">
        <div className="actionbar__total"><span className="lbl">Subtotal fixo / mês</span><span className="val mono" id="fixed-subtotal">{formatBrl(fixedSubtotal)}</span></div>
        <div className="btn-row">
          <Link className="btn btn--ghost" to={cancelTo ?? (mode === "create" ? "/billings/" : ".")}>Cancelar</Link>
          <button className="btn btn--primary" disabled={saving} type="submit">{saving ? "Salvando..." : mode === "create" ? "Criar cobrança" : "Salvar alterações"}</button>
        </div>
      </div>
    </form>
  );
}

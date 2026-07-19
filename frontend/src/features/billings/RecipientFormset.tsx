import { Trash2 } from "lucide-react";

import { FieldError } from "../../components/FieldError";

export interface ContactValue {
  email: string;
  id: string;
  name: string;
}

interface RecipientFormsetProps {
  fieldErrors?: Record<string, string>;
  kind: "recipients" | "reply_to";
  locked?: boolean;
  onChange: (values: ContactValue[]) => void;
  values: ContactValue[];
}

let contactSequence = 0;

function newContact(): ContactValue {
  contactSequence += 1;
  return { email: "", id: `contact-${contactSequence}`, name: "" };
}

export function RecipientFormset({ fieldErrors = {}, kind, locked = false, onChange, values }: RecipientFormsetProps) {
  const isRecipient = kind === "recipients";
  const heading = isRecipient ? "Destinatários" : "Responder para (Reply-To)";
  const description = isRecipient
    ? "Opcional — contatos do inquilino que recebem as comunicações. Cada um recebe um e-mail separado."
    : "Opcional — endereços que recebem as respostas dos inquilinos a estas comunicações.";
  const singular = isRecipient ? "destinatário" : "Reply-To";
  const lockedMessage = isRecipient
    ? "Alguns destinatários estão ocultos. Esta lista não pode ser alterada com segurança."
    : "Alguns endereços Reply-To estão ocultos. Esta lista não pode ser alterada com segurança.";

  const update = (index: number, field: "name" | "email", value: string) => {
    onChange(values.map((contact, current) => current === index ? { ...contact, [field]: value } : contact));
  };

  return (
    <div className="panel">
      <div className="panel__head">
        <div>
          <h3>{heading}</h3>
          <p className="panel__desc">{description}</p>
        </div>
        {!locked ? <button aria-label={`Adicionar ${singular}`} className="btn btn--sm btn--primary" onClick={() => onChange([...values, newContact()])} type="button">
          + Adicionar <span className="sr-only">{singular}</span>
        </button> : null}
      </div>
      <div className="panel__body">
        {locked ? <div className="toast toast--warning" role="status">{lockedMessage}</div> : null}
        <input id={`id_${kind}-TOTAL_FORMS`} name={`${kind}-TOTAL_FORMS`} type="hidden" value={values.length} />
        <div id={`${kind}-container`}>
          {values.map((contact, index) => {
            const nameError = fieldErrors[`${kind}.${index}.name`];
            const emailError = fieldErrors[`${kind}.${index}.email`];
            const rowLabel = isRecipient ? `destinatário ${index + 1}` : `Reply-To ${index + 1}`;
            return (
              <div className="formset-row" id={`${kind}-row-${index}`} key={contact.id}>
                <div className="item-grid">
                  <div className="field mb-0">
                    <label className="field__label" htmlFor={`${kind}-${contact.id}-name`}>Nome</label>
                    <input
                      aria-describedby={nameError ? `${kind}-${contact.id}-name-error` : undefined}
                      aria-label={`Nome do ${rowLabel}`}
                      className="input"
                      disabled={locked}
                      id={`${kind}-${contact.id}-name`}
                      name={`${kind}-${index}-name`}
                      onChange={(event) => update(index, "name", event.target.value)}
                      placeholder={isRecipient ? "Ex.: João" : "Ex.: Ana"}
                      type="text"
                      value={contact.name}
                    />
                    <FieldError id={`${kind}-${contact.id}-name-error`} message={nameError} />
                  </div>
                  <div className="field mb-0">
                    <label className="field__label" htmlFor={`${kind}-${contact.id}-email`}>E-mail</label>
                    <input
                      aria-describedby={emailError ? `${kind}-${contact.id}-email-error` : undefined}
                      aria-label={`E-mail do ${rowLabel}`}
                      className="input"
                      disabled={locked}
                      id={`${kind}-${contact.id}-email`}
                      name={`${kind}-${index}-email`}
                      onChange={(event) => update(index, "email", event.target.value)}
                      placeholder={isRecipient ? "joao@email.com" : "ana@email.com"}
                      type="email"
                      value={contact.email}
                    />
                    <FieldError id={`${kind}-${contact.id}-email-error`} message={emailError} />
                  </div>
                  <div className="field mb-0">
                    <span className="field__label sr-only">Remover</span>
                    {!locked ? <button
                      aria-label={`Remover ${rowLabel}`}
                      className="icon-btn"
                      onClick={() => onChange(values.filter((_, current) => current !== index))}
                      title={`Remover ${singular}`}
                      type="button"
                    >
                      <Trash2 aria-hidden="true" size={16} />
                    </button> : null}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

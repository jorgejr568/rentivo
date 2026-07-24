import { Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { FieldError } from "../../components/FieldError";
import { EmptyState, LoadError, LoadingState } from "../../components/PageState";
import { apiClient, apiRequest } from "../../lib/api/client";
import type { paths } from "../../lib/api/schema";
import { formatBrl, formatBrlInput, parseBrl } from "../../lib/format";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import type { Billing } from "./billSupport";
import {
  errorMessage, firstFieldError, multipartBodySerializer, normalizedFieldErrors,
  parseDateInput, useDocumentTitle
} from "./billSupport";

interface ExtraRow {
  amount: string;
  description: string;
  key: number;
}

interface BillCreatePayload {
  due_date: string | null;
  extras: Array<{ amount: number; description: string }>;
  notes: string;
  reference_month: string;
  variable_amounts: Record<string, number>;
}

type GenerateBilling = Omit<Billing, "capabilities"> & {
  capabilities: Billing["capabilities"] & { can_upload_bill_receipts: boolean };
};

export function BillGeneratePage() {
  const { billingUuid = "" } = useParams<{ billingUuid: string }>();
  const navigate = useNavigate();
  const [billing, setBilling] = useState<GenerateBilling | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [referenceMonth, setReferenceMonth] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [variableAmounts, setVariableAmounts] = useState<Record<string, string>>({});
  const [extras, setExtras] = useState<ExtraRow[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const nextExtraKey = useRef(0);
  const referenceRef = useRef<HTMLInputElement>(null);
  const variableRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const extraRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const loadController = useRef<AbortController | null>(null);
  const mutationController = useRef<AbortController | null>(null);

  useDocumentTitle(billing ? `Gerar Fatura - ${billing.name} - Rentivo` : "Gerar Fatura - Rentivo");

  const load = useCallback(async () => {
    loadController.current?.abort();
    mutationController.current?.abort();
    const controller = new AbortController();
    loadController.current = controller;
    setLoading(true);
    setLoadError("");
    setBilling(null);
    setActionError("");
    setFieldErrors({});
    setSubmitting(false);
    setReferenceMonth("");
    setDueDate("");
    setNotes("");
    setVariableAmounts({});
    setExtras([]);
    setFiles([]);
    nextExtraKey.current = 0;
    variableRefs.current = {};
    extraRefs.current = {};
    try {
      const { data } = await apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}", {
        params: { path: { billing_uuid: billingUuid } }, signal: controller.signal
      }));
      /* v8 ignore next -- an aborted request is intentionally discarded */
      if (controller.signal.aborted) return;
      setBilling(data as GenerateBilling);
      setVariableAmounts(Object.fromEntries(
        data.items.filter((item) => item.item_type === "variable").map((item) => [item.uuid, ""])
      ));
      setLoading(false);
      requestAnimationFrame(() => referenceRef.current?.focus());
    } catch (caught) {
      /* v8 ignore next -- an aborted request is intentionally discarded */
      if (controller.signal.aborted) return;
      setLoadError(errorMessage(caught, "Não foi possível carregar a cobrança."));
      setLoading(false);
    }
  }, [billingUuid]);

  useEffect(() => {
    void load();
    return () => {
      loadController.current?.abort();
      mutationController.current?.abort();
    };
  }, [load]);

  const focusError = (key: string | undefined) => {
    /* v8 ignore next -- callers only invoke focus after resolving a field key */
    if (!key) return;
    if (key === "reference_month") referenceRef.current?.focus();
    else if (key.startsWith("variable_amounts.")) {
      const input = variableRefs.current[key.slice("variable_amounts.".length)];
      if (input) input.focus();
    }
    else extraRefs.current[key]?.focus();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    /* v8 ignore next -- the form is only rendered after billing loading */
    if (!billing) return;
    setActionError("");
    setFieldErrors({});

    const parsedDate = parseDateInput(dueDate);
    if (parsedDate === undefined) {
      setFieldErrors({ due_date: "Informe uma data válida." });
      document.getElementById("due_date")?.focus();
      return;
    }
    const parsedExtras = extras.map((extra) => ({
      amount: parseBrl(extra.amount), description: extra.description.trim(), key: extra.key
    }));
    const localErrors: Record<string, string> = {};
    parsedExtras.forEach((extra, index) => {
      if (!extra.description) localErrors[`extras.${index}.description`] = "Informe a descrição.";
      if (extra.amount === null || extra.amount <= 0) localErrors[`extras.${index}.amount`] = "Informe um valor maior que zero.";
    });
    if (Object.keys(localErrors).length > 0) {
      setFieldErrors(localErrors);
      focusError(Object.keys(localErrors)[0]);
      return;
    }

    const variableValues: Record<string, number> = {};
    billing.items.forEach((item) => {
      if (item.item_type !== "variable") return;
      const parsed = parseBrl(variableAmounts[item.uuid]);
      if (parsed === null) localErrors[`variable_amounts.${item.uuid}`] = "Informe um valor válido.";
      else variableValues[item.uuid] = parsed;
    });
    if (Object.keys(localErrors).length > 0) {
      setFieldErrors(localErrors);
      focusError(Object.keys(localErrors)[0]);
      return;
    }
    const payload: BillCreatePayload = {
      due_date: parsedDate,
      extras: parsedExtras.map(({ amount, description }) => ({ amount: amount!, description })),
      notes,
      reference_month: referenceMonth,
      variable_amounts: variableValues
    };
    type CreateBody =
      paths["/api/v1/billings/{billing_uuid}/bills"]["post"]["requestBody"]["content"]["multipart/form-data"];
    // The multipart `payload` field is sent as a JSON string on the wire; the generated
    // client models it as the pre-serialized BillCreateRequest object, so bridge via `unknown`.
    const requestBody = {
      payload: JSON.stringify(payload),
      ...(billing.capabilities.can_upload_bill_receipts ? { receipt_files: files } : {})
    } as unknown as CreateBody;
    mutationController.current?.abort();
    const controller = new AbortController();
    mutationController.current = controller;
    setSubmitting(true);
    try {
      const { data, response } = await apiRequest(apiClient.POST(
        "/api/v1/billings/{billing_uuid}/bills",
        {
          body: requestBody, bodySerializer: multipartBodySerializer,
          params: { path: { billing_uuid: billingUuid } }, signal: controller.signal
        }
      ));
      if (controller.signal.aborted) return;
      pushAnalyticsFromResponse(response);
      navigate(`/billings/${billingUuid}/bills/${data.uuid}`);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const errors = normalizedFieldErrors(caught);
      setFieldErrors(errors);
      setActionError(errorMessage(caught, "Não foi possível gerar a fatura."));
      requestAnimationFrame(() => focusError(firstFieldError(errors, ["reference_month", "due_date"])));
    } finally {
      if (!controller.signal.aborted) setSubmitting(false);
    }
  };

  if (loading) return <LoadingState label="Carregando cobrança..." />;
  if (loadError) return <LoadError message={loadError} onRetry={() => void load()} />;
  /* v8 ignore next -- successful loading always sets the billing resource */
  if (!billing) return null;
  if (!billing.capabilities.can_manage_bills) {
    return <EmptyState body="Você não possui permissão para gerar faturas nesta cobrança." title="Geração indisponível" />;
  }

  return (
    <>
      <h2 className="mb-1">Gerar Fatura</h2>
      <p className="text-muted">Cobrança: <strong>{billing.name}</strong></p>
      {billing.items.length === 0 && (
        <EmptyState
          action={<Link className="btn btn--primary" to={`/billings/${billingUuid}/edit`}>Cadastrar itens</Link>}
          body="Cadastre ao menos um item antes de gerar a primeira fatura."
          title="Nenhum item cadastrado"
        />
      )}
      {billing.items.length > 0 && (
        <form encType="multipart/form-data" onSubmit={(event) => void submit(event)}>
          <div className="panel"><div className="panel-body panel__body">
            <div className="dates-grid">
              <div className="field">
                <label className="field-label field__label" htmlFor="reference_month">Mês de Referência</label>
                <input aria-describedby={fieldErrors.reference_month ? "reference_month-error" : undefined} className="field-input input" id="reference_month" onChange={(event) => setReferenceMonth(event.target.value)} ref={referenceRef} required type="month" value={referenceMonth} />
                <FieldError id="reference_month-error" message={fieldErrors.reference_month} />
              </div>
              <div className="field">
                <label className="field-label field__label" htmlFor="due_date">Vencimento</label>
                <input aria-describedby={fieldErrors.due_date ? "due_date-error" : undefined} className="field-input input" id="due_date" onChange={(event) => setDueDate(event.target.value)} placeholder="10/03/2025" type="text" value={dueDate} />
                <FieldError id="due_date-error" message={fieldErrors.due_date} />
              </div>
            </div>
          </div></div>

          <div className="panel">
            <div className="panel-head panel__head"><h5>Itens</h5></div>
            <div className="panel-body panel__body">
              {billing.items.map((item) => {
                const key = `variable_amounts.${item.uuid}`;
                return (
                  <div className="formset-row" key={item.uuid}>
                    <div className="generate-item-grid">
                      <div><strong>{item.description}</strong> <span className={`tag tag--${item.item_type}`}>{item.item_type === "fixed" ? "Fixo" : "Variável"}</span></div>
                      <div>{item.item_type === "fixed"
                        ? <input aria-label={`${item.description} (fixo)`} className="field-input" disabled value={formatBrlInput(item.amount)} />
                        : <><input aria-describedby={fieldErrors[key] ? `${key}-error` : undefined} aria-label={item.description} className="field-input" inputMode="decimal" onChange={(event) => setVariableAmounts((values) => ({ ...values, [item.uuid]: event.target.value }))} placeholder="0,00" ref={(node) => { variableRefs.current[item.uuid] = node; }} required value={variableAmounts[item.uuid]} /><FieldError id={`${key}-error`} message={fieldErrors[key]} /></>}
                      </div>
                      <div className="text-muted text-mono">{item.item_type === "fixed" ? formatBrl(item.amount) : ""}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head panel__head"><h5>Despesas Extras</h5><button aria-label="Adicionar despesa extra" className="btn btn--sm btn--primary" onClick={() => setExtras((rows) => [...rows, { amount: "", description: "", key: nextExtraKey.current++ }])} type="button"><Plus aria-hidden="true" size={14} /> Adicionar</button></div>
            <div className="panel-body panel__body">
              {extras.length === 0 && <p className="text-muted">Nenhuma despesa extra.</p>}
              {extras.map((extra, index) => (
                <div className="extras-grid" key={extra.key}>
                  <div className="field mb-0"><input aria-label={`Descrição da despesa extra ${index + 1}`} className="field-input" onChange={(event) => setExtras((rows) => rows.map((row) => row.key === extra.key ? { ...row, description: event.target.value } : row))} placeholder="Descrição" ref={(node) => { extraRefs.current[`extras.${index}.description`] = node; }} value={extra.description} /><FieldError id={`extras.${index}.description-error`} message={fieldErrors[`extras.${index}.description`]} /></div>
                  <div className="field mb-0"><input aria-label={`Valor da despesa extra ${index + 1}`} className="field-input" inputMode="decimal" onChange={(event) => setExtras((rows) => rows.map((row) => row.key === extra.key ? { ...row, amount: event.target.value } : row))} placeholder="0,00" ref={(node) => { extraRefs.current[`extras.${index}.amount`] = node; }} value={extra.amount} /><FieldError id={`extras.${index}.amount-error`} message={fieldErrors[`extras.${index}.amount`]} /></div>
                  <div><button aria-label={`Remover despesa extra ${index + 1}`} className="btn btn--sm btn--danger" onClick={() => setExtras((rows) => rows.filter((row) => row.key !== extra.key))} type="button"><Trash2 aria-hidden="true" size={14} /> Remover</button></div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel"><div className="panel-body panel__body"><div className="field mb-0"><label className="field-label field__label" htmlFor="notes">Observações</label><textarea className="field-textarea input" id="notes" onChange={(event) => setNotes(event.target.value)} rows={3} value={notes} /><FieldError id="notes-error" message={fieldErrors.notes} /></div></div></div>
          {billing.capabilities.can_upload_bill_receipts ? <div className="panel"><div className="panel-head panel__head"><h5>Comprovantes</h5></div><div className="panel-body panel__body"><div className="field"><label className="field-label field__label" htmlFor="generate_receipt_files">Anexar comprovantes</label><input accept=".pdf,.jpg,.jpeg,.png" className="field-input input" id="generate_receipt_files" multiple onChange={(event) => setFiles(Array.from(event.currentTarget.files!))} type="file" /><small className="text-muted">PDF, JPG ou PNG. Maximo 10 MB cada. Voce pode selecionar varios arquivos.</small></div></div></div> : null}
          {actionError && <div className="toast toast--danger" role="alert">{actionError}</div>}
          <div className="btn-group"><button className="btn btn--primary" disabled={submitting} type="submit">{submitting ? "Gerando..." : "Gerar Fatura"}</button><Link className="btn btn--ghost" to={`/billings/${billingUuid}`}>Cancelar</Link></div>
        </form>
      )}
    </>
  );
}

import { Plus, RefreshCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { FieldError } from "../../components/FieldError";
import { LoadError, LoadingState } from "../../components/PageState";
import { apiClient, apiRequest } from "../../lib/api/client";
import { formatBrlInput, formatIsoDate, formatMonth, parseBrl } from "../../lib/format";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import { ReceiptManager } from "./ReceiptManager";
import type { Bill, BillLineItemRequest, Billing } from "./billSupport";
import {
  errorMessage, firstFieldError, normalizedFieldErrors, parseDateInput, useDocumentTitle
} from "./billSupport";

interface EditableLine {
  amount: string;
  description: string;
  itemType: BillLineItemRequest["item_type"];
  key: string;
}

export function BillEditPage() {
  const { billingUuid = "", billUuid = "" } = useParams<{ billingUuid: string; billUuid: string }>();
  const navigate = useNavigate();
  const [billing, setBilling] = useState<Billing | null>(null);
  const [bill, setBill] = useState<Bill | null>(null);
  const [lines, setLines] = useState<EditableLine[]>([]);
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const nextKey = useRef(0);
  const fieldRefs = useRef<Record<string, HTMLInputElement | HTMLTextAreaElement | null>>({});
  const controllerRef = useRef<AbortController | null>(null);
  const mutationControllers = useRef(new Set<AbortController>());
  const routeGeneration = useRef(0);

  useDocumentTitle("Editar Fatura - Rentivo");

  useEffect(() => {
    const controllers = mutationControllers.current;
    const generation = ++routeGeneration.current;
    setActionError("");
    setFieldErrors({});
    setSuccess("");
    setSaving(false);
    setRegenerating(false);
    setDeleting(false);
    setDeleteOpen(false);
    return () => {
      if (routeGeneration.current === generation) routeGeneration.current += 1;
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };
  }, [billingUuid, billUuid]);

  const beginMutation = () => {
    const controller = new AbortController();
    mutationControllers.current.add(controller);
    return { controller, generation: routeGeneration.current };
  };

  const mutationIsCurrent = (controller: AbortController, generation: number) => (
    !controller.signal.aborted && generation === routeGeneration.current
  );

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setLoadError("");
    try {
      const [billingResult, billResult] = await Promise.all([
        apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}", { params: { path: { billing_uuid: billingUuid } }, signal: controller.signal })),
        apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}/bills/{bill_uuid}", { params: { path: { billing_uuid: billingUuid, bill_uuid: billUuid } }, signal: controller.signal }))
      ]);
      /* v8 ignore next -- an aborted request is intentionally discarded */
      if (controller.signal.aborted) return;
      setBilling(billingResult.data);
      setBill(billResult.data);
      setLines(billResult.data.line_items.map((item, index) => ({ amount: formatBrlInput(item.amount), description: item.description, itemType: item.item_type, key: `saved-${item.sort_order}-${index}` })));
      setDueDate(billResult.data.due_date ? formatIsoDate(billResult.data.due_date) : "");
      setNotes(billResult.data.notes);
      setLoading(false);
    } catch (caught) {
      /* v8 ignore next -- an aborted request is intentionally discarded */
      if (controller.signal.aborted) return;
      setLoadError(errorMessage(caught, "Não foi possível carregar a fatura."));
      setLoading(false);
    }
  }, [billUuid, billingUuid]);

  useEffect(() => {
    void load();
    return () => controllerRef.current?.abort();
  }, [load]);

  const focusField = (key: string | undefined) => {
    if (!key) return;
    fieldRefs.current[key]?.focus();
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    /* v8 ignore next -- the form is only rendered after bill loading */
    if (!bill) return;
    setActionError(""); setFieldErrors({}); setSuccess("");
    const parsedDate = parseDateInput(dueDate);
    const errors: Record<string, string> = {};
    if (parsedDate === undefined) errors.due_date = "Informe uma data válida.";
    const lineItems = lines.map((line, index) => {
      const amount = parseBrl(line.amount);
      if (!line.description.trim()) errors[`line_items.${index}.description`] = "Informe a descrição.";
      if (amount === null) errors[`line_items.${index}.amount`] = "Informe um valor válido.";
      return { amount: amount ?? 0, description: line.description.trim(), item_type: line.itemType };
    });
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      focusField(Object.keys(errors)[0]);
      return;
    }
    const { controller, generation } = beginMutation();
    setSaving(true);
    try {
      const { data, response } = await apiRequest(apiClient.PATCH(
        "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}",
        { body: { due_date: parsedDate, line_items: lineItems, notes }, params: { path: { billing_uuid: billingUuid, bill_uuid: bill.uuid } }, signal: controller.signal }
      ));
      if (!mutationIsCurrent(controller, generation)) return;
      pushAnalyticsFromResponse(response);
      setBill(data);
      setSuccess("Fatura atualizada com sucesso.");
    } catch (caught) {
      if (!mutationIsCurrent(controller, generation)) return;
      const apiErrors = normalizedFieldErrors(caught);
      setFieldErrors(apiErrors);
      setActionError(errorMessage(caught, "Não foi possível atualizar a fatura."));
      requestAnimationFrame(() => focusField(firstFieldError(apiErrors, ["line_items.0.description", "due_date", "notes"])));
    } finally {
      mutationControllers.current.delete(controller);
      if (mutationIsCurrent(controller, generation)) setSaving(false);
    }
  };

  const regenerate = async () => {
    /* v8 ignore next -- the action is only rendered after bill loading */
    if (!bill) return;
    const { controller, generation } = beginMutation();
    setRegenerating(true); setActionError("");
    try {
      const { data, response } = await apiRequest(apiClient.POST("/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/regenerate", { params: { path: { billing_uuid: billingUuid, bill_uuid: bill.uuid } }, signal: controller.signal }));
      if (!mutationIsCurrent(controller, generation)) return;
      pushAnalyticsFromResponse(response);
      setBill((current) => ({ ...current!, ...data }));
      setSuccess("O PDF será regenerado em segundo plano.");
    } catch (caught) {
      if (!mutationIsCurrent(controller, generation)) return;
      setActionError(errorMessage(caught, "Não foi possível regenerar o PDF."));
    } finally {
      mutationControllers.current.delete(controller);
      if (mutationIsCurrent(controller, generation)) setRegenerating(false);
    }
  };

  const removeBill = async () => {
    /* v8 ignore next -- the action is only rendered after bill loading */
    if (!bill) return;
    const { controller, generation } = beginMutation();
    setDeleting(true); setActionError("");
    try {
      const { response } = await apiRequest(apiClient.DELETE("/api/v1/billings/{billing_uuid}/bills/{bill_uuid}", { params: { path: { billing_uuid: billingUuid, bill_uuid: bill.uuid } }, signal: controller.signal }));
      if (!mutationIsCurrent(controller, generation)) return;
      pushAnalyticsFromResponse(response);
      navigate(`/billings/${billingUuid}`);
    } catch (caught) {
      if (!mutationIsCurrent(controller, generation)) return;
      setActionError(errorMessage(caught, "Não foi possível excluir a fatura."));
    } finally {
      mutationControllers.current.delete(controller);
      if (mutationIsCurrent(controller, generation)) setDeleting(false);
    }
  };

  if (loading) return <LoadingState label="Carregando fatura..." />;
  if (loadError) return <LoadError message={loadError} onRetry={() => void load()} />;
  /* v8 ignore next -- successful paired loading always sets both resources */
  if (!bill || !billing) return null;

  return (
    <>
      <h2 className="mb-1">Editar Fatura</h2>
      <p className="text-muted">Cobranca: <strong>{billing.name}</strong> · Referencia: <strong>{formatMonth(bill.reference_month)}</strong></p>
      {bill.pdf_render_status === "pending" && <p className="text-muted">O PDF desta fatura está sendo regenerado em segundo plano.</p>}
      {bill.pdf_render_status === "failed" && <p className="text-muted"><strong>Atenção:</strong> a última tentativa de gerar o PDF falhou. Use "Regenerar PDF" para tentar novamente.</p>}

      {bill.capabilities.can_edit ? <form onSubmit={(event) => void save(event)}>
        <div className="panel"><div className="panel-head panel__head"><h5>Itens</h5></div><div className="panel-body panel__body"><div id="items-container">{lines.map((line, index) => <div className="formset-row" key={line.key}><div className="item-grid">
          <div className="field mb-0"><label className="field-label" htmlFor={`line-description-${line.key}`}>Descrição</label><input aria-describedby={fieldErrors[`line_items.${index}.description`] ? `line_items.${index}.description-error` : undefined} className="field-input" id={`line-description-${line.key}`} onChange={(event) => setLines((items) => items.map((item) => item.key === line.key ? { ...item, description: event.target.value } : item))} ref={(node) => { fieldRefs.current[`line_items.${index}.description`] = node; }} value={line.description} /><FieldError id={`line_items.${index}.description-error`} message={fieldErrors[`line_items.${index}.description`]} /></div>
          <div className="field mb-0"><label className="field-label" htmlFor={`line-type-${line.key}`}>Tipo</label><select className="field-select" disabled id={`line-type-${line.key}`} value={line.itemType}><option value="fixed">Fixo</option><option value="variable">Variavel</option><option value="extra">Extra</option></select></div>
          <div className="field mb-0"><label className="field-label" htmlFor={`line-amount-${line.key}`}>Valor (R$)</label><input aria-describedby={fieldErrors[`line_items.${index}.amount`] ? `line_items.${index}.amount-error` : undefined} className="field-input" id={`line-amount-${line.key}`} inputMode="decimal" onChange={(event) => setLines((items) => items.map((item) => item.key === line.key ? { ...item, amount: event.target.value } : item))} ref={(node) => { fieldRefs.current[`line_items.${index}.amount`] = node; }} value={line.amount} /><FieldError id={`line_items.${index}.amount-error`} message={fieldErrors[`line_items.${index}.amount`]} /></div>
          <div>{line.itemType === "extra" && <button aria-label={`Remover ${line.description}`} className="btn btn--sm btn--danger" onClick={() => setLines((items) => items.filter((item) => item.key !== line.key))} type="button"><X aria-hidden="true" size={14} /></button>}</div>
        </div></div>)}</div></div></div>

        <div className="panel"><div className="panel-head panel__head"><h5>Despesas Extras</h5><button aria-label="Adicionar despesa extra" className="btn btn--sm btn--primary" onClick={() => setLines((items) => [...items, { amount: "", description: "", itemType: "extra", key: `new-${nextKey.current++}` }])} type="button"><Plus aria-hidden="true" size={14} /> Adicionar</button></div><div className="panel-body panel__body"><p className="text-muted">Adicione despesas pontuais aos itens da fatura.</p></div></div>
        <div className="panel"><div className="panel-body panel__body"><div className="dates-grid"><div className="field"><label className="field-label" htmlFor="due_date">Vencimento</label><input className="field-input" id="due_date" onChange={(event) => setDueDate(event.target.value)} placeholder="10/03/2025" ref={(node) => { fieldRefs.current.due_date = node; }} value={dueDate} /><FieldError id="due_date-error" message={fieldErrors.due_date} /></div></div><div className="field mb-0"><label className="field-label" htmlFor="notes">Observações</label><textarea className="field-textarea" id="notes" onChange={(event) => setNotes(event.target.value)} ref={(node) => { fieldRefs.current.notes = node; }} rows={3} value={notes} /><FieldError id="notes-error" message={fieldErrors.notes} /></div></div></div>
        {actionError && <div className="toast toast--danger" role="alert">{actionError}</div>}{success && <div className="toast toast--success" role="status">{success}</div>}
        <div className="btn-group"><button className="btn btn--primary" disabled={saving} type="submit">{saving ? "Salvando..." : "Salvar"}</button><Link className="btn btn--ghost" to={`/billings/${billingUuid}/bills/${bill.uuid}`}>Cancelar</Link></div>
      </form> : <p className="text-muted">Você não possui permissão para editar esta fatura.</p>}

      <div className="panel" style={{ marginTop: "1.5rem" }}><div className="panel-head panel__head"><h5>Comprovantes</h5></div><div className="panel-body panel__body"><ReceiptManager billingUuid={billingUuid} billUuid={bill.uuid} capabilities={bill.capabilities} onChange={(receipts) => setBill((current) => ({ ...current!, receipts }))} receipts={bill.receipts} /></div></div>
      <div className="btn-row">{bill.capabilities.can_regenerate && <button className="btn" disabled={regenerating} onClick={() => void regenerate()} type="button"><RefreshCw aria-hidden="true" size={16} /> {regenerating ? "Regenerando..." : "Regenerar PDF"}</button>}{bill.capabilities.can_delete && <button className="btn btn--danger" disabled={deleting} onClick={() => setDeleteOpen(true)} type="button"><Trash2 aria-hidden="true" size={16} /> Excluir fatura</button>}</div>
      <ConfirmDialog acceptLabel="Excluir fatura" body="A fatura e seus arquivos serão removidos. Esta ação não pode ser desfeita." onClose={() => setDeleteOpen(false)} onConfirm={() => void removeBill()} open={deleteOpen} title="Tem certeza que deseja excluir esta fatura?" />
    </>
  );
}

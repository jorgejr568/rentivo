import { ArrowLeft, Eye, Send } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { FieldError } from "../../components/FieldError";
import { LoadError, LoadingState } from "../../components/PageState";
import { apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { formatMonth } from "../../lib/format";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import type { Bill, Billing } from "./billSupport";
import { errorMessage, firstFieldError, normalizedFieldErrors, useDocumentTitle } from "./billSupport";

type CommType = components["schemas"]["CommunicationSendRequest"]["comm_type"];
type Preview = components["schemas"]["CommunicationPreviewResponse"];

function isFullContact(contact: Billing["recipients"][number]): contact is Extract<Billing["recipients"][number], { email: string }> {
  return "email" in contact;
}

export function CommunicationComposePage() {
  const { billingUuid = "", billUuid = "" } = useParams<{ billingUuid: string; billUuid: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const requestedType = searchParams.get("type");
  const commType: CommType | null = requestedType === "bill_ready" || requestedType === "payment_receipt"
    ? requestedType
    : null;
  const isRecibo = commType === "payment_receipt";
  const commLabel = commType ? (isRecibo ? "recibo de pagamento" : "fatura") : "comunicação";
  const [billing, setBilling] = useState<Billing | null>(null);
  const [bill, setBill] = useState<Bill | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [selectedRecipients, setSelectedRecipients] = useState<string[]>([]);
  const [saveScope, setSaveScope] = useState<"" | "billing" | "owner">("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [loading, setLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const loadController = useRef<AbortController | null>(null);
  const previewController = useRef<AbortController | null>(null);
  const sendController = useRef<AbortController | null>(null);
  const previewRequest = useRef(0);
  const recipientRef = useRef<HTMLInputElement>(null);
  const subjectRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const acknowledgementRef = useRef<HTMLInputElement>(null);
  const saveScopeRef = useRef<HTMLSelectElement>(null);

  useDocumentTitle(`Enviar ${commLabel} - Rentivo`);

  const invalidatePreview = useCallback(() => {
    previewController.current?.abort();
    previewRequest.current += 1;
    setPreview(null);
    setAcknowledged(false);
    setPreviewing(false);
  }, []);

  const requestPreview = useCallback(async (nextSubject: string, nextBody: string) => {
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    const request = ++previewRequest.current;
    setPreviewing(true);
    setActionError("");
    try {
      const { data } = await apiRequest(apiClient.POST(
        "/api/v1/billings/{billing_uuid}/communications/preview",
        {
          body: { body: nextBody, subject: nextSubject },
          params: { path: { billing_uuid: billingUuid } },
          signal: controller.signal
        }
      ));
      if (controller.signal.aborted || request !== previewRequest.current) return;
      setPreview(data);
      setAcknowledged(false);
    } catch (caught) {
      if (controller.signal.aborted || request !== previewRequest.current) return;
      setActionError(errorMessage(caught, "Não foi possível atualizar a pré-visualização."));
    } finally {
      if (!controller.signal.aborted && request === previewRequest.current) setPreviewing(false);
    }
  }, [billingUuid]);

  const load = useCallback(async () => {
    /* v8 ignore next -- invalid communication types never invoke resource loading */
    if (!commType) return;
    loadController.current?.abort();
    previewController.current?.abort();
    sendController.current?.abort();
    previewRequest.current += 1;
    const controller = new AbortController();
    loadController.current = controller;
    setBilling(null);
    setBill(null);
    setSubject("");
    setBody("");
    setSelectedRecipients([]);
    setSaveScope("");
    setPreview(null);
    setAcknowledged(false);
    setLoading(true);
    setPreviewing(false);
    setSending(false);
    setLoadError("");
    setActionError("");
    setFieldErrors({});
    try {
      const [billingResult, billResult] = await Promise.all([
        apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}", { params: { path: { billing_uuid: billingUuid } }, signal: controller.signal })),
        apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}/bills/{bill_uuid}", { params: { path: { billing_uuid: billingUuid, bill_uuid: billUuid } }, signal: controller.signal }))
      ]);
      /* v8 ignore next -- an aborted request is intentionally discarded */
      if (controller.signal.aborted) return;
      const template = billingResult.data.communication_templates.find((item) => item.comm_type === commType);
      const nextSubject = template?.subject ?? "";
      const nextBody = template?.body ?? "";
      setBilling(billingResult.data);
      setBill(billResult.data);
      setSubject(nextSubject);
      setBody(nextBody);
      setSelectedRecipients(billingResult.data.recipients.map((recipient) => recipient.uuid));
      setLoading(false);
      const capabilities = billResult.data.capabilities;
      const canSendDocument = capabilities.can_compose && (
        commType === "payment_receipt" ? capabilities.can_send_recibo : capabilities.can_send_invoice
      );
      if (billingResult.data.recipients.length > 0 && canSendDocument) {
        void requestPreview(nextSubject, nextBody);
      }
    } catch (caught) {
      /* v8 ignore next -- an aborted request is intentionally discarded */
      if (controller.signal.aborted) return;
      setLoadError(errorMessage(caught, "Não foi possível carregar a comunicação."));
      setLoading(false);
    }
  }, [billUuid, billingUuid, commType, requestPreview]);

  useEffect(() => {
    if (commType) void load();
    return () => {
      loadController.current?.abort();
      previewController.current?.abort();
      sendController.current?.abort();
      previewRequest.current += 1;
    };
  }, [commType, load]);

  const focusError = (key: string | undefined) => {
    if (key?.startsWith("recipient_uuids")) recipientRef.current?.focus();
    else if (key === "subject") subjectRef.current?.focus();
    else if (key === "body") bodyRef.current?.focus();
    else if (key === "acknowledge_warning") acknowledgementRef.current?.focus();
    else if (key === "save_scope") saveScopeRef.current?.focus();
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    /* v8 ignore next -- invalid communication types never render the send form */
    if (!commType) return;
    setActionError(""); setFieldErrors({});
    if (selectedRecipients.length === 0) {
      setActionError("Selecione ao menos um destinatário.");
      recipientRef.current?.focus();
      return;
    }
    sendController.current?.abort();
    const controller = new AbortController();
    sendController.current = controller;
    setSending(true);
    try {
      const requestBody: components["schemas"]["CommunicationSendRequest"] = {
        acknowledge_warning: acknowledged,
        bill_uuid: billUuid,
        body,
        comm_type: commType,
        recipient_uuids: selectedRecipients,
        save_scope: saveScope || null,
        subject
      };
      const { response } = await apiRequest(apiClient.POST(
        "/api/v1/billings/{billing_uuid}/communications/send",
        { body: requestBody, params: { path: { billing_uuid: billingUuid } }, signal: controller.signal }
      ));
      if (controller.signal.aborted) return;
      pushAnalyticsFromResponse(response);
      navigate(`/billings/${billingUuid}/bills/${billUuid}`);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const errors = normalizedFieldErrors(caught);
      setFieldErrors(errors);
      setActionError(errorMessage(caught, "Não foi possível enviar a comunicação."));
      requestAnimationFrame(() => focusError(firstFieldError(errors, ["recipient_uuids", "subject", "body", "acknowledge_warning", "save_scope"])));
    } finally {
      if (!controller.signal.aborted) setSending(false);
    }
  };

  if (!commType) return <div className="panel"><div className="panel__body"><p className="text-muted">Tipo de comunicação inválido.</p></div></div>;
  if (loading) return <LoadingState label="Carregando comunicação..." />;
  if (loadError) return <LoadError message={loadError} onRetry={() => void load()} />;
  /* v8 ignore next -- successful paired loading always sets both resources */
  if (!billing || !bill) return null;

  if (!bill.capabilities.can_compose) {
    return <div className="panel"><div className="panel__body"><p className="text-muted">Você não possui permissão para enviar esta comunicação.</p></div></div>;
  }
  const canSendDocument = isRecibo ? bill.capabilities.can_send_recibo : bill.capabilities.can_send_invoice;
  if (!canSendDocument) {
    return <div className="panel"><div className="panel__body"><p className="text-muted">{isRecibo ? "O recibo ainda está sendo gerado." : "A fatura ainda está sendo gerada."}</p></div></div>;
  }

  const severe = (preview?.severe.length ?? 0) > 0;
  const mild = (preview?.mild.length ?? 0) > 0;
  const sendDisabled = sending || previewing || !preview || severe || (mild && !acknowledged) || selectedRecipients.length === 0;

  return (
    <>
      <Link className="crumb" to={`/billings/${billingUuid}/bills/${billUuid}`}><ArrowLeft aria-hidden="true" size={16} /> Fatura {formatMonth(bill.reference_month)}</Link>
      <div className="pagehead"><div><h1 className="pagehead__title">Enviar {commLabel}</h1><p className="pagehead__sub">{billing.name} · {formatMonth(bill.reference_month)}. Cada destinatário recebe um e-mail separado com o {isRecibo ? "recibo" : "PDF da fatura"} anexado.</p></div></div>
      {billing.recipients.length === 0 ? <div className="panel"><div className="panel__body"><p className="text-muted">Nenhum destinatário cadastrado. <Link to={`/billings/${billingUuid}/edit`}>Adicione destinatários</Link> na cobrança antes de enviar.</p></div></div> : (
        <form id="comm-form" onSubmit={(event) => void send(event)}>
          <div className="panel"><div className="panel__head"><h3>Destinatários</h3></div><div className="panel__body">{billing.recipients.map((recipient, index) => {
            const label = isFullContact(recipient) ? `${recipient.name} <${recipient.email}>` : "Destinatário protegido";
            return <label className="field" key={recipient.uuid} style={{ alignItems: "center", display: "flex", gap: ".5rem" }}><input aria-describedby={index === 0 && fieldErrors.recipient_uuids ? "recipient_uuids-error" : undefined} checked={selectedRecipients.includes(recipient.uuid)} onChange={(event) => setSelectedRecipients((current) => event.target.checked ? [...current, recipient.uuid] : current.filter((uuid) => uuid !== recipient.uuid))} ref={index === 0 ? recipientRef : undefined} type="checkbox" value={recipient.uuid} /><span>{label}</span></label>;
          })}<FieldError id="recipient_uuids-error" message={fieldErrors.recipient_uuids} /></div></div>

          <div className="panel"><div className="panel__head"><h3>Mensagem</h3><span className="panel__title-eyebrow">Markdown</span></div><div className="panel__body">
            <div className="field"><label className="field__label" htmlFor="subject">Assunto</label><input aria-describedby={fieldErrors.subject ? "subject-error" : undefined} className="input" id="subject" onChange={(event) => { setSubject(event.target.value); invalidatePreview(); }} ref={subjectRef} value={subject} /><FieldError id="subject-error" message={fieldErrors.subject} /></div>
            <div className="field"><label className="field__label" htmlFor="body">Corpo (Markdown — HTML não é permitido)</label><textarea aria-describedby={fieldErrors.body ? "body-error" : undefined} className="input" id="body" onChange={(event) => { setBody(event.target.value); invalidatePreview(); }} ref={bodyRef} rows={12} value={body} /><span className="field__hint">Variáveis: {"{{nome_inquilino}}"}, {"{{unidade}}"}, {"{{mes}}"}, {"{{vencimento}}"}, {"{{total}}"}.</span><FieldError id="body-error" message={fieldErrors.body} /></div>
            <button className="btn btn--sm" disabled={previewing} onClick={() => void requestPreview(subject, body)} type="button"><Eye aria-hidden="true" size={14} /> {previewing ? "Atualizando..." : "Atualizar pré-visualização"}</button>
          </div></div>

          <div className="panel"><div className="panel__head"><h3>Pré-visualização</h3></div><div className="panel__body"><div id="preview" dangerouslySetInnerHTML={{ __html: preview?.html ?? "" }} />{!preview && <p className="text-muted">A pré-visualização aparecerá aqui.</p>}</div></div>
          {(severe || mild) && <div className="panel" id="moderation-panel"><div className="panel__head"><h3>Verificação de conteúdo</h3></div><div className="panel__body">{severe && <div style={{ color: "#c0392b" }}>Conteúdo não permitido (ofensa grave ou ameaça): {preview?.severe.join(", ")}. Edite para enviar.</div>}{mild && <div style={{ color: "#b9770e" }}>Linguagem possivelmente ofensiva: {preview?.mild.join(", ")}.</div>}{mild && !severe && <label style={{ alignItems: "center", display: "flex", gap: ".5rem" }}><input aria-describedby={fieldErrors.acknowledge_warning ? "acknowledge_warning-error" : undefined} checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} ref={acknowledgementRef} type="checkbox" /><span>Reconheço o aviso e quero enviar mesmo assim.</span></label>}<FieldError id="acknowledge_warning-error" message={fieldErrors.acknowledge_warning} /></div></div>}

          <div className="panel"><div className="panel__head"><h3>Salvar modelo (opcional)</h3></div><div className="panel__body"><div className="field"><label className="sr-only" htmlFor="save_scope">Salvar modelo</label><select aria-describedby={fieldErrors.save_scope ? "save_scope-error" : undefined} className="select" id="save_scope" onChange={(event) => setSaveScope(event.target.value as typeof saveScope)} ref={saveScopeRef} value={saveScope}><option value="">Não salvar como modelo</option><option value="billing">Salvar para esta cobrança</option>{billing.capabilities.can_edit && <option value="owner">Salvar para {billing.owner.type === "organization" ? "a organização" : "minha conta"}</option>}</select><FieldError id="save_scope-error" message={fieldErrors.save_scope} /></div></div></div>
          {actionError && <div className="toast toast--danger" role="alert">{actionError}</div>}
          <div className="btn-row"><Link className="btn btn--ghost" to={`/billings/${billingUuid}/bills/${billUuid}`}>Cancelar</Link><button className="btn btn--primary" disabled={sendDisabled} id="comm-send-btn" type="submit"><Send aria-hidden="true" size={16} /> {sending ? "Enviando..." : `Enviar ${commLabel}`}</button></div>
        </form>
      )}
    </>
  );
}

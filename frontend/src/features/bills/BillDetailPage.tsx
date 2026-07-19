import { ArrowLeft, Edit3, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { LoadError, LoadingState } from "../../components/PageState";
import { apiClient, apiRequest } from "../../lib/api/client";
import { formatBrl, formatIsoDate, formatMonth } from "../../lib/format";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import { BillStatusActions } from "./BillStatusActions";
import { ReceiptManager } from "./ReceiptManager";
import type { Bill, Billing } from "./billSupport";
import { errorMessage, formatDateTime, useDocumentTitle } from "./billSupport";

const STATUS_META: Record<string, { className: string; label: string }> = {
  cancelled: { className: "tag--cancelled", label: "Cancelado" },
  delayed_payment: { className: "tag--delayed", label: "Pag. Atrasado" },
  draft: { className: "tag--draft", label: "Rascunho" },
  paid: { className: "tag--paid", label: "Pago" },
  published: { className: "tag--published", label: "Publicado" },
  sent: { className: "tag--sent", label: "Enviado" }
};

export function BillDetailPage() {
  const { billingUuid = "", billUuid = "" } = useParams<{ billingUuid: string; billUuid: string }>();
  const navigate = useNavigate();
  const [billing, setBilling] = useState<Billing | null>(null);
  const [bill, setBill] = useState<Bill | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [success, setSuccess] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [downloadingRecibo, setDownloadingRecibo] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<"communication" | "download" | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const downloadButtonRef = useRef<HTMLButtonElement>(null);
  const communicationButtonRef = useRef<HTMLButtonElement>(null);
  const mutationControllers = useRef(new Set<AbortController>());
  const routeGeneration = useRef(0);

  useDocumentTitle(bill ? `Fatura ${formatMonth(bill.reference_month)} - Rentivo` : "Fatura - Rentivo");

  useEffect(() => {
    const controllers = mutationControllers.current;
    const generation = ++routeGeneration.current;
    setActionError("");
    setSuccess("");
    setDeleting(false);
    setDeleteOpen(false);
    setRegenerating(false);
    setDownloadingRecibo(false);
    setOpenDropdown(null);
    return () => {
      if (routeGeneration.current === generation) routeGeneration.current += 1;
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };
  }, [billingUuid, billUuid]);

  useEffect(() => {
    if (!openDropdown) return;
    const close = () => setOpenDropdown(null);
    const closeWithKeyboard = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const button = openDropdown === "download" ? downloadButtonRef.current : communicationButtonRef.current;
      setOpenDropdown(null);
      button?.focus();
    };
    document.addEventListener("click", close);
    document.addEventListener("keydown", closeWithKeyboard);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", closeWithKeyboard);
    };
  }, [openDropdown]);

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
        apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}", {
          params: { path: { billing_uuid: billingUuid } }, signal: controller.signal
        })),
        apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}/bills/{bill_uuid}", {
          params: { path: { billing_uuid: billingUuid, bill_uuid: billUuid } }, signal: controller.signal
        }))
      ]);
      /* v8 ignore next -- an aborted request is intentionally discarded */
      if (controller.signal.aborted) return;
      setBilling(billingResult.data);
      setBill(billResult.data);
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

  const regenerate = async () => {
    /* v8 ignore next -- the action is only rendered after bill loading */
    if (!bill) return;
    const { controller, generation } = beginMutation();
    setRegenerating(true);
    setActionError("");
    try {
      const { data, response } = await apiRequest(apiClient.POST(
        "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/regenerate",
        { params: { path: { billing_uuid: billingUuid, bill_uuid: bill.uuid } }, signal: controller.signal }
      ));
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
    setDeleting(true);
    setActionError("");
    try {
      const { response } = await apiRequest(apiClient.DELETE(
        "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}",
        { params: { path: { billing_uuid: billingUuid, bill_uuid: bill.uuid } }, signal: controller.signal }
      ));
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

  const downloadRecibo = async (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    const { controller, generation } = beginMutation();
    setDownloadingRecibo(true);
    setActionError("");
    try {
      const { data, response } = await apiRequest(apiClient.GET(
        "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/recibo/download",
        {
          params: { path: { billing_uuid: billingUuid, bill_uuid: billUuid } },
          signal: controller.signal
        }
      ));
      if (!mutationIsCurrent(controller, generation)) return;
      pushAnalyticsFromResponse(response);
      const anchor = document.createElement("a");
      anchor.href = data.download_url;
      anchor.download = data.filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
    } catch {
      if (!mutationIsCurrent(controller, generation)) return;
      setActionError("Não foi possível baixar o recibo.");
    } finally {
      mutationControllers.current.delete(controller);
      if (mutationIsCurrent(controller, generation)) setDownloadingRecibo(false);
    }
  };

  if (loading) return <LoadingState label="Carregando fatura..." />;
  if (loadError) return <LoadError message={loadError} onRetry={() => void load()} />;
  /* v8 ignore next -- successful paired loading always sets both resources */
  if (!bill || !billing) return null;
  const status = STATUS_META[bill.status] ?? { className: "tag--draft", label: bill.status };
  const hasFullCommunication = (communication: Bill["communications"][number]): communication is Extract<Bill["communications"][number], { recipient_email: string }> => "recipient_email" in communication;

  return (
    <>
      <Link className="crumb" to={`/billings/${billingUuid}`}><ArrowLeft aria-hidden="true" size={16} />{billing.name}</Link>
      <div className="pagehead">
        <div><h1 className="pagehead__title">Fatura · {formatMonth(bill.reference_month)}</h1><p className="pagehead__sub">Cobrança: {billing.name}{bill.due_date ? ` · vencimento ${formatIsoDate(bill.due_date)}` : ""}</p></div>
        <div className="page-actions">
          <span className={`tag ${status.className}`}>{["sent", "paid", "delayed_payment"].includes(bill.status) && <span className="dot" />}{status.label}</span>
          {bill.pdf_render_status === "pending" && <span className="tag tag--draft" title="O PDF está sendo regenerado em segundo plano.">Renderizando…</span>}
          {bill.pdf_render_status === "failed" && <span className="tag tag--cancelled" title="Falha ao gerar o PDF. Tente regenerar manualmente.">Falha no PDF</span>}
          {bill.capabilities.can_download_invoice && <div className={`btn-dropdown${openDropdown === "download" ? " open" : ""}`}>
            <button aria-controls="bill-download-menu" aria-expanded={openDropdown === "download"} className="btn btn-dropdown-toggle" onClick={(event) => { event.stopPropagation(); setOpenDropdown((current) => current === "download" ? null : "download"); }} ref={downloadButtonRef} type="button">Baixar <span aria-hidden="true" className="btn-dropdown-caret">▾</span></button>
            <div className="btn-dropdown-menu" id="bill-download-menu">
              <a className="btn-dropdown-item" href={`/api/v1/billings/${billingUuid}/bills/${bill.uuid}/invoice`} target="_blank">Baixar fatura</a>
              {bill.capabilities.can_download_recibo
                ? <a aria-disabled={downloadingRecibo || undefined} className="btn-dropdown-item" href={`/api/v1/billings/${billingUuid}/bills/${bill.uuid}/recibo/download`} onClick={(event) => void downloadRecibo(event)} target="_blank">Baixar recibo</a>
                : <span aria-disabled="true" className="btn-dropdown-item btn-dropdown-item--disabled" title={bill.status === "paid" ? "O recibo ainda está sendo gerado." : "O recibo fica disponível quando a fatura está paga."}>Baixar recibo</span>}
            </div>
          </div>}
          {bill.capabilities.can_edit && <Link className="btn" to={`/billings/${billingUuid}/bills/${bill.uuid}/edit`}><Edit3 aria-hidden="true" size={16} /> Editar</Link>}
          {bill.capabilities.can_compose && <div className={`btn-dropdown${openDropdown === "communication" ? " open" : ""}`}>
            <button aria-controls="bill-communication-menu" aria-expanded={openDropdown === "communication"} className="btn btn--primary btn-dropdown-toggle" onClick={(event) => { event.stopPropagation(); setOpenDropdown((current) => current === "communication" ? null : "communication"); }} ref={communicationButtonRef} type="button">Enviar comunicação <span aria-hidden="true" className="btn-dropdown-caret">▾</span></button>
            <div className="btn-dropdown-menu" id="bill-communication-menu">
              {bill.capabilities.can_send_invoice
                ? <Link className="btn-dropdown-item" to={`/billings/${billingUuid}/bills/${bill.uuid}/communications/compose?type=bill_ready`}>Enviar fatura</Link>
                : <span aria-disabled="true" className="btn-dropdown-item btn-dropdown-item--disabled" title="A fatura ainda está sendo gerada.">Enviar fatura</span>}
              {bill.capabilities.can_send_recibo
                ? <Link className="btn-dropdown-item" to={`/billings/${billingUuid}/bills/${bill.uuid}/communications/compose?type=payment_receipt`}>Enviar recibo</Link>
                : <span aria-disabled="true" className="btn-dropdown-item btn-dropdown-item--disabled" title={bill.status === "paid" ? "O recibo ainda está sendo gerado." : "O recibo fica disponível quando a fatura está paga."}>Enviar recibo</span>}
            </div>
          </div>}
        </div>
      </div>

      <div className="panel" style={{ boxShadow: "var(--sh-lg)" }}>
        <div className="panel__head" style={{ background: "var(--ink)", borderBottomColor: "var(--ink)" }}><span className="flex gap-sm" style={{ alignItems: "center" }}><span className="brand__mark" style={{ borderColor: "#fff", fontSize: "0.8rem", height: 26, width: 26 }}>R</span><span style={{ color: "#fff", fontFamily: "var(--font-display)", fontWeight: 700 }}>rentivo</span></span><span className="mono" style={{ color: "rgba(255,255,255,0.7)", fontSize: "0.72rem", whiteSpace: "nowrap" }}>FATURA · {formatMonth(bill.reference_month)}</span></div>
        <div className="panel__body" style={{ padding: "1.75rem" }}>
          <div className="grid-2 mb-3" style={{ gap: "1.5rem" }}>
            <div><div className="field__label">Recebedor</div><div style={{ fontWeight: 700 }}>{billing.pix_merchant_name || billing.name}</div>{billing.pix_key && <div className="mono muted" style={{ fontSize: "0.82rem", wordBreak: "break-all" }}>{billing.pix_key}</div>}{billing.pix_merchant_city && <div className="muted" style={{ fontSize: "0.82rem" }}>{billing.pix_merchant_city}</div>}</div>
            <div><div className="field__label">Cobrar de</div><div style={{ fontWeight: 700 }}>{billing.name}</div>{billing.description && <div className="muted" style={{ fontSize: "0.82rem" }}>{billing.description}</div>}</div>
          </div>
          <div style={{ border: "2px solid var(--ink)", borderRadius: "var(--r-sm)", overflow: "hidden" }}><table className="table"><thead><tr><th>Descrição</th><th className="center">Tipo</th><th className="num">Valor</th></tr></thead><tbody>
            {bill.line_items.map((item, index) => <tr key={`${item.description}-${item.sort_order}-${index}`}><td className="table__primary">{item.description}</td><td className="center"><span className={`tag tag--${item.item_type}`}>{item.item_type === "fixed" ? "Fixo" : item.item_type === "variable" ? "Variável" : "Extra"}</span></td><td className="num">{formatBrl(item.amount)}</td></tr>)}
            <tr className="total"><td colSpan={2}>Total a pagar</td><td className="num" style={{ fontSize: "1.05rem" }}>{formatBrl(bill.total_amount)}</td></tr>
          </tbody></table></div>
          <div className="flex gap mt-3 wrap" style={{ alignItems: "center", background: "var(--accent-pale)", border: "2px solid var(--accent)", borderRadius: "var(--r)", justifyContent: "space-between", padding: "1.25rem" }}><div><div className="mono" style={{ color: "var(--accent-dark)", fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase" }}>Pague com PIX</div><div style={{ fontFamily: "var(--font-display)", fontSize: "1.9rem", fontWeight: 700 }}>{formatBrl(bill.total_amount)}</div><div className="muted" style={{ fontSize: "0.84rem" }}>O QR Code PIX no padrão EMV vai no PDF da fatura.{bill.due_date && <> Vencimento <strong style={{ color: "var(--ink)" }}>{formatIsoDate(bill.due_date)}</strong>.</>}</div></div>{bill.capabilities.can_download_invoice && <a className="btn btn--ink" href={`/api/v1/billings/${billingUuid}/bills/${bill.uuid}/invoice`} target="_blank">Abrir PDF com QR</a>}</div>
        </div>
      </div>

      {(bill.capabilities.can_transition || bill.capabilities.can_regenerate) && <div className="panel panel--menu-host"><div className="panel__head"><h3>Gerenciar fatura</h3></div><div className="panel__body"><div className="btn-row"><BillStatusActions billingUuid={billingUuid} bill={bill} onChange={setBill} onStale={() => void load()} />{bill.capabilities.can_regenerate && <button className="btn" disabled={regenerating} onClick={() => void regenerate()} type="button"><RefreshCw aria-hidden="true" size={16} />{regenerating ? "Regenerando..." : "Regenerar PDF"}</button>}</div>{bill.status_updated_at && <p className="muted mt-2 mb-0" style={{ fontSize: "0.84rem" }}>Status atualizado em {formatDateTime(bill.status_updated_at)}.</p>}</div></div>}
      {bill.notes && <div className="panel"><div className="panel__head"><h3>Observações</h3></div><div className="panel__body">{bill.notes}</div></div>}
      <div className="panel"><div className="panel__head"><h3>Comprovantes</h3></div><div className="panel__body"><ReceiptManager billingUuid={billingUuid} billUuid={bill.uuid} capabilities={bill.capabilities} onChange={(receipts) => setBill((current) => ({ ...current!, receipts }))} receipts={bill.receipts} /></div></div>
      <div className="panel"><div className="panel__head"><h3>Comunicações</h3></div><div className="panel__body">{bill.communications.length === 0 ? <p className="text-muted">Nenhuma comunicação enviada.</p> : <div className="table-wrap"><table className="table"><thead><tr><th>Data</th><th>Destinatário</th><th>Assunto</th><th className="center">Status</th></tr></thead><tbody>{bill.communications.map((communication) => <tr key={communication.uuid}><td className="mono" style={{ whiteSpace: "nowrap" }}>{formatDateTime(communication.created_at)}</td>{hasFullCommunication(communication) ? <><td className="table__primary">{communication.recipient_name} &lt;{communication.recipient_email}&gt;</td><td>{communication.subject}</td></> : <><td className="table__primary">Dados do destinatário protegidos</td><td>—</td></>}<td className="center"><span className={`tag ${communication.status === "sent" ? "tag--paid" : communication.status === "failed" ? "tag--cancelled" : "tag--draft"}`}>{communication.status === "sent" ? "Enviado" : communication.status === "failed" ? "Falhou" : "Na fila"}</span></td></tr>)}</tbody></table></div>}</div></div>
      {actionError && <div className="toast toast--danger" role="alert">{actionError}</div>}{success && <div className="toast toast--success" role="status">{success}</div>}
      <div className="btn-row"><Link className="btn btn--ghost" to={`/billings/${billingUuid}`}><ArrowLeft aria-hidden="true" size={16} /> Voltar</Link>{bill.capabilities.can_delete && <button className="btn btn--danger" disabled={deleting} onClick={() => setDeleteOpen(true)} type="button"><Trash2 aria-hidden="true" size={16} /> Excluir fatura</button>}</div>
      <ConfirmDialog acceptLabel="Excluir fatura" body="A fatura e seus arquivos serão removidos. Esta ação não pode ser desfeita." onClose={() => setDeleteOpen(false)} onConfirm={() => void removeBill()} open={deleteOpen} title="Tem certeza que deseja excluir esta fatura?" />
    </>
  );
}

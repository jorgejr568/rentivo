import { ChevronLeft, QrCode } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { FieldError } from "../../components/FieldError";
import { LoadError, LoadingState } from "../../components/PageState";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { formatBrl, formatMonth, parseBrl } from "../../lib/format";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import { AttachmentManager } from "./AttachmentManager";

type Attachment = components["schemas"]["AttachmentResponse"];
type Bill = components["schemas"]["BillResponse"];
type BillingCapabilities = components["schemas"]["BillingCapabilitiesResponse"] & {
  can_create_bills: boolean;
  can_create_exports: boolean;
  can_manage_theme: boolean;
  can_read_attachments: boolean;
  can_read_bills: boolean;
  can_read_expenses: boolean;
  can_read_theme: boolean;
  can_upload_bill_receipts: boolean;
  can_write_attachments: boolean;
  can_write_expenses: boolean;
};
type Billing = Omit<components["schemas"]["BillingResponse"], "capabilities"> & { capabilities: BillingCapabilities };
type Expense = components["schemas"]["ExpenseResponse"];
type ExpenseCategory = components["schemas"]["ExpenseCreateRequest"]["category"];
type Organization = components["schemas"]["OrganizationResponse"];

interface DetailData {
  attachments: Attachment[];
  billing: Billing;
  bills: Bill[];
  expenses: Expense[];
  organizations: Organization[];
}

interface LoadedDetail {
  data: DetailData;
  billingUuid: string;
}

type DetailAction = "delete" | "expense-create" | "expense-delete" | "export-csv" | "export-xlsx" | "transfer";

interface ActionToken {
  action: DetailAction;
  billingUuid: string;
  controller: AbortController;
}

const CATEGORY_LABELS: Record<ExpenseCategory, string> = {
  condominio: "Condomínio",
  iptu: "IPTU",
  manutencao: "Manutenção",
  outros: "Outros",
  seguro: "Seguro"
};
const STATUS_LABELS: Record<string, string> = {
  cancelled: "Cancelado",
  delayed_payment: "Pag. Atrasado",
  draft: "Rascunho",
  paid: "Pago",
  published: "Publicado",
  sent: "Enviado"
};

function normalizedFields(error: ApiError): Record<string, string> {
  return Object.fromEntries(Object.entries(error.fields).map(([key, value]) => [key.replace(/^body\./, ""), value]));
}

function StatusTag({ status }: { status: string }) {
  const dotted = status === "sent" || status === "paid" || status === "delayed_payment";
  const style = status === "delayed_payment" ? "delayed" : status;
  return <span className={`tag tag--${style}`}>{dotted ? <span className="dot" /> : null}{STATUS_LABELS[status]}</span>;
}

export function BillingDetailPage() {
  const billingUuid = useParams<{ billingUuid: string }>().billingUuid!;
  const navigate = useNavigate();
  const routeUuidRef = useRef(billingUuid);
  const mutationControllersRef = useRef(new Set<AbortController>());
  const activeActionRef = useRef<ActionToken | null>(null);
  const expenseHeadingRef = useRef<HTMLHeadingElement>(null);
  routeUuidRef.current = billingUuid;
  const [loaded, setLoaded] = useState<LoadedDetail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [notice, setNotice] = useState("");
  const [expenseDescription, setExpenseDescription] = useState("");
  const [expenseCategory, setExpenseCategory] = useState<ExpenseCategory>("iptu");
  const [expenseDate, setExpenseDate] = useState("");
  const [expenseAmount, setExpenseAmount] = useState("");
  const [expenseErrors, setExpenseErrors] = useState<Record<string, string>>({});
  const [pendingExpense, setPendingExpense] = useState<Expense | null>(null);
  const [pendingTransfer, setPendingTransfer] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(false);
  const [organizationUuid, setOrganizationUuid] = useState("");
  const [activeAction, setActiveAction] = useState<DetailAction | null>(null);

  const beginAction = (action: DetailAction): ActionToken | null => {
    if (activeActionRef.current) return null;
    const token = { action, billingUuid, controller: new AbortController() };
    activeActionRef.current = token;
    mutationControllersRef.current.add(token.controller);
    setActiveAction(action);
    return token;
  };
  const actionIsCurrent = (token: ActionToken) => activeActionRef.current === token
    && !token.controller.signal.aborted && routeUuidRef.current === token.billingUuid;
  const finishAction = (token: ActionToken) => {
    mutationControllersRef.current.delete(token.controller);
    if (activeActionRef.current === token) {
      activeActionRef.current = null;
      setActiveAction(null);
    }
  };

  const load = useCallback(async (requestUuid: string, signal?: AbortSignal) => {
    const isCurrent = () => !signal?.aborted && routeUuidRef.current === requestUuid;
    if (isCurrent()) {
      setLoadError("");
      setMutationError("");
    }
    try {
      const billingResult = await apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}", {
        params: { path: { billing_uuid: requestUuid } }, signal
      }));
      const billing = billingResult.data as Billing;
      if (!isCurrent()) return;
      const [billResult, expenseResult, attachmentResult, organizationResult] = await Promise.all([
        billing.capabilities.can_read_bills
          ? apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}/bills", { params: { path: { billing_uuid: requestUuid } }, signal }))
          : null,
        billing.capabilities.can_read_expenses
          ? apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}/expenses", { params: { path: { billing_uuid: requestUuid } }, signal }))
          : null,
        billing.capabilities.can_read_attachments
          ? apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}/attachments", { params: { path: { billing_uuid: requestUuid } }, signal }))
          : null,
        billing.capabilities.can_transfer
          ? apiRequest(apiClient.GET("/api/v1/organizations", { signal }))
          : null
      ]);
      if (isCurrent()) setLoaded({
        billingUuid: requestUuid,
        data: {
          attachments: attachmentResult?.data.items ?? [],
          billing,
          bills: billResult?.data.items ?? [],
          expenses: expenseResult?.data.items ?? [],
          organizations: organizationResult?.data.items ?? []
        }
      });
    } catch {
      if (isCurrent()) setLoadError("Não foi possível carregar a cobrança.");
    }
  }, []);

  useEffect(() => {
    const previousTitle = document.title;
    const controller = new AbortController();
    const mutationControllers = mutationControllersRef.current;
    document.title = "Cobrança - Rentivo";
    activeActionRef.current = null;
    setActiveAction(null);
    setPendingExpense(null);
    setPendingTransfer(false);
    setPendingDelete(false);
    setOrganizationUuid("");
    setNotice("");
    void load(billingUuid, controller.signal);
    return () => {
      controller.abort();
      mutationControllers.forEach((mutationController) => mutationController.abort());
      mutationControllers.clear();
      activeActionRef.current = null;
      document.title = previousTitle;
    };
  }, [billingUuid, load]);
  const data = loaded?.billingUuid === billingUuid ? loaded.data : null;
  useEffect(() => { if (data) document.title = `${data.billing.name} - Rentivo`; }, [data]);
  useEffect(() => {
    const first = Object.keys(expenseErrors)[0];
    if (first) document.querySelector<HTMLElement>(`[name="expense-${first}"]`)?.focus();
  }, [expenseErrors]);

  const exportBills = async (format: "csv" | "xlsx") => {
    const token = beginAction(`export-${format}`);
    if (!token) return;
    setMutationError(""); setNotice("");
    try {
      const { response } = await apiRequest(apiClient.POST("/api/v1/billings/{billing_uuid}/exports", { body: { format }, params: { path: { billing_uuid: token.billingUuid } }, signal: token.controller.signal }));
      if (!actionIsCurrent(token)) return;
      pushAnalyticsFromResponse(response);
      setNotice(`Exportação ${format.toUpperCase()} solicitada. O arquivo será enviado para o seu e-mail.`);
    } catch {
      if (actionIsCurrent(token)) setMutationError("Não foi possível solicitar a exportação.");
    } finally {
      finishAction(token);
    }
  };

  const addExpense = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const token = beginAction("expense-create");
    if (!token) return;
    setExpenseErrors({}); setMutationError("");
    try {
      const { response } = await apiRequest(apiClient.POST("/api/v1/billings/{billing_uuid}/expenses", {
        body: { amount: parseBrl(expenseAmount) ?? 0, category: expenseCategory, description: expenseDescription.trim(), incurred_on: expenseDate },
        params: { path: { billing_uuid: token.billingUuid } }, signal: token.controller.signal
      }));
      if (!actionIsCurrent(token)) return;
      pushAnalyticsFromResponse(response);
      setExpenseDescription(""); setExpenseCategory("iptu"); setExpenseDate(""); setExpenseAmount("");
      await load(token.billingUuid, token.controller.signal);
    } catch (caught) {
      if (actionIsCurrent(token)) {
        if (caught instanceof ApiError && Object.keys(caught.fields).length) setExpenseErrors(normalizedFields(caught));
        else setMutationError("Não foi possível adicionar a despesa.");
      }
    } finally {
      finishAction(token);
    }
  };

  const removeExpense = async (expense: Expense) => {
    const token = beginAction("expense-delete");
    if (!token) return;
    setMutationError("");
    try {
      const { response } = await apiRequest(apiClient.DELETE("/api/v1/billings/{billing_uuid}/expenses/{expense_uuid}", { params: { path: { billing_uuid: token.billingUuid, expense_uuid: expense.uuid } }, signal: token.controller.signal }));
      if (!actionIsCurrent(token)) return;
      pushAnalyticsFromResponse(response);
      await load(token.billingUuid, token.controller.signal);
      if (!actionIsCurrent(token)) return;
      setNotice("Despesa removida.");
      expenseHeadingRef.current?.focus();
    } catch {
      if (actionIsCurrent(token)) setMutationError("Não foi possível remover a despesa.");
    } finally {
      finishAction(token);
    }
  };

  const transfer = async () => {
    const token = beginAction("transfer");
    if (!token) return;
    setMutationError("");
    try {
      const { response } = await apiRequest(apiClient.POST("/api/v1/billings/{billing_uuid}/transfer", { body: { organization_uuid: organizationUuid }, params: { path: { billing_uuid: token.billingUuid } }, signal: token.controller.signal }));
      if (!actionIsCurrent(token)) return;
      pushAnalyticsFromResponse(response);
      navigate("/billings/");
    } catch {
      if (actionIsCurrent(token)) setMutationError("Não foi possível transferir a cobrança.");
    } finally {
      finishAction(token);
    }
  };

  const deleteBilling = async () => {
    const token = beginAction("delete");
    if (!token) return;
    setMutationError("");
    try {
      const { response } = await apiRequest(apiClient.DELETE("/api/v1/billings/{billing_uuid}", { params: { path: { billing_uuid: token.billingUuid } }, signal: token.controller.signal }));
      if (!actionIsCurrent(token)) return;
      pushAnalyticsFromResponse(response);
      navigate("/billings/");
    } catch {
      if (actionIsCurrent(token)) setMutationError("Não foi possível excluir a cobrança.");
    } finally {
      finishAction(token);
    }
  };

  if (loadError) return <LoadError message={loadError} onRetry={() => void load(billingUuid)} />;
  if (!data) return <LoadingState label="Carregando cobrança..." />;
  const { attachments, billing, bills, expenses, organizations } = data;
  const fixedSubtotal = billing.items.reduce((sum, item) => sum + (item.item_type === "fixed" ? item.amount : 0), 0);
  const ownerIsOrganization = billing.owner.type === "organization";
  const hasPixOverride = Boolean(billing.pix_key || billing.pix_merchant_name || billing.pix_merchant_city);

  return (
    <>
      <Link className="crumb" to="/billings/"><ChevronLeft aria-hidden="true" size={16} strokeWidth={2.5} />Minhas Cobranças</Link>
      <div className="pagehead"><div><h1 className="pagehead__title">{billing.name}</h1><p className="pagehead__sub">{billing.description || "Modelo de cobrança recorrente"}{ownerIsOrganization ? " · Organização" : ""}</p></div><div className="page-actions">
        {billing.capabilities.can_create_bills ? billing.pix_needs_setup ? <button className="btn btn--primary" disabled title="Configure os dados do PIX primeiro" type="button">Gerar fatura</button> : <Link className="btn btn--primary" to={`/billings/${billingUuid}/bills/generate`}>Gerar fatura</Link> : null}
        {billing.capabilities.can_read_theme ? <Link className="btn" to={`/themes/billing/${billingUuid}`}>Tema</Link> : null}
        {billing.capabilities.can_edit ? <Link className="btn" to={`/billings/${billingUuid}/edit`}>Editar</Link> : null}
      </div></div>

      {billing.pix_needs_setup ? <div className="toast toast--warning" role="alert">Os dados do PIX não estão configurados. Preencha a chave PIX, o nome e a cidade do recebedor {ownerIsOrganization ? <>em <Link to="/organizations/">Organizações</Link></> : <>em <Link to="/security">Segurança</Link></>}{billing.capabilities.can_edit ? <> ou diretamente na <Link to={`/billings/${billingUuid}/edit`}>edição desta cobrança</Link></> : null}.</div> : null}
      {mutationError ? <div className="toast toast--error" role="alert">{mutationError} <button className="btn btn--sm" onClick={() => void load(billingUuid)} type="button">Tentar novamente</button></div> : null}
      {notice ? <div className="toast toast--success" role="status">{notice}</div> : null}

      <div className="grid-2" style={{ alignItems: "start", gridTemplateColumns: "1.4fr 1fr" }}>
        <div className="panel"><div className="panel__head"><h3>Itens da cobrança</h3><span className="panel__title-eyebrow">Modelo recorrente</span></div><div className="table-wrap"><table className="table"><thead><tr><th>Descrição</th><th className="center">Tipo</th><th className="num">Valor</th></tr></thead><tbody>{billing.items.map((item, index) => <tr key={`${item.description}-${index}`}><td className="table__primary">{item.description}</td><td className="center"><span className={`tag tag--${item.item_type}`}>{item.item_type === "fixed" ? "Fixo" : "Variável"}</span></td><td className="num">{item.item_type === "fixed" ? formatBrl(item.amount) : <span className="muted">por fatura</span>}</td></tr>)}<tr className="total"><td colSpan={2}>Subtotal fixo</td><td className="num">{formatBrl(fixedSubtotal)}</td></tr></tbody></table></div></div>
        <div className="panel"><div className="panel__head"><h3>Recebimento PIX</h3><QrCode aria-hidden="true" size={20} /></div><div className="panel__body">{hasPixOverride ? <>{billing.pix_key ? <div className="field" style={{ marginBottom: "0.9rem" }}><div className="field__label">Chave PIX (override)</div><div className="between" style={{ background: "var(--paper-2)", border: "2px solid var(--ink)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem" }}><span className="mono" style={{ fontSize: "0.85rem", wordBreak: "break-all" }}>{billing.pix_key}</span></div></div> : null}<div className="grid-2" style={{ gap: "0.9rem" }}><div><div className="field__label">Recebedor</div><div style={{ fontSize: "0.9rem", fontWeight: 600 }}>{billing.pix_merchant_name || "—"}</div></div><div><div className="field__label">Cidade</div><div className="mono" style={{ fontSize: "0.85rem" }}>{billing.pix_merchant_city || "—"}</div></div></div></> : <p className="muted mb-2" style={{ fontSize: "0.88rem" }}>Sem override nesta cobrança — usa a configuração do proprietário ({ownerIsOrganization ? "organização" : "sua conta"}).</p>}<div className={`tag ${billing.pix_needs_setup ? "tag--draft" : "tag--paid"} mt-2`} style={{ width: "fit-content" }}><span className="dot" />{billing.pix_needs_setup ? "PIX pendente" : "PIX configurado"}</div></div></div>
      </div>

      {billing.capabilities.can_read_bills || billing.capabilities.can_create_exports ? <div className="panel"><div className="panel__head"><h3>Faturas</h3>{billing.capabilities.can_read_bills ? <span className="panel__title-eyebrow">{bills.length} {bills.length === 1 ? "gerada" : "geradas"}</span> : null}</div>{billing.capabilities.can_create_exports ? <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", padding: "0.75rem 1rem" }}><button className="btn btn--sm" disabled={activeAction !== null} onClick={() => void exportBills("csv")} title="Enviar as faturas em CSV para o seu e-mail" type="button">Exportar CSV</button><button className="btn btn--sm" disabled={activeAction !== null} onClick={() => void exportBills("xlsx")} title="Enviar as faturas em Excel para o seu e-mail" type="button">Exportar Excel</button></div> : null}{billing.capabilities.can_read_bills ? bills.length ? <div className="table-wrap"><table className="table"><thead><tr><th>Referência</th><th className="num">Total</th><th className="center">Vencimento</th><th className="center">Status</th><th /></tr></thead><tbody>{bills.map((bill) => <tr key={bill.uuid}><td className="table__primary"><Link style={{ border: "none" }} to={`/billings/${billingUuid}/bills/${bill.uuid}`}>{formatMonth(bill.reference_month)}</Link></td><td className="num">{formatBrl(bill.total_amount)}</td><td className="center mono" style={{ fontSize: "0.85rem" }}>{bill.due_date || "—"}</td><td className="center"><StatusTag status={bill.status} /></td><td className="num"><Link className="btn btn--sm" to={`/billings/${billingUuid}/bills/${bill.uuid}`}>Ver</Link></td></tr>)}</tbody></table></div> : <div className="empty-state" style={{ padding: "2.5rem" }}><p>Nenhuma fatura gerada para este imóvel.</p>{billing.capabilities.can_create_bills && !billing.pix_needs_setup ? <Link className="btn btn--primary" to={`/billings/${billingUuid}/bills/generate`}>Gerar primeira fatura</Link> : null}</div> : null}</div> : null}

      {billing.capabilities.can_read_expenses || billing.capabilities.can_write_expenses ? <div className="panel"><div className="panel__head"><h3 ref={expenseHeadingRef} tabIndex={-1}>Despesas</h3><span className="panel__title-eyebrow">Resultado líquido (ano)</span></div><div className="panel__body"><div className="grid-2" style={{ gap: "0.9rem", marginBottom: "1rem" }}><div><div className="field__label">Recebido (ano)</div><div style={{ fontWeight: 600 }}>{formatBrl(billing.stats.received)}</div></div><div><div className="field__label">Despesas</div><div style={{ fontWeight: 600 }}>{formatBrl(billing.stats.total_expenses)}</div></div><div><div className="field__label">Resultado líquido</div><div style={{ fontWeight: 700 }}>{formatBrl(billing.stats.net_income)}</div></div></div>
        {billing.capabilities.can_read_expenses ? expenses.length ? <div className="table-wrap"><table className="table"><thead><tr><th>Descrição</th><th className="center">Categoria</th><th className="center">Data</th><th className="num">Valor</th>{billing.capabilities.can_write_expenses ? <th /> : null}</tr></thead><tbody>{expenses.map((expense) => <tr key={expense.uuid}><td className="table__primary">{expense.description}</td><td className="center">{CATEGORY_LABELS[expense.category]}</td><td className="center mono" style={{ fontSize: "0.85rem" }}>{expense.incurred_on}</td><td className="num">{formatBrl(expense.amount)}</td>{billing.capabilities.can_write_expenses ? <td className="num"><button aria-label={`Remover despesa ${expense.description}`} className="btn btn--danger btn--sm" disabled={activeAction !== null} onClick={() => setPendingExpense(expense)} type="button">Remover</button></td> : null}</tr>)}</tbody></table></div> : <p className="muted mb-2" style={{ fontSize: "0.88rem" }}>Nenhuma despesa registrada.</p> : null}
        {billing.capabilities.can_write_expenses ? <form onSubmit={addExpense} style={{ marginTop: "1rem" }}><div className="item-grid"><div className="field mb-0"><input aria-label="Descrição da despesa" className="input" name="expense-description" onChange={(event) => setExpenseDescription(event.target.value)} placeholder="Descrição" required type="text" value={expenseDescription} /><FieldError id="expense-description-error" message={expenseErrors.description} /></div><div className="field mb-0"><select aria-label="Categoria da despesa" className="select" name="expense-category" onChange={(event) => setExpenseCategory(event.target.value as ExpenseCategory)} required value={expenseCategory}>{Object.entries(CATEGORY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><FieldError id="expense-category-error" message={expenseErrors.category} /></div><div className="field mb-0"><input aria-label="Data da despesa" className="input" name="expense-incurred_on" onChange={(event) => setExpenseDate(event.target.value)} required type="date" value={expenseDate} /><FieldError id="expense-date-error" message={expenseErrors.incurred_on} /></div><div className="field mb-0"><input aria-label="Valor da despesa (R$)" className="input" name="expense-amount" onChange={(event) => setExpenseAmount(event.target.value)} placeholder="0,00" required type="text" value={expenseAmount} /><FieldError id="expense-amount-error" message={expenseErrors.amount} /></div><div><button className="btn btn--primary" disabled={activeAction !== null} type="submit">Adicionar despesa</button></div></div></form> : null}
      </div></div> : null}

      {billing.capabilities.can_read_attachments ? <AttachmentManager attachments={attachments} billingUuid={billingUuid} canEdit={billing.capabilities.can_write_attachments} mode="detail" onChanged={load.bind(null, billingUuid)} onError={setMutationError} /> : null}
      {billing.capabilities.can_transfer && organizations.length ? <div className="panel"><div className="panel__head"><h3>Transferir para organização</h3></div><div className="panel__body"><div className="item-grid"><div className="field mb-0"><select aria-label="Organização de destino" className="select" onChange={(event) => setOrganizationUuid(event.target.value)} required value={organizationUuid}><option value="">Selecione...</option>{organizations.map((organization) => <option key={organization.uuid} value={organization.uuid}>{organization.name}</option>)}</select></div><div><button className="btn btn--primary" disabled={!organizationUuid || activeAction !== null} onClick={() => setPendingTransfer(true)} type="button">Transferir</button></div></div></div></div> : null}
      {billing.capabilities.can_delete ? <div className="panel danger-zone"><div className="panel__head"><h3>Zona de perigo</h3></div><div className="panel__body"><p className="muted mb-2" style={{ fontSize: "0.88rem" }}>Excluir remove esta cobrança e suas faturas. Não pode ser desfeito.</p><button className="btn btn--danger btn--sm" disabled={activeAction !== null} onClick={() => setPendingDelete(true)} type="button">Excluir cobrança</button></div></div> : null}

      <ConfirmDialog acceptLabel="Remover" body="A despesa será removida permanentemente." onClose={() => setPendingExpense(null)} onConfirm={() => { if (pendingExpense) void removeExpense(pendingExpense); }} open={pendingExpense !== null} title="Remover esta despesa?" />
      <ConfirmDialog acceptLabel="Confirmar transferência" body="Esta ação não pode ser desfeita." onClose={() => setPendingTransfer(false)} onConfirm={() => void transfer()} open={pendingTransfer} title="Transferir cobrança?" variant="primary" />
      <ConfirmDialog acceptLabel="Excluir cobrança permanentemente" body="A cobrança e suas faturas serão excluídas. Esta ação não pode ser desfeita." onClose={() => setPendingDelete(false)} onConfirm={() => void deleteBilling()} open={pendingDelete} title="Excluir cobrança?" />
    </>
  );
}

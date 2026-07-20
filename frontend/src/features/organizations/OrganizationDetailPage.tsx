import { Building2, ChevronLeft, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { FieldError } from "../../components/FieldError";
import { LoadError, LoadingState } from "../../components/PageState";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { formatBrl } from "../../lib/format";
import { useAuth } from "../auth/AuthProvider";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import { OrganizationMembers } from "./OrganizationMembers";

type Detail = components["schemas"]["OrganizationLoginDetailResponse"];
type Member = components["schemas"]["OrganizationMemberResponse"];
type MemberRole = Member["role"];
type Billing = components["schemas"]["BillingListItemResponse"];
type BillingList = components["schemas"]["BillingListResponse"];
type BillingStats = components["schemas"]["BillingStatsResponse"];
type Invite = components["schemas"]["OrganizationInviteResponse"];
type ActiveAction = { controller: AbortController; generation: number; key: string };

interface Confirmation {
  body: string;
  confirm: () => void;
  label: string;
  title: string;
  variant?: "danger" | "primary";
}

const ROLE_LABELS: Record<MemberRole, string> = {
  admin: "Admin",
  manager: "Gerente",
  viewer: "Visualizador"
};
const ROLE_TAGS: Record<MemberRole, string> = {
  admin: "tag--fixed",
  manager: "tag--variable",
  viewer: "tag--draft"
};
const INVITE_META: Record<Invite["status"], { className: string; label: string }> = {
  accepted: { className: "tag--paid", label: "Aceito" },
  declined: { className: "tag--overdue", label: "Recusado" },
  pending: { className: "tag--pending", label: "Pendente" }
};
const BILL_STATUS: Record<string, { className: string; label: string }> = {
  cancelled: { className: "tag--cancelled", label: "Cancelado" },
  delayed_payment: { className: "tag--delayed", label: "Pag. Atrasado" },
  draft: { className: "tag--draft", label: "Rascunho" },
  paid: { className: "tag--paid", label: "Pago" },
  published: { className: "tag--published", label: "Publicado" },
  sent: { className: "tag--sent", label: "Enviado" }
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function normalizedFields(error: ApiError): Record<string, string> {
  return Object.fromEntries(Object.entries(error.fields).map(([key, value]) => [key.replace(/^body\./, ""), value]));
}

function plural(count: number, singular: string, multiple: string): string {
  return count === 1 ? singular : multiple;
}

function Stats({ stats }: { stats: BillingStats }) {
  return (
    <div className="stats mb-3">
      <div className="stat" style={{ "--bar": "var(--ink)" } as React.CSSProperties}><div className="stat__label">Faturado · {stats.year}</div><div className="stat__value mono">{formatBrl(stats.expected)}</div><div className="stat__meta">{stats.billed_count} {plural(stats.billed_count, "fatura", "faturas")} no ano</div></div>
      <div className="stat" style={{ "--bar": "var(--accent)" } as React.CSSProperties}><div className="stat__label">Recebido · {stats.year}</div><div className="stat__value mono">{formatBrl(stats.received)}</div><div className="stat__meta">{stats.paid_count} {plural(stats.paid_count, "fatura paga", "faturas pagas")}</div></div>
      <div className="stat" style={{ "--bar": "var(--pending)" } as React.CSSProperties}><div className="stat__label">Pendente</div><div className="stat__value mono">{formatBrl(stats.pending)}</div><div className="stat__meta">{stats.pending_count} aguardando</div></div>
      <div className="stat" style={{ "--bar": "var(--overdue)" } as React.CSSProperties}><div className="stat__label">Em atraso</div><div className="stat__value mono">{formatBrl(stats.overdue)}</div><div className="stat__meta">{stats.overdue_count} {plural(stats.overdue_count, "vencida", "vencidas")}</div></div>
    </div>
  );
}

function BillingTable({ billings }: { billings: Billing[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Imóvel</th><th className="center">Itens</th><th className="num">Fatura atual</th><th className="center">Status</th><th /></tr></thead>
        <tbody>
          {billings.map((billing) => {
            const status = billing.current_bill ? BILL_STATUS[billing.current_bill.status] : null;
            return (
              <tr key={billing.uuid}>
                <td className="table__primary"><Link style={{ border: "none" }} to={`/billings/${billing.uuid}`}>{billing.name}</Link></td>
                <td className="center mono">{billing.item_count}</td>
                <td className="num">{billing.current_bill ? formatBrl(billing.current_bill.total_amount) : <span className="muted">—</span>}</td>
                <td className="center">{status ? <span className={`tag ${status.className}`}>{status.label}</span> : <span className="tag tag--draft">Sem fatura</span>}</td>
                <td className="num"><Link className="btn btn--sm" to={`/billings/${billing.uuid}`}>Ver</Link></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function OrganizationDetailPage() {
  const { orgUuid = "" } = useParams<{ orgUuid: string }>();
  const navigate = useNavigate();
  const { refreshSession } = useAuth();
  const previousTitle = useRef(document.title);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [billingList, setBillingList] = useState<BillingList | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [success, setSuccess] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<MemberRole>("viewer");
  const [inviteErrors, setInviteErrors] = useState<Record<string, string>>({});
  const [transferUuid, setTransferUuid] = useState("");
  const [activeAction, setActiveAction] = useState("");
  const activeActionRef = useRef<ActiveAction | null>(null);
  const generationRef = useRef(0);
  const pendingFocusRef = useRef<(() => HTMLElement | null) | null>(null);
  const inviteEmailRef = useRef<HTMLInputElement>(null);
  const membersHeadingRef = useRef<HTMLHeadingElement>(null);
  const transferRef = useRef<HTMLButtonElement>(null);
  const deleteRef = useRef<HTMLButtonElement>(null);
  const mfaRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async (signal?: AbortSignal, generation = generationRef.current) => {
    setLoadError("");
    try {
      const [organizationResult, billingResult] = await Promise.all([
        apiRequest(apiClient.GET("/api/v1/organizations/{organization_uuid}", {
          params: { path: { organization_uuid: orgUuid } }, signal
        })),
        apiRequest(apiClient.GET("/api/v1/billings", { signal }))
      ]);
      if (!signal?.aborted && generation === generationRef.current) {
        setDetail(organizationResult.data as Detail);
        setBillingList(billingResult.data);
      }
    } catch (caught) {
      if (!signal?.aborted && generation === generationRef.current) {
        setLoadError(errorMessage(caught, "Não foi possível carregar a organização."));
      }
    }
  }, [orgUuid]);

  useEffect(() => {
    const generation = ++generationRef.current;
    const controller = new AbortController();
    activeActionRef.current?.controller.abort();
    activeActionRef.current = null;
    pendingFocusRef.current = null;
    setActiveAction("");
    setDetail(null);
    setBillingList(null);
    setLoadError("");
    setActionError("");
    setSuccess("");
    setConfirmation(null);
    setInviteErrors({});
    setInviteEmail("");
    setInviteRole("viewer");
    setTransferUuid("");
    void load(controller.signal, generation);
    return () => controller.abort();
  }, [load]);
  useEffect(() => () => {
    generationRef.current += 1;
    activeActionRef.current?.controller.abort();
    activeActionRef.current = null;
    pendingFocusRef.current = null;
  }, []);
  useEffect(() => { document.title = detail ? `${detail.name} - Rentivo` : "Organização - Rentivo"; }, [detail]);
  useEffect(() => () => { document.title = previousTitle.current; }, []);

  const focusLater = (control: HTMLElement | null) => { pendingFocusRef.current = () => control; };
  const beginAction = () => { setActionError(""); setSuccess(""); };
  const startAction = (key: string): ActiveAction | null => {
    if (activeActionRef.current) return null;
    const action = { controller: new AbortController(), generation: generationRef.current, key };
    activeActionRef.current = action;
    setActiveAction(key);
    beginAction();
    return action;
  };
  const isCurrentAction = (action: ActiveAction) => (
    activeActionRef.current === action
    && !action.controller.signal.aborted
    && action.generation === generationRef.current
  );
  const finishAction = (action: ActiveAction) => {
    if (activeActionRef.current !== action) return;
    activeActionRef.current = null;
    setActiveAction("");
    const resolveControl = pendingFocusRef.current;
    pendingFocusRef.current = null;
    if (resolveControl) setTimeout(() => resolveControl()?.focus(), 0);
  };
  const focusMemberControl = (userId: number) => {
    pendingFocusRef.current = () => document.querySelector<HTMLElement>(`[data-member-id="${userId}"] button[data-member-control]`);
  };
  const runAction = async <T,>(
    key: string,
    request: (signal: AbortSignal) => Promise<T>,
    onSuccess: (result: T) => void,
    onError: (caught: unknown) => void
  ) => {
    const action = startAction(key);
    if (!action) return;
    try {
      const result = await request(action.controller.signal);
      if (isCurrentAction(action)) onSuccess(result);
    } catch (caught) {
      if (isCurrentAction(action)) onError(caught);
    } finally {
      finishAction(action);
    }
  };

  const changeRole = async (member: Member, role: MemberRole, control: HTMLSelectElement) => {
    await runAction(
      `member-role:${member.user_id}`,
      (signal) => apiRequest(apiClient.PATCH("/api/v1/organizations/{organization_uuid}/members/{user_id}", {
        body: { role },
        params: { path: { organization_uuid: orgUuid, user_id: member.user_id } },
        signal
      })),
      ({ data, response }) => {
        pushAnalyticsFromResponse(response);
        setDetail((current) => ({ ...current as Detail, members: (current as Detail).members.map((item) => item.user_id === member.user_id ? data : item) }));
        setSuccess("Papel atualizado com sucesso!");
      },
      (caught) => {
        setActionError(errorMessage(caught, "Não foi possível atualizar o papel."));
        focusLater(control);
      }
    );
  };

  const removeMember = async (member: Member) => {
    const removableMembers = (detail as Detail).members.filter((item) => !item.is_current_user);
    const removedIndex = removableMembers.findIndex((item) => item.user_id === member.user_id);
    const remainingMembers = removableMembers.filter((item) => item.user_id !== member.user_id);
    const focusMember = remainingMembers[Math.min(removedIndex, remainingMembers.length - 1)];
    await runAction(
      `member-remove:${member.user_id}`,
      (signal) => apiRequest(apiClient.DELETE("/api/v1/organizations/{organization_uuid}/members/{user_id}", {
        params: { path: { organization_uuid: orgUuid, user_id: member.user_id } },
        signal
      })),
      ({ response }) => {
        pushAnalyticsFromResponse(response);
        setDetail((current) => ({ ...current as Detail, members: (current as Detail).members.filter((item) => item.user_id !== member.user_id) }));
        setSuccess("Membro removido.");
        if (focusMember) focusMemberControl(focusMember.user_id);
        else focusLater(membersHeadingRef.current);
      },
      (caught) => {
        setActionError(errorMessage(caught, "Não foi possível remover o membro."));
        focusMemberControl(member.user_id);
      }
    );
  };

  const sendInvite = async (event: FormEvent) => {
    event.preventDefault();
    await runAction(
      "invite-create",
      (signal) => {
        setInviteErrors({});
        return apiRequest(apiClient.POST("/api/v1/organizations/{organization_uuid}/invites", {
          body: { email: inviteEmail.trim().toLowerCase(), role: inviteRole },
          params: { path: { organization_uuid: orgUuid } },
          signal
        }));
      },
      ({ data, response }) => {
        pushAnalyticsFromResponse(response);
        setDetail((current) => ({ ...current as Detail, invites: [...(current as Detail).invites, data] }));
        setInviteEmail("");
        setInviteRole("viewer");
        setSuccess("Convite enviado com sucesso!");
      },
      (caught) => {
        if (caught instanceof ApiError) {
          setInviteErrors(normalizedFields(caught));
          setActionError(Object.keys(caught.fields).length ? "" : caught.message);
        } else setActionError("Não foi possível enviar o convite.");
        focusLater(inviteEmailRef.current);
      }
    );
  };

  const updateMfa = async () => {
    await runAction(
      "mfa",
      async (signal) => {
        const result = await apiRequest(apiClient.PUT("/api/v1/organizations/{organization_uuid}/mfa-policy", {
          body: { enforce_mfa: !(detail as Detail).enforce_mfa },
          params: { path: { organization_uuid: orgUuid } },
          signal
        }));
        await refreshSession().catch(() => undefined);
        return result;
      },
      ({ data, response }) => {
        pushAnalyticsFromResponse(response);
        setDetail((current) => ({ ...current as Detail, enforce_mfa: data.enforce_mfa }));
        if (data.mfa_setup_required) navigate("/security/totp/setup");
        else setSuccess("Política de MFA atualizada.");
      },
      (caught) => {
        setActionError(errorMessage(caught, "Não foi possível atualizar a política de MFA."));
        focusLater(mfaRef.current);
      }
    );
  };

  const transferBilling = async () => {
    await runAction(
      "billing-transfer",
      (signal) => apiRequest(apiClient.POST("/api/v1/organizations/{organization_uuid}/billing-transfers", {
        body: { billing_uuid: transferUuid },
        params: { path: { organization_uuid: orgUuid } },
        signal
      })),
      ({ response }) => {
        pushAnalyticsFromResponse(response);
        setBillingList((current) => ({
          ...current as BillingList,
          items: (current as BillingList).items.map((billing) => billing.uuid === transferUuid ? { ...billing, capabilities: { ...billing.capabilities, can_transfer: false }, owner: { name: (detail as Detail).name, type: "organization", uuid: orgUuid } } : billing)
        }));
        setTransferUuid("");
        setSuccess("Cobrança transferida com sucesso!");
      },
      (caught) => {
        setActionError(errorMessage(caught, "Não foi possível transferir a cobrança."));
        focusLater(transferRef.current);
      }
    );
  };

  const deleteOrganization = async () => {
    await runAction(
      "organization-delete",
      (signal) => apiRequest(apiClient.DELETE("/api/v1/organizations/{organization_uuid}", {
        params: { path: { organization_uuid: orgUuid } },
        signal
      })),
      ({ response }) => {
        pushAnalyticsFromResponse(response);
        navigate("/organizations/");
      },
      (caught) => {
        setActionError(errorMessage(caught, "Não foi possível excluir a organização."));
        focusLater(deleteRef.current);
      }
    );
  };

  if (loadError) return <LoadError message={loadError} onRetry={() => void load()} />;
  if (!detail || detail.uuid !== orgUuid || !billingList) return <LoadingState label="Carregando organização..." />;

  const organizationBillings = billingList.items.filter((billing) => billing.owner.type === "organization" && billing.owner.uuid === orgUuid);
  const personalBillings = billingList.items.filter((billing) => billing.owner.type === "user" && billing.capabilities.can_transfer);
  const canManageMembers = detail.capabilities.can_invite;

  return (
    <>
      <Link className="crumb" to="/organizations/"><ChevronLeft aria-hidden="true" size={16} strokeWidth={2.5} />Organizações</Link>
      <div className="pagehead">
        <div className="flex gap" style={{ alignItems: "center" }}>
          <span className="org-card__mark" style={{ fontSize: "1.4rem", height: 52, width: 52 }}>{detail.name.slice(0, 1).toUpperCase()}</span>
          <div><h1 className="pagehead__title">{detail.name}</h1><p className="pagehead__sub">{detail.members.length} membros · {organizationBillings.length} cobranças · você é {ROLE_LABELS[detail.current_role]}</p></div>
        </div>
        <div className="page-actions">
          {detail.capabilities.can_create_billing ? <Link className="btn btn--primary" to="/billings/create">+ Nova cobrança</Link> : null}
          {detail.capabilities.can_manage ? <><Link className="btn" to={`/themes/organization/${orgUuid}`}>Tema</Link><Link className="btn" to={`/organizations/${orgUuid}/edit`}>Editar</Link></> : null}
        </div>
      </div>
      {success ? <div className="toast toast--success" role="status">{success}</div> : null}
      {actionError ? <div className="toast toast--danger" role="alert">{actionError}</div> : null}
      {organizationBillings.length && detail.capabilities.can_view_billing_stats && detail.stats ? <Stats stats={detail.stats} /> : null}
      <div className="panel">
        <div className="panel__head"><h3>Cobranças da organização</h3>{detail.capabilities.can_create_billing ? <Link className="btn btn--sm btn--primary" to="/billings/create">+ Nova cobrança</Link> : <span className="panel__title-eyebrow">Status da fatura atual</span>}</div>
        {organizationBillings.length ? <BillingTable billings={organizationBillings} /> : <div className="empty-state" style={{ padding: "2.5rem 1.5rem" }}><p>Nenhuma cobrança nesta organização ainda.</p><p className="muted" style={{ fontSize: "0.85rem", marginTop: "-0.6rem" }}>Crie uma cobrança ou transfira uma das suas para cá.</p>{detail.capabilities.can_create_billing ? <Link className="btn btn--primary" to="/billings/create">+ Nova cobrança</Link> : null}</div>}
      </div>
      <div className="organization-detail-grid">
        <div className="stack gap">
          <OrganizationMembers canManageMembers={canManageMembers} disabled={activeAction !== ""} headingRef={membersHeadingRef} members={detail.members} onRemove={(member) => setConfirmation({ body: "Remover este membro?", confirm: () => void removeMember(member), label: "Remover membro", title: "Remover membro?" })} onRoleChange={(member, role, control) => void changeRole(member, role, control)} />
          {canManageMembers && detail.invites.length ? <div className="panel"><div className="panel__head"><h3>Convites enviados</h3></div><div className="table-wrap"><table className="table"><thead><tr><th>E-mail</th><th className="center">Papel</th><th className="center">Status</th></tr></thead><tbody>{detail.invites.map((invite) => { const status = INVITE_META[invite.status]; return <tr key={invite.uuid}><td className="mono" style={{ fontSize: "0.85rem" }}>{invite.invited_email}</td><td className="center"><span className={`tag ${ROLE_TAGS[invite.role]}`}>{ROLE_LABELS[invite.role]}</span></td><td className="center"><span className={`tag ${status.className}`}><span className="dot" />{status.label}</span></td></tr>; })}</tbody></table></div></div> : null}
        </div>
        <div className="stack gap">
          {canManageMembers ? <div className="panel"><div className="panel__head"><h3>Convidar membro</h3><Mail aria-hidden="true" size={18} /></div><div className="panel__body"><form onSubmit={(event) => void sendInvite(event)}><div className="field"><label className="field__label" htmlFor="invite-email">E-mail</label><input aria-describedby={inviteErrors.email ? "invite-email-error" : undefined} className="input mono" disabled={activeAction !== ""} id="invite-email" onChange={(event) => setInviteEmail(event.target.value)} placeholder="nome@email.com" ref={inviteEmailRef} required type="email" value={inviteEmail} /><FieldError id="invite-email-error" message={inviteErrors.email} /></div><div className="field"><label className="field__label" htmlFor="invite-role">Papel</label><select aria-label="Papel do convite" className="select" disabled={activeAction !== ""} id="invite-role" onChange={(event) => setInviteRole(event.target.value as MemberRole)} value={inviteRole}>{Object.entries(ROLE_LABELS).map(([role, label]) => <option key={role} value={role}>{label}</option>)}</select></div><button className="btn btn--primary btn--block" disabled={activeAction !== ""} type="submit">Enviar convite</button></form></div></div> : null}
          {detail.capabilities.can_manage ? <>
            <div className="panel"><div className="panel__head"><h3>Autenticação (MFA)</h3><ShieldCheck aria-hidden="true" size={18} /></div><div className="panel__body"><div className="between" style={{ alignItems: "flex-start" }}><div style={{ maxWidth: "70%" }}><div style={{ fontSize: "0.92rem", fontWeight: 700 }}>Exigir MFA</div><p className="muted mb-0" style={{ fontSize: "0.82rem", marginTop: "0.15rem" }}>{detail.enforce_mfa ? "Obrigatório para todos os membros." : "Opcional para os membros."}</p></div><button aria-checked={detail.enforce_mfa} aria-label={detail.enforce_mfa ? "Desativar exigência de MFA" : "Ativar exigência de MFA"} className="switch" disabled={activeAction !== ""} onClick={() => void updateMfa()} ref={mfaRef} role="switch" title={detail.enforce_mfa ? "Desativar exigência de MFA" : "Ativar exigência de MFA"} type="button" /></div></div></div>
            {personalBillings.length ? <div className="panel"><div className="panel__head"><h3>Transferir cobrança</h3><Building2 aria-hidden="true" size={18} /></div><div className="panel__body"><div className="field"><label className="field__label" htmlFor="transfer-billing">Cobrança para transferir</label><select className="select" disabled={activeAction !== ""} id="transfer-billing" onChange={(event) => setTransferUuid(event.target.value)} value={transferUuid}><option value="">Selecione</option>{personalBillings.map((billing) => <option key={billing.uuid} value={billing.uuid}>{billing.name}</option>)}</select></div><button className="btn btn--primary btn--block" disabled={!transferUuid || activeAction !== ""} onClick={() => setConfirmation({ body: "Tem certeza? Esta ação não pode ser desfeita.", confirm: () => void transferBilling(), label: "Transferir", title: "Transferir cobrança?", variant: "primary" })} ref={transferRef} type="button">Transferir cobrança</button></div></div> : null}
            <div className="panel danger-zone"><div className="panel__head"><h3>Zona de perigo</h3></div><div className="panel__body"><p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>Excluir remove a organização e desvincula suas cobranças. Não pode ser desfeito.</p><button className="btn btn--danger btn--block" disabled={activeAction !== ""} onClick={() => setConfirmation({ body: "Tem certeza que deseja excluir esta organização? Esta ação não pode ser desfeita.", confirm: () => void deleteOrganization(), label: "Excluir organização", title: "Excluir organização?" })} ref={deleteRef} type="button">Excluir organização</button></div></div>
          </> : <><div className="panel"><div className="panel__head"><h3>Sobre a organização</h3><Building2 aria-hidden="true" size={18} /></div><div className="panel__body"><div className="between" style={{ borderBottom: "1.5px solid var(--line)", padding: "0.45rem 0" }}><span className="muted">Seu papel</span><span className={`tag ${ROLE_TAGS[detail.current_role]}`}>{ROLE_LABELS[detail.current_role]}</span></div><div className="between" style={{ borderBottom: "1.5px solid var(--line)", padding: "0.45rem 0" }}><span className="muted">Membros</span><span className="mono">{detail.members.length}</span></div><div className="between" style={{ padding: "0.45rem 0" }}><span className="muted">MFA obrigatório</span>{detail.enforce_mfa ? <span className="tag tag--paid"><span className="dot" />Sim</span> : <span className="tag tag--draft">Não</span>}</div></div></div><div className="panel" style={{ background: "var(--paper-2)" }}><div className="panel__body flex gap-sm"><LockKeyhole aria-hidden="true" size={18} /><p className="muted mb-0">{detail.capabilities.can_create_billing ? "Como gerente você pode criar cobranças e gerar faturas. Gerenciar membros e configurações é restrito a administradores." : "Como visualizador você tem acesso de leitura. Gerenciar cobranças, membros e configurações é restrito a gerentes e administradores."}</p></div></div></>}
        </div>
      </div>
      <ConfirmDialog acceptLabel={confirmation?.label} body={confirmation?.body} onClose={() => setConfirmation(null)} onConfirm={() => confirmation?.confirm()} open={confirmation !== null} title={confirmation?.title ?? "Confirmar"} variant={confirmation?.variant} />
    </>
  );
}

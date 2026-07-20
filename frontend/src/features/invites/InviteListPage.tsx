import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { LoadError, LoadingState } from "../../components/PageState";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { useAuth } from "../auth/AuthProvider";
import { pushAnalyticsFromResponse } from "../auth/analytics";

type Invite = components["schemas"]["PendingInviteLoginResponse"];
type Selection = { action: "accept" | "decline"; invite: Invite } | null;
type ActiveResponse = { controller: AbortController; generation: number };
type ResponseOutcome =
  | { action: "accept"; data: components["schemas"]["InviteAcceptResponse"]; response: Response }
  | { action: "decline"; data: components["schemas"]["InviteDeclineResponse"]; response: Response };

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function InviteListPage() {
  const navigate = useNavigate();
  const { refreshSession } = useAuth();
  const [invites, setInvites] = useState<Invite[] | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [message, setMessage] = useState("");
  const [responding, setResponding] = useState(false);
  const actionRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const activeResponseRef = useRef<ActiveResponse | null>(null);
  const generationRef = useRef(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const pendingFocusRef = useRef<(() => HTMLElement | null) | null>(null);

  const load = useCallback(async (signal?: AbortSignal, generation = generationRef.current) => {
    setLoadError("");
    try {
      const { data } = await apiRequest(apiClient.GET("/api/v1/invites", { signal }));
      if (!signal?.aborted && generation === generationRef.current) {
        setInvites((data as components["schemas"]["PendingInviteLoginListResponse"]).items);
      }
    } catch (caught) {
      if (!signal?.aborted && generation === generationRef.current) {
        setLoadError(errorMessage(caught, "Não foi possível carregar os convites."));
      }
    }
  }, []);

  useEffect(() => {
    const previousTitle = document.title;
    const controller = new AbortController();
    const generation = ++generationRef.current;
    document.title = "Convites - Rentivo";
    void load(controller.signal, generation);
    return () => {
      generationRef.current += 1;
      controller.abort();
      activeResponseRef.current?.controller.abort();
      activeResponseRef.current = null;
      pendingFocusRef.current = null;
      document.title = previousTitle;
    };
  }, [load]);

  const respond = async (action: "accept" | "decline", invite: Invite) => {
    if (activeResponseRef.current) return;
    const active = { controller: new AbortController(), generation: generationRef.current };
    activeResponseRef.current = active;
    setResponding(true);
    setActionError("");
    setMessage("");
    const isCurrent = () => (
      activeResponseRef.current === active
      && !active.controller.signal.aborted
      && active.generation === generationRef.current
    );
    try {
      let outcome: ResponseOutcome;
      if (action === "accept") {
        const result = await apiRequest(apiClient.POST("/api/v1/invites/{invite_uuid}/accept", {
          params: { path: { invite_uuid: invite.uuid } },
          signal: active.controller.signal
        }));
        outcome = { action, data: result.data, response: result.response };
      } else {
        const result = await apiRequest(apiClient.POST("/api/v1/invites/{invite_uuid}/decline", {
          params: { path: { invite_uuid: invite.uuid } },
          signal: active.controller.signal
        }));
        outcome = { action, data: result.data, response: result.response };
      }
      if (!isCurrent()) return;
      pushAnalyticsFromResponse(outcome.response);
      await refreshSession().catch(() => undefined);
      if (!isCurrent()) return;
      if (outcome.action === "accept") {
        navigate(outcome.data.mfa_setup_required ? "/security/totp/setup" : `/organizations/${outcome.data.organization_uuid}`);
        return;
      }
      const currentInvites = invites as Invite[];
      const removedIndex = currentInvites.findIndex((item) => item.uuid === invite.uuid);
      const remaining = currentInvites.filter((item) => item.uuid !== invite.uuid);
      const focusInvite = remaining[Math.min(removedIndex, remaining.length - 1)];
      setInvites(remaining);
      setMessage("Convite recusado.");
      pendingFocusRef.current = () => (
        focusInvite ? actionRefs.current[`decline:${focusInvite.uuid}`] : headingRef.current
      );
    } catch (caught) {
      if (!isCurrent()) return;
      setActionError(errorMessage(caught, action === "accept" ? "Não foi possível aceitar o convite." : "Não foi possível recusar o convite."));
      pendingFocusRef.current = () => actionRefs.current[`${action}:${invite.uuid}`];
    } finally {
      if (activeResponseRef.current === active) {
        activeResponseRef.current = null;
        setResponding(false);
        const resolveControl = pendingFocusRef.current;
        pendingFocusRef.current = null;
        if (resolveControl) setTimeout(() => resolveControl()?.focus(), 0);
      }
    }
  };

  if (loadError) return <LoadError message={loadError} onRetry={() => void load()} />;
  if (!invites) return <LoadingState label="Carregando convites..." />;

  return (
    <>
      <div className="page-header">
        <div className="page-header-info"><h1 className="page-title" ref={headingRef} tabIndex={-1}>Convites Pendentes</h1></div>
      </div>
      {message ? <div className="toast toast--success" role="status">{message}</div> : null}
      {actionError ? <div className="toast toast--danger" role="alert">{actionError}</div> : null}
      {invites.length ? (
        <div className="panel">
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Organização</th><th className="text-center">Papel</th><th>Convidado por</th><th className="text-right">Ações</th></tr></thead>
              <tbody>
                {invites.map((invite) => (
                  <tr key={invite.uuid}>
                    <td>{invite.organization_name}{invite.enforce_mfa ? <> <span className="tag tag--mfa">MFA</span></> : null}</td>
                    <td className="text-center">{invite.role}</td>
                    <td>{invite.invited_by_email}</td>
                    <td className="text-right">
                      <button className="btn btn--sm btn--primary" disabled={responding} onClick={() => setSelection({ action: "accept", invite })} ref={(element) => { actionRefs.current[`accept:${invite.uuid}`] = element; }} type="button">Aceitar</button>{" "}
                      <button className="btn btn--sm btn--danger" disabled={responding} onClick={() => setSelection({ action: "decline", invite })} ref={(element) => { actionRefs.current[`decline:${invite.uuid}`] = element; }} type="button">Recusar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="panel"><div className="empty-state"><p>Nenhum convite pendente.</p></div></div>
      )}
      <ConfirmDialog
        acceptLabel={selection?.action === "accept" ? "Aceitar convite" : "Recusar convite"}
        body={selection?.action === "accept" ? "Você passará a fazer parte desta organização." : "O convite será recusado e removido da lista."}
        onClose={() => setSelection(null)}
        onConfirm={() => { if (selection) void respond(selection.action, selection.invite); }}
        open={selection !== null}
        title={selection?.action === "accept" ? "Aceitar convite?" : "Recusar convite?"}
        variant={selection?.action === "accept" ? "primary" : "danger"}
      />
    </>
  );
}

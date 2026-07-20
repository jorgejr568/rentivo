import { useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import type { Bill } from "./billSupport";
import { errorMessage } from "./billSupport";

type Transition = components["schemas"]["AvailableTransitionResponse"];

export interface BillStatusActionsProps {
  billingUuid: string;
  bill: Bill;
  onChange: (bill: Bill) => void;
  onStale: () => void;
}

interface ConfirmationCopy {
  accept: string;
  body: string;
  title: string;
}

const CONFIRMATIONS: Record<string, ConfirmationCopy> = {
  "cancelled:cancelled": {
    accept: "Cancelar fatura",
    body: "A cobrança é cancelada e deixa de ser tratada como ativa. Você pode reabri-la depois como rascunho, se precisar.",
    title: "Cancelar esta fatura?"
  },
  "paid:cancelled": {
    accept: "Cancelar fatura",
    body: "A cobrança é cancelada e deixa de ser tratada como ativa. Você pode reabri-la depois como rascunho, se precisar.",
    title: "Cancelar esta fatura?"
  },
  "published:draft": {
    accept: "Voltar para rascunho",
    body: "A fatura volta para rascunho e sai do fluxo de cobrança até ser publicada novamente.",
    title: "Voltar para rascunho?"
  },
  "sent:paid": {
    accept: "Marcar como pago",
    body: "Isto marca a fatura como paga, libera o recibo e registra a data de pagamento. Você poderá reverter depois, se necessário.",
    title: "Marcar fatura como paga?"
  },
  "delayed_payment:paid": {
    accept: "Marcar como pago",
    body: "Isto marca a fatura como paga, libera o recibo e registra a data de pagamento. Você poderá reverter depois, se necessário.",
    title: "Marcar fatura como paga?"
  },
  "paid:sent": {
    accept: "Reverter pagamento",
    body: "Isto reverte o pagamento: a fatura deixa de constar como paga e volta para enviada.",
    title: "Reverter o pagamento?"
  },
  "sent:published": {
    accept: "Voltar para publicado",
    body: "A fatura volta para publicado. O registro de envio é mantido, mas ela deixa de constar como enviada.",
    title: "Voltar para publicado?"
  },
  "cancelled:draft": {
    accept: "Reabrir fatura",
    body: "A fatura é reaberta como rascunho e volta a poder ser editada e publicada.",
    title: "Reabrir esta fatura?"
  }
};

function confirmationFor(status: string, transition: Transition): ConfirmationCopy {
  return CONFIRMATIONS[`${status}:${transition.target}`]
    ?? CONFIRMATIONS[`cancelled:${transition.target}`]
    ?? { accept: transition.label, body: "Confirme a alteração de status desta fatura.", title: "Alterar status da fatura?" };
}

export function BillStatusActions({ billingUuid, bill, onChange, onStale }: BillStatusActionsProps) {
  const [selected, setSelected] = useState<Transition | null>(null);
  const [busyTarget, setBusyTarget] = useState("");
  const [error, setError] = useState("");
  const controllerRef = useRef<AbortController | null>(null);
  const routeGeneration = useRef(0);

  useEffect(() => {
    const generation = ++routeGeneration.current;
    setSelected(null);
    setBusyTarget("");
    setError("");
    return () => {
      if (routeGeneration.current === generation) routeGeneration.current += 1;
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [billingUuid, bill.uuid]);

  if (!bill.capabilities.can_transition || bill.available_transitions.length === 0) return null;

  const changeStatus = async (transition: Transition) => {
    /* v8 ignore next -- rendered transition controls prevent concurrent requests */
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const generation = routeGeneration.current;
    setBusyTarget(transition.target);
    setError("");
    try {
      const { data, response } = await apiRequest(apiClient.POST(
        "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/transitions",
        {
          body: {
            current_status: bill.status as components["schemas"]["BillStatus"],
            target: transition.target as components["schemas"]["BillStatus"]
          },
          params: { path: { billing_uuid: billingUuid, bill_uuid: bill.uuid } },
          signal: controller.signal
        }
      ));
      if (controller.signal.aborted || generation !== routeGeneration.current) return;
      pushAnalyticsFromResponse(response);
      onChange(data);
    } catch (caught) {
      if (controller.signal.aborted || generation !== routeGeneration.current) return;
      setError(errorMessage(caught, "Não foi possível alterar o status da fatura."));
      if (caught instanceof ApiError && caught.status === 409) onStale();
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      if (!controller.signal.aborted && generation === routeGeneration.current) setBusyTarget("");
    }
  };

  const [primary, ...others] = bill.available_transitions;
  const renderButton = (transition: Transition, primaryButton: boolean) => (
    <button
      className={primaryButton ? "btn btn--primary" : `status-menu__item${transition.style === "danger" ? " status-menu__item--danger" : ""}`}
      disabled={Boolean(busyTarget)}
      key={transition.target}
      onClick={() => transition.requires_confirmation ? setSelected(transition) : void changeStatus(transition)}
      type="button"
    >
      {busyTarget === transition.target ? "Atualizando..." : transition.label}
    </button>
  );
  const confirmation = selected ? confirmationFor(bill.status, selected) : null;

  return (
    <>
      <div className="btn-row">
        {renderButton(primary, true)}
        {others.length > 0 && (
          <details className="status-menu">
            <summary className="btn">Alterar status</summary>
            <div className="status-menu__panel" role="menu">
              {others.map((transition) => renderButton(transition, false))}
            </div>
          </details>
        )}
      </div>
      {error && <div className="toast toast--danger" role="alert">{error}</div>}
      <ConfirmDialog
        acceptLabel={confirmation?.accept}
        body={confirmation?.body}
        onClose={() => setSelected(null)}
        onConfirm={() => { if (selected) void changeStatus(selected); }}
        open={Boolean(selected)}
        title={confirmation?.title ?? "Alterar status da fatura?"}
        variant={selected?.style === "primary" ? "primary" : "danger"}
      />
    </>
  );
}

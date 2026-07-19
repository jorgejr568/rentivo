import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { LoadError, LoadingState } from "../../components/PageState";
import { apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { formatBrl } from "../../lib/format";

type BillingList = components["schemas"]["BillingListResponse"];
type Stats = components["schemas"]["BillingStatsResponse"];

const STATUS_LABELS: Record<string, string> = {
  cancelled: "Cancelado",
  delayed_payment: "Pag. Atrasado",
  draft: "Rascunho",
  paid: "Pago",
  published: "Publicado",
  sent: "Enviado"
};

function plural(count: number, singular: string, pluralValue: string): string {
  return count === 1 ? singular : pluralValue;
}

function KpiCards({ stats }: { stats: Stats }) {
  return (
    <div className="stats mb-3">
      <div className="stat" style={{ "--bar": "var(--ink)" } as React.CSSProperties}><div className="stat__label">Faturado · {stats.year}</div><div className="stat__value mono">{formatBrl(stats.expected)}</div><div className="stat__meta">{stats.billed_count} {plural(stats.billed_count, "fatura", "faturas")} no ano</div></div>
      <div className="stat" style={{ "--bar": "var(--accent)" } as React.CSSProperties}><div className="stat__label">Recebido · {stats.year}</div><div className="stat__value mono">{formatBrl(stats.received)}</div><div className="stat__meta">{stats.paid_count} {plural(stats.paid_count, "fatura paga", "faturas pagas")}</div></div>
      <div className="stat" style={{ "--bar": "var(--pending)" } as React.CSSProperties}><div className="stat__label">Pendente</div><div className="stat__value mono">{formatBrl(stats.pending)}</div><div className="stat__meta">{stats.pending_count} aguardando</div></div>
      <div className="stat" style={{ "--bar": "var(--overdue)" } as React.CSSProperties}><div className="stat__label">Em atraso</div><div className="stat__value mono">{formatBrl(stats.overdue)}</div><div className="stat__meta">{stats.overdue_count} {plural(stats.overdue_count, "vencida", "vencidas")}</div></div>
    </div>
  );
}

function StatusTag({ status }: { status: string }) {
  const dotted = status === "sent" || status === "paid" || status === "delayed_payment";
  return <span className={`tag tag--${status === "delayed_payment" ? "delayed" : status}`}>{dotted ? <span className="dot" /> : null}{STATUS_LABELS[status]}</span>;
}

export function BillingListPage() {
  const [payload, setPayload] = useState<BillingList | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async (signal?: AbortSignal) => {
    setError("");
    try {
      const { data } = await apiRequest(apiClient.GET("/api/v1/billings", { signal }));
      if (!signal?.aborted) setPayload(data);
    } catch {
      if (!signal?.aborted) setError("Não foi possível carregar as cobranças.");
    }
  }, []);

  useEffect(() => {
    const previousTitle = document.title;
    const controller = new AbortController();
    document.title = "Minhas Cobranças - Rentivo";
    void load(controller.signal);
    return () => { controller.abort(); document.title = previousTitle; };
  }, [load]);

  if (error) return <LoadError message={error} onRetry={() => void load()} />;
  if (!payload) return <LoadingState label="Carregando cobranças..." />;
  const needsPix = payload.items.filter((billing) => billing.pix_needs_setup);

  return (
    <>
      <div className="pagehead">
        <div><h1 className="pagehead__title">Minhas Cobranças</h1><p className="pagehead__sub">{payload.items.length} {plural(payload.items.length, "imóvel cadastrado", "imóveis cadastrados")}</p></div>
        <div className="btn-row"><Link className="btn" to="/organizations/">Organizações</Link><Link className="btn btn--primary" to="/billings/create">+ Nova cobrança</Link></div>
      </div>
      {payload.user_pix_incomplete ? <div className="toast toast--warning" role="alert"><span>Você ainda não configurou seus dados de PIX.</span> <Link to="/security">Configure agora</Link> para conseguir gerar faturas das suas cobranças pessoais.</div> : null}
      {needsPix.length ? (
        <div className="toast toast--warning" role="alert">
          <span>{`As cobranças a seguir não podem gerar faturas até que a chave PIX, o nome e a cidade do recebedor sejam preenchidos ${payload.user_pix_incomplete ? "(na sua conta ou na organização, ou diretamente na cobrança)" : "(no proprietário ou na própria cobrança)"}:`}</span>
          <ul className="mb-0" style={{ marginTop: "0.5rem" }}>{needsPix.map((billing) => <li key={billing.uuid}><Link to={`/billings/${billing.uuid}`}>{billing.name}</Link></li>)}</ul>
        </div>
      ) : null}
      {payload.items.length ? (
        <><KpiCards stats={payload.stats} /><div className="panel"><div className="panel__head"><h3>Imóveis &amp; cobranças</h3><span className="panel__title-eyebrow">Status da fatura atual</span></div><div className="table-wrap"><table className="table"><thead><tr><th>Imóvel</th><th className="center">Itens</th><th className="num">Fatura atual</th><th className="center">Status</th><th /></tr></thead><tbody>{payload.items.map((billing) => <tr key={billing.uuid}><td><Link className="table__primary" style={{ border: "none" }} to={`/billings/${billing.uuid}`}>{billing.name}</Link>{billing.owner.type === "organization" ? <span className="tag tag--solid ms-1">Org</span> : null}{billing.description ? <div className="table__sub">{billing.description}</div> : null}</td><td className="center mono">{billing.item_count}</td><td className="num">{billing.current_bill ? formatBrl(billing.current_bill.total_amount) : <span className="muted">—</span>}</td><td className="center">{billing.current_bill ? <StatusTag status={billing.current_bill.status} /> : <span className="tag tag--draft">Sem fatura</span>}</td><td className="num"><Link className="btn btn--sm" to={`/billings/${billing.uuid}`}>Ver</Link></td></tr>)}</tbody></table></div></div></>
      ) : <div className="panel"><div className="empty-state"><p>Nenhuma cobrança cadastrada.</p><Link className="btn btn--primary" to="/billings/create">Criar primeira cobrança</Link></div></div>}
    </>
  );
}

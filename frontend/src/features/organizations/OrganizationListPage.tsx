import { ArrowRight, LockKeyhole } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { LoadError, LoadingState } from "../../components/PageState";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";

type Organization = components["schemas"]["OrganizationResponse"];

function messageFor(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Não foi possível carregar as organizações.";
}

export function OrganizationListPage() {
  const [organizations, setOrganizations] = useState<Organization[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    setError("");
    try {
      const { data } = await apiRequest(apiClient.GET("/api/v1/organizations", { signal }));
      if (!signal?.aborted) setOrganizations(data.items);
    } catch (caught) {
      if (!signal?.aborted) setError(messageFor(caught));
    }
  }, []);

  useEffect(() => {
    const previousTitle = document.title;
    const controller = new AbortController();
    document.title = "Organizações - Rentivo";
    void load(controller.signal);
    return () => {
      controller.abort();
      document.title = previousTitle;
    };
  }, [load]);

  if (error) return <LoadError message={error} onRetry={() => void load()} />;
  if (!organizations) return <LoadingState label="Carregando organizações..." />;

  return (
    <>
      <div className="pagehead">
        <div>
          <h1 className="pagehead__title">Organizações</h1>
          <p className="pagehead__sub">Gerencie imóveis em equipe, com cargos e permissões.</p>
        </div>
        <div className="btn-row">
          <Link className="btn btn--primary" to="/organizations/create">+ Nova organização</Link>
        </div>
      </div>

      {organizations.length ? (
        <div className="org-grid">
          {organizations.map((organization) => (
            <Link className="org-card" key={organization.uuid} to={`/organizations/${organization.uuid}`}>
              <div className="org-card__top">
                <span className="org-card__mark">{organization.name.slice(0, 1).toUpperCase()}</span>
                <ArrowRight aria-hidden="true" color="var(--muted)" size={20} />
              </div>
              <div className="org-card__name">{organization.name}</div>
              <div className="org-card__foot">
                <span className="org-card__mfa">
                  <LockKeyhole aria-hidden="true" size={14} />
                  Abrir organização
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="panel">
          <div className="empty-state">
            <p>Você não faz parte de nenhuma organização.</p>
            <Link className="btn btn--primary" to="/organizations/create">Criar organização</Link>
          </div>
        </div>
      )}
    </>
  );
}

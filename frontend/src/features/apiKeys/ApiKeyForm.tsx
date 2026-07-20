import { useMemo, useState, type FormEvent } from "react";

import type { components } from "../../lib/api/schema";

type ApiKey = components["schemas"]["APIKeyResponse"];
type ApiKeyCreate = components["schemas"]["APIKeyCreateRequest"];
type ApiKeyOptions = components["schemas"]["APIKeyOptionsResponse"];

export type ApiKeyFormPayload = Omit<ApiKeyCreate, "grants"> & {
  grants?: ApiKeyCreate["grants"];
};

interface ApiKeyFormProps {
  initialKey?: ApiKey;
  loading?: boolean;
  onCancel: () => void;
  onSubmit: (payload: ApiKeyFormPayload) => Promise<void> | void;
  options: ApiKeyOptions;
}

const SCOPE_LABELS: Record<string, string> = {
  "billings:read": "Consultar cobranças",
  "billings:write": "Gerenciar cobranças",
  "bills:read": "Consultar faturas",
  "bills:write": "Gerenciar faturas",
  "communications:read": "Consultar comunicações",
  "communications:send": "Enviar comunicações",
  "expenses:read": "Consultar despesas",
  "expenses:write": "Gerenciar despesas",
  "exports:create": "Criar exportações",
  "files:read": "Consultar arquivos",
  "files:write": "Gerenciar arquivos",
  "organizations:read": "Consultar organizações",
  "profile:read": "Consultar perfil",
  "themes:read": "Consultar temas",
  "themes:write": "Gerenciar temas"
};

function defaultExpiration(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

function explicitExpiration(value: string, maxDays: number): string {
  const selectedEndOfDay = new Date(`${value}T23:59:59.999Z`).getTime();
  const maximum = Date.now() + maxDays * 24 * 60 * 60 * 1000 - 60_000;
  return new Date(Math.min(selectedEndOfDay, maximum)).toISOString();
}

// eslint-disable-next-line react-refresh/only-export-components
export function scopeLabel(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope;
}

export function ApiKeyForm({ initialKey, loading = false, onCancel, onSubmit, options }: ApiKeyFormProps) {
  const initialOrganizations = useMemo(
    () => {
      const selectable = new Set(options.organizations.map((organization) => organization.resource_id));
      return initialKey?.grants
        .filter((grant) => grant.available && grant.resource_type === "organization" && grant.resource_id)
        .filter((grant) => selectable.has(grant.resource_id as string))
        .map((grant) => grant.resource_id as string) ?? [];
    },
    [initialKey, options.organizations]
  );
  const [name, setName] = useState(initialKey?.name ?? "");
  const [scopes, setScopes] = useState<string[]>(initialKey?.scopes ?? []);
  const [personal, setPersonal] = useState(
    initialKey?.grants.some((grant) => grant.available && grant.resource_type === "user") ?? false
  );
  const [organizations, setOrganizations] = useState<string[]>(initialOrganizations);
  const [expiresAt, setExpiresAt] = useState(defaultExpiration(options.default_expiration_days));
  const [expirationChanged, setExpirationChanged] = useState(false);
  const [grantsChanged, setGrantsChanged] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  function toggle(values: string[], value: string): string[] {
    return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    const normalizedName = name.trim();
    const hasWorkspace = personal || organizations.length > 0 || Boolean(initialKey && !grantsChanged);
    if (!normalizedName || scopes.length === 0 || !hasWorkspace) {
      return;
    }
    await onSubmit({
      ...(!initialKey && expirationChanged
        ? { expires_at: explicitExpiration(expiresAt, options.max_expiration_days) }
        : {}),
      ...(!initialKey || grantsChanged ? {
        grants: [
          ...(personal ? [{ resource_id: "personal", resource_type: "user" as const }] : []),
          ...organizations.map((resourceId) => ({ resource_id: resourceId, resource_type: "organization" as const }))
        ]
      } : {}),
      name: normalizedName,
      scopes
    });
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      <div className="field">
        <label className="field-label" htmlFor="api-key-name">Nome</label>
        <input autoFocus className="field-input" id="api-key-name" maxLength={255} onChange={(event) => setName(event.target.value)} value={name} />
        {submitted && !name.trim() ? <span className="field-hint" style={{ color: "var(--danger)" }}>Informe um nome para a chave.</span> : null}
      </div>
      <fieldset className="field" style={{ border: 0, margin: "0 0 1.1rem", padding: 0 }}>
        <legend className="field-label">Permissões</legend>
        <div className="form-grid">
          {options.scopes.map((scope) => (
            <label key={scope} style={{ alignItems: "center", display: "flex", gap: "0.5rem", marginBottom: "0.65rem" }}>
              <input checked={scopes.includes(scope)} onChange={() => setScopes(toggle(scopes, scope))} type="checkbox" />
              {scopeLabel(scope)}
            </label>
          ))}
        </div>
        {submitted && scopes.length === 0 ? <span className="field-hint" style={{ color: "var(--danger)" }}>Selecione pelo menos um escopo.</span> : null}
      </fieldset>
      <fieldset className="field" style={{ border: 0, margin: "0 0 1.1rem", padding: 0 }}>
        <legend className="field-label">Espaços de trabalho</legend>
        <label style={{ alignItems: "center", display: "flex", gap: "0.5rem", marginBottom: "0.65rem" }}>
          <input checked={personal} onChange={(event) => { setPersonal(event.target.checked); setGrantsChanged(true); }} type="checkbox" />
          Pessoal
        </label>
        {options.organizations.map((organization) => (
          <label key={organization.resource_id} style={{ alignItems: "center", display: "flex", gap: "0.5rem", marginBottom: "0.65rem" }}>
            <input
              checked={organizations.includes(organization.resource_id)}
              onChange={() => { setOrganizations(toggle(organizations, organization.resource_id)); setGrantsChanged(true); }}
              type="checkbox"
            />
            {organization.name}
          </label>
        ))}
        {submitted && !personal && organizations.length === 0 && (!initialKey || grantsChanged) ? <span className="field-hint" style={{ color: "var(--danger)" }}>Selecione pelo menos um espaço de trabalho.</span> : null}
      </fieldset>
      {!initialKey ? (
        <div className="field" style={{ maxWidth: "350px" }}>
          <label className="field-label" htmlFor="api-key-expiration">Expira em</label>
          <input className="field-input" id="api-key-expiration" max={defaultExpiration(options.max_expiration_days)} min={new Date().toISOString().slice(0, 10)} onChange={(event) => { setExpiresAt(event.target.value); setExpirationChanged(true); }} required type="date" value={expiresAt} />
        </div>
      ) : null}
      <div className="btn-row">
        <button className="btn btn--primary btn--sm" disabled={loading} type="submit">{initialKey ? "Salvar alterações" : "Criar chave"}</button>
        <button className="btn btn--sm" disabled={loading} onClick={onCancel} type="button">Cancelar</button>
      </div>
    </form>
  );
}

import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { ApiKeyForm, type ApiKeyFormPayload } from "./ApiKeyForm";
import { ApiKeyList } from "./ApiKeyList";
import { ApiKeySecretDialog } from "./ApiKeySecretDialog";

type ApiKey = components["schemas"]["APIKeyResponse"];
type ApiKeyCreate = components["schemas"]["APIKeyCreateRequest"];
type ApiKeyOptions = components["schemas"]["APIKeyOptionsResponse"];

export function ApiKeySection() {
  const [items, setItems] = useState<ApiKey[]>([]);
  const [options, setOptions] = useState<ApiKeyOptions | null>(null);
  const [editing, setEditing] = useState<ApiKey | null>(null);
  const [creating, setCreating] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listResult, optionsResult] = await Promise.all([
        apiRequest(apiClient.GET("/api/v1/api-keys")),
        apiRequest(apiClient.GET("/api/v1/api-keys/options"))
      ]);
      setItems(listResult.data.items);
      setOptions(optionsResult.data);
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as chaves de integração.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function save(payload: ApiKeyFormPayload) {
    setSaving(true);
    setError(null);
    try {
      if (editing) {
        const { data } = await apiRequest(
          apiClient.PATCH("/api/v1/api-keys/{key_uuid}", {
            body: {
              ...(payload.grants ? { grants: payload.grants } : {}),
              name: payload.name,
              scopes: payload.scopes
            },
            params: { path: { key_uuid: editing.uuid } }
          })
        );
        setItems((current) => current.map((key) => key.uuid === data.uuid ? data : key));
        setEditing(null);
        setMessage("Chave de integração atualizada.");
      } else {
        const { data } = await apiRequest(
          apiClient.POST("/api/v1/api-keys", { body: payload as ApiKeyCreate })
        );
        const { secret: issuedSecret, ...visibleKey } = data;
        setItems((current) => [visibleKey, ...current]);
        setCreating(false);
        setSecret(issuedSecret);
      }
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível salvar a chave de integração.");
    } finally {
      setSaving(false);
    }
  }

  async function revoke() {
    const target = revokeTarget!;
    setRevokeTarget(null);
    setError(null);
    try {
      await apiRequest(
        apiClient.DELETE("/api/v1/api-keys/{key_uuid}", {
          params: { path: { key_uuid: target.uuid } }
        })
      );
      setItems((current) => current.map((key) => key.uuid === target.uuid ? { ...key, revoked_at: new Date().toISOString() } : key));
      setMessage("Chave de integração revogada.");
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível revogar a chave de integração.");
    }
  }

  return (
    <div className="panel">
      <div className="panel-head"><h5>Chaves de Integração</h5></div>
      <div className="panel-body">
        {error ? <div className="toast toast--danger" role="alert">{error}</div> : null}
        {message ? <div className="toast toast--success" role="status">{message}</div> : null}
        {loading ? <p role="status">Carregando...</p> : null}
        {!loading && !options ? <button className="btn btn--sm" onClick={() => void load()} type="button">Tentar novamente</button> : null}
        {!loading && options ? (
          <>
            {creating || editing ? (
              <ApiKeyForm initialKey={editing ?? undefined} loading={saving} onCancel={() => { setCreating(false); setEditing(null); }} onSubmit={save} options={options} />
            ) : (
              <>
                <ApiKeyList items={items} onEdit={setEditing} onRevoke={setRevokeTarget} options={options} />
                <button className="btn btn--primary btn--sm" onClick={() => setCreating(true)} style={{ marginTop: "1rem" }} type="button">Criar chave</button>
              </>
            )}
          </>
        ) : null}
      </div>
      <ConfirmDialog acceptLabel="Revogar chave" body={revokeTarget ? `A chave “${revokeTarget.name}” deixará de funcionar imediatamente.` : ""} onClose={() => setRevokeTarget(null)} onConfirm={() => void revoke()} open={revokeTarget !== null} title="Revogar chave" />
      <ApiKeySecretDialog onClose={() => { setSecret(""); setMessage("Chave de integração criada."); }} open={Boolean(secret)} secret={secret} />
    </div>
  );
}

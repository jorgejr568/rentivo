import { KeyRound, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import type { components } from "../../lib/api/schema";

type Passkey = components["schemas"]["PasskeyResponse"];

interface PasskeyManagerProps {
  onDelete: (uuid: string) => Promise<void>;
  onRegister: (name: string) => Promise<void>;
  onSessionRevoked: () => void;
  organizationEnforced: boolean;
  passkeys: Passkey[];
}

const DATE_FORMAT = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" });

export function PasskeyManager({ onDelete, onRegister, onSessionRevoked, organizationEnforced, passkeys }: PasskeyManagerProps) {
  const [name, setName] = useState("");
  const [target, setTarget] = useState<Passkey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { if (error) inputRef.current?.focus(); }, [error]);

  async function register() {
    setLoading(true);
    setError(null);
    try {
      await onRegister(name.trim() || "Minha Passkey");
      setName("");
    } catch (caught: unknown) {
      if (caught instanceof DOMException && caught.name === "NotAllowedError") {
        return;
      }
      setError(caught instanceof Error ? caught.message : "Não foi possível cadastrar a passkey.");
    } finally {
      setLoading(false);
    }
  }

  async function remove() {
    const uuid = target!.uuid;
    setTarget(null);
    setLoading(true);
    setError(null);
    try {
      await onDelete(uuid);
      onSessionRevoked();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Não foi possível remover a passkey.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="panel">
      <div className="panel-head"><h5>Passkeys (Chaves de Acesso)</h5></div>
      <div className="panel-body">
        {organizationEnforced ? <div className="mfa-enforcement-banner">Sua organização exige autenticação multifator. Mantenha pelo menos um fator ativo.</div> : null}
        {error ? <div className="toast toast--danger" role="alert">{error}</div> : null}
        {passkeys.length ? (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Nome</th><th>Criada em</th><th>Último uso</th><th className="text-right">Ações</th></tr></thead>
              <tbody>{passkeys.map((passkey) => (
                <tr key={passkey.uuid}>
                  <td>{passkey.name || "Sem nome"}</td>
                  <td>{DATE_FORMAT.format(new Date(passkey.created_at))}</td>
                  <td>{passkey.last_used_at ? DATE_FORMAT.format(new Date(passkey.last_used_at)) : "Nunca"}</td>
                  <td className="text-right"><button aria-label={`Remover ${passkey.name}`} className="icon-btn" disabled={loading} onClick={() => setTarget(passkey)} title="Remover" type="button"><Trash2 aria-hidden="true" size={16} /></button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : <p>Nenhuma passkey cadastrada.</p>}
        <div style={{ alignItems: "center", display: "flex", flexWrap: "wrap", gap: "0.75rem", marginTop: "1rem" }}>
          <input aria-label="Nome da passkey" className="field-input" onChange={(event) => setName(event.target.value)} placeholder="Nome da passkey" ref={inputRef} style={{ width: "220px" }} value={name} />
          <button className="btn btn--primary btn--sm" disabled={loading} onClick={() => void register()} type="button"><KeyRound aria-hidden="true" size={15} style={{ marginRight: "0.35rem", verticalAlign: "text-bottom" }} />Adicionar Passkey</button>
        </div>
      </div>
      <ConfirmDialog acceptLabel="Remover passkey" body="Você precisará entrar novamente após remover esta passkey." onClose={() => setTarget(null)} onConfirm={() => void remove()} open={target !== null} title="Remover esta passkey?" />
    </div>
  );
}

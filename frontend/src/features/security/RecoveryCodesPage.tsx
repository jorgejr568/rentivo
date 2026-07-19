import { Copy } from "lucide-react";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

interface RecoveryLocationState { recoveryCodes?: string[] }

export function RecoveryCodesPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { refreshSession } = useAuth();
  const recoveryCodes = (location.state as RecoveryLocationState | null)?.recoveryCodes;
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const [continuing, setContinuing] = useState(false);
  const [refreshFailed, setRefreshFailed] = useState(false);

  if (!recoveryCodes?.length) {
    return <Navigate replace to="/security" />;
  }

  async function copyCodes() {
    try {
      await navigator.clipboard.writeText(recoveryCodes!.join("\n"));
      setCopied(true);
      setCopyFailed(false);
    } catch {
      setCopyFailed(true);
    }
  }

  async function continueToSecurity() {
    setContinuing(true);
    setRefreshFailed(false);
    try {
      await refreshSession();
      navigate("/security");
    } catch {
      setRefreshFailed(true);
    } finally {
      setContinuing(false);
    }
  }

  return (
    <>
      <div className="page-header"><div className="page-header-info"><h2 className="page-title">Códigos de Recuperação</h2><p className="page-subtitle">Guarde estes códigos em um local seguro. Cada código pode ser usado apenas uma vez.</p></div></div>
      <div className="panel"><div className="panel-head"><h5>Seus códigos de recuperação</h5></div><div className="panel-body">
        <div className="mfa-enforcement-banner" style={{ background: "#fff8e1", borderColor: "#f9a825" }}>Atenção: estes códigos não serão exibidos novamente. Salve-os agora!</div>
        {copyFailed ? <div className="toast toast--danger" role="alert">Não foi possível copiar os códigos.</div> : null}
        {refreshFailed ? <div className="toast toast--danger" role="alert">Não foi possível atualizar sua sessão. Tente novamente.</div> : null}
        <div className="recovery-grid" id="recovery-codes">{recoveryCodes.map((code) => <code key={code}>{code}</code>)}</div>
        <div className="btn-row" style={{ marginTop: "1rem" }}>
          <button className="btn btn--sm" onClick={() => void copyCodes()} type="button"><Copy aria-hidden="true" size={15} style={{ marginRight: "0.35rem", verticalAlign: "text-bottom" }} />{copied ? "Copiado!" : "Copiar todos"}</button>
          <button aria-busy={continuing} className="btn btn--primary btn--sm" disabled={continuing} onClick={() => void continueToSecurity()} type="button">{refreshFailed ? "Tentar novamente" : "Continuar"}</button>
        </div>
      </div></div>
    </>
  );
}

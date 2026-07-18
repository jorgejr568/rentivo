import { Copy } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";

interface RecoveryLocationState { recoveryCodes?: string[] }

export function RecoveryCodesPage() {
  const location = useLocation();
  const recoveryCodes = (location.state as RecoveryLocationState | null)?.recoveryCodes;
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

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

  return (
    <>
      <div className="page-header"><div className="page-header-info"><h2 className="page-title">Códigos de Recuperação</h2><p className="page-subtitle">Guarde estes códigos em um local seguro. Cada código pode ser usado apenas uma vez.</p></div></div>
      <div className="panel"><div className="panel-head"><h5>Seus códigos de recuperação</h5></div><div className="panel-body">
        <div className="mfa-enforcement-banner" style={{ background: "#fff8e1", borderColor: "#f9a825" }}>Atenção: estes códigos não serão exibidos novamente. Salve-os agora!</div>
        {copyFailed ? <div className="toast toast--danger" role="alert">Não foi possível copiar os códigos.</div> : null}
        <div className="recovery-grid" id="recovery-codes">{recoveryCodes.map((code) => <code key={code}>{code}</code>)}</div>
        <div className="btn-row" style={{ marginTop: "1rem" }}>
          <button className="btn btn--sm" onClick={() => void copyCodes()} type="button"><Copy aria-hidden="true" size={15} style={{ marginRight: "0.35rem", verticalAlign: "text-bottom" }} />{copied ? "Copiado!" : "Copiar todos"}</button>
          <Link className="btn btn--primary btn--sm" to="/security">Continuar</Link>
        </div>
      </div></div>
    </>
  );
}

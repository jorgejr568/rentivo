import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { SubmitButton } from "../auth/AuthComponents";
import { useAuth } from "../auth/AuthProvider";
import { pushAnalyticsFromResponse } from "../auth/analytics";

type Setup = components["schemas"]["TOTPSetupResponse"];

export function TotpSetupPage() {
  const { bootstrap, refreshSession, status } = useAuth();
  const navigate = useNavigate();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [code, setCode] = useState("");
  const [attempt, setAttempt] = useState(0);
  const codeRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async (signal: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await apiRequest(
        apiClient.POST("/api/v1/security/totp/setup", { signal })
      );
      setSetup(data);
    } catch (caught: unknown) {
      if (!signal.aborted) setError(caught instanceof ApiError ? caught.message : "Não foi possível iniciar a configuração TOTP.");
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    document.title = "Configurar TOTP - Rentivo";
    if (status !== "authenticated") {
      return;
    }
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [attempt, load, status]);

  useEffect(() => { if (error) codeRef.current?.focus(); }, [error]);

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setConfirming(true);
    setError(null);
    try {
      const { data, response } = await apiRequest(
        apiClient.POST("/api/v1/security/totp/confirm", {
          body: { code: code.trim() }
        })
      );
      pushAnalyticsFromResponse(response);
      await refreshSession();
      navigate("/security/recovery-codes", { replace: true, state: { recoveryCodes: data.recovery_codes } });
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível confirmar o código.");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <>
      <div className="page-header"><div className="page-header-info"><h2 className="page-title">Configurar Autenticação TOTP</h2><p className="page-subtitle">Escaneie o QR code com seu aplicativo autenticador.</p></div></div>
      {bootstrap?.capabilities.mfa_setup_required ? <div className="mfa-enforcement-banner">Sua organização exige autenticação multifator. Configure o TOTP ou uma passkey para continuar.</div> : null}
      {error ? <div className="toast toast--danger" role="alert">{error}</div> : null}
      {loading ? <p role="status">Carregando...</p> : null}
      {!loading && !setup ? <button className="btn btn--primary" onClick={() => setAttempt((value) => value + 1)} type="button">Tentar novamente</button> : null}
      {setup ? (
        <>
          <div className="panel"><div className="panel-head"><h5>1. Escaneie o QR Code</h5></div><div className="panel-body">
            <p>Abra seu aplicativo autenticador (Google Authenticator, Authy, etc.) e escaneie o código abaixo:</p>
            <div className="qr-code-wrap"><img alt="QR Code TOTP" height="250" src={`data:image/png;base64,${setup.qr_code_base64}`} width="250" /></div>
            <details style={{ marginTop: "1rem" }}><summary style={{ color: "var(--ink-50)", cursor: "pointer", fontSize: "0.9rem" }}>Inserir manualmente</summary><p style={{ marginTop: "0.5rem" }}>Use esta chave no seu aplicativo:</p><div className="secret-key">{setup.secret}</div></details>
          </div></div>
          <div className="panel"><div className="panel-head"><h5>2. Confirme o código</h5></div><div className="panel-body">
            <p>Após escanear, digite o código de 6 dígitos exibido no aplicativo:</p>
            <form onSubmit={(event) => void confirm(event)} style={{ marginTop: "1rem" }}><div className="field" style={{ maxWidth: "280px" }}><label className="field-label" htmlFor="totp-code">Código de verificação</label><input autoComplete="one-time-code" autoFocus className="field-input" id="totp-code" inputMode="numeric" maxLength={6} onChange={(event) => setCode(event.target.value)} placeholder="000000" ref={codeRef} required value={code} /></div><SubmitButton loading={confirming}>Confirmar e Ativar</SubmitButton></form>
          </div></div>
          {bootstrap?.capabilities.mfa_setup_required ? <p style={{ marginTop: "1rem" }}><Link className="btn btn--sm" to="/security">Ou cadastrar uma Passkey</Link></p> : null}
        </>
      ) : null}
    </>
  );
}

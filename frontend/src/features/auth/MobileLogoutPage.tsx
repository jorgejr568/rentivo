import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import { useAuth } from "./AuthProvider";
import { openMobileAuthorizationCallback } from "./mobileAuthorization";

type LogoutPhase = "checking" | "complete" | "failed" | "logging-out";

export function MobileLogoutPage() {
  const { retrySession, status } = useAuth();
  const [searchParams] = useSearchParams();
  const mobileState = searchParams.get("state");
  const [attempt, setAttempt] = useState(0);
  const [phase, setPhase] = useState<LogoutPhase>("checking");

  const returnToApp = useCallback(() => {
    openMobileAuthorizationCallback(
      `rentivo://auth/logout?state=${encodeURIComponent(mobileState!)}`
    );
  }, [mobileState]);

  useEffect(() => {
    document.title = "Sair - Rentivo";
  }, []);

  useEffect(() => {
    if (!mobileState || status === "error" || status === "loading") {
      return;
    }
    let active = true;
    setPhase("logging-out");
    void (async () => {
      if (status === "authenticated") {
        try {
          await apiRequest(apiClient.POST("/api/v1/auth/logout"));
        } catch (caught: unknown) {
          if (!(caught instanceof ApiError && caught.status === 401)) {
            if (active) {
              setPhase("failed");
            }
            return;
          }
        }
      }
      if (active) {
        setPhase("complete");
        returnToApp();
      }
    })();
    return () => {
      active = false;
    };
  }, [attempt, mobileState, returnToApp, status]);

  if (!mobileState) {
    return (
      <LogoutPanel heading="Solicitação inválida">
        <div className="toast toast--danger" role="alert">
          Não foi possível validar a solicitação do aplicativo.
        </div>
      </LogoutPanel>
    );
  }

  if (status === "error") {
    return (
      <LogoutPanel heading="Saindo do Rentivo">
        <div className="toast toast--danger" role="alert">
          Não foi possível verificar a sessão do site.
        </div>
        <button className="btn btn--primary btn--block btn--lg" onClick={retrySession} type="button">
          Tentar novamente
        </button>
      </LogoutPanel>
    );
  }

  if (phase === "failed") {
    return (
      <LogoutPanel heading="Saindo do Rentivo">
        <div className="toast toast--danger" role="alert">
          Não foi possível encerrar a sessão no site.
        </div>
        <button
          className="btn btn--primary btn--block btn--lg"
          onClick={() => setAttempt((value) => value + 1)}
          type="button"
        >
          Tentar novamente
        </button>
      </LogoutPanel>
    );
  }

  if (phase === "complete") {
    return (
      <LogoutPanel heading="Sessão encerrada" mark="✓">
        <p className="muted" style={{ margin: "0.75rem 0 1.5rem" }}>
          Você saiu do site e já pode continuar no app Rentivo.
        </p>
        <button className="btn btn--primary btn--block btn--lg" onClick={returnToApp} type="button">
          Voltar para o app agora
        </button>
      </LogoutPanel>
    );
  }

  return (
    <LogoutPanel heading="Saindo do Rentivo">
      <p className="muted" role="status" style={{ margin: "0.75rem 0 0" }}>
        Encerrando a sessão do site antes de voltar ao aplicativo...
      </p>
    </LogoutPanel>
  );
}

function LogoutPanel({
  children,
  heading,
  mark = "R"
}: {
  children: React.ReactNode;
  heading: string;
  mark?: string;
}) {
  return (
    <div className="login-wrap">
      <div className="panel">
        <div className="panel__body" style={{ padding: "2.25rem", textAlign: "center" }}>
          <div aria-hidden="true" className="auth-mark" style={{ margin: "0 auto 1rem" }}>
            {mark}
          </div>
          <h1 style={{ fontSize: "1.5rem", margin: 0 }}>{heading}</h1>
          {children}
        </div>
      </div>
    </div>
  );
}

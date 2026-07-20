import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { components } from "../../lib/api/schema";
import { useAuth } from "./AuthProvider";

type AuthConfig = components["schemas"]["AuthConfigResponse"];

export function StandardAuthPanel({ children }: { children: ReactNode }) {
  return (
    <div className="login-wrap">
      <div className="panel login-panel">
        <div className="panel-body" style={{ padding: "2rem" }}>
          {children}
        </div>
      </div>
    </div>
  );
}

export function RentivoTitle() {
  return (
    <h2 className="login-title">
      Ren<span>tivo</span>
    </h2>
  );
}

export function LoginAuthHeader() {
  return (
    <div style={{ marginBottom: "1.75rem", textAlign: "center" }}>
      <div className="auth-mark">R</div>
      <h2 style={{ fontSize: "1.5rem", margin: 0 }}>
        Entrar no rent<span style={{ color: "var(--accent-dark)" }}>ivo</span>
      </h2>
      <p className="muted" style={{ fontSize: "0.9rem", margin: "0.35rem 0 0" }}>
        Bem-vindo de volta.
      </p>
    </div>
  );
}

export function AuthError({ message }: { message: string | null }) {
  return message ? (
    <div className="toast toast--error" role="alert">
      {message}
    </div>
  ) : null;
}

interface SubmitButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading: boolean;
}

export function SubmitButton({ children, className, loading, ...props }: SubmitButtonProps) {
  return (
    <button
      {...props}
      aria-busy={loading}
      className={className ?? "btn btn--primary"}
      disabled={loading || props.disabled}
      type="submit"
    >
      {loading ? (
        <LoaderCircle
          aria-hidden="true"
          size={16}
          style={{ marginRight: "0.45rem", verticalAlign: "text-bottom" }}
        />
      ) : null}
      {children}
    </button>
  );
}

export function GoogleAuthLink() {
  return (
    <a
      className="btn btn--block"
      href="/api/v1/auth/google/start"
      style={{
        alignItems: "center",
        display: "inline-flex",
        gap: "0.55rem",
        justifyContent: "center"
      }}
    >
      <svg
        aria-hidden="true"
        className="google-icon"
        focusable="false"
        height="18"
        viewBox="0 0 18 18"
        width="18"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M17.64 9.2045c0-.6381-.0573-1.2518-.1636-1.8409H9v3.4814h4.8436c-.2086 1.125-.8427 2.0782-1.7959 2.7164v2.2581h2.9087c1.7018-1.5668 2.6836-3.874 2.6836-6.615z"
          fill="#4285F4"
        />
        <path
          d="M9 18c2.43 0 4.4673-.806 5.9564-2.1805l-2.9087-2.2581c-.8059.54-1.8368.859-3.0477.859-2.344 0-4.3282-1.5831-5.036-3.7104H.9574v2.3318C2.4382 15.9832 5.4818 18 9 18z"
          fill="#34A853"
        />
        <path
          d="M3.964 10.71c-.18-.54-.2822-1.1168-.2822-1.71s.1023-1.17.2823-1.71V4.9582H.9573A8.9965 8.9965 0 0 0 0 9c0 1.4523.3477 2.8268.9573 4.0418L3.964 10.71z"
          fill="#FBBC05"
        />
        <path
          d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.346l2.5813-2.5814C13.4632.8918 11.4259 0 9 0 5.4818 0 2.4382 2.0168.9573 4.9582L3.964 7.29C4.6718 5.1627 6.6559 3.5795 9 3.5795z"
          fill="#EA4335"
        />
      </svg>
      Continuar com Google
    </a>
  );
}

export function AuthConfigGate({ children }: { children: (config: AuthConfig) => ReactNode }) {
  const { config, configStatus, retryConfig } = useAuth();
  if (configStatus === "loading") {
    return (
      <StandardAuthPanel>
        <p className="muted" role="status">
          Carregando...
        </p>
      </StandardAuthPanel>
    );
  }
  if (configStatus === "error") {
    return (
      <StandardAuthPanel>
        <AuthError message="Não foi possível carregar as opções de autenticação. Tente novamente." />
        <button className="btn btn--primary" onClick={retryConfig} type="button">
          Tentar novamente
        </button>
      </StandardAuthPanel>
    );
  }
  return children(config!);
}

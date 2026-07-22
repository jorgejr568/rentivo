import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import {
  AuthConfigGate,
  AuthError,
  GoogleAuthLink,
  LoginAuthHeader,
  SubmitButton
} from "./AuthComponents";
import { postLoginPath, useAuth } from "./AuthProvider";
import { pushAnalyticsFromResponse } from "./analytics";
import { saveMfaChallenge, takeAuthFlash } from "./authStorage";
import { openMobileAuthorizationCallback } from "./mobileAuthorization";
import { Turnstile, type TurnstileHandle } from "./Turnstile";

type LoginRequest = components["schemas"]["LoginRequest"];

const GOOGLE_ERROR = "Não foi possível entrar com o Google. Tente novamente.";

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const mobileState = searchParams.get("mobile_state");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [error, setError] = useState<string | null>(() =>
    searchParams.get("error") === "google_auth_failed" ? GOOGLE_ERROR : null
  );
  const [flash] = useState(takeAuthFlash);
  const [loading, setLoading] = useState(false);
  const [mobileCallbackURL, setMobileCallbackURL] = useState<string | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const turnstileRef = useRef<TurnstileHandle>(null);
  const mobileAuthorizationStarted = useRef(false);
  const mobileCallbackOpened = useRef(false);

  const completeMobileAuthorization = useCallback(async () => {
    if (!mobileState) {
      return;
    }
    const { data: authorization } = await apiRequest(
      apiClient.POST("/api/v1/auth/mobile/authorize", { body: { state: mobileState } })
    );
    setMobileCallbackURL(
      `rentivo://auth/callback?code=${encodeURIComponent(authorization.authorization_code)}&state=${encodeURIComponent(authorization.state)}`
    );
  }, [mobileState]);

  const openMobileCallback = useCallback(() => {
    if (!mobileCallbackURL || mobileCallbackOpened.current) {
      return;
    }
    mobileCallbackOpened.current = true;
    openMobileAuthorizationCallback(mobileCallbackURL);
  }, [mobileCallbackURL]);

  useEffect(() => {
    document.title = mobileCallbackURL ? "Voltar para o app - Rentivo" : "Entrar - Rentivo";
  }, [mobileCallbackURL]);

  useEffect(() => {
    if (error) {
      emailRef.current?.focus();
    }
  }, [error]);

  useEffect(() => {
    if (!mobileState && auth.status === "authenticated" && auth.bootstrap) {
      navigate(postLoginPath(auth.bootstrap), { replace: true });
    }
  }, [auth.bootstrap, auth.status, mobileState, navigate]);

  useEffect(() => {
    if (!mobileState || auth.status !== "authenticated" || mobileAuthorizationStarted.current) {
      return;
    }
    mobileAuthorizationStarted.current = true;
    void completeMobileAuthorization().catch(() => {
      setError("Não foi possível concluir a autorização no aplicativo. Tente novamente.");
    });
  }, [auth.status, completeMobileAuthorization, mobileState]);

  useEffect(() => {
    if (!mobileCallbackURL) {
      return;
    }
    const timer = window.setTimeout(openMobileCallback, 1_000);
    return () => window.clearTimeout(timer);
  }, [mobileCallbackURL, openMobileCallback]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    const payload: LoginRequest = {
      credential_transport: "cookie",
      email: email.trim(),
      password,
      turnstile_token: turnstileToken
    };
    try {
      const { data } = await apiRequest(
        apiClient.POST("/api/v1/auth/login", { body: payload })
      );
      if (data.status === "mfa_required") {
        saveMfaChallenge({ challengeId: data.challenge_id, methods: data.methods });
        navigate(`/mfa-verify?challenge=${encodeURIComponent(data.challenge_id)}`);
        return;
      }
      if (mobileState) {
        await completeMobileAuthorization();
        return;
      }
      auth.authenticate(data);
      navigate(postLoginPath(data.bootstrap));
    } catch (caught: unknown) {
      if (caught instanceof ApiError) {
        pushAnalyticsFromResponse(caught.response);
        setError(caught.message);
      } else {
        setError("Não foi possível concluir a solicitação. Tente novamente.");
      }
      turnstileRef.current?.reset();
    } finally {
      setLoading(false);
    }
  }

  if (mobileCallbackURL) {
    return <MobileAuthorizationStatus onReturnToApp={openMobileCallback} />;
  }

  return (
    <AuthConfigGate>
      {(config) => (
        <div className="login-wrap">
          <div className="panel">
            <div className="panel__body" style={{ padding: "2.25rem" }}>
              <LoginAuthHeader />
              {flash ? (
                <div className="toast toast--success" role="status">
                  {flash}
                </div>
              ) : null}
              <AuthError message={error} />
              <form onSubmit={handleSubmit}>
                <div className="field">
                  <label className="field__label" htmlFor="email">
                    E-mail
                  </label>
                  <input
                    autoFocus
                    className="input"
                    id="email"
                    name="email"
                    onChange={(event) => setEmail(event.target.value)}
                    ref={emailRef}
                    required
                    type="email"
                    value={email}
                  />
                </div>
                <div className="field">
                  <label className="field__label" htmlFor="password">
                    Senha
                  </label>
                  <input
                    className="input"
                    id="password"
                    name="password"
                    onChange={(event) => setPassword(event.target.value)}
                    required
                    type="password"
                    value={password}
                  />
                </div>
                <p style={{ fontSize: "0.85rem", margin: "-0.4rem 0 1rem", textAlign: "right" }}>
                  <Link to="/forgot-password">Esqueceu sua senha?</Link>
                </p>
                <Turnstile
                  enabled={config.feature_flags.turnstile}
                  onToken={setTurnstileToken}
                  ref={turnstileRef}
                  siteKey={config.feature_flags.turnstile_site_key}
                />
                <SubmitButton
                  className="btn btn--primary btn--block btn--lg"
                  loading={loading}
                >
                  Entrar
                </SubmitButton>
              </form>
              {config.feature_flags.google_auth ? (
                <>
                  <div style={{ alignItems: "center", display: "flex", gap: "0.75rem", margin: "1.25rem 0" }}>
                    <hr style={{ border: "none", borderTop: "1px solid var(--border, #ddd)", flex: 1, margin: 0 }} />
                    <span className="muted" style={{ fontSize: "0.85rem" }}>
                      ou
                    </span>
                    <hr style={{ border: "none", borderTop: "1px solid var(--border, #ddd)", flex: 1, margin: 0 }} />
                  </div>
                  <GoogleAuthLink />
                </>
              ) : null}
              <p className="muted" style={{ fontSize: "0.88rem", margin: "1.25rem 0 0", textAlign: "center" }}>
                Não tem conta? <Link to="/signup">Criar conta</Link>
              </p>
            </div>
          </div>
        </div>
      )}
    </AuthConfigGate>
  );
}

function MobileAuthorizationStatus({ onReturnToApp }: { onReturnToApp: () => void }) {
  return (
    <div className="login-wrap">
      <div className="panel">
        <div className="panel__body" style={{ padding: "2.25rem", textAlign: "center" }}>
          <LoginAuthHeader />
          <div aria-hidden="true" className="auth-mark" style={{ margin: "0 auto 1rem" }}>✓</div>
          <h2 style={{ fontSize: "1.5rem", margin: 0 }}>Tudo pronto</h2>
          <p className="muted" style={{ margin: "0.75rem 0 1.5rem" }}>
            Você já pode continuar no app Rentivo. Esta página vai voltar ao aplicativo automaticamente.
          </p>
          <button className="btn btn--primary btn--block btn--lg" onClick={onReturnToApp} type="button">
            Voltar para o app agora
          </button>
        </div>
      </div>
    </div>
  );
}

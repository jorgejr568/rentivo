import { useEffect, useRef, useState, type FormEvent } from "react";
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
import { Turnstile, type TurnstileHandle } from "./Turnstile";

type LoginRequest = components["schemas"]["LoginRequest"];

const GOOGLE_ERROR = "Não foi possível entrar com o Google. Tente novamente.";

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [error, setError] = useState<string | null>(() =>
    searchParams.get("error") === "google_auth_failed" ? GOOGLE_ERROR : null
  );
  const [flash] = useState(takeAuthFlash);
  const [loading, setLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const turnstileRef = useRef<TurnstileHandle>(null);

  useEffect(() => {
    document.title = "Entrar - Rentivo";
  }, []);

  useEffect(() => {
    if (error) {
      emailRef.current?.focus();
    }
  }, [error]);

  useEffect(() => {
    if (auth.status === "authenticated" && auth.bootstrap) {
      navigate(postLoginPath(auth.bootstrap), { replace: true });
    }
  }, [auth.bootstrap, auth.status, navigate]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    const payload: LoginRequest = {
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

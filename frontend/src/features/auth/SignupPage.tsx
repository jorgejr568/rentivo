import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import {
  AuthConfigGate,
  AuthError,
  GoogleAuthLink,
  RentivoTitle,
  StandardAuthPanel,
  SubmitButton
} from "./AuthComponents";
import { postLoginPath, useAuth } from "./AuthProvider";
import { Turnstile, type TurnstileHandle } from "./Turnstile";

type SignupRequest = components["schemas"]["SignupRequest"];

export function SignupPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const turnstileRef = useRef<TurnstileHandle>(null);

  useEffect(() => {
    document.title = "Criar Conta - Rentivo";
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
    if (password !== confirmPassword) {
      setError("As senhas não coincidem.");
      return;
    }

    setLoading(true);
    const payload: SignupRequest = {
      confirm_password: confirmPassword,
      email: email.trim(),
      password,
      turnstile_token: turnstileToken
    };
    try {
      const { data } = await apiRequest(
        apiClient.POST("/api/v1/auth/signup", { body: payload })
      );
      auth.authenticate(data);
      navigate(postLoginPath(data.bootstrap));
    } catch (caught: unknown) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível concluir a solicitação. Tente novamente."
      );
      turnstileRef.current?.reset();
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthConfigGate>
      {(config) => (
        <StandardAuthPanel>
          <RentivoTitle />
          <AuthError message={error} />
          <form onSubmit={handleSubmit}>
            <div className="field">
              <label className="field-label" htmlFor="signup-email">
                E-mail
              </label>
              <input
                autoFocus
                className="field-input"
                id="signup-email"
                name="email"
                onChange={(event) => setEmail(event.target.value)}
                ref={emailRef}
                required
                type="email"
                value={email}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="signup-password">
                Senha
              </label>
              <input
                className="field-input"
                id="signup-password"
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="confirm-password">
                Confirmar Senha
              </label>
              <input
                className="field-input"
                id="confirm-password"
                name="confirm_password"
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
                type="password"
                value={confirmPassword}
              />
            </div>
            <Turnstile
              enabled={config.feature_flags.turnstile}
              onToken={setTurnstileToken}
              ref={turnstileRef}
              siteKey={config.feature_flags.turnstile_site_key}
            />
            <SubmitButton
              loading={loading}
              style={{ marginTop: "0.5rem", width: "100%" }}
            >
              Criar Conta
            </SubmitButton>
          </form>
          {config.feature_flags.google_auth ? (
            <>
              <div
                style={{
                  alignItems: "center",
                  display: "flex",
                  gap: "0.75rem",
                  margin: "1.25rem 0"
                }}
              >
                <hr
                  style={{
                    border: "none",
                    borderTop: "1px solid var(--border, #ddd)",
                    flex: 1,
                    margin: 0
                  }}
                />
                <span className="muted" style={{ fontSize: "0.85rem" }}>
                  ou
                </span>
                <hr
                  style={{
                    border: "none",
                    borderTop: "1px solid var(--border, #ddd)",
                    flex: 1,
                    margin: 0
                  }}
                />
              </div>
              <GoogleAuthLink />
            </>
          ) : null}
          <p style={{ marginTop: "1rem", textAlign: "center" }}>
            Já tem conta? <Link to="/login">Entrar</Link>
          </p>
        </StandardAuthPanel>
      )}
    </AuthConfigGate>
  );
}

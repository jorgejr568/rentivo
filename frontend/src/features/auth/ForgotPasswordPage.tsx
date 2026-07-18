import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import {
  AuthConfigGate,
  AuthError,
  RentivoTitle,
  StandardAuthPanel,
  SubmitButton
} from "./AuthComponents";
import { postLoginPath, useAuth } from "./AuthProvider";
import { pushAnalyticsEvent } from "./analytics";
import { Turnstile, type TurnstileHandle } from "./Turnstile";

type PasswordForgotRequest = components["schemas"]["PasswordForgotRequest"];

export function ForgotPasswordPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const turnstileRef = useRef<TurnstileHandle>(null);

  useEffect(() => {
    document.title = "Esqueci minha senha - Rentivo";
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
    const payload: PasswordForgotRequest = {
      email: email.trim().toLowerCase(),
      turnstile_token: turnstileToken
    };
    try {
      const { data } = await apiRequest(
        apiClient.POST("/api/v1/auth/password/forgot", { body: payload })
      );
      data.analytics_events.forEach((analyticsEvent) =>
        pushAnalyticsEvent({ ...analyticsEvent })
      );
      setSent(true);
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
          <p>
            Informe o e-mail da sua conta. Se ele estiver cadastrado, enviaremos um link para
            redefinir a senha.
          </p>
          {sent ? (
            <div className="toast toast--success" role="status">
              Se o e-mail estiver cadastrado, em instantes você receberá uma mensagem com
              instruções.
            </div>
          ) : (
            <>
              <AuthError message={error} />
              <form onSubmit={handleSubmit}>
                <div className="field">
                  <label className="field-label" htmlFor="forgot-email">
                    E-mail
                  </label>
                  <input
                    autoFocus
                    className="field-input"
                    id="forgot-email"
                    name="email"
                    onChange={(event) => setEmail(event.target.value)}
                    ref={emailRef}
                    required
                    type="email"
                    value={email}
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
                  Enviar link
                </SubmitButton>
              </form>
            </>
          )}
          <p style={{ marginTop: "1rem", textAlign: "center" }}>
            <Link to="/login">Voltar para o login</Link>
          </p>
        </StandardAuthPanel>
      )}
    </AuthConfigGate>
  );
}

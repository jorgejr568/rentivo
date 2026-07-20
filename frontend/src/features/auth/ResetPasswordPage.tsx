import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import {
  AuthError,
  RentivoTitle,
  StandardAuthPanel,
  SubmitButton
} from "./AuthComponents";
import { pushAnalyticsFromResponse } from "./analytics";
import { setAuthFlash } from "./authStorage";

type PasswordResetRequest = components["schemas"]["PasswordResetRequest"];

const INVALID_LINK = "Link inválido ou expirado. Solicite uma nova redefinição.";
const RESET_SUCCESS = "Senha redefinida com sucesso. Faça login com a nova senha.";

export function ResetPasswordPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(!token);
  const [loading, setLoading] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = "Redefinir senha - Rentivo";
  }, []);

  useEffect(() => {
    if (error) {
      passwordRef.current?.focus();
    }
  }, [error]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("As senhas não coincidem.");
      return;
    }

    setLoading(true);
    const payload: PasswordResetRequest = {
      confirm_password: confirmPassword,
      password,
      token
    };
    try {
      const { response } = await apiRequest(
        apiClient.POST("/api/v1/auth/password/reset", { body: payload })
      );
      pushAnalyticsFromResponse(response);
      setAuthFlash(RESET_SUCCESS);
      navigate("/login", { replace: true });
    } catch (caught: unknown) {
      if (caught instanceof ApiError && caught.code === "invalid_or_expired_reset_token") {
        setInvalid(true);
      } else {
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível concluir a solicitação. Tente novamente."
        );
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <StandardAuthPanel>
      <RentivoTitle />
      {invalid ? (
        <>
          <div className="toast toast--error" role="alert">
            {INVALID_LINK}
          </div>
          <p style={{ marginTop: "1rem", textAlign: "center" }}>
            <Link to="/forgot-password">Pedir novo link</Link>
          </p>
        </>
      ) : (
        <>
          <AuthError message={error} />
          <form onSubmit={handleSubmit}>
            <div className="field">
              <label className="field-label" htmlFor="new-password">
                Nova senha
              </label>
              <input
                autoFocus
                className="field-input"
                id="new-password"
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                ref={passwordRef}
                required
                type="password"
                value={password}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="confirm-new-password">
                Confirmar nova senha
              </label>
              <input
                className="field-input"
                id="confirm-new-password"
                name="confirm_password"
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
                type="password"
                value={confirmPassword}
              />
            </div>
            <SubmitButton
              loading={loading}
              style={{ marginTop: "0.5rem", width: "100%" }}
            >
              Redefinir senha
            </SubmitButton>
          </form>
        </>
      )}
    </StandardAuthPanel>
  );
}

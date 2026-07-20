import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { AuthError, StandardAuthPanel, SubmitButton } from "./AuthComponents";
import { postLoginPath, useAuth } from "./AuthProvider";
import { pushAnalyticsEvent, pushAnalyticsFromResponse } from "./analytics";
import { loadMfaChallenge } from "./authStorage";
import { authenticateWithPasskey } from "./webauthn";

type AuthenticatedResponse = components["schemas"]["AuthenticatedResponse"];
type MfaCodeVerifyRequest = components["schemas"]["MFACodeVerifyRequest"];
type PasskeyAuthBeginRequest = components["schemas"]["PasskeyAuthBeginRequest"];
type PasskeyAuthCompleteRequest = components["schemas"]["PasskeyAuthCompleteRequest"];
type VerificationMethod = "passkey" | "recovery" | "totp";

const INVALID_CODE = "Código inválido. Tente novamente.";
const RATE_LIMITED = "Muitas tentativas. Aguarde alguns minutos.";
const PASSKEY_ERROR = "Erro na autenticação com passkey. Tente novamente.";

export function MfaVerifyPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const challengeId = searchParams.get("challenge") ?? "";
  const [challenge] = useState(() => loadMfaChallenge(challengeId));
  const [code, setCode] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loadingMethod, setLoadingMethod] = useState<VerificationMethod | null>(null);
  const [focusMethod, setFocusMethod] = useState<VerificationMethod>("totp");
  const codeRef = useRef<HTMLInputElement>(null);
  const recoveryRef = useRef<HTMLInputElement>(null);
  const passkeyRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    document.title = "Verificação MFA - Rentivo";
  }, []);

  useEffect(() => {
    if (!challenge) {
      navigate("/login", { replace: true });
    }
  }, [challenge, navigate]);

  useEffect(() => {
    if (!error) {
      return;
    }
    if (focusMethod === "recovery") {
      recoveryRef.current?.focus();
    } else if (focusMethod === "passkey") {
      passkeyRef.current?.focus();
    } else {
      codeRef.current?.focus();
    }
  }, [error, focusMethod]);

  if (!challenge) {
    return null;
  }

  const activeChallenge = challenge;
  const methods = new Set(activeChallenge.methods);

  function completeAuthentication(response: AuthenticatedResponse) {
    auth.authenticate(response);
    navigate(postLoginPath(response.bootstrap));
  }

  function handleVerificationError(caught: unknown, method: VerificationMethod) {
    setFocusMethod(method);
    if (caught instanceof ApiError) {
      pushAnalyticsFromResponse(caught.response);
      if (caught.code === "invalid_mfa_code") {
        pushAnalyticsEvent({ event: "rentivo_mfa_verify_failed" });
        setError(INVALID_CODE);
      } else if (caught.code === "mfa_rate_limited") {
        setError(RATE_LIMITED);
      } else {
        setError(caught.message);
      }
      return;
    }
    setError("Não foi possível concluir a solicitação. Tente novamente.");
  }

  async function verifyCode(
    event: FormEvent<HTMLFormElement>,
    method: "recovery" | "totp"
  ) {
    event.preventDefault();
    setError(null);
    setLoadingMethod(method);
    const payload: MfaCodeVerifyRequest = {
      challenge_id: activeChallenge.challengeId,
      code: (method === "recovery" ? recoveryCode : code).trim(),
      credential_transport: "cookie"
    };
    try {
      const request = method === "recovery"
        ? apiClient.POST("/api/v1/auth/mfa/recovery/verify", { body: payload })
        : apiClient.POST("/api/v1/auth/mfa/totp/verify", { body: payload });
      const { data, response } = await apiRequest(
        request
      );
      pushAnalyticsFromResponse(response);
      completeAuthentication(data);
    } catch (caught: unknown) {
      handleVerificationError(caught, method);
    } finally {
      setLoadingMethod(null);
    }
  }

  async function verifyPasskey() {
    setError(null);
    setLoadingMethod("passkey");
    try {
      const beginPayload: PasskeyAuthBeginRequest = {
        challenge_id: activeChallenge.challengeId,
        credential_transport: "cookie"
      };
      const { data: options } = await apiRequest(
        apiClient.POST("/api/v1/auth/mfa/passkeys/begin", { body: beginPayload })
      );
      const credential = await authenticateWithPasskey(options);
      if (!credential) {
        return;
      }
      const completePayload: PasskeyAuthCompleteRequest = {
        challenge_id: activeChallenge.challengeId,
        credential,
        credential_transport: "cookie"
      };
      const { data, response } = await apiRequest(
        apiClient.POST("/api/v1/auth/mfa/passkeys/complete", { body: completePayload })
      );
      pushAnalyticsFromResponse(response);
      completeAuthentication(data);
    } catch (caught: unknown) {
      if (caught instanceof Error && caught.name === "NotAllowedError") {
        return;
      }
      if (caught instanceof ApiError) {
        handleVerificationError(caught, "passkey");
      } else {
        setFocusMethod("passkey");
        setError(PASSKEY_ERROR);
      }
    } finally {
      setLoadingMethod(null);
    }
  }

  return (
    <StandardAuthPanel>
      <h2 className="login-title">Verificação MFA</h2>
      <p className="text-muted" style={{ marginBottom: "1.5rem" }}>
        Digite o código do seu aplicativo autenticador.
      </p>

      <AuthError message={error} />

      {methods.has("totp") ? (
        <form id="totp-form" onSubmit={(event) => void verifyCode(event, "totp")}>
          <div className="field">
            <label className="field-label" htmlFor="code">
              Código de autenticação
            </label>
            <input
              autoComplete="one-time-code"
              autoFocus
              className="field-input"
              id="code"
              inputMode="numeric"
              maxLength={8}
              name="code"
              onChange={(event) => setCode(event.target.value)}
              placeholder="000000"
              ref={codeRef}
              required
              type="text"
              value={code}
            />
          </div>
          <SubmitButton
            disabled={loadingMethod !== null}
            loading={loadingMethod === "totp"}
            style={{ width: "100%" }}
          >
            Verificar
          </SubmitButton>
        </form>
      ) : null}

      {methods.has("passkey") ? (
        <>
          {methods.has("totp") ? (
            <hr style={{ borderColor: "var(--ink-10)", margin: "1.5rem 0" }} />
          ) : null}
          <button
            aria-busy={loadingMethod === "passkey"}
            className="btn"
            disabled={loadingMethod !== null}
            onClick={() => void verifyPasskey()}
            ref={passkeyRef}
            style={{ width: "100%" }}
            type="button"
          >
            Usar Passkey
          </button>
        </>
      ) : null}

      {methods.has("recovery") ? (
        <details style={{ marginTop: "1.5rem" }}>
          <summary style={{ color: "var(--ink-50)", cursor: "pointer", fontSize: "0.9rem" }}>
            Usar código de recuperação
          </summary>
          <form
            onSubmit={(event) => void verifyCode(event, "recovery")}
            style={{ marginTop: "0.75rem" }}
          >
            <div className="field">
              <label className="field-label" htmlFor="recovery-code">
                Código de recuperação
              </label>
              <input
                className="field-input"
                id="recovery-code"
                name="code"
                onChange={(event) => setRecoveryCode(event.target.value)}
                placeholder="Código de recuperação"
                ref={recoveryRef}
                required
                type="text"
                value={recoveryCode}
              />
            </div>
            <SubmitButton
              className="btn btn--sm"
              disabled={loadingMethod !== null}
              loading={loadingMethod === "recovery"}
              style={{ width: "100%" }}
            >
              Verificar com código de recuperação
            </SubmitButton>
          </form>
        </details>
      ) : null}
    </StandardAuthPanel>
  );
}

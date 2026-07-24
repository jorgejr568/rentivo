import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { ApiKeySection } from "../apiKeys/ApiKeySection";
import { SubmitButton } from "../auth/AuthComponents";
import { useAuth } from "../auth/AuthProvider";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import { PasskeyManager } from "./PasskeyManager";
import { createPasskey } from "./webauthn";

type SecuritySummary = components["schemas"]["SecuritySummaryResponse"];

function messageFor(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function SecurityPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<SecuritySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [savingPix, setSavingPix] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [disablingTotp, setDisablingTotp] = useState(false);
  const [showDisableTotp, setShowDisableTotp] = useState(false);
  const [showDeleteAccount, setShowDeleteAccount] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [pixKey, setPixKey] = useState("");
  const [pixName, setPixName] = useState("");
  const [pixCity, setPixCity] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [disablePassword, setDisablePassword] = useState("");
  const actionRef = useRef<HTMLElement | null>(null);
  const pixRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const recoveryRef = useRef<HTMLButtonElement>(null);
  const disableTotpRef = useRef<HTMLInputElement>(null);
  const deleteAccountRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const { data } = await apiRequest(apiClient.GET("/api/v1/security"));
      setSummary(data);
      setPixKey(data.profile.pix_key);
      setPixName(data.profile.pix_merchant_name);
      setPixCity(data.profile.pix_merchant_city);
    } catch (caught: unknown) {
      setLoadError(messageFor(caught, "Não foi possível carregar as configurações de segurança."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { document.title = "Segurança - Rentivo"; void load(); }, [load]);
  useEffect(() => { if (actionError) actionRef.current?.focus(); }, [actionError]);

  function startAction(focusTarget: HTMLElement | null = null) {
    actionRef.current = focusTarget;
    setActionError(null);
    setMessage(null);
  }

  async function updatePix(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    startAction(pixRef.current);
    setSavingPix(true);
    try {
      const { data } = await apiRequest(
        apiClient.POST("/api/v1/security/pix", {
          body: {
            pix_key: pixKey.trim(),
            pix_merchant_city: pixCity.trim(),
            pix_merchant_name: pixName.trim()
          }
        })
      );
      setSummary((value) => ({ ...value!, profile: data.profile }));
      setMessage("Dados do PIX atualizados.");
    } catch (caught: unknown) {
      setActionError(messageFor(caught, "Não foi possível atualizar os dados do PIX."));
    } finally {
      setSavingPix(false);
    }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    startAction(passwordRef.current);
    if (newPassword !== confirmPassword) {
      setActionError("As senhas não coincidem.");
      return;
    }
    setChangingPassword(true);
    try {
      const { response } = await apiRequest(
        apiClient.POST("/api/v1/security/change-password", {
          body: {
            confirm_password: confirmPassword,
            current_password: currentPassword,
            new_password: newPassword
          }
        })
      );
      pushAnalyticsFromResponse(response);
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setMessage("Senha alterada com sucesso!");
    } catch (caught: unknown) {
      setActionError(messageFor(caught, "Não foi possível alterar a senha."));
    } finally {
      setChangingPassword(false);
    }
  }

  async function regenerateRecoveryCodes() {
    startAction(recoveryRef.current);
    try {
      const { data, response } = await apiRequest(
        apiClient.POST("/api/v1/security/recovery-codes/regenerate")
      );
      pushAnalyticsFromResponse(response);
      navigate("/security/recovery-codes", { state: { recoveryCodes: data.recovery_codes } });
    } catch (caught: unknown) {
      setActionError(messageFor(caught, "Não foi possível regenerar os códigos de recuperação."));
    }
  }

  async function disableTotp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    startAction(disableTotpRef.current);
    setDisablingTotp(true);
    try {
      const { response } = await apiRequest(
        apiClient.POST("/api/v1/security/totp/disable", {
          body: { password: disablePassword }
        })
      );
      pushAnalyticsFromResponse(response);
      await logout().catch(() => undefined);
    } catch (caught: unknown) {
      setActionError(messageFor(caught, "Não foi possível desativar o TOTP."));
    } finally {
      setDisablingTotp(false);
    }
  }

  async function deleteAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    startAction(deleteAccountRef.current);
    setDeletingAccount(true);
    try {
      const { response } = await apiRequest(
        apiClient.POST("/api/v1/security/delete-account", {
          body: { password: deletePassword }
        })
      );
      pushAnalyticsFromResponse(response);
      await logout().catch(() => undefined);
    } catch (caught: unknown) {
      setActionError(messageFor(caught, "Não foi possível excluir a conta."));
    } finally {
      setDeletingAccount(false);
    }
  }

  async function registerPasskey(name: string) {
    startAction();
    const { data: begin } = await apiRequest(
      apiClient.POST("/api/v1/security/passkeys/register/begin")
    );
    const credential = await createPasskey(begin.options);
    if (!credential) throw new DOMException("Operação cancelada.", "NotAllowedError");
    const { data, response } = await apiRequest(
      apiClient.POST("/api/v1/security/passkeys/register/complete", {
        body: { challenge_id: begin.challenge_id, credential, name }
      })
    );
    pushAnalyticsFromResponse(response);
    setSummary((value) => ({ ...value!, passkeys: [...value!.passkeys, data] }));
    setMessage("Passkey cadastrada.");
  }

  async function deletePasskey(uuid: string) {
    startAction();
    const { response } = await apiRequest(
      apiClient.DELETE("/api/v1/security/passkeys/{passkey_uuid}", {
        params: { path: { passkey_uuid: uuid } }
      })
    );
    pushAnalyticsFromResponse(response);
  }

  if (loading) return <p role="status">Carregando...</p>;
  if (!summary) return <><div className="toast toast--danger" role="alert">{loadError}</div><button className="btn btn--primary" onClick={() => void load()} type="button">Tentar novamente</button></>;

  const pixIncomplete = !summary.profile.pix_key || !summary.profile.pix_merchant_name || !summary.profile.pix_merchant_city;
  return (
    <>
      <div className="page-header"><div className="page-header-info"><h2 className="page-title">Segurança</h2><p className="page-subtitle">Gerencie sua senha e configurações de autenticação multifator.</p></div></div>
      {summary.mfa.setup_required ? <div className="mfa-enforcement-banner">Sua organização exige autenticação multifator. Configure o TOTP ou uma passkey para continuar.</div> : null}
      {actionError ? <div className="toast toast--danger" role="alert">{actionError}</div> : null}
      {message ? <div className="toast toast--success" role="status">{message}</div> : null}
      <div className="panel"><div className="panel-head"><h5>Dados do PIX</h5></div><div className="panel-body">
        <p className="field-hint mb-1">Estes dados são usados para gerar o QR Code nas faturas das suas cobranças pessoais. Todos os três campos são obrigatórios para gerar faturas.</p>
        {pixIncomplete ? <div className="toast toast--warning" role="alert">Preencha todos os campos abaixo para poder gerar faturas das cobranças pessoais.</div> : null}
        <form onSubmit={(event) => void updatePix(event)}>
          <div className="field"><label className="field-label" htmlFor="pix_key">Chave PIX</label><input className="field-input" id="pix_key" onChange={(event) => setPixKey(event.target.value)} ref={pixRef} style={{ maxWidth: "350px" }} value={pixKey} /><span className="field-hint">Para celular, inclua +55 (caso contrário 11 dígitos são tratados como CPF).</span></div>
          <div className="field"><label className="field-label" htmlFor="pix_merchant_name">Nome do recebedor</label><input className="field-input" id="pix_merchant_name" maxLength={25} onChange={(event) => setPixName(event.target.value)} style={{ maxWidth: "350px" }} value={pixName} /><span className="field-hint">Até 25 caracteres.</span></div>
          <div className="field"><label className="field-label" htmlFor="pix_merchant_city">Cidade do recebedor</label><input className="field-input" id="pix_merchant_city" maxLength={15} onChange={(event) => setPixCity(event.target.value)} style={{ maxWidth: "350px" }} value={pixCity} /><span className="field-hint">Até 15 caracteres, sem acentos.</span></div>
          <SubmitButton className="btn btn--primary btn--sm" loading={savingPix}>Salvar Dados PIX</SubmitButton>
        </form>
      </div></div>
      <div className="panel"><div className="panel-head"><h5>Alterar Senha</h5></div><div className="panel-body"><form onSubmit={(event) => void changePassword(event)}>
        <div className="field"><label className="field-label" htmlFor="current_password">Senha atual</label><input className="field-input" id="current_password" onChange={(event) => setCurrentPassword(event.target.value)} ref={passwordRef} required style={{ maxWidth: "350px" }} type="password" value={currentPassword} /></div>
        <div className="field"><label className="field-label" htmlFor="new_password">Nova senha</label><input className="field-input" id="new_password" onChange={(event) => setNewPassword(event.target.value)} required style={{ maxWidth: "350px" }} type="password" value={newPassword} /></div>
        <div className="field"><label className="field-label" htmlFor="confirm_password">Confirmar nova senha</label><input className="field-input" id="confirm_password" onChange={(event) => setConfirmPassword(event.target.value)} required style={{ maxWidth: "350px" }} type="password" value={confirmPassword} /></div>
        <SubmitButton className="btn btn--primary btn--sm" loading={changingPassword}>Alterar Senha</SubmitButton>
      </form></div></div>
      <div className="panel"><div className="panel-head"><h5>Autenticação por Aplicativo (TOTP)</h5></div><div className="panel-body">
        {summary.totp.enabled ? <><p>TOTP está <strong style={{ color: "var(--emerald)" }}>ativado</strong>.</p><p style={{ marginTop: "0.5rem" }}>Códigos de recuperação restantes: <strong>{summary.totp.recovery_codes_remaining}</strong>{summary.totp.recovery_codes_remaining < 3 ? <span style={{ color: "var(--danger)", fontWeight: 600 }}> — Recomendamos regenerar seus códigos.</span> : null}</p><div className="btn-row" style={{ marginTop: "1rem" }}><button className="btn btn--sm" onClick={() => void regenerateRecoveryCodes()} ref={recoveryRef} type="button">Regenerar Códigos de Recuperação</button>{!showDisableTotp ? <button className="btn btn--sm btn--danger" onClick={() => setShowDisableTotp(true)} type="button">Desativar TOTP</button> : null}</div>{showDisableTotp ? <div style={{ marginTop: "1rem" }}><form onSubmit={(event) => void disableTotp(event)}><div className="field"><label className="field-label" htmlFor="disable-totp-password">Confirme sua senha para desativar</label><input className="field-input" id="disable-totp-password" onChange={(event) => setDisablePassword(event.target.value)} ref={disableTotpRef} required type="password" value={disablePassword} /></div><SubmitButton className="btn btn--danger btn--sm" loading={disablingTotp}>Confirmar Desativação</SubmitButton></form></div> : null}</> : <><p>TOTP não está configurado.</p><Link className="btn btn--primary" style={{ marginTop: "0.75rem" }} to="/security/totp/setup">Configurar TOTP</Link></>}
      </div></div>
      <PasskeyManager onDelete={deletePasskey} onRegister={registerPasskey} onSessionRevoked={() => { void logout().catch(() => undefined); }} organizationEnforced={summary.mfa.organization_enforced} passkeys={summary.passkeys} />
      <ApiKeySection />
      <div className="panel">
        <div className="panel-head"><h5>Excluir conta</h5></div>
        <div className="panel-body">
          <p>A exclusão é permanente: suas cobranças são removidas e seus dados pessoais são apagados. Registros exigidos por lei podem ser retidos conforme a <Link to="/privacy">Política de Privacidade</Link>. Se você entra apenas com o Google, defina uma senha antes em Esqueci minha senha.</p>
          {!showDeleteAccount ? <button className="btn btn--sm btn--danger" onClick={() => setShowDeleteAccount(true)} type="button">Excluir conta</button> : null}
          {showDeleteAccount ? <form onSubmit={(event) => void deleteAccount(event)}>
            <div className="field"><label className="field-label" htmlFor="delete-account-password">Confirme sua senha para excluir a conta</label><input className="field-input" id="delete-account-password" onChange={(event) => setDeletePassword(event.target.value)} ref={deleteAccountRef} required type="password" value={deletePassword} /></div>
            <SubmitButton className="btn btn--danger btn--sm" loading={deletingAccount}>Excluir minha conta permanentemente</SubmitButton>
          </form> : null}
        </div>
      </div>
    </>
  );
}

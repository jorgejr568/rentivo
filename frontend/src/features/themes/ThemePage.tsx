import { ArrowLeft, Eye, RotateCcw, Save } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent
} from "react";
import { Link, useParams } from "react-router-dom";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { FieldError } from "../../components/FieldError";
import { LoadError, LoadingState } from "../../components/PageState";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { pushAnalyticsFromResponse } from "../auth/analytics";

type ThemeResponse = components["schemas"]["ThemeResponse"];
type ThemeValues = components["schemas"]["ThemeUpdateRequest"];
type ThemeTarget = "billing" | "organization" | "user";
type ColorKey = keyof Pick<
  ThemeValues,
  "primary" | "primary_light" | "secondary" | "secondary_dark" | "text_color" | "text_contrast"
>;

export interface ThemePageProps {
  backUrl?: string;
  ownerLabel?: string;
  target: ThemeTarget;
  targetUuid?: string;
}

const SOURCE_LABELS: Record<ThemeResponse["effective_source"], string> = {
  billing: "desta cobrança",
  default: "padrão do sistema",
  organization: "da organização",
  user: "do usuário"
};

const TARGET_META: Record<ThemeTarget, {
  backPrefix: string;
  missing: string;
  resetSuccess: string;
  saveSuccess: string;
  title: string;
}> = {
  billing: {
    backPrefix: "/billings/",
    missing: "Não foi possível identificar a cobrança.",
    resetSuccess: "Tema da cobrança redefinido para o padrão.",
    saveSuccess: "Tema da cobrança salvo com sucesso!",
    title: "Tema da cobrança"
  },
  organization: {
    backPrefix: "/organizations/",
    missing: "Não foi possível identificar a organização.",
    resetSuccess: "Tema da organização redefinido para o padrão.",
    saveSuccess: "Tema da organização salvo com sucesso!",
    title: "Tema da organização"
  },
  user: {
    backPrefix: "/billings/",
    missing: "",
    resetSuccess: "Tema redefinido para o padrão.",
    saveSuccess: "Tema salvo com sucesso!",
    title: "Meu Tema"
  }
};

const COLOR_FIELDS: Array<{ key: ColorKey; label: string }> = [
  { key: "primary", label: "Primária" },
  { key: "primary_light", label: "Primária Clara" },
  { key: "secondary", label: "Secundária" },
  { key: "secondary_dark", label: "Secundária Escura" },
  { key: "text_color", label: "Texto" },
  { key: "text_contrast", label: "Contraste" }
];

const INITIAL_VALUES: ThemeValues = {
  header_font: "Montserrat",
  primary: "#8A4C94",
  primary_light: "#EEE4F1",
  secondary: "#6EAFAE",
  secondary_dark: "#357B7C",
  text_color: "#282830",
  text_contrast: "#FFFFFF",
  text_font: "Montserrat"
};

const SECTION_HEADING_STYLE = {
  fontSize: "0.98rem",
  margin: 0,
  whiteSpace: "nowrap"
} as const;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function normalizeFieldErrors(fields: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(fields).map(([key, message]) => [key.replace(/^body\./, ""), message])
  );
}

function fieldErrorId(fields: Record<string, string>, key: string): string | undefined {
  return fields[key] ? `${key}-error` : undefined;
}

async function getTheme(target: ThemeTarget, uuid: string, signal: AbortSignal) {
  if (target === "organization") {
    return apiRequest(apiClient.GET("/api/v1/themes/organizations/{org_uuid}", {
      params: { path: { org_uuid: uuid } },
      signal
    }));
  }
  if (target === "billing") {
    return apiRequest(apiClient.GET("/api/v1/themes/billings/{billing_uuid}", {
      params: { path: { billing_uuid: uuid } },
      signal
    }));
  }
  return apiRequest(apiClient.GET("/api/v1/themes/user", { signal }));
}

async function putTheme(
  target: ThemeTarget,
  uuid: string,
  body: ThemeValues,
  signal: AbortSignal
) {
  if (target === "organization") {
    return apiRequest(apiClient.PUT("/api/v1/themes/organizations/{org_uuid}", {
      body,
      params: { path: { org_uuid: uuid } },
      signal
    }));
  }
  if (target === "billing") {
    return apiRequest(apiClient.PUT("/api/v1/themes/billings/{billing_uuid}", {
      body,
      params: { path: { billing_uuid: uuid } },
      signal
    }));
  }
  return apiRequest(apiClient.PUT("/api/v1/themes/user", { body, signal }));
}

async function deleteTheme(target: ThemeTarget, uuid: string, signal: AbortSignal) {
  if (target === "organization") {
    return apiRequest(apiClient.DELETE("/api/v1/themes/organizations/{org_uuid}", {
      params: { path: { org_uuid: uuid } },
      signal
    }));
  }
  if (target === "billing") {
    return apiRequest(apiClient.DELETE("/api/v1/themes/billings/{billing_uuid}", {
      params: { path: { billing_uuid: uuid } },
      signal
    }));
  }
  return apiRequest(apiClient.DELETE("/api/v1/themes/user", { signal }));
}

export function ThemePage({ backUrl, ownerLabel, target, targetUuid }: ThemePageProps) {
  const { billingUuid, orgUuid } = useParams<{ billingUuid?: string; orgUuid?: string }>();
  const routeUuid = target === "organization"
    ? orgUuid ?? ""
    : target === "billing"
      ? billingUuid ?? ""
      : "";
  const uuid = targetUuid ?? routeUuid;
  const meta = TARGET_META[target];
  const [theme, setTheme] = useState<ThemeResponse | null>(null);
  const resolvedOwnerLabel = ownerLabel
    ?? (theme
      ? target === "user" ? theme.owner_name : `${theme.owner_name} — Tema`
      : meta.title);
  const [values, setValues] = useState<ThemeValues>(INITIAL_VALUES);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [success, setSuccess] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const previewTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentPreviewUrl = useRef("");
  const previewController = useRef<AbortController | null>(null);
  const loadController = useRef<AbortController | null>(null);
  const saveController = useRef<AbortController | null>(null);
  const resetController = useRef<AbortController | null>(null);
  const targetGeneration = useRef(0);
  const targetKey = `${target}:${uuid}`;
  const renderedTargetKey = useRef(targetKey);
  if (renderedTargetKey.current !== targetKey) {
    renderedTargetKey.current = targetKey;
    targetGeneration.current += 1;
  }

  const cancelMutationWork = useCallback(() => {
    saveController.current?.abort();
    saveController.current = null;
    resetController.current?.abort();
    resetController.current = null;
  }, []);

  const cancelPreviewWork = useCallback(() => {
    previewController.current?.abort();
    previewController.current = null;
    if (previewTimer.current !== null) {
      clearTimeout(previewTimer.current);
      previewTimer.current = null;
    }
  }, []);

  const requestPreview = useCallback(async (nextValues: ThemeValues) => {
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    const outcome = await apiRequest(
      apiClient.POST("/api/v1/themes/preview", {
        body: nextValues,
        parseAs: "blob",
        signal: controller.signal
      })
    ).then(
      ({ data }) => ({ data }),
      (error: unknown) => ({ error })
    );
    if (controller.signal.aborted) {
      return;
    }
    if ("error" in outcome) {
      setPreviewError(errorMessage(outcome.error, "Não foi possível gerar a pré-visualização."));
      return;
    }
    const nextUrl = URL.createObjectURL(outcome.data);
    if (currentPreviewUrl.current) {
      URL.revokeObjectURL(currentPreviewUrl.current);
    }
    currentPreviewUrl.current = nextUrl;
    setPreviewUrl(nextUrl);
    setPreviewError("");
  }, []);

  const load = useCallback(async () => {
    loadController.current?.abort();
    cancelPreviewWork();
    if (currentPreviewUrl.current) {
      URL.revokeObjectURL(currentPreviewUrl.current);
      currentPreviewUrl.current = "";
    }
    setPreviewUrl("");
    setPreviewError("");
    setTheme(null);
    setLoading(true);
    setLoadError("");
    setActionError("");
    setFieldErrors({});

    const controller = new AbortController();
    loadController.current = controller;
    if (target !== "user" && !uuid) {
      setLoadError(meta.missing);
      setLoading(false);
      return;
    }

    const outcome = await getTheme(target, uuid, controller.signal).then(
      (themeResult) => ({ themeResult }),
      (error: unknown) => ({ error })
    );

    if (controller.signal.aborted || loadController.current !== controller) {
      return;
    }
    if ("error" in outcome) {
      setLoadError(errorMessage(outcome.error, "Não foi possível carregar o tema."));
      setLoading(false);
      return;
    }

    const { data } = outcome.themeResult;
    const nextValues = data.stored ?? data.effective;
    setTheme(data);
    setValues(nextValues);
    setLoading(false);
    void requestPreview(nextValues);
  }, [cancelPreviewWork, meta.missing, requestPreview, target, uuid]);

  useEffect(() => {
    cancelMutationWork();
    setSaving(false);
    setResetting(false);
    setResetOpen(false);
    setSuccess("");
    void load();
    return () => {
      targetGeneration.current += 1;
      cancelMutationWork();
      loadController.current?.abort();
      cancelPreviewWork();
    };
  }, [cancelMutationWork, cancelPreviewWork, load]);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = `${resolvedOwnerLabel} - Rentivo`;
    return () => {
      document.title = previousTitle;
    };
  }, [resolvedOwnerLabel]);

  useEffect(() => () => {
    loadController.current?.abort();
    cancelPreviewWork();
    if (currentPreviewUrl.current) {
      URL.revokeObjectURL(currentPreviewUrl.current);
    }
  }, [cancelPreviewWork]);

  function schedulePreview(nextValues: ThemeValues) {
    if (previewTimer.current !== null) {
      clearTimeout(previewTimer.current);
    }
    previewTimer.current = setTimeout(() => {
      previewTimer.current = null;
      void requestPreview(nextValues);
    }, 300);
  }

  function updateValue<Key extends keyof ThemeValues>(key: Key, value: ThemeValues[Key]) {
    const nextValues = { ...values, [key]: value };
    setValues(nextValues);
    setFieldErrors((current) => ({ ...current, [key]: "" }));
    schedulePreview(nextValues);
  }

  function previewNow() {
    if (previewTimer.current !== null) {
      clearTimeout(previewTimer.current);
      previewTimer.current = null;
    }
    void requestPreview(values);
  }

  async function saveTheme(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const controller = new AbortController();
    const generation = targetGeneration.current;
    saveController.current = controller;
    const ownsRequest = () => (
      !controller.signal.aborted
      && saveController.current === controller
      && targetGeneration.current === generation
    );
    setSaving(true);
    setSuccess("");
    setActionError("");
    setFieldErrors({});
    try {
      const { data, response } = await putTheme(target, uuid, values, controller.signal);
      if (!ownsRequest()) {
        return;
      }
      setTheme(data);
      setValues(data.effective);
      setSuccess(meta.saveSuccess);
      pushAnalyticsFromResponse(response);
    } catch (error) {
      if (!ownsRequest()) {
        return;
      }
      setActionError(errorMessage(error, "Não foi possível salvar o tema."));
      setFieldErrors(error instanceof ApiError ? normalizeFieldErrors(error.fields) : {});
    } finally {
      if (ownsRequest()) {
        saveController.current = null;
        setSaving(false);
      }
    }
  }

  async function resetTheme() {
    const controller = new AbortController();
    const generation = targetGeneration.current;
    resetController.current = controller;
    const ownsRequest = () => (
      !controller.signal.aborted
      && resetController.current === controller
      && targetGeneration.current === generation
    );
    setResetting(true);
    setSuccess("");
    setActionError("");
    try {
      await deleteTheme(target, uuid, controller.signal);
      if (!ownsRequest()) {
        return;
      }
      setSuccess(meta.resetSuccess);
      await load();
    } catch (error) {
      if (!ownsRequest()) {
        return;
      }
      setActionError(errorMessage(error, "Não foi possível restaurar o tema padrão."));
    } finally {
      if (ownsRequest()) {
        resetController.current = null;
        setResetting(false);
      }
    }
  }

  if (loading) {
    return <LoadingState label="Carregando tema..." />;
  }
  if (!theme) {
    return <LoadError message={loadError} onRetry={() => void load()} />;
  }

  const resolvedBackUrl = backUrl ?? `${meta.backPrefix}${target === "user" ? "" : uuid}`;

  return (
    <>
      <div className="page-header">
        <div className="page-header-info">
          <h1 className="page-title">{resolvedOwnerLabel}</h1>
        </div>
        <div className="page-actions">
          <Link className="btn btn--ghost" to={resolvedBackUrl}>
            <ArrowLeft aria-hidden="true" size={16} /> Voltar
          </Link>
        </div>
      </div>

      {success ? <div className="toast toast--success" role="status">{success}</div> : null}
      {actionError ? <div className="toast toast--danger" role="alert">{actionError}</div> : null}
      {!theme.capabilities.can_edit ? (
        <div className="toast toast--warning" role="status">Você tem acesso somente para consulta.</div>
      ) : null}
      {target === "billing" ? (
        <div
          className="toast toast--success"
          style={{ background: "var(--paper)", borderLeftColor: "var(--charcoal)" }}
        >
          Tema efetivo atual: <strong>{SOURCE_LABELS[theme.effective_source]}</strong>
        </div>
      ) : null}

      <div className="theme-editor">
        <div className="theme-editor-form">
          <form id="theme-form" onSubmit={(event) => void saveTheme(event)}>
            <div className="panel">
              <div className="panel-head"><h2 style={SECTION_HEADING_STYLE}>Fontes</h2></div>
              <div className="panel-body">
                <div className="dates-grid">
                  <div className="field mb-0">
                    <label className="field-label" htmlFor="header_font">Fonte do Cabeçalho</label>
                    <select
                      aria-describedby={fieldErrorId(fieldErrors, "header_font")}
                      className="field-select"
                      disabled={!theme.capabilities.can_edit}
                      id="header_font"
                      name="header_font"
                      onChange={(event: ChangeEvent<HTMLSelectElement>) => updateValue(
                        "header_font",
                        event.target.value as ThemeValues["header_font"]
                      )}
                      value={values.header_font}
                    >
                      {theme.options.fonts.map((font) => <option key={font} value={font}>{font}</option>)}
                    </select>
                    <FieldError id="header_font-error" message={fieldErrors.header_font} />
                  </div>
                  <div className="field mb-0">
                    <label className="field-label" htmlFor="text_font">Fonte do Texto</label>
                    <select
                      aria-describedby={fieldErrorId(fieldErrors, "text_font")}
                      className="field-select"
                      disabled={!theme.capabilities.can_edit}
                      id="text_font"
                      name="text_font"
                      onChange={(event: ChangeEvent<HTMLSelectElement>) => updateValue(
                        "text_font",
                        event.target.value as ThemeValues["text_font"]
                      )}
                      value={values.text_font}
                    >
                      {theme.options.fonts.map((font) => <option key={font} value={font}>{font}</option>)}
                    </select>
                    <FieldError id="text_font-error" message={fieldErrors.text_font} />
                  </div>
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="panel-head"><h2 style={SECTION_HEADING_STYLE}>Cores</h2></div>
              <div className="panel-body">
                <div className="theme-color-grid">
                  {COLOR_FIELDS.map(({ key, label }) => (
                    <div className="field mb-0" key={key}>
                      <label className="field-label" htmlFor={key}>{label}</label>
                      <input
                        aria-describedby={fieldErrorId(fieldErrors, key)}
                        className="field-input"
                        disabled={!theme.capabilities.can_edit}
                        id={key}
                        name={key}
                        onChange={(event) => updateValue(key, event.target.value)}
                        style={{ height: 42, padding: 4 }}
                        type="color"
                        value={values[key]}
                      />
                      <FieldError id={`${key}-error`} message={fieldErrors[key]} />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="btn-group">
              <button className="btn btn--primary" disabled={!theme.capabilities.can_edit || saving} type="submit">
                <Save aria-hidden="true" size={16} /> Salvar
              </button>
              <button className="btn" disabled={saving} onClick={previewNow} type="button">
                <Eye aria-hidden="true" size={16} /> Visualizar
              </button>
            </div>
          </form>

          {theme.capabilities.can_reset ? (
            <div className="mt-2">
              <button
                className="btn btn--sm btn--danger"
                disabled={resetting}
                onClick={() => setResetOpen(true)}
                type="button"
              >
                <RotateCcw aria-hidden="true" size={16} /> Usar Padrão
              </button>
            </div>
          ) : null}
        </div>

        <div className="theme-editor-preview">
          <div className="panel" style={{ height: "100%" }}>
            <div className="panel-head"><h2 style={SECTION_HEADING_STYLE}>Pré-visualização</h2></div>
            <div className="panel-body" style={{ display: "flex", flex: 1, padding: 0 }}>
              <iframe
                src={previewUrl || undefined}
                style={{ border: "none", flex: 1, minHeight: 600, width: "100%" }}
                title="Pré-visualização do tema"
              />
            </div>
            {previewError ? <div className="toast toast--danger" role="alert">{previewError}</div> : null}
          </div>
        </div>
      </div>

      <ConfirmDialog
        acceptLabel="Usar padrão"
        body="Tem certeza que deseja restaurar o tema padrão?"
        onClose={() => setResetOpen(false)}
        onConfirm={() => void resetTheme()}
        open={resetOpen}
        title="Restaurar o tema padrão?"
      />
    </>
  );
}

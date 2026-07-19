import { ChevronLeft } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { LoadError, LoadingState } from "../../components/PageState";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { parseBrl } from "../../lib/format";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import { BillingForm, type BillingFormValues } from "./BillingForm";
import { emptyBillingValues } from "./billingFormValues";

type Organization = components["schemas"]["OrganizationResponse"];
type CreateRequest = components["schemas"]["BillingCreateRequest"];

function normalizedFields(error: ApiError): Record<string, string> {
  return Object.fromEntries(Object.entries(error.fields).map(([key, value]) => [key.replace(/^body\./, ""), value]));
}

function createBody(values: BillingFormValues): CreateRequest {
  const recipients = values.recipients.map(({ email, name }) => ({ email: email.trim(), name: name.trim() }));
  const replyTo = values.replyTo.map(({ email, name }) => ({ email: email.trim(), name: name.trim() }));
  return {
    description: values.description.trim(),
    items: values.items.map((item) => ({ amount: item.itemType === "variable" ? 0 : (parseBrl(item.amount) ?? 0), description: item.description.trim(), item_type: item.itemType })),
    name: values.name.trim(),
    owner: values.ownerType === "organization" ? { type: "organization", uuid: values.ownerUuid } : { type: "user" },
    pix_key: values.pixKey.trim(),
    pix_merchant_city: values.pixMerchantCity.trim(),
    pix_merchant_name: values.pixMerchantName.trim(),
    ...(recipients.length ? { recipients } : {}),
    ...(replyTo.length ? { reply_to: replyTo } : {})
  };
}

export function BillingCreatePage() {
  const navigate = useNavigate();
  const createControllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(false);
  const [organizations, setOrganizations] = useState<Organization[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoadError("");
    try {
      const { data } = await apiRequest(apiClient.GET("/api/v1/organizations", { signal }));
      if (!signal?.aborted) setOrganizations(data.items);
    } catch {
      if (!signal?.aborted) setLoadError("Não foi possível carregar as organizações.");
    }
  }, []);

  useEffect(() => {
    const previousTitle = document.title;
    const controller = new AbortController();
    mountedRef.current = true;
    document.title = "Nova cobrança - Rentivo";
    void load(controller.signal);
    return () => {
      mountedRef.current = false;
      controller.abort();
      createControllerRef.current?.abort();
      createControllerRef.current = null;
      document.title = previousTitle;
    };
  }, [load]);

  const submit = async (values: BillingFormValues) => {
    if (createControllerRef.current) return;
    const controller = new AbortController();
    createControllerRef.current = controller;
    const isCurrent = () => mountedRef.current && !controller.signal.aborted && createControllerRef.current === controller;
    setSaving(true); setError(""); setFieldErrors({});
    try {
      const { data, response } = await apiRequest(apiClient.POST("/api/v1/billings", { body: createBody(values), signal: controller.signal }));
      if (!isCurrent()) return;
      pushAnalyticsFromResponse(response);
      navigate(`/billings/${data.uuid}`);
    } catch (caught) {
      if (!isCurrent()) return;
      if (caught instanceof ApiError && Object.keys(caught.fields).length) setFieldErrors(normalizedFields(caught));
      else setError(caught instanceof ApiError ? caught.message : "Não foi possível criar a cobrança.");
    } finally {
      const shouldUpdate = isCurrent();
      if (createControllerRef.current === controller) createControllerRef.current = null;
      if (shouldUpdate) setSaving(false);
    }
  };

  if (loadError) return <LoadError message={loadError} onRetry={() => void load()} />;
  if (!organizations) return <LoadingState label="Carregando formulário..." />;
  return <><Link className="crumb" to="/billings/"><ChevronLeft aria-hidden="true" size={16} strokeWidth={2.5} />Minhas Cobranças</Link><div className="pagehead"><div><h1 className="pagehead__title">Nova cobrança</h1><p className="pagehead__sub">Monte o modelo recorrente uma vez — ele será reutilizado em cada fatura mensal.</p></div></div><BillingForm error={error} fieldErrors={fieldErrors} mode="create" onSubmit={(values) => void submit(values)} organizations={organizations} saving={saving} values={emptyBillingValues()} /></>;
}

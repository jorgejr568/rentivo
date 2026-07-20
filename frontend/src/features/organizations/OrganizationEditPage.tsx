import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { LoadError, LoadingState } from "../../components/PageState";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import { OrganizationForm, type OrganizationValues } from "./OrganizationForm";

type Detail = components["schemas"]["OrganizationLoginDetailResponse"];

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function normalizedFields(error: ApiError): Record<string, string> {
  return Object.fromEntries(Object.entries(error.fields).map(([key, value]) => [key.replace(/^body\./, ""), value]));
}

function valuesFor(detail: Detail): OrganizationValues {
  return {
    name: detail.name,
    pix_key: detail.settings?.pix_key ?? "",
    pix_merchant_city: detail.settings?.pix_merchant_city ?? "",
    pix_merchant_name: detail.settings?.pix_merchant_name ?? ""
  };
}

export function OrganizationEditPage() {
  const { orgUuid = "" } = useParams<{ orgUuid: string }>();
  const navigate = useNavigate();
  const previousTitle = useRef(document.title);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const generationRef = useRef(0);
  const saveRef = useRef<AbortController | null>(null);

  const load = useCallback(async (signal?: AbortSignal, generation = generationRef.current) => {
    setLoadError("");
    try {
      const { data } = await apiRequest(apiClient.GET("/api/v1/organizations/{organization_uuid}", {
        params: { path: { organization_uuid: orgUuid } },
        signal
      }));
      if (!signal?.aborted && generation === generationRef.current) setDetail(data as Detail);
    } catch (caught) {
      if (!signal?.aborted && generation === generationRef.current) {
        setLoadError(errorMessage(caught, "Não foi possível carregar a organização."));
      }
    }
  }, [orgUuid]);

  useEffect(() => {
    const generation = ++generationRef.current;
    const controller = new AbortController();
    saveRef.current?.abort();
    saveRef.current = null;
    setDetail(null);
    setError("");
    setFieldErrors({});
    setSaving(false);
    void load(controller.signal, generation);
    return () => controller.abort();
  }, [load]);
  useEffect(() => () => {
    generationRef.current += 1;
    saveRef.current?.abort();
    saveRef.current = null;
  }, []);
  useEffect(() => {
    document.title = detail ? `Editar ${detail.name} - Rentivo` : "Editar Organização - Rentivo";
  }, [detail]);
  useEffect(() => () => { document.title = previousTitle.current; }, []);

  const submit = async (values: OrganizationValues) => {
    if (saveRef.current) return;
    const controller = new AbortController();
    const generation = generationRef.current;
    saveRef.current = controller;
    setSaving(true);
    setError("");
    setFieldErrors({});
    try {
      const { response } = await apiRequest(apiClient.PATCH("/api/v1/organizations/{organization_uuid}", {
        body: {
          name: values.name.trim(),
          pix_key: values.pix_key.trim(),
          pix_merchant_city: values.pix_merchant_city.trim(),
          pix_merchant_name: values.pix_merchant_name.trim()
        },
        params: { path: { organization_uuid: orgUuid } },
        signal: controller.signal
      }));
      if (controller.signal.aborted || generation !== generationRef.current) return;
      pushAnalyticsFromResponse(response);
      navigate(`/organizations/${orgUuid}`);
    } catch (caught) {
      if (controller.signal.aborted || generation !== generationRef.current) return;
      if (caught instanceof ApiError) {
        setError(Object.keys(caught.fields).length ? "" : caught.message);
        setFieldErrors(normalizedFields(caught));
      } else {
        setError("Não foi possível atualizar a organização.");
      }
    } finally {
      if (saveRef.current === controller) {
        saveRef.current = null;
        setSaving(false);
      }
    }
  };

  if (loadError) return <LoadError message={loadError} onRetry={() => void load()} />;
  if (!detail || detail.uuid !== orgUuid) return <LoadingState label="Carregando organização..." />;
  if (!detail.capabilities.can_manage) {
    return <div className="toast toast--warning" role="alert">Você não tem permissão para editar esta organização.</div>;
  }

  return (
    <>
      <h2 className="mb-3">Editar Organização</h2>
      <OrganizationForm error={error} fieldErrors={fieldErrors} key={detail.uuid} mode="edit" onSubmit={(values) => void submit(values)} organizationUuid={orgUuid} saving={saving} values={valuesFor(detail)} />
    </>
  );
}

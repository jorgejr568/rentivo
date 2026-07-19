import { ChevronLeft } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { LoadError, LoadingState } from "../../components/PageState";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { formatBrlInput, parseBrl } from "../../lib/format";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import { AttachmentManager } from "./AttachmentManager";
import { BillingForm, type BillingFormValues } from "./BillingForm";

type Attachment = components["schemas"]["AttachmentResponse"];
type BillingCapabilities = components["schemas"]["BillingCapabilitiesResponse"] & {
  can_read_attachments: boolean;
  can_write_attachments: boolean;
};
type Billing = Omit<components["schemas"]["BillingResponse"], "capabilities"> & {
  capabilities: BillingCapabilities;
};
type UpdateRequest = components["schemas"]["BillingUpdateRequest"];

interface LockedContacts {
  recipients: boolean;
  replyTo: boolean;
}

function normalizedFields(error: ApiError): Record<string, string> {
  return Object.fromEntries(Object.entries(error.fields).map(([key, value]) => [key.replace(/^body\./, ""), value]));
}

function fullContacts(contacts: Billing["recipients"], prefix: string) {
  return contacts.filter((contact): contact is components["schemas"]["ContactResponse"] => "name" in contact && "email" in contact)
    .map((contact) => ({ email: contact.email, id: `${prefix}-${contact.uuid}`, name: contact.name }));
}

function valuesFor(billing: Billing): BillingFormValues {
  return {
    description: billing.description,
    items: billing.items.map((item) => ({ amount: item.item_type === "fixed" ? formatBrlInput(item.amount) : "", description: item.description, id: `item-${item.uuid}`, itemType: item.item_type, uuid: item.uuid })),
    name: billing.name,
    ownerType: billing.owner.type,
    ownerUuid: billing.owner.uuid ?? "",
    pixKey: billing.pix_key,
    pixMerchantCity: billing.pix_merchant_city,
    pixMerchantName: billing.pix_merchant_name,
    recipients: fullContacts(billing.recipients, "recipient"),
    replyTo: fullContacts(billing.reply_to, "reply")
  };
}

function updateBody(values: BillingFormValues, lockedContacts: LockedContacts): UpdateRequest {
  return {
    description: values.description.trim(),
    items: values.items.map((item) => ({
      amount: item.itemType === "variable" ? 0 : (parseBrl(item.amount) ?? 0),
      description: item.description.trim(),
      item_type: item.itemType,
      ...(item.uuid ? { uuid: item.uuid } : {})
    })),
    name: values.name.trim(), pix_key: values.pixKey.trim(), pix_merchant_city: values.pixMerchantCity.trim(), pix_merchant_name: values.pixMerchantName.trim(),
    ...(!lockedContacts.recipients ? { recipients: values.recipients.map(({ email, name }) => ({ email: email.trim(), name: name.trim() })) } : {}),
    ...(!lockedContacts.replyTo ? { reply_to: values.replyTo.map(({ email, name }) => ({ email: email.trim(), name: name.trim() })) } : {})
  };
}

export function BillingEditPage() {
  const billingUuid = useParams<{ billingUuid: string }>().billingUuid!;
  const navigate = useNavigate();
  const routeUuidRef = useRef(billingUuid);
  const requestControllersRef = useRef(new Set<AbortController>());
  const saveControllerRef = useRef<AbortController | null>(null);
  routeUuidRef.current = billingUuid;
  const [billing, setBilling] = useState<Billing | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [attachmentError, setAttachmentError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const lockedContacts: LockedContacts = {
    recipients: billing?.recipients.some((contact) => !("name" in contact && "email" in contact)) ?? false,
    replyTo: billing?.reply_to.some((contact) => !("name" in contact && "email" in contact)) ?? false
  };

  const load = useCallback(async (signal?: AbortSignal) => {
    const requestUuid = billingUuid;
    const isCurrent = () => !signal?.aborted && routeUuidRef.current === requestUuid;
    setLoadError("");
    setBilling(null);
    setAttachments([]);
    setError("");
    setAttachmentError("");
    setFieldErrors({});
    try {
      const billingResult = await apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}", {
        params: { path: { billing_uuid: requestUuid } }, signal
      }));
      const loadedBilling = billingResult.data as Billing;
      if (!isCurrent()) return;
      const attachmentResult = loadedBilling.capabilities.can_read_attachments
        ? await apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}/attachments", {
          params: { path: { billing_uuid: requestUuid } }, signal
        }))
        : null;
      if (isCurrent()) {
        setBilling(loadedBilling);
        setAttachments(attachmentResult?.data.items ?? []);
      }
    } catch {
      if (isCurrent()) setLoadError("Não foi possível carregar a cobrança.");
    }
  }, [billingUuid]);

  const refreshAttachments = useCallback(async () => {
    const requestUuid = billingUuid;
    const controller = new AbortController();
    requestControllersRef.current.add(controller);
    const isCurrent = () => !controller.signal.aborted && routeUuidRef.current === requestUuid;
    try {
      const { data } = await apiRequest(apiClient.GET("/api/v1/billings/{billing_uuid}/attachments", { params: { path: { billing_uuid: requestUuid } }, signal: controller.signal }));
      if (isCurrent()) setAttachments(data.items);
    } catch (caught) {
      if (isCurrent()) throw caught;
    } finally {
      requestControllersRef.current.delete(controller);
    }
  }, [billingUuid]);

  useEffect(() => {
    const previousTitle = document.title;
    const controller = new AbortController();
    const requestControllers = requestControllersRef.current;
    document.title = "Editar cobrança - Rentivo";
    setSaving(false);
    saveControllerRef.current = null;
    void load(controller.signal);
    return () => {
      controller.abort();
      requestControllers.forEach((requestController) => requestController.abort());
      requestControllers.clear();
      saveControllerRef.current = null;
      document.title = previousTitle;
    };
  }, [load]);
  useEffect(() => { if (billing) document.title = `Editar ${billing.name} - Rentivo`; }, [billing]);

  const submit = async (values: BillingFormValues) => {
    if (saveControllerRef.current) return;
    const requestUuid = billingUuid;
    const controller = new AbortController();
    saveControllerRef.current = controller;
    requestControllersRef.current.add(controller);
    const isCurrent = () => !controller.signal.aborted && routeUuidRef.current === requestUuid && saveControllerRef.current === controller;
    setSaving(true); setError(""); setFieldErrors({});
    try {
      const { response } = await apiRequest(apiClient.PATCH("/api/v1/billings/{billing_uuid}", { body: updateBody(values, lockedContacts), params: { path: { billing_uuid: requestUuid } }, signal: controller.signal }));
      if (!isCurrent()) return;
      pushAnalyticsFromResponse(response);
      navigate(`/billings/${requestUuid}`);
    } catch (caught) {
      if (!isCurrent()) return;
      if (caught instanceof ApiError && Object.keys(caught.fields).length) setFieldErrors(normalizedFields(caught));
      else setError(caught instanceof ApiError ? caught.message : "Não foi possível atualizar a cobrança.");
    } finally {
      const shouldUpdate = isCurrent();
      requestControllersRef.current.delete(controller);
      if (saveControllerRef.current === controller) saveControllerRef.current = null;
      if (shouldUpdate) setSaving(false);
    }
  };

  if (loadError) return <LoadError message={loadError} onRetry={() => void load()} />;
  if (!billing) return <LoadingState label="Carregando cobrança..." />;
  if (!billing.capabilities.can_edit) return <div className="panel"><div className="empty-state"><p>Você não tem permissão para editar esta cobrança.</p><Link className="btn" to={`/billings/${billingUuid}`}>Voltar</Link></div></div>;
  return <><Link className="crumb" to={`/billings/${billingUuid}`}><ChevronLeft aria-hidden="true" size={16} strokeWidth={2.5} />{billing.name}</Link><div className="pagehead"><div><h1 className="pagehead__title">Editar cobrança</h1><p className="pagehead__sub">Atualize o modelo recorrente. As mudanças valem para as próximas faturas.</p></div></div><BillingForm cancelTo={`/billings/${billingUuid}`} error={error} fieldErrors={fieldErrors} lockedContacts={lockedContacts} mode="edit" onSubmit={(values) => void submit(values)} organizations={[]} saving={saving} values={valuesFor(billing)} />{attachmentError ? <div className="toast toast--error" role="alert">{attachmentError}</div> : null}{billing.capabilities.can_read_attachments || billing.capabilities.can_write_attachments ? <AttachmentManager attachments={attachments} billingUuid={billingUuid} canEdit={billing.capabilities.can_write_attachments} mode="edit" onChanged={billing.capabilities.can_read_attachments ? refreshAttachments : () => {}} onError={setAttachmentError} /> : null}</>;
}

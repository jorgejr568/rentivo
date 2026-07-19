import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { FieldError } from "../../components/FieldError";
import { ApiError, apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { pushAnalyticsFromResponse } from "../auth/analytics";

type Attachment = components["schemas"]["AttachmentResponse"];
type AttachmentMutation = "delete" | "upload";

interface MutationToken {
  controller: AbortController;
  kind: AttachmentMutation;
  requestUuid: string;
}

interface AttachmentManagerProps {
  attachments: Attachment[];
  billingUuid: string;
  canEdit: boolean;
  mode: "detail" | "edit";
  onChanged: () => void | Promise<void>;
  onError: (message: string) => void;
}

function normalizedFields(error: ApiError): Record<string, string> {
  return Object.fromEntries(Object.entries(error.fields).map(([key, value]) => [key.replace(/^body\./, ""), value]));
}

export function AttachmentManager({ attachments, billingUuid, canEdit, mode, onChanged, onError }: AttachmentManagerProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const currentUuidRef = useRef(billingUuid);
  const controllersRef = useRef(new Set<AbortController>());
  const activeMutationRef = useRef<MutationToken | null>(null);
  currentUuidRef.current = billingUuid;
  const [name, setName] = useState("");
  const [activeMutation, setActiveMutation] = useState<AttachmentMutation | null>(null);
  const [fileError, setFileError] = useState("");
  const [success, setSuccess] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Attachment | null>(null);

  useEffect(() => {
    const controllers = controllersRef.current;
    setName("");
    setActiveMutation(null);
    activeMutationRef.current = null;
    setFileError("");
    setSuccess("");
    setPendingDelete(null);
    if (fileRef.current) fileRef.current.value = "";
    return () => {
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
      activeMutationRef.current = null;
    };
  }, [billingUuid]);

  const beginMutation = (kind: AttachmentMutation): MutationToken | null => {
    if (activeMutationRef.current) return null;
    const token = { controller: new AbortController(), kind, requestUuid: billingUuid };
    activeMutationRef.current = token;
    controllersRef.current.add(token.controller);
    setActiveMutation(kind);
    return token;
  };
  const mutationIsCurrent = (token: MutationToken) => activeMutationRef.current === token
    && !token.controller.signal.aborted && currentUuidRef.current === token.requestUuid;
  const finishMutation = (token: MutationToken) => {
    controllersRef.current.delete(token.controller);
    if (activeMutationRef.current === token) {
      activeMutationRef.current = null;
      setActiveMutation(null);
    }
  };

  const upload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setFileError("Selecione um arquivo.");
      fileRef.current?.focus();
      return;
    }
    const token = beginMutation("upload");
    if (!token) return;
    setFileError("");
    setSuccess("");
    try {
      const { response } = await apiRequest(apiClient.POST("/api/v1/billings/{billing_uuid}/attachments", {
        body: { file, name: name.trim() },
        params: { path: { billing_uuid: token.requestUuid } }, signal: token.controller.signal
      }));
      if (!mutationIsCurrent(token)) return;
      pushAnalyticsFromResponse(response);
      setName("");
      if (fileRef.current) fileRef.current.value = "";
      setSuccess("Documento enviado.");
      try {
        await onChanged();
      } catch {
        if (mutationIsCurrent(token)) onError("Não foi possível atualizar a lista de documentos.");
      }
    } catch (caught) {
      if (!mutationIsCurrent(token)) return;
      if (caught instanceof ApiError) {
        const fields = normalizedFields(caught);
        if (fields.file) {
          setFileError(fields.file);
          fileRef.current?.focus();
        } else {
          onError(caught.message);
        }
      } else {
        onError("Não foi possível enviar o documento.");
      }
    } finally {
      finishMutation(token);
    }
  };

  const remove = async (attachment: Attachment) => {
    const token = beginMutation("delete");
    if (!token) return;
    setSuccess("");
    try {
      try {
        const { response } = await apiRequest(apiClient.DELETE("/api/v1/billings/{billing_uuid}/attachments/{attachment_uuid}", {
          params: { path: { attachment_uuid: attachment.uuid, billing_uuid: token.requestUuid } }, signal: token.controller.signal
        }));
        if (!mutationIsCurrent(token)) return;
        pushAnalyticsFromResponse(response);
      } catch {
        if (mutationIsCurrent(token)) onError("Não foi possível remover o documento.");
        return;
      }
      setSuccess("Documento removido.");
      try {
        await onChanged();
      } catch {
        if (mutationIsCurrent(token)) onError("Não foi possível atualizar a lista de documentos.");
      }
      if (mutationIsCurrent(token)) headingRef.current?.focus();
    } finally {
      finishMutation(token);
    }
  };

  const table = attachments.length ? (
    <div className="table-wrap" style={mode === "edit" ? { marginBottom: "1rem" } : undefined}>
      <table className="table">
        <thead><tr><th>Nome</th><th>Arquivo</th><th className="num">Tamanho</th><th /></tr></thead>
        <tbody>{attachments.map((attachment) => <tr key={attachment.uuid}>
          <td className="table__primary">{attachment.name}</td><td className="muted">{attachment.filename}</td>
          <td className="num">{(attachment.file_size / 1024).toFixed(1)} KB</td>
          <td className="num" style={{ whiteSpace: "nowrap" }}>
            <a className="btn btn--sm" href={`/api/v1/billings/${billingUuid}/attachments/${attachment.uuid}`} rel="noreferrer" target="_blank">{mode === "edit" ? "Ver" : "Baixar"}</a>
            {mode === "edit" && canEdit ? <button aria-label={`Remover documento ${attachment.name}`} className="btn btn--sm btn--danger" disabled={activeMutation !== null} onClick={() => setPendingDelete(attachment)} type="button">Remover</button> : null}
          </td>
        </tr>)}</tbody>
      </table>
    </div>
  ) : mode === "detail" ? (
    <div className="empty-state" style={{ padding: "2rem" }}><p>Nenhum documento anexado.</p>{canEdit ? <Link className="btn btn--sm" to={`/billings/${billingUuid}/edit`}>Anexar documento</Link> : null}</div>
  ) : <p className="muted mb-2" style={{ fontSize: "0.88rem" }}>Nenhum documento anexado.</p>;

  return (
    <>
      {success ? <div className="toast toast--success" role="status">{success}</div> : null}
      <div className="panel" style={mode === "edit" ? { marginTop: "1.5rem" } : undefined}>
        <div className="panel__head"><h3 ref={headingRef} tabIndex={-1}>Documentos</h3><span className="panel__title-eyebrow">{mode === "edit" ? "Contrato, etc." : `${attachments.length} ${attachments.length === 1 ? "anexo" : "anexos"}`}</span></div>
        {mode === "detail" ? table : <div className="panel__body">{table}{canEdit ? <form encType="multipart/form-data" onSubmit={upload}>
          <div className="field"><label className="field__label" htmlFor="attachment_name">Nome do documento</label><input className="input" id="attachment_name" maxLength={255} name="name" onChange={(event) => setName(event.target.value)} placeholder="Ex.: Contrato de locação" type="text" value={name} /></div>
          <div className="field"><label className="field__label" htmlFor="attachment_file">Arquivo</label><input accept=".pdf,.jpg,.jpeg,.png" aria-describedby="attachment-file-hint attachment-file-error" className="input" id="attachment_file" name="attachment_file" ref={fileRef} type="file" /><span className="field__hint" id="attachment-file-hint">PDF, JPG ou PNG. Máximo 10 MB.</span><FieldError id="attachment-file-error" message={fileError} /></div>
          <button className="btn btn--sm btn--primary" disabled={activeMutation !== null} type="submit">{activeMutation === "upload" ? "Enviando..." : "Enviar"}</button>
        </form> : null}</div>}
      </div>
      <ConfirmDialog acceptLabel="Remover" body="Esta ação não pode ser desfeita." onClose={() => setPendingDelete(null)} onConfirm={() => { if (pendingDelete) void remove(pendingDelete); }} open={pendingDelete !== null} title="Remover documento?" />
    </>
  );
}

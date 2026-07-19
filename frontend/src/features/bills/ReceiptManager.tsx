import { Eye, GripVertical, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import Sortable from "sortablejs";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { apiClient, apiRequest } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import { pushAnalyticsFromResponse } from "../auth/analytics";
import type { BillCapabilities, Receipt } from "./billSupport";
import { errorMessage, formatFileSize, multipartBodySerializer } from "./billSupport";

export interface ReceiptManagerProps {
  billingUuid: string;
  billUuid: string;
  capabilities: BillCapabilities;
  onChange: (receipts: Receipt[]) => void;
  receipts: Receipt[];
}

type BusyAction = "delete" | "reorder" | "upload" | null;

function uniqueFiles(files: File[]): File[] {
  const seen = new Set<string>();
  return files.filter((file) => {
    const key = `${file.name}:${file.size}:${file.lastModified}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function appendUnique(receipts: Receipt[], additions: Receipt[]): Receipt[] {
  const existing = new Set(receipts.map((receipt) => receipt.uuid));
  return [...receipts, ...additions.filter((receipt) => !existing.has(receipt.uuid))];
}

export function ReceiptManager({ billingUuid, billUuid, capabilities, onChange, receipts }: ReceiptManagerProps) {
  const [current, setCurrent] = useState(receipts);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState<BusyAction>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [removing, setRemoving] = useState<Receipt | null>(null);
  const [reorderAnnouncement, setReorderAnnouncement] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLTableSectionElement>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const currentRef = useRef(receipts);
  const sortableRef = useRef<Sortable | null>(null);
  const reorderRef = useRef<(next: Receipt[]) => void>(() => undefined);
  const operation = useRef(0);

  useEffect(() => {
    currentRef.current = receipts;
    setCurrent(receipts);
  }, [receipts]);

  useEffect(() => {
    operation.current += 1;
    setBusy(null);
    setError("");
    setSuccess("");
    setFiles([]);
    setRemoving(null);
    setReorderAnnouncement("");
  }, [billingUuid, billUuid]);

  useEffect(() => {
    if (success) successRef.current?.focus();
  }, [success]);

  const publish = (next: Receipt[]) => {
    currentRef.current = next;
    setCurrent(next);
    onChange(next);
  };

  const restorePersistedOrder = () => {
    const list = listRef.current;
    if (list) {
      const persisted = new Set(currentRef.current.map((receipt) => receipt.uuid));
      list.querySelectorAll<HTMLTableRowElement>("tr[data-uuid]").forEach((row) => {
        if (!persisted.has(row.dataset.uuid!)) row.remove();
      });
      const rows = new Map(Array.from(list.querySelectorAll<HTMLTableRowElement>("tr[data-uuid]"), (row) => [row.dataset.uuid, row]));
      currentRef.current.forEach((receipt) => {
        const row = rows.get(receipt.uuid);
        if (row) list.append(row);
      });
    }
    setCurrent([...currentRef.current]);
  };

  const upload = async (event: FormEvent) => {
    event.preventDefault();
    if (files.length === 0) {
      setError("Selecione ao menos um comprovante.");
      fileRef.current?.focus();
      return;
    }
    const request = ++operation.current;
    setBusy("upload");
    setError("");
    setSuccess("");
    try {
      type UploadBody = components["schemas"]["Body_upload_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipts_post"];
      const body: UploadBody = { receipt_files: files };
      const { data, response } = await apiRequest(apiClient.POST(
        "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipts",
        {
          body,
          bodySerializer: multipartBodySerializer,
          params: { path: { billing_uuid: billingUuid, bill_uuid: billUuid } }
        }
      ));
      if (request !== operation.current) return;
      pushAnalyticsFromResponse(response);
      publish(appendUnique(currentRef.current, data.items));
      setFiles([]);
      if (fileRef.current) fileRef.current.value = "";
      setSuccess(`${data.attached} comprovante(s) anexado(s).${data.skipped ? ` ${data.skipped} arquivo(s) ignorado(s).` : ""}`);
    } catch (caught) {
      if (request !== operation.current) return;
      setError(errorMessage(caught, "Não foi possível anexar os comprovantes."));
      fileRef.current?.focus();
    } finally {
      if (request === operation.current) setBusy(null);
    }
  };

  const remove = async () => {
    /* v8 ignore next -- confirmation is only available after selecting a receipt */
    if (!removing) return;
    const request = ++operation.current;
    const receiptUuid = removing.uuid;
    setBusy("delete");
    setError("");
    try {
      const { response } = await apiRequest(apiClient.DELETE(
        "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipts/{receipt_uuid}",
        { params: { path: { billing_uuid: billingUuid, bill_uuid: billUuid, receipt_uuid: receiptUuid } } }
      ));
      if (request !== operation.current) return;
      pushAnalyticsFromResponse(response);
      publish(currentRef.current.filter((receipt) => receipt.uuid !== receiptUuid));
      setSuccess("Comprovante removido.");
    } catch (caught) {
      if (request !== operation.current) return;
      setError(errorMessage(caught, "Não foi possível remover o comprovante."));
    } finally {
      if (request === operation.current) {
        setBusy(null);
        setRemoving(null);
      }
    }
  };

  const reorder = async (next: Receipt[]) => {
    const request = ++operation.current;
    setCurrent(next);
    setBusy("reorder");
    setError("");
    try {
      const { data } = await apiRequest(apiClient.PUT(
        "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipt-order",
        {
          body: { order: next.map((receipt) => receipt.uuid) },
          params: { path: { billing_uuid: billingUuid, bill_uuid: billUuid } }
        }
      ));
      if (request !== operation.current) return;
      const latest = currentRef.current;
      const latestByUuid = new Map(latest.map((receipt) => [receipt.uuid, receipt]));
      const ordered = data.items.flatMap((receipt) => latestByUuid.get(receipt.uuid) ?? []);
      const returned = new Set(ordered.map((receipt) => receipt.uuid));
      publish([...ordered, ...latest.filter((receipt) => !returned.has(receipt.uuid))]);
      setSuccess("Ordem dos comprovantes atualizada.");
    } catch (caught) {
      if (request !== operation.current) return;
      restorePersistedOrder();
      setError(errorMessage(caught, "Não foi possível reordenar os comprovantes."));
    } finally {
      if (request === operation.current) setBusy(null);
    }
  };

  reorderRef.current = (next) => { void reorder(next); };

  const move = (index: number, delta: -1 | 1) => {
    const target = index + delta;
    if (target < 0 || target >= currentRef.current.length) return;
    const next = [...currentRef.current];
    const moved = next[index];
    [next[index], next[target]] = [next[target], next[index]];
    setReorderAnnouncement(`${moved.filename} movido para ${delta < 0 ? "cima" : "baixo"}.`);
    void reorder(next);
  };

  const sortableEnabled = capabilities.can_reorder_receipts && current.length > 0;

  useEffect(() => {
    const list = listRef.current;
    /* v8 ignore next -- enabled receipt lists always render the table body */
    if (!sortableEnabled || !list) return;
    const sortable = Sortable.create(list, {
      animation: 150,
      disabled: false,
      ghostClass: "sortable-ghost",
      handle: ".drag-handle",
      onEnd: () => {
        const byUuid = new Map(currentRef.current.map((receipt) => [receipt.uuid, receipt]));
        const rows = Array.from(list.querySelectorAll<HTMLTableRowElement>("tr[data-uuid]"));
        const next = rows.flatMap((row) => {
          const receipt = byUuid.get(row.dataset.uuid!);
          return receipt ? [receipt] : [];
        });
        if (next.length !== rows.length || rows.length !== currentRef.current.length) {
          restorePersistedOrder();
          return;
        }
        reorderRef.current(next);
      }
    });
    sortableRef.current = sortable;
    return () => {
      sortable.destroy();
      if (sortableRef.current === sortable) sortableRef.current = null;
    };
  }, [billUuid, billingUuid, sortableEnabled]);

  useEffect(() => {
    sortableRef.current?.option("disabled", Boolean(busy));
  }, [busy]);

  const handleReorderKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    move(index, event.key === "ArrowUp" ? -1 : 1);
  };

  return (
    <>
      {current.length > 0 ? (
        <div className="table-wrap" style={{ marginBottom: "1rem" }}>
          <table className="table data-table">
            <thead><tr>{capabilities.can_reorder_receipts && <th style={{ width: "4rem" }} />}<th>Arquivo</th><th className="num">Tamanho</th><th /></tr></thead>
            <tbody id="receipt-list" ref={listRef}>
              {current.map((receipt, index) => (
                <tr data-uuid={receipt.uuid} key={receipt.uuid}>
                  {capabilities.can_reorder_receipts && (
                    <td className="drag-handle">
                      <button aria-keyshortcuts="ArrowUp ArrowDown" aria-label={`Reordenar ${receipt.filename}`} className="drag-handle" disabled={Boolean(busy)} onKeyDown={(event) => handleReorderKey(event, index)} title="Arrastar ou usar as setas para reordenar" type="button"><GripVertical aria-hidden="true" size={14} /></button>
                    </td>
                  )}
                  <td className="table__primary">{receipt.filename}</td>
                  <td className="num">{formatFileSize(receipt.file_size)}</td>
                  <td className="num" style={{ whiteSpace: "nowrap" }}>
                    <a aria-label={`Ver ${receipt.filename}`} className="btn btn--sm" href={`/api/v1/billings/${billingUuid}/bills/${billUuid}/receipts/${receipt.uuid}`} target="_blank"><Eye aria-hidden="true" size={14} /> Ver</a>
                    {capabilities.can_delete_receipts && <button aria-label={`Remover ${receipt.filename}`} className="btn btn--sm btn--danger" disabled={Boolean(busy)} onClick={() => setRemoving(receipt)} type="button"><Trash2 aria-hidden="true" size={14} /> Remover</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="text-muted">Nenhum comprovante anexado.</p>}

      {capabilities.can_upload_receipts && (
        <form encType="multipart/form-data" onSubmit={(event) => void upload(event)}>
          <div className="field">
            <label className="field__label field-label" htmlFor="receipt_files">Anexar comprovantes</label>
            <input accept=".pdf,.jpg,.jpeg,.png" className="input field-input" id="receipt_files" multiple name="receipt_files" onChange={(event) => setFiles(uniqueFiles(Array.from(event.currentTarget.files ?? [])))} ref={fileRef} type="file" />
            <span className="field__hint text-muted">PDF, JPG ou PNG. Máximo 10 MB cada. Você pode selecionar vários arquivos.</span>
          </div>
          {busy === "upload" && <progress aria-label="Progresso do envio" />}
          <button className="btn btn--sm btn--primary" disabled={Boolean(busy)} type="submit"><Upload aria-hidden="true" size={14} /> {busy === "upload" ? "Enviando..." : "Enviar comprovantes"}</button>
        </form>
      )}
      {error && <div className="toast toast--danger" role="alert">{error}</div>}
      {success && <div className="toast toast--success" ref={successRef} role="status" tabIndex={-1}>{success}</div>}
      <div aria-live="polite" className="sr-only">{reorderAnnouncement}</div>
      <ConfirmDialog acceptLabel="Remover" body="O arquivo será removido desta fatura e o PDF será atualizado." onClose={() => setRemoving(null)} onConfirm={() => void remove()} open={Boolean(removing)} title="Remover comprovante?" />
    </>
  );
}

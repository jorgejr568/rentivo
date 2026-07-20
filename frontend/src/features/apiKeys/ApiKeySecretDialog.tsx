import { CheckCircle2, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface ApiKeySecretDialogProps {
  onClose: () => void;
  open: boolean;
  secret: string;
}

export function ApiKeySecretDialog({ onClose, open, secret }: ApiKeySecretDialogProps) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const checkboxRef = useRef<HTMLInputElement>(null);
  const copyRef = useRef<HTMLButtonElement>(null);
  const doneRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      setAcknowledged(false);
      setCopied(false);
      setCopyFailed(false);
      return;
    }
    const previousOverflow = document.body.style.overflow;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const focusable = [copyRef.current, checkboxRef.current, doneRef.current]
        .filter((element): element is HTMLButtonElement | HTMLInputElement =>
          Boolean(element && !element.hasAttribute("disabled"))
        );
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown, true);
    checkboxRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [open]);

  if (!open) {
    return null;
  }

  async function copySecret() {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
      setCopyFailed(false);
    } catch {
      setCopied(false);
      setCopyFailed(true);
    }
  }

  return (
    <div className="modal-overlay">
      <div aria-labelledby="api-key-secret-title" aria-modal="true" className="modal" role="dialog">
        <div className="modal__head">
          <span aria-hidden="true" className="modal__icon modal__icon--primary">
            <CheckCircle2 size={20} />
          </span>
          <h2 className="modal__title" id="api-key-secret-title">Chave de integração criada</h2>
        </div>
        <div className="modal__body">
          <div className="mfa-enforcement-banner" style={{ background: "#fff8e1", borderColor: "#f9a825" }}>
            Esta chave será exibida apenas uma vez. Guarde-a agora.
          </div>
          <div className="secret-key">{secret}</div>
          <button aria-describedby={copyFailed ? "api-key-copy-error" : undefined} className="btn btn--sm" onClick={() => void copySecret()} ref={copyRef} style={{ marginTop: "0.75rem" }} type="button">
            <Copy aria-hidden="true" size={15} style={{ marginRight: "0.35rem", verticalAlign: "text-bottom" }} />
            {copied ? "Copiada!" : "Copiar chave"}
          </button>
          {copyFailed ? <div className="toast toast--danger mt-2" id="api-key-copy-error" role="alert">Não foi possível copiar a chave. Selecione e copie manualmente.</div> : null}
          <label style={{ alignItems: "flex-start", display: "flex", gap: "0.55rem", marginTop: "1rem" }}>
            <input
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
              ref={checkboxRef}
              type="checkbox"
            />
            Guardei esta chave em um local seguro.
          </label>
        </div>
        <div className="modal__foot">
          <button className="btn btn--primary" disabled={!acknowledged} onClick={onClose} ref={doneRef} type="button">
            Concluir
          </button>
        </div>
      </div>
    </div>
  );
}

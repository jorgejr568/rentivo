import { AlertTriangle, CircleCheck } from "lucide-react";
import { useEffect, useRef } from "react";

export interface ConfirmDialogProps {
  acceptLabel?: string;
  body?: string;
  onClose: () => void;
  onConfirm: () => void;
  open: boolean;
  title: string;
  variant?: "danger" | "primary";
}

export function ConfirmDialog({
  acceptLabel = "Confirmar",
  body = "",
  onClose,
  onConfirm,
  open,
  title,
  variant = "danger"
}: ConfirmDialogProps) {
  const acceptRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const previousBodyOverflow = document.body.style.overflow;
    const restoreFocus = () => previouslyFocused?.focus();
    const closeDialog = () => {
      onClose();
      restoreFocus();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDialog();
        return;
      }

      if (event.key !== "Tab" || !cancelRef.current || !acceptRef.current) {
        return;
      }

      const isOnCancel = document.activeElement === cancelRef.current;
      const isOnAccept = document.activeElement === acceptRef.current;
      if ((!event.shiftKey && isOnAccept) || (event.shiftKey && isOnCancel)) {
        event.preventDefault();
        (isOnAccept ? cancelRef.current : acceptRef.current).focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    document.body.style.overflow = "hidden";
    cancelRef.current?.focus();

    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      document.body.style.overflow = previousBodyOverflow;
      restoreFocus();
    };
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  const isPrimary = variant === "primary";
  const Icon = isPrimary ? CircleCheck : AlertTriangle;

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) {
          onClose();
        }
      }}
    >
      <div aria-describedby="confirm-body" aria-labelledby="confirm-title" aria-modal="true" className="modal" role="dialog">
        <div className="modal__head">
          <span className={`modal__icon${isPrimary ? " modal__icon--primary" : ""}`} aria-hidden="true">
            <Icon size={20} />
          </span>
          <h2 className="modal__title" id="confirm-title">{title}</h2>
        </div>
        <div className="modal__body" id="confirm-body">{body}</div>
        <div className="modal__foot">
          <button className="btn btn--ghost" onClick={onClose} ref={cancelRef} type="button">Voltar</button>
          <button
            className={`btn ${isPrimary ? "btn--primary" : "btn--danger"}`}
            onClick={() => {
              onConfirm();
              onClose();
            }}
            ref={acceptRef}
            type="button"
          >
            {acceptLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

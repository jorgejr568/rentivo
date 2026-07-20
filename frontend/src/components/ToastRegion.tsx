import { useState } from "react";

export interface Toast {
  category: "success" | "error" | "warning" | "danger" | "info";
  id: string;
  message: string;
}

interface ToastRegionProps {
  toasts: Toast[];
}

export function ToastRegion({ toasts }: ToastRegionProps) {
  const [dismissedIds, setDismissedIds] = useState<string[]>([]);

  return toasts
    .filter((toast) => !dismissedIds.includes(toast.id))
    .map((toast) => (
      <div className={`toast toast--${toast.category}`} data-dismissible key={toast.id} role="alert">
        {toast.message}
        <button
          aria-label="Fechar"
          className="toast-close"
          onClick={() => setDismissedIds((ids) => [...ids, toast.id])}
          type="button"
        />
      </div>
    ));
}

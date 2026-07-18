import type { ReactNode } from "react";

interface LoadingStateProps {
  label?: string;
}

interface LoadErrorProps {
  message: string;
  onRetry: () => void;
}

interface EmptyStateProps {
  action?: ReactNode;
  body: string;
  title: string;
}

export function LoadingState({ label = "Carregando..." }: LoadingStateProps) {
  return (
    <div aria-live="polite" className="empty-state" role="status">
      <p>{label}</p>
    </div>
  );
}

export function LoadError({ message, onRetry }: LoadErrorProps) {
  return (
    <div className="empty-state">
      <p role="alert">{message}</p>
      <button className="btn btn--primary" onClick={onRetry} type="button">
        Tentar novamente
      </button>
    </div>
  );
}

export function EmptyState({ action, body, title }: EmptyStateProps) {
  return (
    <section className="empty-state">
      <h2>{title}</h2>
      <p>{body}</p>
      {action}
    </section>
  );
}

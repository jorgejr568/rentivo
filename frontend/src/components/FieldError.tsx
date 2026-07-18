interface FieldErrorProps {
  id: string;
  message?: string;
}

export function FieldError({ id, message }: FieldErrorProps) {
  if (!message) {
    return null;
  }
  return (
    <span className="field-hint" id={id} role="alert" style={{ color: "var(--danger)" }}>
      {message}
    </span>
  );
}

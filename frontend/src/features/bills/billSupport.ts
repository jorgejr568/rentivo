import { useEffect, useRef } from "react";

import { ApiError } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";

export type Billing = components["schemas"]["BillingResponse"];
export type Bill = components["schemas"]["BillDetailResponse"];
export type BillCapabilities = components["schemas"]["BillCapabilitiesResponse"];
export type BillLineItemRequest = components["schemas"]["BillLineItemRequest"];
export type BillStatus = components["schemas"]["BillStatus"];
export type Receipt = components["schemas"]["ReceiptResponse"];

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}
export function normalizedFieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  return Object.fromEntries(
    Object.entries(error.fields).map(([key, message]) => [key.replace(/^body\./, ""), message])
  );
}

export function firstFieldError(
  fields: Record<string, string>,
  preferred: string[]
): string | undefined {
  return preferred.find((key) => fields[key]) ?? Object.keys(fields)[0];
}

export function parseDateInput(value: string): string | null | undefined {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const brazilian = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(trimmed);
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  const parts = brazilian
    ? [brazilian[3], brazilian[2], brazilian[1]]
    : iso
      ? [iso[1], iso[2], iso[3]]
      : null;
  if (!parts) return undefined;
  const [year, month, day] = parts.map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return undefined;
  }
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function multipartBodySerializer(body: unknown): BodyInit {
  const form = new FormData();
  if (typeof body !== "object" || body === null) return form;
  Object.entries(body).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    const values = Array.isArray(value) ? value : [value];
    values.forEach((item) => form.append(key, item instanceof Blob ? item : String(item)));
  });
  return form;
}

export function formatFileSize(bytes: number): string {
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export function formatDateTime(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit", hour: "2-digit", minute: "2-digit", month: "2-digit", year: "numeric"
  }).format(parsed).replace(",", "");
}

export function useDocumentTitle(title: string) {
  const previousTitle = useRef<string | null>(null);
  useEffect(() => {
    if (previousTitle.current === null) previousTitle.current = document.title;
    document.title = title;
    return () => {
      if (previousTitle.current !== null) document.title = previousTitle.current;
    };
  }, [title]);
}

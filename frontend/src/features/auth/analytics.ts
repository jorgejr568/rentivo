declare global {
  interface Window {
    dataLayer?: Array<Record<string, unknown>>;
  }
}

let configured = false;
let enabled = false;
let pendingEvents: Array<Record<string, unknown>> = [];

const ANALYTICS_DIMENSIONS = {
  "X-Rentivo-Analytics-Bill-Uuid-Hash": "bill_uuid_hash",
  "X-Rentivo-Analytics-Billing-Uuid-Hash": "billing_uuid_hash",
  "X-Rentivo-Analytics-Comm-Type": "comm_type",
  "X-Rentivo-Analytics-Count": "count",
  "X-Rentivo-Analytics-Line-Item-Count": "line_item_count",
  "X-Rentivo-Analytics-Method": "method",
  "X-Rentivo-Analytics-New-Status": "new_status",
  "X-Rentivo-Analytics-Reason": "reason",
  "X-Rentivo-Analytics-Receipt-Count": "receipt_count",
  "X-Rentivo-Analytics-Recipient-Count": "recipient_count",
  "X-Rentivo-Analytics-Reference-Month": "reference_month",
  "X-Rentivo-Analytics-Scope": "scope",
  "X-Rentivo-Analytics-Total-Amount-Brl": "total_amount_brl",
  "X-Rentivo-Analytics-Total-Bytes": "total_bytes",
  "X-Rentivo-Analytics-Via": "via"
} as const;

const NUMERIC_ANALYTICS_DIMENSIONS = new Set<string>([
  "count",
  "line_item_count",
  "receipt_count",
  "recipient_count",
  "total_amount_brl",
  "total_bytes"
]);

export function configureAnalytics(containerId: string) {
  configured = true;
  enabled = Boolean(containerId);
  if (!enabled) {
    pendingEvents = [];
    return;
  }

  window.dataLayer = window.dataLayer ?? [];
  if (!document.querySelector("script[data-rentivo-gtm]")) {
    window.dataLayer.push({ event: "gtm.js", "gtm.start": Date.now() });

    const script = document.createElement("script");
    script.async = true;
    script.dataset.rentivoGtm = "true";
    script.src = `https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(containerId)}`;
    document.head.append(script);
  }
  window.dataLayer.push(...pendingEvents);
  pendingEvents = [];
}

export function pushAnalyticsEvent(event: Record<string, unknown>) {
  if (!configured) {
    pendingEvents.push(event);
    return;
  }
  if (!enabled) {
    return;
  }
  window.dataLayer = window.dataLayer ?? [];
  window.dataLayer.push(event);
}

export function pushAnalyticsFromResponse(response: Response) {
  const event = response.headers.get("X-Rentivo-Analytics-Event");
  if (!event) {
    return;
  }
  const payload: Record<string, unknown> = { event };
  Object.entries(ANALYTICS_DIMENSIONS).forEach(([header, dimension]) => {
    const value = response.headers.get(header);
    if (!value) return;
    if (!NUMERIC_ANALYTICS_DIMENSIONS.has(dimension)) {
      payload[dimension] = value;
      return;
    }
    const numericValue = Number(value);
    if (Number.isFinite(numericValue)) payload[dimension] = numericValue;
  });
  pushAnalyticsEvent(payload);
}

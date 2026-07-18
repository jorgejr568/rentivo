declare global {
  interface Window {
    dataLayer?: Array<Record<string, unknown>>;
  }
}

let configured = false;
let enabled = false;
let pendingEvents: Array<Record<string, unknown>> = [];

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
  const reason = response.headers.get("X-Rentivo-Analytics-Reason");
  const scope = response.headers.get("X-Rentivo-Analytics-Scope");
  const via = response.headers.get("X-Rentivo-Analytics-Via");
  pushAnalyticsEvent({
    event,
    ...(reason ? { reason } : {}),
    ...(scope ? { scope } : {}),
    ...(via ? { via } : {})
  });
}

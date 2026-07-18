import { beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  interface Window {
    dataLayer?: Array<Record<string, unknown>>;
  }
}

beforeEach(() => {
  vi.resetModules();
  delete window.dataLayer;
  document.head.querySelectorAll("script[data-rentivo-gtm]").forEach((script) => script.remove());
});

describe("auth analytics", () => {
  it("is a no-op while GTM is disabled", async () => {
    const { configureAnalytics, pushAnalyticsEvent } = await import("./analytics");

    pushAnalyticsEvent({ event: "queued_while_loading" });
    configureAnalytics("");
    pushAnalyticsEvent({ event: "rentivo_login_success", via: "password" });

    expect(window.dataLayer).toBeUndefined();
    expect(document.querySelector("script[data-rentivo-gtm]")).toBeNull();
  });

  it("loads GTM once and preserves business event payloads", async () => {
    window.dataLayer = [{ event: "existing" }];
    const { configureAnalytics, pushAnalyticsEvent } = await import("./analytics");

    pushAnalyticsEvent({ event: "queued_before_config" });
    expect(window.dataLayer).toEqual([{ event: "existing" }]);
    configureAnalytics("GTM-TEST ID");
    configureAnalytics("GTM-TEST ID");
    pushAnalyticsEvent({ event: "rentivo_login_failed", reason: "bad_credentials" });

    expect(document.querySelectorAll("script[data-rentivo-gtm]")).toHaveLength(1);
    expect(document.querySelector<HTMLScriptElement>("script[data-rentivo-gtm]")?.src).toContain(
      "id=GTM-TEST%20ID"
    );
    expect(window.dataLayer).toEqual([
      { event: "existing" },
      expect.objectContaining({ event: "gtm.js" }),
      { event: "queued_before_config" },
      { event: "rentivo_login_failed", reason: "bad_credentials" }
    ]);

    delete window.dataLayer;
    pushAnalyticsEvent({ event: "rentivo_login_success" });
    expect(window.dataLayer).toEqual([{ event: "rentivo_login_success" }]);
  });

  it("forwards analytics response headers without empty dimensions", async () => {
    const { configureAnalytics, pushAnalyticsFromResponse } = await import("./analytics");
    configureAnalytics("GTM-TEST");

    pushAnalyticsFromResponse(
      new Response(null, {
        headers: {
          "X-Rentivo-Analytics-Event": "rentivo_login_failed",
          "X-Rentivo-Analytics-Reason": "bad_credentials"
        }
      })
    );
    pushAnalyticsFromResponse(
      new Response(null, {
        headers: {
          "X-Rentivo-Analytics-Event": "rentivo_login_success",
          "X-Rentivo-Analytics-Scope": "user",
          "X-Rentivo-Analytics-Via": "google"
        }
      })
    );
    pushAnalyticsFromResponse(new Response(null));

    expect(window.dataLayer?.slice(-2)).toEqual([{
      event: "rentivo_login_failed",
      reason: "bad_credentials"
    }, {
      event: "rentivo_login_success",
      scope: "user",
      via: "google"
    }]);
  });
});

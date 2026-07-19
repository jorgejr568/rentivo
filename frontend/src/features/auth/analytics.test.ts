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

  it("forwards every approved analytics response header without empty or unapproved dimensions", async () => {
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
          "X-Rentivo-Analytics-Bill-Uuid-Hash": "bill-hash",
          "X-Rentivo-Analytics-Billing-Uuid-Hash": "billing-hash",
          "X-Rentivo-Analytics-Comm-Type": "payment_receipt",
          "X-Rentivo-Analytics-Count": "3",
          "X-Rentivo-Analytics-Line-Item-Count": "4",
          "X-Rentivo-Analytics-Method": "password",
          "X-Rentivo-Analytics-New-Status": "paid",
          "X-Rentivo-Analytics-Receipt-Count": "2",
          "X-Rentivo-Analytics-Recipient-Count": "5",
          "X-Rentivo-Analytics-Reference-Month": "2026-07",
          "X-Rentivo-Analytics-Scope": "user",
          "X-Rentivo-Analytics-Secret": "must-not-leak",
          "X-Rentivo-Analytics-Total-Amount-Brl": "2513",
          "X-Rentivo-Analytics-Total-Bytes": "2048",
          "X-Rentivo-Analytics-Via": "google"
        }
      })
    );
    pushAnalyticsFromResponse(new Response(null, { headers: {
      "X-Rentivo-Analytics-Count": "not-a-number",
      "X-Rentivo-Analytics-Event": "rentivo_invalid_numeric_dimension"
    } }));
    pushAnalyticsFromResponse(new Response(null));

    expect(window.dataLayer?.slice(-3)).toEqual([{
      event: "rentivo_login_failed",
      reason: "bad_credentials"
    }, {
      event: "rentivo_login_success",
      bill_uuid_hash: "bill-hash",
      billing_uuid_hash: "billing-hash",
      comm_type: "payment_receipt",
      count: 3,
      line_item_count: 4,
      method: "password",
      new_status: "paid",
      receipt_count: 2,
      recipient_count: 5,
      reference_month: "2026-07",
      scope: "user",
      total_amount_brl: 2513,
      total_bytes: 2048,
      via: "google"
    }, {
      event: "rentivo_invalid_numeric_dimension"
    }]);
  });
});

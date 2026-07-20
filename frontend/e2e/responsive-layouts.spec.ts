import { expect, test, type Page } from "@playwright/test";

import { installApiMocks } from "./support/api-mocks";

async function mockJson(page: Page, path: string, body: unknown) {
  await page.route(`**/api/v1${path}`, async (route) => {
    await route.fulfill({
      body: JSON.stringify(body),
      contentType: "application/json; charset=utf-8",
      status: 200
    });
  });
}

async function expectSingleColumn(page: Page, selector: string) {
  const grid = page.locator(selector);
  await expect(grid).toBeVisible();
  await expect.poll(() => grid.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length)).toBe(1);
}

test("populated detail and theme grids collapse to one column on mobile", async ({ isMobile, page }) => {
  test.skip(!isMobile, "Mobile layout regression");
  await installApiMocks(page, { pendingInviteCount: 0 });
  await mockJson(page, "/billings/billing-responsive", {
    capabilities: {
      can_create_bills: false,
      can_create_exports: false,
      can_delete: false,
      can_edit: false,
      can_manage_bills: false,
      can_manage_theme: false,
      can_read_attachments: false,
      can_read_bills: false,
      can_read_expenses: false,
      can_read_theme: false,
      can_transfer: false,
      can_upload_bill_receipts: false,
      can_write_attachments: false,
      can_write_expenses: false
    },
    communication_templates: [],
    created_at: "2026-07-17T15:00:00Z",
    description: "Cobrança responsiva",
    items: [{ amount: 100000, description: "Aluguel", item_type: "fixed", uuid: "item-responsive" }],
    name: "Apartamento responsivo",
    owner: { name: null, type: "user", uuid: null },
    pix_key: "ana@example.com",
    pix_merchant_city: "SAO PAULO",
    pix_merchant_name: "ANA SILVA",
    pix_needs_setup: false,
    recipients: [],
    reply_to: [],
    stats: {
      active_count: 0,
      billed_count: 0,
      expected: 0,
      net_income: 0,
      overdue: 0,
      overdue_count: 0,
      paid_count: 0,
      pending: 0,
      pending_count: 0,
      received: 0,
      total_expenses: 0,
      year: 2026
    },
    updated_at: "2026-07-17T15:00:00Z",
    uuid: "billing-responsive"
  });
  await mockJson(page, "/organizations/org-responsive", {
    capabilities: {
      can_create_billing: true,
      can_invite: true,
      can_manage: true,
      can_view_billing_stats: false
    },
    created_at: "2026-07-17T15:00:00Z",
    current_role: "admin",
    enforce_mfa: false,
    invites: [],
    members: [{ created_at: null, email: "ana@example.com", is_current_user: true, role: "admin", user_id: 42 }],
    name: "Organização responsiva",
    settings: { pix_key: "ana@example.com", pix_merchant_city: "SAO PAULO", pix_merchant_name: "ANA SILVA" },
    stats: null,
    updated_at: "2026-07-17T15:00:00Z",
    uuid: "org-responsive"
  });

  await page.goto("/billings/billing-responsive");
  await expect(page.getByRole("heading", { name: "Itens da cobrança" })).toBeVisible();
  await expectSingleColumn(page, ".billing-detail-grid");

  await page.goto("/organizations/org-responsive");
  await expect(page.getByRole("heading", { name: "Membros" })).toBeVisible();
  await expectSingleColumn(page, ".organization-detail-grid");

  await page.goto("/themes/user");
  await expect(page.getByRole("heading", { name: "Cores" })).toBeVisible();
  await expectSingleColumn(page, ".theme-color-grid");
});

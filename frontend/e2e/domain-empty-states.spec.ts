import { expect, test, type Page } from "@playwright/test";

import { installApiMocks } from "./support/api-mocks";

async function expectPath(page: Page, path: string) {
  await expect(page).toHaveURL((url) => url.pathname === path);
}

async function navigatePrimary(page: Page, isMobile: boolean, name: string, path: string) {
  const menu = page.getByRole("button", { name: "Menu" });
  if (isMobile) {
    await expect(menu).toBeVisible();
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await menu.click();
    await expect(menu).toHaveAttribute("aria-expanded", "true");
  } else {
    await expect(menu).toBeHidden();
  }

  await page.getByRole("link", { exact: true, name }).click();
  await expectPath(page, path);
  if (isMobile) await expect(menu).toHaveAttribute("aria-expanded", "false");
}

async function navigateAccount(page: Page, name: string, path: string) {
  const account = page.getByRole("button", { name: /ana@example\.com/i });
  await account.click();
  await expect(account).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("link", { exact: true, name }).click();
  await expectPath(page, path);
  await expect(account).toHaveAttribute("aria-expanded", "false");
}

test("a fresh account has complete authenticated destination pages", async ({ isMobile, page }) => {
  const api = await installApiMocks(page, { apiKeys: [], pendingInviteCount: 0 });

  await page.goto("/");
  await expectPath(page, "/billings/");
  await expect(page.getByRole("heading", { level: 1, name: "Minhas Cobranças" })).toBeVisible();
  await expect(page.getByText("Nenhuma cobrança cadastrada.")).toBeVisible();
  const createBilling = page.getByRole("link", { name: "Criar primeira cobrança" });
  await expect(createBilling).toHaveAttribute("href", "/billings/create");
  await createBilling.click();
  await expectPath(page, "/billings/create");

  await navigatePrimary(page, isMobile, "Organizações", "/organizations/");
  await expect(page.getByRole("heading", { level: 1, name: "Organizações" })).toBeVisible();
  await expect(page.getByText("Você não faz parte de nenhuma organização.")).toBeVisible();
  const createOrganization = page.getByRole("link", { name: "Criar organização" });
  await expect(createOrganization).toHaveAttribute("href", "/organizations/create");
  await createOrganization.click();
  await expectPath(page, "/organizations/create");

  if (isMobile) {
    await navigatePrimary(page, true, "Minhas Cobranças", "/billings/");
    await page.goto("/invites/");
  } else {
    await navigateAccount(page, "Convites", "/invites/");
  }
  await expect(page.getByRole("heading", { level: 1, name: "Convites Pendentes" })).toBeVisible();
  await expect(page.getByText("Nenhum convite pendente.")).toBeVisible();

  if (isMobile) await page.goto("/themes/user");
  else await navigateAccount(page, "Tema", "/themes/user");
  await expect(page.getByRole("heading", { level: 1, name: "Meu Tema" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Fontes" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Cores" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Pré-visualização" })).toBeVisible();
  await expect(page.getByLabel("Fonte do Cabeçalho")).toHaveValue("Montserrat");
  await expect(page.getByLabel("Fonte do Texto")).toHaveValue("Montserrat");
  await expect(page.getByRole("link", { name: "Voltar" })).toHaveAttribute("href", "/billings/");

  expect(api.unexpectedRequests).toEqual([]);
});

import { expect, test } from "@playwright/test";

import { installApiMocks, settleVisualPage } from "./support/api-mocks";

test("login visual parity", async ({ page }) => {
  await installApiMocks(page, { session: "anonymous" });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
  await settleVisualPage(page);

  await expect(page).toHaveScreenshot("login.png", { fullPage: true });
});

test("security visual parity", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/security");
  await expect(page.getByRole("heading", { name: "Chaves de Integração" })).toBeVisible();
  await settleVisualPage(page);

  await expect(page).toHaveScreenshot("security.png", { fullPage: true });
});

test("API-key form visual parity", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/security");
  await page.getByRole("button", { name: "Criar chave" }).click();
  await expect(page.getByRole("group", { name: "Espaços de trabalho" })).toBeVisible();
  await settleVisualPage(page);

  const apiKeyPanel = page.locator(".panel").filter({
    has: page.getByRole("heading", { name: "Chaves de Integração" })
  });
  await expect(apiKeyPanel).toHaveScreenshot("api-key-form.png");
});

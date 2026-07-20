import { expect, test } from "@playwright/test";

import { defaultSecuritySummary, installApiMocks } from "./support/api-mocks";

test("updates PIX and password, then reveals regenerated recovery codes once", async ({ page }) => {
  const api = await installApiMocks(page);
  await page.goto("/security");
  await expect(page.getByRole("heading", { name: "Segurança" })).toBeVisible();

  await page.getByLabel("Chave PIX").fill("financeiro@example.com");
  await page.getByLabel("Nome do recebedor").fill("FINANCEIRO ACME");
  await page.getByLabel("Cidade do recebedor").fill("CAMPINAS");
  await page.getByRole("button", { name: "Salvar Dados PIX" }).click();
  await expect(page.getByRole("status")).toContainText("Dados do PIX atualizados.");

  await page.getByLabel("Senha atual").fill("current-password-e2e");
  await page.getByLabel("Nova senha", { exact: true }).fill("new-password-e2e");
  await page.getByLabel("Confirmar nova senha").fill("new-password-e2e");
  await page.getByRole("button", { name: "Alterar Senha" }).click();
  await expect(page.getByRole("status")).toContainText("Senha alterada com sucesso!");
  await expect(page.getByLabel("Senha atual")).toHaveValue("");

  await page.getByRole("button", { name: "Regenerar Códigos de Recuperação" }).click();
  await expect(page).toHaveURL(/\/security\/recovery-codes$/);
  await expect(
    page.getByRole("heading", { exact: true, name: "Códigos de Recuperação" })
  ).toBeVisible();
  await expect(page.getByText("RECOVERY-ALPHA")).toBeVisible();

  const pix = api.requests.find((request) => request.path === "/security/pix");
  expect(pix?.body).toEqual({
    pix_key: "financeiro@example.com",
    pix_merchant_city: "CAMPINAS",
    pix_merchant_name: "FINANCEIRO ACME"
  });
  expect(api.requests.some((request) => request.path === "/security/change-password")).toBe(true);
  expect(api.unexpectedRequests).toEqual([]);
});

test("completes TOTP setup and registers a passkey through browser credentials", async ({ page }) => {
  const security = {
    ...defaultSecuritySummary,
    passkeys: [],
    totp: { enabled: false, recovery_codes_remaining: 0 }
  };
  const api = await installApiMocks(page, { security });
  await page.goto("/security");

  await page.getByRole("link", { name: "Configurar TOTP" }).click();
  await expect(page.getByRole("img", { name: "QR Code TOTP" })).toBeVisible();
  await page.getByLabel("Código de verificação").fill("123456");
  await page.getByRole("button", { name: "Confirmar e Ativar" }).click();
  await expect(page.getByText("RECOVERY-BRAVO")).toBeVisible();

  await page.getByRole("button", { name: "Continuar" }).click();
  await page.getByLabel("Nome da passkey").fill("Celular E2E");
  await page.getByRole("button", { name: "Adicionar Passkey" }).click();
  await expect(page.getByRole("status")).toContainText("Passkey cadastrada.");
  await expect(page.getByText("Celular E2E")).toBeVisible();

  const registration = api.requests.find(
    (request) => request.path === "/security/passkeys/register/complete"
  );
  expect(registration?.body).toMatchObject({
    challenge_id: "passkey-challenge-e2e",
    name: "Celular E2E"
  });
  expect(api.unexpectedRequests).toEqual([]);
});

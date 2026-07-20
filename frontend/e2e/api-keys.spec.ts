import { expect, test } from "@playwright/test";

import { TEST_API_SECRET, installApiMocks } from "./support/api-mocks";

test("creates a scoped multi-workspace key, reveals it once, and revokes it", async ({ page }) => {
  const api = await installApiMocks(page, { apiKeys: [] });
  await page.goto("/security");
  await expect(page.getByRole("heading", { name: "Chaves de Integração" })).toBeVisible();

  await page.getByRole("button", { name: "Criar chave" }).click();
  await page.getByLabel("Nome", { exact: true }).fill("Aplicativo móvel");
  await page.getByLabel("Consultar perfil").check();
  await page.getByLabel("Consultar cobranças").check();
  await page.getByRole("checkbox", { name: "Pessoal", exact: true }).check();
  await page.getByLabel("Acme Administração").check();
  await page.getByLabel("Expira em").fill("2026-10-15");
  await page.getByRole("button", { name: "Criar chave" }).click();

  const secretDialog = page.getByRole("dialog", { name: "Chave de integração criada" });
  await expect(secretDialog).toBeVisible();
  await expect(secretDialog.getByText(TEST_API_SECRET)).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /Guardei esta chave/i })).toBeFocused();
  await expect(page.getByRole("button", { name: "Concluir" })).toBeDisabled();
  await page.getByRole("checkbox", { name: /Guardei esta chave/i }).check();
  await page.getByRole("button", { name: "Concluir" }).click();

  await expect(secretDialog).toBeHidden();
  await expect(page.getByText("Aplicativo móvel")).toBeVisible();
  await page.getByRole("button", { name: "Revogar Aplicativo móvel" }).click();
  const revokeDialog = page.getByRole("dialog", { name: "Revogar chave" });
  await expect(revokeDialog).toBeVisible();
  await expect(revokeDialog.getByRole("button", { name: "Voltar" })).toBeFocused();
  await revokeDialog.getByRole("button", { name: "Revogar chave" }).click();
  await expect(page.getByText("Revogada", { exact: true })).toBeVisible();

  const creation = api.requests.find(
    (request) => request.method === "POST" && request.path === "/api-keys"
  );
  expect(creation?.body).toMatchObject({
    grants: [
      { resource_id: "personal", resource_type: "user" },
      {
        resource_id: "11111111-1111-4111-8111-111111111111",
        resource_type: "organization"
      }
    ],
    name: "Aplicativo móvel",
    scopes: ["profile:read", "billings:read"]
  });
  expect(api.unexpectedRequests).toEqual([]);
});

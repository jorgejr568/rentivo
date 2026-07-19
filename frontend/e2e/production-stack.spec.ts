import { expect, request as playwrightRequest, test } from "@playwright/test";

const productionStackMode = process.env.PLAYWRIGHT_PRODUCTION_STACK === "1";

test.skip(
  !productionStackMode,
  "Set PLAYWRIGHT_PRODUCTION_STACK=1 and PLAYWRIGHT_BASE_URL (or BASE_URL) to run against the real stack."
);
test.setTimeout(120_000);

test("exercises the replacement stack without network interception", async ({ baseURL, page }) => {
  expect(baseURL, "The production-stack project requires an external base URL.").toBeTruthy();
  const origin = new URL(baseURL!).origin;
  const unique = `${Date.now()}-${process.pid}`;
  const email = `production-stack-${unique}@example.com`;
  const password = `Release-${unique}-Aa1!`;

  await test.step("serve public metadata and crawler contracts", async () => {
    await page.goto("/");
    await expect(page).toHaveTitle("Rentivo — Gestão de cobranças para imóveis com PIX");
    await expect(
      page.getByRole("heading", { level: 1, name: /cobranças de aluguel.*pix em segundos/i })
    ).toBeVisible();
    await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /plataforma gratuita/i);
    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute("content", /Rentivo/);

    const robots = await page.request.get("/robots.txt");
    expect(robots.status()).toBe(200);
    expect(robots.headers()["content-type"]).toMatch(/^text\/plain(?:;|$)/);
    expect(await robots.text()).toContain(`Sitemap: ${origin}/sitemap.xml`);

    const sitemap = await page.request.get("/sitemap.xml");
    expect(sitemap.status()).toBe(200);
    expect(sitemap.headers()["content-type"]).toMatch(/^application\/xml(?:;|$)/);
    expect(await sitemap.text()).toContain(`<loc>${origin}/</loc>`);
  });

  await test.step("create a fresh account and render every empty destination", async () => {
    await page.goto("/signup");
    await page.getByLabel("E-mail").fill(email);
    await page.getByLabel("Senha", { exact: true }).fill(password);
    await page.getByLabel("Confirmar Senha").fill(password);
    await page.getByRole("button", { name: "Criar Conta" }).click();

    await expect(page).toHaveURL(/\/billings\/$/);
    await expect(page.getByText("Nenhuma cobrança cadastrada.")).toBeVisible();

    await page.goto("/organizations/");
    await expect(page.getByText("Você não faz parte de nenhuma organização.")).toBeVisible();

    await page.goto("/themes/user");
    await expect(page.getByRole("heading", { level: 1, name: "Meu Tema" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Fontes" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Cores" })).toBeVisible();

    await page.goto("/security");
    await expect(page.getByRole("heading", { name: "Segurança" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Chaves de Integração" })).toBeVisible();
    await page.getByRole("link", { name: "Configurar TOTP" }).click();
    await expect(page).toHaveURL(/\/security\/totp\/setup$/);
    await expect(page.getByRole("heading", { name: /Configurar TOTP/i })).toBeVisible();
  });

  let organizationUuid = "";
  await test.step("deny an organization outside an integration key grant", async () => {
    await page.goto("/organizations/create");
    await page.getByLabel("Nome", { exact: true }).fill(`Organização ${unique}`);
    await page.getByRole("button", { name: "Criar organização" }).click();
    await expect(page).toHaveURL(/\/organizations\/[0-9a-f-]+$/);
    organizationUuid = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1)!;

    await page.goto("/security");
    await page.getByRole("button", { name: "Criar chave" }).click();
    await page.getByLabel("Nome", { exact: true }).fill(`Gate ${unique}`);
    await page.getByLabel("Consultar organizações").check();
    await page.getByRole("checkbox", { name: "Pessoal", exact: true }).check();
    await page.getByRole("button", { name: "Criar chave" }).click();

    const dialog = page.getByRole("dialog", { name: "Chave de integração criada" });
    await expect(dialog).toBeVisible();
    const integrationSecret = (await dialog.locator(".secret-key").textContent())?.trim();
    expect(integrationSecret).toMatch(/^rntv-v1-/);

    const integration = await playwrightRequest.newContext({
      baseURL: origin,
      extraHTTPHeaders: { Authorization: `Bearer ${integrationSecret}` }
    });
    try {
      const denied = await integration.get(`/api/v1/organizations/${organizationUuid}`);
      expect(denied.status()).toBe(404);
      expect(denied.headers()["content-type"]).toMatch(/^application\/problem\+json(?:;|$)/);
      expect(await denied.json()).toMatchObject({ code: "not_found", status: 404 });
    } finally {
      await integration.dispose();
    }

    await dialog.getByRole("checkbox", { name: /Guardei esta chave/i }).check();
    await dialog.getByRole("button", { name: "Concluir" }).click();
  });

  await test.step("create a billing and its first real invoice", async () => {
    await page.goto("/billings/create");
    await page.getByLabel("Nome do imóvel").fill(`Apartamento ${unique}`);
    await page.getByLabel("Chave PIX").fill(email);
    await page.getByLabel("Nome do recebedor").fill("RENTIVO RELEASE");
    await page.getByLabel("Cidade do recebedor").fill("SALVADOR");
    await page.getByLabel("Descrição do item 1").fill("Aluguel");
    await page.getByLabel("Valor do item 1 (R$)").fill("1.250,00");
    await page.getByRole("button", { name: "Criar cobrança" }).click();

    await expect(page).toHaveURL(/\/billings\/[0-9a-f-]+$/);
    await expect(page.getByText("Nenhuma fatura gerada para este imóvel.")).toBeVisible();
    await page.getByRole("link", { name: "Gerar primeira fatura" }).click();
    await page.getByLabel("Mês de Referência").fill("2030-12");
    await page.getByLabel("Vencimento").fill("10/12/2030");
    await page.getByRole("button", { name: "Gerar Fatura" }).click();

    await expect(page).toHaveURL(/\/billings\/[0-9a-f-]+\/bills\/[0-9a-f-]+$/);
    const billPath = new URL(page.url()).pathname;
    const [billingUuid, billUuid] = billPath.split("/").filter(Boolean).filter((part) => part !== "billings" && part !== "bills");
    await expect.poll(
      async () => {
        const response = await page.request.get(`/api/v1/billings/${billingUuid}/bills/${billUuid}`);
        expect(response.status()).toBe(200);
        return (await response.json() as { pdf_render_status: string | null }).pdf_render_status;
      },
      { message: "The worker did not finish the invoice PDF.", timeout: 60_000 }
    ).toBe("succeeded");

    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: "Fatura · Dezembro 2030" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Abrir PDF com QR" })).toBeVisible();
    const invoice = await page.request.get(`/api/v1/billings/${billingUuid}/bills/${billUuid}/invoice`);
    expect(invoice.status()).toBe(200);
    expect(invoice.headers()["content-type"]).toMatch(/^application\/pdf(?:;|$)/);
  });

  await test.step("revoke the login token on logout", async () => {
    const authenticatedCookies = await page.context().cookies();
    const accessCookie = authenticatedCookies.find((cookie) => cookie.name.endsWith("rentivo_access"));
    expect(accessCookie, "Expected the HttpOnly login-token cookie before logout.").toBeTruthy();

    await page.getByRole("button", { name: new RegExp(email, "i") }).click();
    await page.getByRole("button", { name: "Sair" }).click();
    await expect(page).toHaveURL(/\/login$/);

    const replay = await playwrightRequest.newContext({
      baseURL: origin,
      extraHTTPHeaders: { Cookie: `${accessCookie!.name}=${accessCookie!.value}` }
    });
    try {
      const revoked = await replay.get("/api/v1/auth/session");
      expect(revoked.status()).toBe(401);
      expect(await revoked.json()).toMatchObject({ code: "authentication_required", status: 401 });
    } finally {
      await replay.dispose();
    }

    await page.getByLabel("E-mail").fill(email);
    await page.getByLabel("Senha", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page).toHaveURL(/\/billings\/$/);
  });
});

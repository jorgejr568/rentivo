import { expect, test } from "@playwright/test";

import { installApiMocks } from "./support/api-mocks";

test("password login establishes the shell session and preserves the legacy destination", async ({
  isMobile,
  page
}) => {
  const api = await installApiMocks(page, { session: "anonymous" });
  await page.goto("/login");

  await page.getByLabel("E-mail").fill("ana@example.com");
  await page.getByLabel("Senha", { exact: true }).fill("correct-horse-e2e");
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page).toHaveURL(/\/billings\/$/);
  await expect(page.getByRole("navigation")).toBeVisible();
  if (isMobile) {
    await page.getByRole("button", { name: "Menu" }).click();
    await expect(page.getByRole("link", { name: "Minhas Cobranças" })).toBeVisible();
  } else {
    await expect(page.getByRole("button", { name: /ana@example\.com/i })).toBeVisible();
  }

  const login = api.requests.find(
    (request) => request.method === "POST" && request.path === "/auth/login"
  );
  expect(login?.body).toEqual({
    email: "ana@example.com",
    password: "correct-horse-e2e",
    turnstile_token: ""
  });
  expect(api.unexpectedRequests).toEqual([]);
});

test("protected routes do not render or request private data before session validation", async ({
  page
}) => {
  const api = await installApiMocks(page, { session: "pending" });
  await page.goto("/security");

  await expect(page.getByRole("heading", { name: "Segurança" })).toHaveCount(0);
  expect(api.requests.some((request) => request.path === "/security")).toBe(false);

  api.releaseSession("authenticated");
  await expect(page.getByRole("heading", { name: "Segurança" })).toBeVisible();
  expect(api.requests.some((request) => request.path === "/security")).toBe(true);
  expect(api.unexpectedRequests).toEqual([]);
});

test("anonymous visitors are redirected before a protected screen can load", async ({ page }) => {
  const api = await installApiMocks(page, { session: "anonymous" });
  await page.goto("/security");

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Segurança" })).toHaveCount(0);
  expect(api.requests.some((request) => request.path === "/security")).toBe(false);
  expect(api.unexpectedRequests).toEqual([]);
});

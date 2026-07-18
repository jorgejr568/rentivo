import { expect, test, type Page } from "@playwright/test";

import { installApiMocks } from "./support/api-mocks";

async function expectAccessibleFundamentals(page: Page) {
  const issues = await page.locator("body").evaluate(() => {
    const visible = (element: HTMLElement) => {
      const style = getComputedStyle(element);
      return style.display !== "none" && style.visibility !== "hidden";
    };
    const duplicateIds = Array.from(document.querySelectorAll<HTMLElement>("[id]"))
      .map((element) => element.id)
      .filter((id, index, ids) => id && ids.indexOf(id) !== index);
    const unnamedButtons = Array.from(document.querySelectorAll<HTMLButtonElement>("button"))
      .filter(visible)
      .filter((button) => !(button.innerText.trim() || button.getAttribute("aria-label")))
      .map((button) => button.outerHTML);
    const unlabeledInputs = Array.from(
      document.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(
        "input:not([type=hidden]), select, textarea"
      )
    )
      .filter(visible)
      .filter(
        (input) =>
          input.labels?.length === 0 &&
          !input.getAttribute("aria-label") &&
          !input.getAttribute("aria-labelledby")
      )
      .map((input) => input.outerHTML);
    const imagesWithoutAlt = Array.from(document.querySelectorAll<HTMLImageElement>("img"))
      .filter(visible)
      .filter((image) => !image.hasAttribute("alt"))
      .map((image) => image.outerHTML);
    const focusableHiddenContent = Array.from(
      document.querySelectorAll<HTMLElement>(
        '[aria-hidden="true"] a, [aria-hidden="true"] button, [aria-hidden="true"] input, [aria-hidden="true"] [tabindex]:not([tabindex="-1"])'
      )
    ).map((element) => element.outerHTML);
    return { duplicateIds, focusableHiddenContent, imagesWithoutAlt, unlabeledInputs, unnamedButtons };
  });
  expect(issues).toEqual({
    duplicateIds: [],
    focusableHiddenContent: [],
    imagesWithoutAlt: [],
    unlabeledInputs: [],
    unnamedButtons: []
  });
}

test("public authentication has a main landmark, labels, and a logical keyboard path", async ({
  page
}) => {
  await installApiMocks(page, { session: "anonymous" });
  await page.goto("/login");

  await expect(page.getByRole("main")).toHaveCount(1);
  await expect(page.getByLabel("E-mail")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Senha", { exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Esqueceu sua senha?" })).toBeFocused();
  await expectAccessibleFundamentals(page);
});

test("security exposes navigation and main landmarks without unlabeled controls", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/security");

  await expect(page.getByRole("navigation")).toHaveCount(1);
  await expect(page.getByRole("main")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "Segurança" })).toBeVisible();
  await expectAccessibleFundamentals(page);

  await page.getByRole("button", { name: "Revogar Painel financeiro" }).focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Revogar chave" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Voltar" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Revogar Painel financeiro" })).toBeFocused();
});

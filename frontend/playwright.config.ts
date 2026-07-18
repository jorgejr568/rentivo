import { defineConfig } from "@playwright/test";
import process from "node:process";

const PORT = 4173;

export default defineConfig({
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.001
    }
  },
  forbidOnly: Boolean(process.env.CI),
  fullyParallel: false,
  outputDir: "test-results/playwright",
  projects: [
    {
      name: "desktop",
      use: { viewport: { height: 900, width: 1440 } }
    },
    {
      name: "mobile",
      use: { isMobile: true, viewport: { height: 844, width: 390 } }
    }
  ],
  reporter: process.env.CI ? "github" : "list",
  retries: process.env.CI ? 1 : 0,
  snapshotPathTemplate: "{testDir}/snapshots/{platform}/{projectName}/{arg}{ext}",
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    colorScheme: "light",
    contextOptions: { reducedMotion: "reduce" },
    locale: "pt-BR",
    permissions: ["clipboard-read", "clipboard-write"],
    timezoneId: "America/Sao_Paulo",
    trace: "off"
  },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    url: `http://127.0.0.1:${PORT}`
  },
  workers: 1
});

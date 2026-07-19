import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { AUTH_CONFIG, AUTHENTICATED_RESPONSE, jsonResponse } from "../../test/auth";
import { AuthProvider } from "../auth/AuthProvider";
import { RecoveryCodesPage } from "./RecoveryCodesPage";

function LocationProbe() {
  return <span>{useLocation().pathname}</span>;
}

function renderRecovery(recoveryCodes?: string[]) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (url === "/api/v1/auth/session") return jsonResponse(AUTHENTICATED_RESPONSE);
    throw new Error(`Unexpected request: ${url}`);
  }));
  const entry = recoveryCodes
    ? { pathname: "/security/recovery-codes", state: { recoveryCodes } }
    : "/security/recovery-codes";
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AuthProvider>
        <Routes>
          <Route element={<RecoveryCodesPage />} path="/security/recovery-codes" />
          <Route element={<LocationProbe />} path="/security" />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

afterEach(() => vi.unstubAllGlobals());

it("shows and copies one-time recovery codes", async () => {
  const user = userEvent.setup();
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
  renderRecovery(["one", "two"]);

  expect(screen.getByText("one")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Copiar todos" }));
  expect(writeText).toHaveBeenCalledWith("one\ntwo");
  expect(screen.getByRole("button", { name: "Copiado!" })).toBeVisible();
});

it("returns to security when codes are absent", () => {
  renderRecovery();
  expect(screen.getByText("/security")).toBeVisible();
});

it("reports clipboard failures", async () => {
  const user = userEvent.setup();
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
  renderRecovery(["one"]);
  await user.click(screen.getByRole("button", { name: "Copiar todos" }));
  expect(await screen.findByText("Não foi possível copiar os códigos.")).toBeVisible();
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, it, vi } from "vitest";

import { RecoveryCodesPage } from "./RecoveryCodesPage";

it("shows and copies one-time recovery codes", async () => {
  const user = userEvent.setup();
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
  render(
    <MemoryRouter initialEntries={[{ pathname: "/security/recovery-codes", state: { recoveryCodes: ["one", "two"] } }]}>
      <Routes><Route element={<RecoveryCodesPage />} path="/security/recovery-codes" /></Routes>
    </MemoryRouter>
  );

  expect(screen.getByText("one")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Copiar todos" }));
  expect(writeText).toHaveBeenCalledWith("one\ntwo");
  expect(screen.getByRole("button", { name: "Copiado!" })).toBeVisible();
});

it("returns to security when codes are absent", () => {
  function Probe() { return <span>{useLocation().pathname}</span>; }
  render(<MemoryRouter initialEntries={["/security/recovery-codes"]}><Routes><Route element={<RecoveryCodesPage />} path="/security/recovery-codes" /><Route element={<Probe />} path="/security" /></Routes></MemoryRouter>);
  expect(screen.getByText("/security")).toBeVisible();
});

it("reports clipboard failures", async () => {
  const user = userEvent.setup();
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
  render(<MemoryRouter initialEntries={[{ pathname: "/security/recovery-codes", state: { recoveryCodes: ["one"] } }]}><Routes><Route element={<RecoveryCodesPage />} path="/security/recovery-codes" /></Routes></MemoryRouter>);
  await user.click(screen.getByRole("button", { name: "Copiar todos" }));
  expect(await screen.findByText("Não foi possível copiar os códigos.")).toBeVisible();
});

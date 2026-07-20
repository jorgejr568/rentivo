import { render, screen, waitFor } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";

import { App } from "./App";
import { AUTH_CONFIG, AUTHENTICATED_RESPONSE, jsonResponse } from "../test/auth";
import { createAppRouter } from "./router";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
    if (String(input) === "/api/v1/auth/session") {
      return jsonResponse(AUTHENTICATED_RESPONSE);
    }
    throw new Error(`Unexpected request: ${String(input)}`);
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the application providers and shell after session authentication", async () => {
    render(<App />);

    await waitFor(() => expect(window.location.pathname).toBe("/billings/"));
    expect(await screen.findByRole("button", { name: "user@example.com" })).toBeVisible();
    expect(screen.getByRole("main")).toHaveClass("wrapper", "main-content");
  });

  it("renders feature routes through the shell outlet", async () => {
    window.history.pushState({}, "", "/feature-preview");
    const router = createAppRouter([
      { element: <h1>Prévia da funcionalidade</h1>, path: "/feature-preview" }
    ]);

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "Prévia da funcionalidade" })).toBeVisible();
    expect(screen.getByRole("main")).toContainElement(screen.getByRole("heading"));
    router.dispose();
    window.history.pushState({}, "", "/");
  });
});

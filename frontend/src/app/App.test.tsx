import { render, screen } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";

import { App } from "./App";
import { createAppRouter } from "./router";

describe("App", () => {
  it("renders the application providers and shell", () => {
    render(<App />);

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

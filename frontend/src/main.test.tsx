import { act, screen } from "@testing-library/react";
import { vi } from "vitest";

import { AUTH_CONFIG, AUTHENTICATED_RESPONSE, jsonResponse } from "./test/auth";

describe("main", () => {
  it("mounts the application into the root element", async () => {
    document.body.innerHTML = '<div id="root"></div>';
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
      if (String(input) === "/api/v1/auth/session") {
        return jsonResponse(AUTHENTICATED_RESPONSE);
      }
      throw new Error(`Unexpected request: ${String(input)}`);
    }));

    let appRoot: Awaited<typeof import("./main")>["appRoot"];
    await act(async () => {
      ({ appRoot } = await import("./main"));
    });

    expect(await screen.findByRole("main")).toBeInTheDocument();
    act(() => appRoot.unmount());
    vi.unstubAllGlobals();
  });
});

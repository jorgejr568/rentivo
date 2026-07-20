import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { vi } from "vitest";

import { AuthProvider } from "../features/auth/AuthProvider";
import { AUTH_CONFIG, AUTHENTICATED_RESPONSE, jsonResponse, problemResponse } from "./auth";

type Handler = (init: RequestInit | undefined) => Promise<Response> | Response;

interface RenderAuthOptions {
  configHandler?: Handler;
  handlers?: Record<string, Handler>;
  path?: string;
  session?: "anonymous" | "authenticated";
  sessionHandler?: Handler;
}

// eslint-disable-next-line react-refresh/only-export-components
function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

export function renderAuth(
  element: ReactElement,
  {
    configHandler,
    handlers = {},
    path = "/login",
    session = "anonymous",
    sessionHandler
  }: RenderAuthOptions = {}
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/auth/config") {
      return configHandler ? configHandler(init) : jsonResponse(AUTH_CONFIG);
    }
    if (url === "/api/v1/auth/session") {
      if (sessionHandler) {
        return sessionHandler(init);
      }
      return session === "authenticated"
        ? jsonResponse(AUTHENTICATED_RESPONSE)
        : problemResponse();
    }
    const handler = handlers[url];
    if (handler) {
      return handler(init);
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        {element}
        <LocationProbe />
      </AuthProvider>
    </MemoryRouter>
  );
  return { ...view, fetchMock };
}

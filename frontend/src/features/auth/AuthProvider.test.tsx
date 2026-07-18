import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient, apiRequest } from "../../lib/api/client";
import {
  AUTH_CONFIG,
  AUTHENTICATED_RESPONSE,
  AUTHENTICATED_WITH_EVENT,
  jsonResponse,
  problemResponse
} from "../../test/auth";
import {
  AuthenticatedAppShell,
  AuthProvider,
  postLoginPath,
  useAuth
} from "./AuthProvider";
import { saveMfaChallenge } from "./authStorage";

function Probe() {
  const auth = useAuth();
  const location = useLocation();
  return (
    <>
      <span>{auth.status}</span>
      <span>{auth.configStatus}</span>
      <span>{auth.bootstrap?.user.email ?? "sem usuário"}</span>
      <span data-testid="path">{location.pathname}</span>
      <button onClick={() => auth.authenticate(AUTHENTICATED_WITH_EVENT)} type="button">
        autenticar
      </button>
      <button onClick={() => void auth.logout()} type="button">
        sair
      </button>
      <button onClick={auth.retryConfig} type="button">
        tentar configuração
      </button>
      <button onClick={auth.retrySession} type="button">
        tentar sessão
      </button>
      <button
        onClick={() => void apiRequest(apiClient.GET("/api/v1/profile")).catch(() => undefined)}
        type="button"
      >
        expirar
      </button>
    </>
  );
}

function Wrapper({ children, path = "/private" }: { children: ReactNode; path?: string }) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>{children}</AuthProvider>
    </MemoryRouter>
  );
}

function installFetch({
  configFailures = 0,
  session = "authenticated"
}: {
  configFailures?: number;
  session?: "anonymous" | "authenticated";
} = {}) {
  let remainingConfigFailures = configFailures;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    const url = String(input);
    if (url === "/api/v1/auth/config") {
      if (remainingConfigFailures > 0) {
        remainingConfigFailures -= 1;
        return new Response(null, { status: 503 });
      }
      return jsonResponse(AUTH_CONFIG);
    }
    if (url === "/api/v1/auth/session") {
      return session === "authenticated"
        ? jsonResponse(AUTHENTICATED_RESPONSE)
        : problemResponse();
    }
    if (url === "/api/v1/auth/logout") {
      return new Response(null, {
        headers: { "X-Rentivo-Analytics-Event": "rentivo_logout" },
        status: 204
      });
    }
    if (url === "/api/v1/profile") {
      return problemResponse();
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  delete window.dataLayer;
  document.head.querySelectorAll("script[data-rentivo-gtm]").forEach((script) => script.remove());
});

describe("AuthProvider", () => {
  it("bootstraps non-secret session and authentication configuration", async () => {
    installFetch();

    render(
      <Wrapper>
        <Probe />
      </Wrapper>
    );

    expect(await screen.findByText("user@example.com")).toBeVisible();
    expect(screen.getByText("authenticated")).toBeVisible();
    expect(screen.getByText("ready")).toBeVisible();
    expect(document.querySelector("script[data-rentivo-gtm]")).toBeInTheDocument();
  });

  it("clears an anonymous startup session for the route guard", async () => {
    installFetch({ session: "anonymous" });

    render(
      <Wrapper>
        <Probe />
      </Wrapper>
    );

    expect(await screen.findByText("anonymous")).toBeVisible();
    expect(screen.getByTestId("path")).toHaveTextContent("/private");
  });

  it("preserves public MFA progress during anonymous session bootstrap", async () => {
    installFetch({ session: "anonymous" });
    saveMfaChallenge({ challengeId: "challenge", methods: ["totp", "recovery"] });

    render(
      <Wrapper path="/mfa-verify">
        <Probe />
      </Wrapper>
    );

    expect(await screen.findByText("anonymous")).toBeVisible();
    expect(sessionStorage.getItem("rentivo.auth.mfa")).toContain("challenge");
  });

  it.each([
    "/login",
    "/signup",
    "/mfa-verify",
    "/forgot-password",
    "/reset-password",
    "/auth/google/callback"
  ])("keeps anonymous visitors on the public auth URL %s", async (path) => {
    installFetch({ session: "anonymous" });

    render(
      <Wrapper path={path}>
        <Probe />
      </Wrapper>
    );

    expect(await screen.findByText("anonymous")).toBeVisible();
    expect(screen.getByTestId("path")).toHaveTextContent(path);
  });

  it("retries a failed public configuration request", async () => {
    const user = userEvent.setup();
    installFetch({ configFailures: 1 });

    render(
      <Wrapper>
        <Probe />
      </Wrapper>
    );

    expect(await screen.findByText("error")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "tentar configuração" }));
    expect(await screen.findByText("ready")).toBeVisible();
  });

  it("keeps a transient session failure retryable without treating it as logout", async () => {
    const user = userEvent.setup();
    let sessionAttempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/v1/auth/config") return jsonResponse(AUTH_CONFIG);
        if (url === "/api/v1/auth/session") {
          sessionAttempts += 1;
          return sessionAttempts === 1
            ? new Response(null, { status: 503 })
            : jsonResponse(AUTHENTICATED_RESPONSE);
        }
        throw new Error(`Unexpected request: ${url}`);
      })
    );

    render(
      <Wrapper>
        <Probe />
      </Wrapper>
    );

    expect(await screen.findByText("error")).toBeVisible();
    expect(screen.getByTestId("path")).toHaveTextContent("/private");
    await user.click(screen.getByRole("button", { name: "tentar sessão" }));
    expect(await screen.findByText("authenticated")).toBeVisible();
    expect(screen.getByText("user@example.com")).toBeVisible();
  });

  it("accepts login bootstrap, clears challenge state, and pushes its analytics", async () => {
    const user = userEvent.setup();
    installFetch({ session: "anonymous" });
    saveMfaChallenge({ challengeId: "challenge", methods: ["totp"] });

    render(
      <Wrapper path="/login">
        <Probe />
      </Wrapper>
    );

    await screen.findByText("anonymous");
    await user.click(screen.getByRole("button", { name: "autenticar" }));

    expect(screen.getByText("authenticated")).toBeVisible();
    expect(sessionStorage.getItem("rentivo.auth.mfa")).toBeNull();
    expect(window.dataLayer?.at(-1)).toEqual({
      event: "rentivo_login_success",
      reason: null,
      via: "password"
    });
  });

  it("does not let a delayed anonymous bootstrap undo a completed login", async () => {
    const user = userEvent.setup();
    let resolveSession!: (response: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/v1/auth/config") {
          return jsonResponse(AUTH_CONFIG);
        }
        if (url === "/api/v1/auth/session") {
          return new Promise<Response>((resolve) => {
            resolveSession = resolve;
          });
        }
        throw new Error(`Unexpected request: ${url}`);
      })
    );

    render(
      <Wrapper path="/login">
        <Probe />
      </Wrapper>
    );

    expect(await screen.findByText("ready")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "autenticar" }));
    expect(screen.getByText("authenticated")).toBeVisible();

    await act(async () => resolveSession(problemResponse()));

    expect(screen.getByText("authenticated")).toBeVisible();
    expect(screen.getByText("user@example.com")).toBeVisible();
    expect(screen.getByTestId("path")).toHaveTextContent("/login");
  });

  it("sends CSRF on logout, clears state, navigates, and pushes the event", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetch();

    render(
      <Wrapper>
        <Probe />
      </Wrapper>
    );

    await screen.findByText("authenticated");
    await user.click(screen.getByRole("button", { name: "sair" }));

    await waitFor(() => expect(screen.getByText("anonymous")).toBeVisible());
    expect(screen.getByTestId("path")).toHaveTextContent("/login");
    const logoutCall = fetchMock.mock.calls.find(([url]) => url === "/api/v1/auth/logout");
    expect(new Headers(logoutCall?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-token");
    expect(window.dataLayer?.at(-1)).toEqual({ event: "rentivo_logout" });
  });

  it("globally expires a later authenticated request", async () => {
    const user = userEvent.setup();
    installFetch();

    render(
      <Wrapper>
        <Probe />
      </Wrapper>
    );

    await screen.findByText("authenticated");
    await user.click(screen.getByRole("button", { name: "expirar" }));

    await waitFor(() => expect(screen.getByText("anonymous")).toBeVisible());
    expect(screen.getByTestId("path")).toHaveTextContent("/login");
  });

  it("connects authenticated bootstrap data to the existing shell", async () => {
    installFetch();

    render(
      <Wrapper>
        <AuthenticatedAppShell />
      </Wrapper>
    );

    expect(await screen.findByRole("button", { name: /user@example.com/i })).toBeVisible();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("requires the hook to be rendered inside its provider", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    expect(() =>
      render(
        <MemoryRouter>
          <Probe />
        </MemoryRouter>
      )
    ).toThrow("useAuth deve ser usado dentro de AuthProvider.");
  });
});

describe("postLoginPath", () => {
  it("preserves normal and organization-enforced MFA destinations", () => {
    expect(postLoginPath(AUTHENTICATED_RESPONSE.bootstrap)).toBe("/billings/");
    expect(
      postLoginPath({
        ...AUTHENTICATED_RESPONSE.bootstrap,
        capabilities: {
          ...AUTHENTICATED_RESPONSE.bootstrap.capabilities,
          mfa_setup_required: true
        }
      })
    ).toBe("/security/totp/setup");
  });
});

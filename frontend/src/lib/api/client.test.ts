import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  apiClient,
  apiRequest,
  setCsrfToken,
  setUnauthorizedHandler
} from "./client";

const problem = {
  code: "authentication_required",
  detail: "Autenticação necessária.",
  fields: {},
  request_id: "problem-request-id",
  status: 401,
  title: "Não autenticado",
  type: "https://rentivo.app/problems/authentication_required"
};

afterEach(() => {
  setCsrfToken("");
  setUnauthorizedHandler(null);
  vi.unstubAllGlobals();
});

describe("typed API client", () => {
  it("uses the versioned same-origin JSON API and captures request IDs", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "response-request-id"
        }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiRequest(apiClient.GET("/api/v1/health"));

    expect(result.data).toEqual({ status: "ok" });
    expect(result.requestId).toBe("response-request-id");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/health",
      expect.objectContaining({ credentials: "same-origin", method: "GET" })
    );
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("Accept")).toBe(
      "application/json"
    );
  });

  it("adds JSON and CSRF headers only to authenticated mutations", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf-token");

    const result = await apiRequest(
      apiClient.POST("/api/v1/security/totp/disable", {
        body: { password: "password" }
      })
    );
    await apiRequest(
      apiClient.POST("/api/v1/auth/login", {
        body: {
          email: "user@example.com",
          password: "password",
          turnstile_token: ""
        },
        headers: { "X-Test": "present" }
      })
    );

    expect(result.data).toBeUndefined();
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/security/totp/disable",
      expect.objectContaining({ body: JSON.stringify({ password: "password" }) })
    );
    const authenticatedHeaders = new Headers(fetchMock.mock.calls[0][1].headers);
    expect(authenticatedHeaders.get("Content-Type")).toBe("application/json");
    expect(authenticatedHeaders.get("X-CSRF-Token")).toBe("csrf-token");

    const publicHeaders = new Headers(fetchMock.mock.calls[1][1].headers);
    expect(publicHeaders.get("X-CSRF-Token")).toBeNull();
    expect(publicHeaders.get("X-Test")).toBe("present");
  });

  it("serializes query parameters without changing the API path", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "authenticated" }), {
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest(
      apiClient.GET("/api/v1/auth/google/callback", {
        params: { query: { code: "code value", state: "state" } }
      })
    );

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/auth/google/callback?code=code%20value&state=state"
    );
  });

  it("preserves request cancellation across the same-origin adapter", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest(apiClient.GET("/api/v1/health", { signal: controller.signal }));

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it("throws problem details and invokes the global handler for authenticated 401s", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(problem), {
          headers: {
            "Content-Type": "application/problem+json",
            "X-Request-ID": "header-request-id"
          },
          status: 401
        })
      )
    );

    const request = apiRequest(apiClient.GET("/api/v1/auth/session"));

    await expect(request).rejects.toMatchObject({
      code: "authentication_required",
      fields: {},
      message: "Autenticação necessária.",
      requestId: "problem-request-id",
      status: 401
    });
    await request.catch((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).response.headers.get("X-Request-ID")).toBe(
        "header-request-id"
      );
    });
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("does not globally handle expected public-auth 401s", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(problem), {
          headers: { "Content-Type": "application/problem+json" },
          status: 401
        })
      )
    );

    await expect(
      apiRequest(
        apiClient.POST("/api/v1/auth/login", {
          body: { email: "user@example.com", password: "password", turnstile_token: "" }
        })
      )
    ).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("does not clear the session for an expired passkey registration challenge", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ...problem,
            code: "passkey_challenge_expired",
            detail: "O desafio de passkey expirou."
          }),
          {
            headers: { "Content-Type": "application/problem+json" },
            status: 401
          }
        )
      )
    );

    await expect(
      apiRequest(
        apiClient.POST("/api/v1/security/passkeys/register/complete", {
          body: {
            challenge_id: "expired",
            credential: {
              clientExtensionResults: {},
              id: "credential",
              rawId: "credential",
              response: { attestationObject: "attestation", clientDataJSON: "client-data" },
              type: "public-key"
            },
            name: "Notebook"
          }
        })
      )
    ).rejects.toMatchObject({ code: "passkey_challenge_expired", status: 401 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("normalizes non-problem failures and malformed problem bodies", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("upstream failed", { status: 502 }))
      .mockResolvedValueOnce(
        new Response("not-json", {
          headers: { "Content-Type": "application/problem+json" },
          status: 500
        })
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest(apiClient.GET("/api/v1/health"))).rejects.toMatchObject({
      code: "request_failed",
      message: "Não foi possível concluir a solicitação. Tente novamente.",
      status: 502
    });
    await expect(apiRequest(apiClient.GET("/api/v1/health"))).rejects.toMatchObject({
      code: "request_failed",
      status: 500
    });
  });

  it("exposes only generated paths and request bodies", () => {
    const assertGeneratedContracts = () => {
      // @ts-expect-error This endpoint is absent from the generated OpenAPI paths.
      void apiClient.GET("/api/v1/not-a-real-endpoint");
      // @ts-expect-error The generated login request requires password and Turnstile fields.
      void apiClient.POST("/api/v1/auth/login", { body: { email: "user@example.com" } });
    };

    expect(apiClient).toBeDefined();
    expect(assertGeneratedContracts).toBeTypeOf("function");
  });
});

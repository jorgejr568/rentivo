import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { authenticateWithPasskey } from "./webauthn";

const options: components["schemas"]["WebAuthnAuthenticationOptions"] = {
  allowCredentials: [{ id: "AQI", transports: ["internal"], type: "public-key" }],
  challenge: "AwQ",
  rpId: "rentivo.com.br",
  timeout: 60000,
  userVerification: "preferred"
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("authenticateWithPasskey", () => {
  it("uses the browser JSON helpers when available", async () => {
    const parsed = { challenge: new Uint8Array([3, 4]).buffer };
    const jsonCredential = { id: "credential", type: "public-key" };
    const get = vi.fn().mockResolvedValue({ toJSON: () => jsonCredential });
    vi.stubGlobal("PublicKeyCredential", {
      parseRequestOptionsFromJSON: vi.fn().mockReturnValue(parsed)
    });
    vi.stubGlobal("navigator", { credentials: { get } });

    await expect(authenticateWithPasskey(options)).resolves.toEqual(jsonCredential);
    expect(PublicKeyCredential.parseRequestOptionsFromJSON).toHaveBeenCalledWith(options);
    expect(get).toHaveBeenCalledWith({ publicKey: parsed });
  });

  it("falls back to base64url conversion and legacy credential serialization", async () => {
    const response = {
      authenticatorData: new Uint8Array([1, 2]).buffer,
      clientDataJSON: new Uint8Array([3]).buffer,
      signature: new Uint8Array([4]).buffer,
      userHandle: new Uint8Array([5]).buffer
    };
    const get = vi.fn().mockResolvedValue({
      authenticatorAttachment: "platform",
      getClientExtensionResults: () => ({ appid: true }),
      id: "credential",
      rawId: new Uint8Array([6]).buffer,
      response,
      type: "public-key"
    });
    vi.stubGlobal("PublicKeyCredential", {});
    vi.stubGlobal("navigator", { credentials: { get } });

    const result = await authenticateWithPasskey({
      ...options,
      allowCredentials: [{ id: "AQI", transports: null, type: "public-key" }]
    });

    const request = get.mock.calls[0][0].publicKey as PublicKeyCredentialRequestOptions;
    expect(Array.from(new Uint8Array(request.challenge as ArrayBuffer))).toEqual([3, 4]);
    expect(Array.from(new Uint8Array(request.allowCredentials![0].id as ArrayBuffer))).toEqual([
      1,
      2
    ]);
    expect(request.allowCredentials![0].transports).toBeUndefined();
    expect(result).toEqual({
      authenticatorAttachment: "platform",
      clientExtensionResults: { appid: true },
      id: "credential",
      rawId: "Bg",
      response: {
        authenticatorData: "AQI",
        clientDataJSON: "Aw",
        signature: "BA",
        userHandle: "BQ"
      },
      type: "public-key"
    });
  });

  it("omits a missing user handle and returns null when no credential is selected", async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce({
        getClientExtensionResults: () => ({}),
        id: "credential",
        rawId: new Uint8Array([6]).buffer,
        response: {
          authenticatorData: new Uint8Array([1]).buffer,
          clientDataJSON: new Uint8Array([2]).buffer,
          signature: new Uint8Array([3]).buffer,
          userHandle: null
        },
        type: "public-key"
      })
      .mockResolvedValueOnce(null);
    vi.stubGlobal("PublicKeyCredential", {});
    vi.stubGlobal("navigator", { credentials: { get } });

    const result = await authenticateWithPasskey(options);

    expect(result?.response).not.toHaveProperty("userHandle");
    await expect(authenticateWithPasskey(options)).resolves.toBeNull();
  });

  it("rejects browsers without passkey support", async () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    vi.stubGlobal("navigator", {});

    await expect(authenticateWithPasskey(options)).rejects.toThrow(
      "Passkeys não são compatíveis com este navegador."
    );
  });
});

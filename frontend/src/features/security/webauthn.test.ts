import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { createPasskey } from "./webauthn";

const options: components["schemas"]["WebAuthnRegistrationOptions"] = {
  attestation: "none",
  authenticatorSelection: {
    authenticatorAttachment: "platform",
    requireResidentKey: false,
    residentKey: "preferred",
    userVerification: "preferred"
  },
  challenge: "AwQ",
  excludeCredentials: [{ id: "AQI", transports: ["internal"], type: "public-key" }],
  hints: ["client-device"],
  pubKeyCredParams: [{ alg: -7, type: "public-key" }],
  rp: { id: "rentivo.com.br", name: "Rentivo" },
  timeout: 60000,
  user: { displayName: "User", id: "BQ", name: "user@example.com" }
};

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("createPasskey", () => {
  it("uses browser JSON helpers and credential serialization when available", async () => {
    const parsed = { challenge: new Uint8Array([3, 4]).buffer };
    const jsonCredential = { id: "credential", type: "public-key" };
    const create = vi.fn().mockResolvedValue({ toJSON: () => jsonCredential });
    vi.stubGlobal("PublicKeyCredential", { parseCreationOptionsFromJSON: vi.fn().mockReturnValue(parsed) });
    vi.stubGlobal("navigator", { credentials: { create } });
    await expect(createPasskey(options)).resolves.toEqual(jsonCredential);
    expect(PublicKeyCredential.parseCreationOptionsFromJSON).toHaveBeenCalledWith(options);
    expect(create).toHaveBeenCalledWith({ publicKey: parsed });
  });

  it("converts base64url options and serializes legacy attestation credentials", async () => {
    const create = vi.fn().mockResolvedValue({
      authenticatorAttachment: "platform",
      getClientExtensionResults: () => ({ credProps: { rk: true } }),
      id: "credential",
      rawId: new Uint8Array([6]).buffer,
      response: {
        attestationObject: new Uint8Array([1, 2]).buffer,
        clientDataJSON: new Uint8Array([3]).buffer,
        getTransports: () => ["internal"]
      },
      type: "public-key"
    });
    vi.stubGlobal("PublicKeyCredential", {});
    vi.stubGlobal("navigator", { credentials: { create } });
    const result = await createPasskey(options);
    const request = create.mock.calls[0][0].publicKey as PublicKeyCredentialCreationOptions;
    expect(Array.from(new Uint8Array(request.challenge as ArrayBuffer))).toEqual([3, 4]);
    expect(Array.from(new Uint8Array(request.user.id as ArrayBuffer))).toEqual([5]);
    expect(Array.from(new Uint8Array(request.excludeCredentials![0].id as ArrayBuffer))).toEqual([1, 2]);
    expect(result).toEqual({
      authenticatorAttachment: "platform",
      clientExtensionResults: { credProps: { rk: true } },
      id: "credential",
      rawId: "Bg",
      response: { attestationObject: "AQI", clientDataJSON: "Aw", transports: ["internal"] },
      type: "public-key"
    });
  });

  it("omits nullable options and optional legacy credential fields", async () => {
    const create = vi.fn()
      .mockResolvedValueOnce({
        authenticatorAttachment: null,
        getClientExtensionResults: () => ({}),
        id: "credential",
        rawId: new Uint8Array([1]).buffer,
        response: { attestationObject: new Uint8Array([2]).buffer, clientDataJSON: new Uint8Array([3]).buffer },
        type: "public-key"
      })
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null);
    vi.stubGlobal("PublicKeyCredential", {});
    vi.stubGlobal("navigator", { credentials: { create } });
    const nullableOptions = {
      ...options,
      attestation: null,
      authenticatorSelection: null,
      excludeCredentials: [{ id: "AQI", transports: null, type: "public-key" as const }],
      rp: { id: null, name: "Rentivo" },
      timeout: null
    };
    const result = await createPasskey(nullableOptions);
    const request = create.mock.calls[0][0].publicKey as PublicKeyCredentialCreationOptions;
    expect(request.attestation).toBeUndefined();
    expect(request.authenticatorSelection).toBeUndefined();
    expect(request.excludeCredentials![0].transports).toBeUndefined();
    expect(request.rp).not.toHaveProperty("id");
    expect(result).not.toHaveProperty("authenticatorAttachment");
    expect(result?.clientExtensionResults).toEqual({});
    expect(result?.response.transports).toBeUndefined();
    await expect(createPasskey(nullableOptions)).resolves.toBeNull();
    await expect(createPasskey({
      ...nullableOptions,
      authenticatorSelection: {
        authenticatorAttachment: null,
        requireResidentKey: null,
        residentKey: null,
        userVerification: null
      }
    })).resolves.toBeNull();
  });

  it("rejects browsers without passkey support", async () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    vi.stubGlobal("navigator", {});
    await expect(createPasskey(options)).rejects.toThrow("Passkeys não são compatíveis com este navegador.");
    vi.stubGlobal("PublicKeyCredential", {});
    await expect(createPasskey(options)).rejects.toThrow("Passkeys não são compatíveis com este navegador.");
  });
});

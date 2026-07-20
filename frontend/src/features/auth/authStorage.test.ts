import { beforeEach, describe, expect, it } from "vitest";

import {
  clearMfaChallenge,
  loadMfaChallenge,
  saveMfaChallenge,
  setAuthFlash,
  takeAuthFlash
} from "./authStorage";

beforeEach(() => {
  sessionStorage.clear();
});

describe("auth session storage", () => {
  it("round-trips non-secret MFA challenge progress", () => {
    saveMfaChallenge({ challengeId: "challenge-1", methods: ["totp", "recovery"] });

    expect(loadMfaChallenge("challenge-1")).toEqual({
      challengeId: "challenge-1",
      methods: ["totp", "recovery"]
    });
    expect(loadMfaChallenge("another-challenge")).toBeNull();

    clearMfaChallenge();
    expect(loadMfaChallenge("challenge-1")).toBeNull();
  });

  it("rejects malformed or incomplete challenge storage", () => {
    sessionStorage.setItem("rentivo.auth.mfa", "not-json");
    expect(loadMfaChallenge("challenge-1")).toBeNull();

    sessionStorage.setItem("rentivo.auth.mfa", JSON.stringify({ challengeId: 123, methods: [] }));
    expect(loadMfaChallenge("challenge-1")).toBeNull();

    sessionStorage.setItem(
      "rentivo.auth.mfa",
      JSON.stringify({ challengeId: "challenge-1", methods: ["totp", 2] })
    );
    expect(loadMfaChallenge("challenge-1")).toBeNull();
  });

  it("returns a one-shot PT-BR flash message", () => {
    expect(takeAuthFlash()).toBeNull();

    setAuthFlash("Senha redefinida com sucesso.");

    expect(takeAuthFlash()).toBe("Senha redefinida com sucesso.");
    expect(takeAuthFlash()).toBeNull();
  });
});

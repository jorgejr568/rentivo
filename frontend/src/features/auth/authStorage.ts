const MFA_STORAGE_KEY = "rentivo.auth.mfa";
const FLASH_STORAGE_KEY = "rentivo.auth.flash";

export interface StoredMfaChallenge {
  challengeId: string;
  methods: string[];
}

export function saveMfaChallenge(challenge: StoredMfaChallenge) {
  sessionStorage.setItem(MFA_STORAGE_KEY, JSON.stringify(challenge));
}

export function loadMfaChallenge(challengeId: string): StoredMfaChallenge | null {
  const stored = sessionStorage.getItem(MFA_STORAGE_KEY);
  if (!stored) {
    return null;
  }

  try {
    const value = JSON.parse(stored) as Partial<StoredMfaChallenge>;
    if (
      value.challengeId !== challengeId ||
      !Array.isArray(value.methods) ||
      !value.methods.every((method) => typeof method === "string")
    ) {
      return null;
    }
    return { challengeId: value.challengeId, methods: value.methods };
  } catch {
    return null;
  }
}

export function clearMfaChallenge() {
  sessionStorage.removeItem(MFA_STORAGE_KEY);
}

export function setAuthFlash(message: string) {
  sessionStorage.setItem(FLASH_STORAGE_KEY, message);
}

export function takeAuthFlash(): string | null {
  const message = sessionStorage.getItem(FLASH_STORAGE_KEY);
  sessionStorage.removeItem(FLASH_STORAGE_KEY);
  return message;
}

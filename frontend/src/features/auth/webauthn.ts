function base64urlToBuffer(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(base64);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0)).buffer;
}

function bufferToBase64url(value: ArrayBuffer): string {
  const binary = Array.from(new Uint8Array(value), (byte) => String.fromCharCode(byte)).join("");
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function parseRequestOptions(options: WebAuthnOptions): PublicKeyCredentialRequestOptions {
  if (typeof PublicKeyCredential.parseRequestOptionsFromJSON === "function") {
    return PublicKeyCredential.parseRequestOptionsFromJSON(
      options as PublicKeyCredentialRequestOptionsJSON
    );
  }

  return {
    ...options,
    allowCredentials: options.allowCredentials?.map((credential) => ({
      ...credential,
      id: base64urlToBuffer(credential.id),
      transports: (credential.transports ?? undefined) as AuthenticatorTransport[] | undefined,
      type: "public-key" as const
    })),
    challenge: base64urlToBuffer(options.challenge),
    userVerification: options.userVerification as UserVerificationRequirement | undefined
  };
}

function serializeCredential(credential: PublicKeyCredential): WebAuthnCredential {
  if (typeof credential.toJSON === "function") {
    return credential.toJSON() as WebAuthnCredential;
  }

  const response = credential.response as AuthenticatorAssertionResponse;
  const extensionResults = credential.getClientExtensionResults();
  const authenticatorAttachment = credential.authenticatorAttachment;
  return {
    ...(authenticatorAttachment === "cross-platform" || authenticatorAttachment === "platform"
      ? { authenticatorAttachment }
      : {}),
    ...(typeof extensionResults.appid === "boolean"
      ? { clientExtensionResults: { appid: extensionResults.appid } }
      : {}),
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    response: {
      authenticatorData: bufferToBase64url(response.authenticatorData),
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      signature: bufferToBase64url(response.signature),
      ...(response.userHandle
        ? { userHandle: bufferToBase64url(response.userHandle) }
        : {})
    },
    type: "public-key"
  };
}

export async function authenticateWithPasskey(
  options: WebAuthnOptions
): Promise<WebAuthnCredential | null> {
  if (
    typeof PublicKeyCredential === "undefined" ||
    typeof navigator.credentials?.get !== "function"
  ) {
    throw new Error("Passkeys não são compatíveis com este navegador.");
  }

  const credential = (await navigator.credentials.get({
    publicKey: parseRequestOptions(options)
  })) as PublicKeyCredential | null;
  return credential ? serializeCredential(credential) : null;
}
import type { components } from "../../lib/api/schema";

type WebAuthnCredential = components["schemas"]["WebAuthnAuthenticationCredential"];
type WebAuthnOptions = components["schemas"]["WebAuthnAuthenticationOptions"];

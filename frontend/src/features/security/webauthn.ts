import type { components } from "../../lib/api/schema";

type RegistrationCredential = components["schemas"]["WebAuthnRegistrationCredential"];
type RegistrationOptions = components["schemas"]["WebAuthnRegistrationOptions"];

function decode(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0)).buffer;
}

function encode(value: ArrayBuffer): string {
  const binary = Array.from(new Uint8Array(value), (byte) => String.fromCharCode(byte)).join("");
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function parseOptions(options: RegistrationOptions): PublicKeyCredentialCreationOptions {
  if (typeof PublicKeyCredential.parseCreationOptionsFromJSON === "function") {
    return PublicKeyCredential.parseCreationOptionsFromJSON(options as PublicKeyCredentialCreationOptionsJSON);
  }
  return {
    ...options,
    attestation: options.attestation ?? undefined,
    authenticatorSelection: options.authenticatorSelection
      ? {
          authenticatorAttachment: options.authenticatorSelection.authenticatorAttachment ?? undefined,
          requireResidentKey: options.authenticatorSelection.requireResidentKey ?? undefined,
          residentKey: options.authenticatorSelection.residentKey ?? undefined,
          userVerification: options.authenticatorSelection.userVerification ?? undefined
        }
      : undefined,
    challenge: decode(options.challenge),
    excludeCredentials: options.excludeCredentials.map((credential) => ({
      ...credential,
      id: decode(credential.id),
      transports: (credential.transports ?? undefined) as AuthenticatorTransport[] | undefined
    })),
    pubKeyCredParams: options.pubKeyCredParams,
    rp: { ...(options.rp.id ? { id: options.rp.id } : {}), name: options.rp.name },
    timeout: options.timeout ?? undefined,
    user: { ...options.user, id: decode(options.user.id) }
  };
}

function serialize(credential: PublicKeyCredential): RegistrationCredential {
  if (typeof credential.toJSON === "function") {
    return credential.toJSON() as RegistrationCredential;
  }
  const response = credential.response as AuthenticatorAttestationResponse;
  const attachment = credential.authenticatorAttachment;
  const extensions = credential.getClientExtensionResults();
  return {
    ...(attachment === "cross-platform" || attachment === "platform" ? { authenticatorAttachment: attachment } : {}),
    clientExtensionResults: typeof extensions.credProps?.rk === "boolean" ? { credProps: { rk: extensions.credProps.rk } } : {},
    id: credential.id,
    rawId: encode(credential.rawId),
    response: {
      attestationObject: encode(response.attestationObject),
      clientDataJSON: encode(response.clientDataJSON),
      transports: typeof response.getTransports === "function"
        ? response.getTransports() as RegistrationCredential["response"]["transports"]
        : undefined
    },
    type: "public-key"
  };
}

export async function createPasskey(options: RegistrationOptions): Promise<RegistrationCredential | null> {
  if (typeof PublicKeyCredential === "undefined" || typeof navigator.credentials?.create !== "function") {
    throw new Error("Passkeys não são compatíveis com este navegador.");
  }
  const credential = await navigator.credentials.create({ publicKey: parseOptions(options) }) as PublicKeyCredential | null;
  return credential ? serialize(credential) : null;
}

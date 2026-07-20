from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _AuthRequest(_StrictModel):
    pass


CredentialTransport = Literal["cookie", "body"]


def _with_default_cookie_transport(value: object) -> object:
    if isinstance(value, dict) and "credential_transport" not in value:
        return {**value, "credential_transport": "cookie"}
    return value


class _CredentialTransportRequest(_AuthRequest):
    credential_transport: CredentialTransport = "cookie"


class _CookieMFAChallengeRequest(_AuthRequest):
    credential_transport: Literal["cookie"] = "cookie"


class _BodyMFAChallengeRequest(_AuthRequest):
    credential_transport: Literal["body"]
    challenge_token: str = Field(min_length=1)


class SignupRequest(_CredentialTransportRequest):
    email: str
    password: str = Field(min_length=1)
    confirm_password: str = Field(min_length=1)
    turnstile_token: str = ""

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("E-mail obrigatório.")
        return value

    @model_validator(mode="after")
    def matching_passwords(self) -> SignupRequest:
        if self.password != self.confirm_password:
            raise ValueError("As senhas não coincidem.")
        return self


class LoginRequest(_CredentialTransportRequest):
    email: str
    password: str = Field(min_length=1)
    turnstile_token: str = ""

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("E-mail obrigatório.")
        return value


class PasswordForgotRequest(_AuthRequest):
    email: str
    turnstile_token: str = ""

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("E-mail obrigatório.")
        return value


class PasswordResetRequest(_AuthRequest):
    token: str = Field(min_length=1)
    password: str = Field(min_length=1)
    confirm_password: str = Field(min_length=1)

    @model_validator(mode="after")
    def matching_passwords(self) -> PasswordResetRequest:
        if self.password != self.confirm_password:
            raise ValueError("As senhas não coincidem.")
        return self


class CookieMFACodeVerifyRequest(_CookieMFAChallengeRequest):
    challenge_id: str = Field(min_length=1)
    code: str = Field(min_length=1)


class BodyMFACodeVerifyRequest(_BodyMFAChallengeRequest):
    challenge_id: str = Field(min_length=1)
    code: str = Field(min_length=1)


class MFACodeVerifyRequest(
    RootModel[
        Annotated[
            CookieMFACodeVerifyRequest | BodyMFACodeVerifyRequest,
            Field(discriminator="credential_transport"),
        ]
    ]
):
    @model_validator(mode="before")
    @classmethod
    def default_cookie_transport(cls, value: object) -> object:
        return _with_default_cookie_transport(value)

    @property
    def challenge_id(self) -> str:
        return self.root.challenge_id

    @property
    def challenge_token(self) -> str | None:
        return getattr(self.root, "challenge_token", None)

    @property
    def code(self) -> str:
        return self.root.code

    @property
    def credential_transport(self) -> CredentialTransport:
        return self.root.credential_transport


class CookiePasskeyAuthBeginRequest(_CookieMFAChallengeRequest):
    challenge_id: str = Field(min_length=1)


class BodyPasskeyAuthBeginRequest(_BodyMFAChallengeRequest):
    challenge_id: str = Field(min_length=1)


class PasskeyAuthBeginRequest(
    RootModel[
        Annotated[
            CookiePasskeyAuthBeginRequest | BodyPasskeyAuthBeginRequest,
            Field(discriminator="credential_transport"),
        ]
    ]
):
    @model_validator(mode="before")
    @classmethod
    def default_cookie_transport(cls, value: object) -> object:
        return _with_default_cookie_transport(value)

    @property
    def challenge_id(self) -> str:
        return self.root.challenge_id

    @property
    def challenge_token(self) -> str | None:
        return getattr(self.root, "challenge_token", None)

    @property
    def credential_transport(self) -> CredentialTransport:
        return self.root.credential_transport


class WebAuthnModel(_StrictModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class WebAuthnCredentialDescriptor(WebAuthnModel):
    id: str = Field(min_length=1)
    type: Literal["public-key"]
    transports: (
        tuple[
            Literal["ble", "cable", "hybrid", "internal", "nfc", "smart-card", "usb"],
            ...,
        ]
        | None
    ) = None


class WebAuthnAuthenticationOptions(WebAuthnModel):
    challenge: str = Field(min_length=1)
    timeout: int = Field(gt=0)
    rp_id: str = Field(alias="rpId", min_length=1)
    allow_credentials: tuple[WebAuthnCredentialDescriptor, ...] = Field(alias="allowCredentials")
    user_verification: Literal["discouraged", "preferred", "required"] = Field(alias="userVerification")


class WebAuthnAuthenticatorAssertionResponse(WebAuthnModel):
    client_data_json: str = Field(alias="clientDataJSON", min_length=1)
    authenticator_data: str = Field(alias="authenticatorData", min_length=1)
    signature: str = Field(min_length=1)
    user_handle: str | None = Field(default=None, alias="userHandle")


class WebAuthnAuthenticationExtensions(WebAuthnModel):
    appid: bool | None = None


class WebAuthnAuthenticationCredential(WebAuthnModel):
    id: str = Field(min_length=1)
    raw_id: str = Field(alias="rawId", min_length=1)
    type: Literal["public-key"]
    response: WebAuthnAuthenticatorAssertionResponse
    authenticator_attachment: Literal["cross-platform", "platform"] | None = Field(
        default=None,
        alias="authenticatorAttachment",
    )
    client_extension_results: WebAuthnAuthenticationExtensions = Field(
        default_factory=WebAuthnAuthenticationExtensions,
        alias="clientExtensionResults",
    )


class CookiePasskeyAuthCompleteRequest(_CookieMFAChallengeRequest):
    challenge_id: str = Field(min_length=1)
    credential: WebAuthnAuthenticationCredential


class BodyPasskeyAuthCompleteRequest(_BodyMFAChallengeRequest):
    challenge_id: str = Field(min_length=1)
    credential: WebAuthnAuthenticationCredential


class PasskeyAuthCompleteRequest(
    RootModel[
        Annotated[
            CookiePasskeyAuthCompleteRequest | BodyPasskeyAuthCompleteRequest,
            Field(discriminator="credential_transport"),
        ]
    ]
):
    @model_validator(mode="before")
    @classmethod
    def default_cookie_transport(cls, value: object) -> object:
        return _with_default_cookie_transport(value)

    @property
    def challenge_id(self) -> str:
        return self.root.challenge_id

    @property
    def challenge_token(self) -> str | None:
        return getattr(self.root, "challenge_token", None)

    @property
    def credential(self) -> WebAuthnAuthenticationCredential:
        return self.root.credential

    @property
    def credential_transport(self) -> CredentialTransport:
        return self.root.credential_transport


class AnalyticsEvent(_StrictModel):
    event: str
    via: str | None = None
    reason: str | None = None


class AnalyticsSettings(_StrictModel):
    gtm_container_id: str = ""


class BootstrapAnalytics(AnalyticsSettings):
    events: tuple[AnalyticsEvent, ...] = ()


class FeatureFlags(_StrictModel):
    google_auth: bool = False
    turnstile: bool = False
    turnstile_site_key: str = ""


class BootstrapUser(_StrictModel):
    id: int
    email: str


class FrontendCapabilities(_StrictModel):
    scopes: tuple[str, ...]
    mfa_setup_required: bool


class BootstrapResponse(_StrictModel):
    user: BootstrapUser
    capabilities: FrontendCapabilities
    pending_invite_count: int = Field(ge=0)
    feature_flags: FeatureFlags
    analytics: BootstrapAnalytics
    csrf_token: str


class _AuthenticatedResponseBase(_StrictModel):
    status: Literal["authenticated"] = "authenticated"
    bootstrap: BootstrapResponse


class CookieAuthenticatedResponse(_AuthenticatedResponseBase):
    credential_transport: Literal["cookie"]


class BodyAuthenticatedResponse(_AuthenticatedResponseBase):
    credential_transport: Literal["body"]
    access_token: str = Field(min_length=1)
    token_type: Literal["Bearer"]
    expires_in: int = Field(gt=0)


class AuthenticatedResponse(
    RootModel[
        Annotated[
            CookieAuthenticatedResponse | BodyAuthenticatedResponse,
            Field(discriminator="credential_transport"),
        ]
    ]
):
    pass


class SessionResponse(_AuthenticatedResponseBase):
    pass


class _MFARequiredResponseBase(_StrictModel):
    status: Literal["mfa_required"] = "mfa_required"
    challenge_id: str
    methods: tuple[str, ...]


class CookieMFARequiredResponse(_MFARequiredResponseBase):
    credential_transport: Literal["cookie"]


class BodyMFARequiredResponse(_MFARequiredResponseBase):
    credential_transport: Literal["body"]
    challenge_token: str = Field(min_length=1)


class MFARequiredResponse(
    RootModel[
        Annotated[
            CookieMFARequiredResponse | BodyMFARequiredResponse,
            Field(discriminator="credential_transport"),
        ]
    ]
):
    pass


class AcceptedResponse(_StrictModel):
    status: Literal["accepted"] = "accepted"
    analytics_events: tuple[AnalyticsEvent, ...] = ()


class CSRFResponse(_StrictModel):
    csrf_token: str


class AuthConfigResponse(_StrictModel):
    feature_flags: FeatureFlags
    analytics: AnalyticsSettings

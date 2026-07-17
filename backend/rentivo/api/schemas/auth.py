from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _AuthRequest(_StrictModel):
    pass


class SignupRequest(_AuthRequest):
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


class LoginRequest(_AuthRequest):
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


class AuthenticatedResponse(_StrictModel):
    status: Literal["authenticated"] = "authenticated"
    bootstrap: BootstrapResponse


class MFARequiredResponse(_StrictModel):
    status: Literal["mfa_required"] = "mfa_required"
    challenge_id: str
    methods: tuple[str, ...]


class AcceptedResponse(_StrictModel):
    status: Literal["accepted"] = "accepted"
    analytics_events: tuple[AnalyticsEvent, ...] = ()


class CSRFResponse(_StrictModel):
    csrf_token: str


class AuthConfigResponse(_StrictModel):
    feature_flags: FeatureFlags
    analytics: AnalyticsSettings

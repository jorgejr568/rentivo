from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import structlog
from pydantic import BaseModel, PrivateAttr

from rentivo.context import Actor
from rentivo.models.api_key import APIKey
from rentivo.models.audit_log import AuditEventType
from rentivo.models.user import User
from rentivo.observability import traced
from rentivo.services.api_key_service import APIKeyService
from rentivo.services.audit_serializers import serialize_user
from rentivo.services.audit_service import AuditService
from rentivo.services.auth_challenge_service import AuthChallengeService
from rentivo.services.job_service import JobService
from rentivo.services.known_device_service import KnownDeviceService
from rentivo.services.mfa_service import MFAService
from rentivo.services.user_service import UserService

BootstrapBuilder = Callable[..., dict[str, Any]]
logger = structlog.get_logger(__name__)


class LoginResult(BaseModel):
    status: Literal["authenticated", "mfa_required"]
    bootstrap: dict[str, Any] | None = None
    challenge_id: str | None = None
    methods: tuple[str, ...] = ()

    _user: User | None = PrivateAttr(default=None)
    _api_key: APIKey | None = PrivateAttr(default=None)
    _access_credential: str | None = PrivateAttr(default=None)
    _challenge_nonce: str | None = PrivateAttr(default=None)
    _analytics_event: dict[str, Any] | None = PrivateAttr(default=None)

    @property
    def user(self) -> User | None:
        return self._user

    @property
    def api_key(self) -> APIKey | None:
        return self._api_key

    @property
    def access_credential(self) -> str | None:
        return self._access_credential

    @property
    def challenge_nonce(self) -> str | None:
        return self._challenge_nonce

    @property
    def analytics_event(self) -> dict[str, Any] | None:
        return self._analytics_event

    @classmethod
    def authenticated(
        cls,
        *,
        user: User,
        api_key: APIKey,
        access_credential: str,
        bootstrap: dict[str, Any],
        analytics_event: dict[str, Any],
    ) -> LoginResult:
        result = cls(status="authenticated", bootstrap=bootstrap)
        result._user = user
        result._api_key = api_key
        result._access_credential = access_credential
        result._analytics_event = analytics_event
        return result

    @classmethod
    def mfa_required(
        cls,
        *,
        challenge_id: str,
        methods: tuple[str, ...],
        challenge_nonce: str,
    ) -> LoginResult:
        result = cls(status="mfa_required", challenge_id=challenge_id, methods=methods)
        result._challenge_nonce = challenge_nonce
        return result


class LoginService:
    def __init__(
        self,
        *,
        user_service: UserService,
        api_key_service: APIKeyService,
        challenge_service: AuthChallengeService,
        mfa_service: MFAService,
        audit_service: AuditService,
        known_device_service: KnownDeviceService,
        job_service: JobService,
        bootstrap_builder: BootstrapBuilder,
        public_app_url: str,
    ) -> None:
        self.user_service = user_service
        self.api_key_service = api_key_service
        self.challenge_service = challenge_service
        self.mfa_service = mfa_service
        self.audit_service = audit_service
        self.known_device_service = known_device_service
        self.job_service = job_service
        self.bootstrap_builder = bootstrap_builder
        self.public_app_url = public_app_url.rstrip("/")

    @staticmethod
    def _actor(user: User, api_key: APIKey | None = None) -> Actor:
        return Actor(
            user_id=user.id,
            email=user.email,
            source="web",
            api_key_uuid=None if api_key is None else api_key.uuid,
            is_login_token=None if api_key is None else api_key.is_login_token,
        )

    def _mfa_methods(self, user_id: int) -> tuple[str, ...]:
        methods: list[str] = []
        if self.mfa_service.has_confirmed_totp(user_id):
            methods.extend(("totp", "recovery"))
        if self.mfa_service.list_passkeys(user_id):
            methods.append("passkey")
        return tuple(methods)

    def _discard_undelivered_key(self, api_key: APIKey) -> None:
        try:
            self.api_key_service.logout(api_key)
        except Exception:
            pass

    @traced("login.complete", record_exception_details=False)
    def complete_login(
        self,
        *,
        user: User,
        via: str,
        client_ip: str,
        user_agent: str,
        audit_metadata: dict[str, Any] | None = None,
        audit_event: str = AuditEventType.USER_LOGIN,
        analytics_event: dict[str, Any] | None = None,
        notify_new_device: bool = True,
        audit_new_state: dict[str, Any] | None = None,
    ) -> LoginResult:
        issued = self.api_key_service.issue_login(user_id=user.id, name="Web login")
        try:
            mfa_setup_required = self.mfa_service.user_requires_mfa_setup(user.id)
            bootstrap = self.bootstrap_builder(
                user=user,
                api_key=issued.key,
                mfa_setup_required=mfa_setup_required,
            )
            if notify_new_device:
                self.known_device_service.notify_if_new(
                    user=user,
                    user_agent=user_agent,
                    client_ip=client_ip,
                    job_service=self.job_service,
                )
            metadata = {"ip": client_ip, **(audit_metadata or {})}
            self.audit_service.safe_log_for(
                self._actor(user, issued.key),
                audit_event,
                entity_type="user",
                entity_id=user.id,
                new_state=({"user_id": user.id, "email": user.email} if audit_new_state is None else audit_new_state),
                metadata=metadata,
            )
        except BaseException:
            self._discard_undelivered_key(issued.key)
            raise
        return LoginResult.authenticated(
            user=user,
            api_key=issued.key,
            access_credential=issued.secret,
            bootstrap=bootstrap,
            analytics_event=analytics_event or {"event": "rentivo_login_success", "via": via},
        )

    @traced("login.password", record_exception_details=False)
    def login_with_password(
        self,
        *,
        email: str,
        password: str,
        client_ip: str,
        user_agent: str,
    ) -> LoginResult | None:
        user = self.user_service.authenticate(email, password)
        if user is None:
            return None
        methods = self._mfa_methods(user.id)
        if methods:
            issued = self.challenge_service.issue(
                user_id=user.id,
                phase="login",
                allowed_methods=methods,
            )
            self.audit_service.safe_log_for(
                self._actor(user),
                AuditEventType.MFA_CHALLENGE_ISSUED,
                entity_type="user",
                entity_id=user.id,
                metadata={"ip": client_ip},
            )
            return LoginResult.mfa_required(
                challenge_id=issued.challenge.uuid,
                methods=methods,
                challenge_nonce=issued.nonce,
            )
        return self.complete_login(
            user=user,
            via="password",
            client_ip=client_ip,
            user_agent=user_agent,
        )

    @traced("login.google", record_exception_details=False)
    def login_with_google(
        self,
        *,
        email: str,
        client_ip: str,
        user_agent: str,
    ) -> LoginResult:
        user = self.user_service.get_by_email(email)
        is_new = False
        if user is None:
            try:
                user = self.user_service.register_google_user(email)
            except ValueError:
                user = self.user_service.get_by_email(email)
                if user is None:
                    raise
            else:
                is_new = True

        if is_new:
            actor = self._actor(user)
            self.audit_service.safe_log_for(
                actor,
                AuditEventType.USER_SIGNUP,
                entity_type="user",
                entity_id=user.id,
                new_state=serialize_user(user),
                metadata={"method": "google"},
            )
            try:
                self.job_service.enqueue_for(
                    actor,
                    "email.send",
                    {
                        "event": "welcome",
                        "to_email": user.email,
                        "ctx": {
                            "email": user.email,
                            "pix_setup_url": f"{self.public_app_url}/security/pix",
                        },
                    },
                )
            except Exception:
                logger.exception("google_signup_welcome_dispatch_failed", user_id=user.id)

        methods = self._mfa_methods(user.id)
        if methods:
            issued = self.challenge_service.issue(
                user_id=user.id,
                phase="login",
                allowed_methods=methods,
            )
            self.audit_service.safe_log_for(
                self._actor(user),
                AuditEventType.MFA_CHALLENGE_ISSUED,
                entity_type="user",
                entity_id=user.id,
                metadata={"ip": client_ip, "method": "google"},
            )
            return LoginResult.mfa_required(
                challenge_id=issued.challenge.uuid,
                methods=methods,
                challenge_nonce=issued.nonce,
            )

        return self.complete_login(
            user=user,
            via="google",
            client_ip=client_ip,
            user_agent=user_agent,
            audit_metadata={"method": "google"},
            analytics_event=({"event": "rentivo_signup_completed", "via": "google"} if is_new else None),
        )

    def login(self, **kwargs: Any) -> LoginResult | None:
        return self.login_with_password(**kwargs)

    @traced("login.change_password", record_exception_details=False)
    def change_password(
        self,
        *,
        principal: Any,
        current_password: str,
        new_password: str,
    ) -> bool:
        user = self.user_service.authenticate(principal.user.email, current_password)
        if user is None:
            return False
        self.user_service.change_password_and_revoke_other_logins(
            principal.user.id,
            new_password,
            principal.api_key.uuid,
        )
        return True

    @traced("login.signup", record_exception_details=False)
    def signup(
        self,
        *,
        email: str,
        password: str,
        client_ip: str,
        user_agent: str,
    ) -> LoginResult:
        user = self.user_service.register_user(email, password)
        try:
            result = self.complete_login(
                user=user,
                via="signup",
                client_ip=client_ip,
                user_agent=user_agent,
                audit_event=AuditEventType.USER_SIGNUP,
                analytics_event={"event": "rentivo_signup_completed"},
                notify_new_device=False,
                audit_new_state=serialize_user(user),
            )
        except BaseException:
            try:
                if user.id is not None:
                    self.user_service.delete_new_user(user.id)
            except Exception:
                logger.exception("signup_user_compensation_failed", user_id=user.id)
            raise
        try:
            self.job_service.enqueue_for(
                self._actor(user),
                "email.send",
                {
                    "event": "welcome",
                    "to_email": user.email,
                    "ctx": {
                        "email": user.email,
                        "pix_setup_url": f"{self.public_app_url}/security/pix",
                    },
                },
            )
        except Exception:
            logger.exception("signup_welcome_dispatch_failed", user_id=user.id)
        return result

    def bootstrap(self, principal: Any) -> dict[str, Any]:
        return self.bootstrap_builder(
            user=principal.user,
            api_key=principal.api_key,
            mfa_setup_required=self.mfa_service.user_requires_mfa_setup(principal.user.id),
        )

from __future__ import annotations

import hashlib
from datetime import datetime

import structlog

from rentivo.models.known_device import KnownDevice
from rentivo.observability import traced
from rentivo.repositories.base import KnownDeviceRepository
from rentivo.settings import settings

logger = structlog.get_logger(__name__)


class KnownDeviceService:
    def __init__(self, repo: KnownDeviceRepository) -> None:
        self.repo = repo

    @staticmethod
    def fingerprint(user_agent: str, remote_ip: str) -> str:
        """SHA-256 fingerprint of (user-agent, IPv4 /24 subnet).

        For IPv4 the last octet is dropped to /24, so the same browser at the same
        site doesn't repeatedly trigger an alert when the carrier rotates the user's
        last octet. IPv6 (or any non-dotted-quad input) is hashed verbatim, which
        means clients with rotating SLAACs WILL alert per address change. If that
        becomes noisy, group IPv6 to /64 by extracting the first four hextets.
        """
        subnet = remote_ip
        parts = remote_ip.split(".")
        if len(parts) == 4:
            subnet = ".".join(parts[:3]) + ".0"
        joined = f"{user_agent.strip()}|{subnet}"
        return hashlib.sha256(joined.encode()).hexdigest()

    @traced("known_device.register_login")
    def register_login(self, user_id: int, user_agent: str, remote_ip: str) -> bool:
        """Record this login. Returns True if the device was already known, False otherwise.

        Single round-trip: one repo.get followed by one repo.upsert (which either
        touches last_seen on the existing row or inserts a new one).
        """
        device_hash = self.fingerprint(user_agent, remote_ip)
        existing = self.repo.get(user_id, device_hash)
        self.repo.upsert(
            KnownDevice(
                user_id=user_id,
                device_hash=device_hash,
                user_agent_snippet=user_agent[:255],
            )
        )
        return existing is not None

    @traced("known_device.notify_if_new")
    def notify_if_new(
        self,
        *,
        user,
        user_agent: str,
        client_ip: str,
        job_service,
        source: str = "web",
    ) -> None:
        """Enqueue a new_device_login email iff the device is unseen.

        The password-reset CTA URL is derived here from settings so the four
        login call sites don't each assemble it.
        """
        if self.register_login(user.id, user_agent, client_ip):
            return

        forgot_password_url = f"{settings.public_app_url.rstrip('/')}/forgot-password"
        job_service.enqueue(
            "email.send",
            {
                "event": "new_device_login",
                "to_email": user.email,
                "ctx": {
                    "email": user.email,
                    "logged_in_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "source_ip": client_ip,
                    "user_agent": user_agent,
                    "reset_url": forgot_password_url,
                },
            },
            source=source,
            actor_id=user.id,
            actor_username=user.email,
        )

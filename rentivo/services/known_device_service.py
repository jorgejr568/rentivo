from __future__ import annotations

import hashlib

import structlog

from rentivo.models.known_device import KnownDevice
from rentivo.repositories.base import KnownDeviceRepository

logger = structlog.get_logger(__name__)


class KnownDeviceService:
    def __init__(self, repo: KnownDeviceRepository) -> None:
        self.repo = repo

    @staticmethod
    def fingerprint(user_agent: str, remote_ip: str) -> str:
        # IP is grouped to /24 (IPv4) so the same browser at the same site doesn't
        # repeatedly trigger an alert when the user's last octet rotates.
        subnet = remote_ip
        parts = remote_ip.split(".")
        if len(parts) == 4:
            subnet = ".".join(parts[:3]) + ".0"
        joined = f"{user_agent.strip()}|{subnet}"
        return hashlib.sha256(joined.encode()).hexdigest()

    def is_known(self, user_id: int, user_agent: str, remote_ip: str) -> bool:
        return self.repo.get(user_id, self.fingerprint(user_agent, remote_ip)) is not None

    def remember(self, user_id: int, user_agent: str, remote_ip: str) -> KnownDevice:
        return self.repo.upsert(
            KnownDevice(
                user_id=user_id,
                device_hash=self.fingerprint(user_agent, remote_ip),
                user_agent_snippet=user_agent[:255],
            )
        )

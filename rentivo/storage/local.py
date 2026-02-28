import logging
from pathlib import Path

from rentivo.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> str:
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        resolved = str(path.resolve())
        logger.debug("Saved %s (%d bytes) to %s", key, len(data), resolved)
        return resolved

    def get(self, key: str) -> bytes:
        path = self.base_dir / key
        resolved = path.resolve()
        logger.debug("Reading %s from %s", key, resolved)
        return resolved.read_bytes()

    def get_url(self, key: str) -> str:
        resolved = str((self.base_dir / key).resolve())
        logger.debug("Resolved URL for %s: %s", key, resolved)
        return resolved

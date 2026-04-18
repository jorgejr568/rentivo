import logging
from pathlib import Path

from rentivo.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        path = Path(key)
        if not path.is_absolute():
            path = self.base_dir / key
        return path.resolve()

    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> str:
        path = self._resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        resolved = str(path)
        logger.debug("Saved %s (%d bytes) to %s", key, len(data), resolved)
        return resolved

    def get(self, key: str) -> bytes:
        path = self._resolve_path(key)
        logger.debug("Reading %s from %s", key, path)
        return path.read_bytes()

    def get_url(self, key: str) -> str:
        resolved = str(self._resolve_path(key))
        logger.debug("Resolved URL for %s: %s", key, resolved)
        return resolved

    def delete(self, key: str) -> None:
        path = self._resolve_path(key)
        path.unlink(missing_ok=True)
        logger.debug("Deleted %s from %s", key, path)

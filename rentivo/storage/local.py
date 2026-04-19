import logging
from pathlib import Path

from rentivo.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        candidate = (self.base_dir / key).resolve()
        try:
            candidate.relative_to(self.base_dir)
        except ValueError as e:
            raise ValueError(f"Unsafe storage key: {key!r}") from e
        return candidate

    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> str:
        path = self._safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        resolved = str(path)
        logger.debug("Saved %s (%d bytes) to %s", key, len(data), resolved)
        return resolved

    def get(self, key: str) -> bytes:
        path = self._safe_path(key)
        logger.debug("Reading %s from %s", key, path)
        return path.read_bytes()

    def get_url(self, key: str) -> str:
        resolved = str(self._safe_path(key))
        logger.debug("Resolved URL for %s: %s", key, resolved)
        return resolved

    def delete(self, key: str) -> None:
        try:
            path = self._safe_path(key)
        except ValueError:
            logger.warning("Refusing to delete unsafe key: %s", key)
            return
        try:
            path.unlink()
            logger.debug("Deleted %s", path)
        except FileNotFoundError:
            logger.debug("Delete skipped (not found): %s", path)

from pathlib import Path

import structlog

from rentivo.storage.base import FileRef, StorageBackend

logger = structlog.get_logger(__name__)


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
        logger.debug("storage_saved", backend="local", key=key, bytes=len(data), path=resolved)
        return resolved

    def get(self, key: str) -> bytes:
        path = self._safe_path(key)
        logger.debug("storage_read", backend="local", key=key, path=str(path))
        return path.read_bytes()

    def get_url(self, key: str) -> str:
        resolved = str(self._safe_path(key))
        logger.debug("storage_url", backend="local", key=key, path=resolved)
        return resolved

    def get_ref(self, key: str) -> FileRef:
        resolved = str(self._safe_path(key))
        logger.debug("storage_ref", backend="local", key=key, path=resolved)
        return FileRef(kind="local", location=resolved)

    def delete(self, key: str) -> None:
        try:
            path = self._safe_path(key)
        except ValueError:
            logger.warning("storage_delete_refused_unsafe_key", backend="local", key=key)
            return
        try:
            path.unlink()
            logger.debug("storage_deleted", backend="local", path=str(path))
        except FileNotFoundError:
            logger.debug("storage_delete_not_found", backend="local", path=str(path))

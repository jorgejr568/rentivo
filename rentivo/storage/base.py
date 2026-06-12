from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class FileRef:
    """Where a stored object can be served from, without leaking which
    backend is active.

    ``kind="local"``: ``location`` is an absolute filesystem path — serve it
    directly (e.g. Starlette ``FileResponse``).
    ``kind="url"``: ``location`` is a (presigned) URL — redirect to it.
    """

    kind: Literal["local", "url"]
    location: str


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str = "application/pdf") -> str:
        """Save data and return the storage path/URL."""
        ...

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Retrieve file data by key."""
        ...

    @abstractmethod
    def get_url(self, key: str) -> str:
        """Return a presigned URL (S3) or absolute file path (local)."""
        ...

    @abstractmethod
    def get_ref(self, key: str) -> FileRef:
        """Resolve a key to a FileRef so callers can serve the object
        without backend-specific dispatch (no os.path.isfile probing)."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the object at the given key. No-op if missing."""
        ...

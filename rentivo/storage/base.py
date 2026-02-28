from abc import ABC, abstractmethod


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

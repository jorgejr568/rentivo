from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes) -> str:
        """Save data and return the storage path/URL."""
        ...

    @abstractmethod
    def get_url(self, key: str) -> str:
        """Return a presigned URL (S3) or absolute file path (local)."""
        ...

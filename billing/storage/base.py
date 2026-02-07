from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes) -> str:
        """Save data and return the storage path/URL."""
        ...

    @abstractmethod
    def get_path(self, key: str) -> str:
        """Return a local file path or URL for the stored object."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def get_presigned_url(self, key: str) -> str:
        """Return a presigned URL (S3) or absolute file path (local)."""
        ...

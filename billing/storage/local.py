from pathlib import Path

from billing.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes) -> str:
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path.resolve())

    def get_path(self, key: str) -> str:
        return str((self.base_dir / key).resolve())

    def exists(self, key: str) -> bool:
        return (self.base_dir / key).exists()

    def get_presigned_url(self, key: str) -> str:
        return str((self.base_dir / key).resolve())

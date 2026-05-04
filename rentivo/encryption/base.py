from __future__ import annotations

from abc import ABC, abstractmethod


class EncryptionBackend(ABC):
    """Abstract field-encryption backend.

    Implementations must satisfy these contracts:
    - ``encrypt(plaintext)`` is idempotent: calling it on an already-encrypted
      value returns the value unchanged.
    - ``decrypt(value)`` is idempotent: calling it on a plaintext (non-encrypted)
      value returns the value unchanged.
    - ``is_encrypted(value)`` returns True iff ``value`` has the ciphertext
      shape produced by this backend.

    Together these allow encrypted and plaintext rows to coexist while a
    backfill is in progress.
    """

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Return ``plaintext`` encrypted to this backend's ciphertext format."""
        ...

    @abstractmethod
    def decrypt(self, value: str) -> str:
        """Return the plaintext for ``value``. If ``value`` is not encrypted, return it unchanged."""
        ...

    @abstractmethod
    def is_encrypted(self, value: str) -> bool:
        """True iff ``value`` has the ciphertext shape this backend produces."""
        ...

    def decrypt_many(self, values: list[str]) -> list[str]:
        """Decrypt a batch of values, returning plaintexts in the same order.

        Default implementation calls ``decrypt`` sequentially. Backends with
        network round-trips per call (e.g. KMS) should override this to
        parallelise the work — the repository read paths invoke this once per
        list/detail query, so the override turns N sequential RTTs into one.
        """
        return [self.decrypt(v) for v in values]

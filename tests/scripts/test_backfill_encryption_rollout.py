"""End-to-end rollout test: base64 → KMS → backfill.

Stitches together the full operator playbook from CLAUDE.md to verify each
step is reachable in code:
1. App deployed with RENTIVO_ENCRYPTION_BACKEND=base64 — row stored as b64:v1:
2. App switched to RENTIVO_ENCRYPTION_BACKEND=kms — KMSBackend.decrypt
   transparently unwraps the b64:v1: row.
3. make backfill-encryption — backfill rewrites the row as enc:v1:
4. App still reads correctly — KMSBackend.decrypt round-trips the enc:v1: row.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from rentivo.encryption.base64 import Base64Backend
from rentivo.encryption.kms import KMSBackend
from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
from rentivo.scripts import backfill_encryption


@pytest.fixture()
def kms_mock():
    """A MagicMock'd KMS client wrapped around a deterministic in-memory store
    so encrypt/decrypt round-trips work in tests."""
    client = MagicMock()
    store: dict[bytes, bytes] = {}

    def fake_encrypt(KeyId, Plaintext):
        blob = b"BLOB-" + Plaintext
        store[blob] = Plaintext
        return {"CiphertextBlob": blob}

    def fake_decrypt(CiphertextBlob, KeyId):
        return {"Plaintext": store[CiphertextBlob]}

    client.encrypt.side_effect = fake_encrypt
    client.decrypt.side_effect = fake_decrypt
    return client


def test_full_rollout_base64_to_kms_via_backfill(db_connection, kms_mock):
    # --- Step 1: deploy with base64 backend, write a user with PIX ---
    base64_backend = Base64Backend()
    base64_repo = SQLAlchemyUserRepository(db_connection, base64_backend)
    user = base64_repo.create(User(email="alice@example.com", password_hash="x"))
    base64_repo.update_pix(user.id, "alice@pix.com", "Alice", "Sao Paulo")

    # Sanity: the row at rest is b64:v1: ciphertext, not plaintext.
    raw = (
        db_connection.execute(
            text("SELECT pix_key, pix_merchant_name, pix_merchant_city FROM users WHERE id = :id"),
            {"id": user.id},
        )
        .mappings()
        .fetchone()
    )
    assert raw["pix_key"].startswith("b64:v1:")
    assert raw["pix_merchant_name"].startswith("b64:v1:")
    assert raw["pix_merchant_city"].startswith("b64:v1:")

    # --- Step 2: app switches to KMS backend; reads must still return plaintext ---
    with patch("rentivo.encryption.kms.boto3") as mock_boto3:
        mock_boto3.client.return_value = kms_mock
        kms_backend = KMSBackend(
            key_id="alias/rentivo",
            region="us-east-1",
            access_key_id="k",
            secret_access_key="s",
        )

        kms_repo = SQLAlchemyUserRepository(db_connection, kms_backend)
        fetched = kms_repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.pix_key == "alice@pix.com"
        assert fetched.pix_merchant_name == "Alice"
        assert fetched.pix_merchant_city == "Sao Paulo"

        # The transitional read path should NOT have called KMS Decrypt.
        # (b64:v1: rows are decoded locally.)
        kms_mock.decrypt.assert_not_called()

        # --- Step 3: operator runs backfill ---
        backfill_encryption.run(db_connection, kms_backend, dry_run=False)

        # --- Step 4: rows are now stored as enc:v1: under KMS ---
        raw_after = (
            db_connection.execute(
                text("SELECT pix_key, pix_merchant_name, pix_merchant_city FROM users WHERE id = :id"),
                {"id": user.id},
            )
            .mappings()
            .fetchone()
        )
        assert raw_after["pix_key"].startswith("enc:v1:")
        assert raw_after["pix_merchant_name"].startswith("enc:v1:")
        assert raw_after["pix_merchant_city"].startswith("enc:v1:")

        # And the plaintext blob inside the enc:v1: payload is the original PIX.
        encoded_blob = raw_after["pix_key"][len("enc:v1:") :]
        assert base64.b64decode(encoded_blob) == b"BLOB-alice@pix.com"

        # --- Final read still works through the repo ---
        fetched_final = kms_repo.get_by_id(user.id)
        assert fetched_final is not None
        assert fetched_final.pix_key == "alice@pix.com"
        assert fetched_final.pix_merchant_name == "Alice"
        assert fetched_final.pix_merchant_city == "Sao Paulo"

        # The KMS decrypt was called now that rows are enc:v1: (3 columns × 1 read = 3 calls).
        assert kms_mock.decrypt.call_count == 3

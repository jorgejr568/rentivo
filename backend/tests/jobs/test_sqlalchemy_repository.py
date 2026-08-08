"""Tests for the encrypting job repository and its at-rest payload envelope.

``backend/rentivo/jobs/sqlalchemy.py`` is in the coverage ``omit`` list because
``claim_batch`` uses MariaDB-only SQL (``NOW()``, ``INTERVAL ... SECOND``,
``FOR UPDATE SKIP LOCKED``) that cannot execute on the SQLite test suite. These
tests still cover the parts that matter: the codec is pure, and ``enqueue``
uses a portable INSERT that runs on SQLite.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from rentivo.encryption.base import EncryptionBackend
from rentivo.encryption.base64 import Base64Backend
from rentivo.jobs.sqlalchemy import (
    SQLAlchemyJobRepository,
    decode_job_payload,
    encode_job_payload,
)

PAYLOAD = {
    "event": "password_reset",
    "to_email": "tenant@example.com",
    "ctx": {"email": "tenant@example.com", "reset_url": "https://app.example/reset-password?token=SECRET"},
}


class _BrokenBackend(EncryptionBackend):
    """Decrypt always raises — stands in for a KMS outage or a destroyed key."""

    def encrypt(self, plaintext: str) -> str:
        return "enc:v1:" + plaintext

    def decrypt(self, value: str) -> str:
        raise RuntimeError("kms unavailable")

    def is_encrypted(self, value: str) -> bool:
        return value.startswith("enc:v1:")


def test_encode_produces_valid_json_object_wrapping_the_ciphertext():
    encoded = encode_job_payload(Base64Backend(), PAYLOAD)

    outer = json.loads(encoded)
    assert isinstance(outer, dict), "MariaDB's implicit json_valid CHECK requires valid JSON"
    assert set(outer) == {"__enc"}
    assert outer["__enc"].startswith("b64:v1:")


def test_encode_does_not_leak_plaintext_into_the_stored_string():
    encoded = encode_job_payload(Base64Backend(), PAYLOAD)

    assert "tenant@example.com" not in encoded
    assert "SECRET" not in encoded
    assert "password_reset" not in encoded


def test_encode_decode_round_trips():
    encryption = Base64Backend()

    assert decode_job_payload(encryption, encode_job_payload(encryption, PAYLOAD)) == PAYLOAD


def test_decode_passes_through_legacy_plaintext_json():
    assert decode_job_payload(Base64Backend(), json.dumps(PAYLOAD)) == PAYLOAD


def test_decode_accepts_a_dict_already_parsed_by_the_driver():
    assert decode_job_payload(Base64Backend(), dict(PAYLOAD)) == PAYLOAD


def test_decode_decrypts_an_envelope_dict_already_parsed_by_the_driver():
    encryption = Base64Backend()
    envelope = json.loads(encode_job_payload(encryption, PAYLOAD))

    assert decode_job_payload(encryption, envelope) == PAYLOAD


def test_enqueue_writes_ciphertext_not_plaintext(db_connection):
    repo = SQLAlchemyJobRepository(db_connection, Base64Backend())

    job = repo.enqueue("email.send", PAYLOAD)

    stored = db_connection.execute(text("SELECT payload FROM jobs WHERE ulid = :u"), {"u": job.ulid}).scalar_one()
    assert "tenant@example.com" not in stored
    assert "SECRET" not in stored
    assert json.loads(stored)["__enc"].startswith("b64:v1:")
    assert job.payload == PAYLOAD, "the returned Job carries the plaintext payload"


def test_decode_rows_returns_decoded_payloads_for_decodable_rows():
    encryption = Base64Backend()
    repo = SQLAlchemyJobRepository(None, encryption)
    rows = [{"id": 1, "ulid": "A", "payload": encode_job_payload(encryption, PAYLOAD)}]

    assert repo._decode_rows(rows) == [(rows[0], PAYLOAD)]


def test_decode_rows_skips_undecodable_rows_and_keeps_the_rest():
    repo = SQLAlchemyJobRepository(None, _BrokenBackend())
    good = {"id": 1, "ulid": "A", "payload": json.dumps(PAYLOAD)}
    bad = {"id": 2, "ulid": "B", "payload": json.dumps({"__enc": "enc:v1:whatever"})}

    assert repo._decode_rows([good, bad]) == [(good, PAYLOAD)]


def test_decode_rows_returns_empty_when_nothing_can_be_decoded():
    repo = SQLAlchemyJobRepository(None, _BrokenBackend())
    bad = {"id": 2, "ulid": "B", "payload": json.dumps({"__enc": "enc:v1:whatever"})}

    assert repo._decode_rows([bad]) == []


def _naive_utc_now() -> datetime:
    """The clock a terminal row's ``updated_at`` is written on.

    Production stamps those rows with SQL ``NOW()`` on a UTC database server
    (stock ``mariadb:11``), *not* with the repository's naive Sao Paulo helper.
    Tests that write ``updated_at`` by hand must use this clock, or a cutoff
    computed on the wrong one looks correct while being three hours off.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _finish(db_connection, job_id: int, status: str, updated_at: datetime) -> None:
    """Move a job to a terminal state with an explicit `updated_at`.

    ``mark_succeeded`` cannot be used here: it stamps the row with MariaDB's
    ``NOW()``, which SQLite does not provide. ``updated_at`` must therefore be a
    naive UTC timestamp -- see ``_naive_utc_now``.
    """
    db_connection.execute(
        text("UPDATE jobs SET status = :status, updated_at = :updated_at WHERE id = :id"),
        {"status": status, "updated_at": updated_at, "id": job_id},
    )


def test_has_active_or_recent_sees_a_pending_job(db_connection):
    repo = SQLAlchemyJobRepository(db_connection, Base64Backend())
    repo.enqueue("auth.cleanup", {})

    assert repo.has_active_or_recent("auth.cleanup", 3600) is True


def test_has_active_or_recent_sees_a_running_job(db_connection):
    repo = SQLAlchemyJobRepository(db_connection, Base64Backend())
    job = repo.enqueue("auth.cleanup", {})
    # A running job is old by `updated_at` yet must still block a new enqueue.
    _finish(db_connection, job.id, "running", _naive_utc_now() - timedelta(days=1))

    assert repo.has_active_or_recent("auth.cleanup", 3600) is True


def test_has_active_or_recent_sees_a_run_that_finished_just_inside_the_window(db_connection):
    repo = SQLAlchemyJobRepository(db_connection, Base64Backend())
    job = repo.enqueue("auth.cleanup", {})
    _finish(db_connection, job.id, "succeeded", _naive_utc_now() - timedelta(seconds=3540))

    assert repo.has_active_or_recent("auth.cleanup", 3600) is True


def test_has_active_or_recent_ignores_a_run_that_finished_just_outside_the_window(db_connection):
    """The window is measured on the database clock, not app-local SP time.

    The row finished 61 minutes ago in UTC terms, so a 3600-second window has
    already elapsed. A cutoff derived from naive Sao Paulo wall-clock sits three
    extra hours in the past, and this row would still look "recent" -- stretching
    the effective window to `within_seconds` plus the UTC offset.
    """
    repo = SQLAlchemyJobRepository(db_connection, Base64Backend())
    job = repo.enqueue("auth.cleanup", {})
    _finish(db_connection, job.id, "succeeded", _naive_utc_now() - timedelta(seconds=3660))

    assert repo.has_active_or_recent("auth.cleanup", 3600) is False


def test_has_active_or_recent_ignores_a_run_that_finished_before_the_window(db_connection):
    repo = SQLAlchemyJobRepository(db_connection, Base64Backend())
    job = repo.enqueue("auth.cleanup", {})
    _finish(db_connection, job.id, "succeeded", _naive_utc_now() - timedelta(hours=2))

    assert repo.has_active_or_recent("auth.cleanup", 3600) is False


def test_has_active_or_recent_ignores_other_job_types(db_connection):
    repo = SQLAlchemyJobRepository(db_connection, Base64Backend())
    repo.enqueue("email.send", PAYLOAD)

    assert repo.has_active_or_recent("auth.cleanup", 3600) is False


def test_repository_requires_an_encryption_backend():
    with pytest.raises(TypeError):
        SQLAlchemyJobRepository(None)

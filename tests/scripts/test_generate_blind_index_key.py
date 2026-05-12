"""Tests for the blind-index key generator script."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock


def test_generates_32_bytes_and_calls_kms_encrypt(monkeypatch, capsys):
    from rentivo.scripts import generate_blind_index_key

    fake_client = MagicMock()
    fake_client.encrypt.return_value = {"CiphertextBlob": b"\x99" * 64}
    monkeypatch.setattr(generate_blind_index_key, "_get_kms_client", lambda: fake_client)
    monkeypatch.setattr("rentivo.settings.settings.kms_key_id", "alias/rentivo")

    generate_blind_index_key.main()

    args = fake_client.encrypt.call_args.kwargs
    assert args["KeyId"] == "alias/rentivo"
    assert len(args["Plaintext"]) == 32

    captured = capsys.readouterr().out
    assert base64.b64encode(b"\x99" * 64).decode() in captured


def test_refuses_when_kms_key_id_missing(monkeypatch):
    from rentivo.scripts import generate_blind_index_key

    monkeypatch.setattr("rentivo.settings.settings.kms_key_id", "")

    import pytest

    with pytest.raises(SystemExit) as exc_info:
        generate_blind_index_key.main()
    assert exc_info.value.code == 2

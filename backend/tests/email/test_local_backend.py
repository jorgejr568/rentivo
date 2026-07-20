import os

import pytest

from rentivo.email.base import EmailMessage
from rentivo.email.local import LocalEmailBackend


@pytest.fixture
def msg():
    return EmailMessage(
        to="alice@example.com",
        subject="Olá",
        text_body="Texto",
        html_body="<p>Texto</p>",
        from_address="noreply@rentivo.com.br",
    )


def test_send_writes_eml_file(tmp_path, msg):
    backend = LocalEmailBackend(str(tmp_path))
    path = backend.send(msg)
    assert os.path.exists(path)
    contents = open(path).read()
    assert "To: alice@example.com" in contents
    assert "Subject:" in contents
    assert "<p>Texto</p>" in contents


def test_send_creates_directory(tmp_path, msg):
    target = tmp_path / "nested" / "outbox"
    LocalEmailBackend(str(target)).send(msg)
    assert target.is_dir()


def test_send_uses_unique_filenames(tmp_path, msg):
    backend = LocalEmailBackend(str(tmp_path))
    a = backend.send(msg)
    b = backend.send(msg)
    assert a != b

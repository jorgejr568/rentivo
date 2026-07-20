from datetime import datetime
from unittest.mock import MagicMock

from rentivo.jobs.backend import DatabaseJobBackend, JobBackend
from rentivo.jobs.base import Job


def test_database_backend_is_a_jobbackend():
    assert issubclass(DatabaseJobBackend, JobBackend)


def test_database_backend_delegates_enqueue_to_repo():
    repo = MagicMock()
    expected = Job(id=7, ulid="01J", job_type="email.send", payload={}, attempts=0, max_attempts=5)
    repo.enqueue.return_value = expected

    backend = DatabaseJobBackend(repo)
    run_after = datetime(2026, 1, 1)
    out = backend.enqueue("email.send", {"k": "v"}, run_after=run_after, max_attempts=3)

    assert out is expected
    repo.enqueue.assert_called_once_with("email.send", {"k": "v"}, run_after, 3)

import pytest

from rentivo.jobs.base import Job, JobRepository, PermanentJobError


def test_job_dataclass_is_frozen_and_holds_expected_fields():
    job = Job(
        id=1,
        ulid="01HXYZ",
        job_type="email.send",
        payload={"event": "welcome"},
        attempts=2,
        max_attempts=5,
    )
    assert job.id == 1
    assert job.ulid == "01HXYZ"
    assert job.job_type == "email.send"
    assert job.payload == {"event": "welcome"}
    assert job.attempts == 2
    assert job.max_attempts == 5
    with pytest.raises(Exception):
        job.id = 99  # frozen dataclass


def test_permanent_job_error_is_an_exception():
    with pytest.raises(PermanentJobError, match="boom"):
        raise PermanentJobError("boom")


def test_job_repository_abc_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        JobRepository()  # type: ignore[abstract]

"""Importing this package registers every handler via decorator side-effects."""

from rentivo.jobs.handlers import email, s3  # noqa: F401

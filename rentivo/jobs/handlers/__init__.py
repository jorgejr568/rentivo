"""Importing this package registers every handler via decorator side-effects."""

from rentivo.jobs.handlers import communication, email, pdf, recibo, s3  # noqa: F401

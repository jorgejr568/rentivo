"""Importing this package registers every handler via decorator side-effects."""

from rentivo.jobs.handlers import communication, email, export, pdf, recibo, s3  # noqa: F401

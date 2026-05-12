"""Exception hierarchy.

Catching `OntEndReasonError` catches every error this package raises.
Library callers can also catch the more specific subclasses if they want
to distinguish I/O failures from analysis failures from validation failures.

The CLI dispatcher catches `OntEndReasonError`, pretty-prints `[error] <msg>`,
and exits with code 1. Any other exception (programming bugs in this package
or its dependencies) propagates as a normal traceback.
"""

from __future__ import annotations


class OntEndReasonError(Exception):
    """Base class for every error raised by ont-end-reason."""


class IOError(OntEndReasonError):  # noqa: A001 — intentional shadow; subclass is enough to disambiguate
    """File/directory not found, unreadable, or in an unexpected format."""


class AnalysisError(OntEndReasonError):
    """Analysis-level error: bad input shape, math domain error, etc."""


class ValidationError(OntEndReasonError):
    """Schema-validation failure: a sequencing_summary.txt column missing or
    a manifest field has the wrong type."""

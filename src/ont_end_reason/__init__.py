"""ont-end-reason — Oxford Nanopore end_reason analysis toolkit.

Public API exports the most-used names. See README.md for usage and
docs/superpowers/specs/2026-05-12-ont-end-reason-design.md for architecture.

Lazy imports keep CLI cold start fast — the analysis and visualisation
submodules pull in matplotlib / plotly / pysam only when accessed.
"""

from __future__ import annotations

__version__ = "0.2.0"

# Re-export the public surface. Each lazy attribute resolves to its
# implementation on first access so importing the package alone is fast.
from .codes import (
    CODES,
    FAILED,
    NAMES,
    RECOMMENDED_KEEP,
    TRUNCATED,
    parse_keep_list,
    to_full,
    to_short,
)
from .errors import (
    AnalysisError,
    OntEndReasonError,
    ValidationError,
)
from .errors import (
    IOError as OntIOError,
)

__all__ = [
    # codes
    "CODES",
    "FAILED",
    "NAMES",
    "RECOMMENDED_KEEP",
    "TRUNCATED",
    "AnalysisError",
    # errors
    "OntEndReasonError",
    "OntIOError",
    "ValidationError",
    "__version__",
    "parse_keep_list",
    "to_full",
    "to_short",
]


def __dir__() -> list[str]:
    return __all__

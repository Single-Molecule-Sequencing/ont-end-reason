"""io subpackage — data discovery, format-specific readers, schema validation.

Public surface:

    from ont_end_reason.io import discover, Manifest, ReadRecord
    from ont_end_reason.io.readers import (
        extract_from_pod5,
        extract_from_fast5,
        extract_from_summary,
        detect_format,
    )
    from ont_end_reason.io.schema import (
        SequencingSummarySchema,
        validate_summary,
    )
"""

from __future__ import annotations

from .discover import discover
from .manifest import Manifest, ReadRecord
from .readers import (
    detect_format,
    extract_from_fast5,
    extract_from_pod5,
    extract_from_summary,
)
from .schema import SequencingSummarySchema, validate_summary

__all__ = [
    "Manifest",
    "ReadRecord",
    "SequencingSummarySchema",
    "detect_format",
    "discover",
    "extract_from_fast5",
    "extract_from_pod5",
    "extract_from_summary",
    "validate_summary",
]

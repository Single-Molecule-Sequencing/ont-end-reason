"""Schema validation for sequencing_summary.txt.

The canonical column set is documented in
`end-reason-paper/source-materials/spec.yaml`. This module validates that a
given summary file has the required columns and (optionally) flags
unexpected columns the user might want to know about.

We deliberately do NOT enforce column types or value ranges here — that's
analysis-level validation. This module is just structural.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..errors import ValidationError

# Columns every reader expects. A subset of the full spec.yaml; only the
# columns this package actually uses are required.
REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "read_id",
        "end_reason",
    }
)

# Columns frequently used by analyses but not strictly required.
RECOMMENDED_COLUMNS: frozenset[str] = frozenset(
    {
        "sequence_length_template",
        "mean_qscore_template",
        "channel",
        "mux",
        "start_time",
        "duration",
    }
)


@dataclass
class SequencingSummarySchema:
    """Result of validating a sequencing_summary.txt header.

    `missing_required` is non-empty when the file is unusable.
    `missing_recommended` is informational — analyses that need those
    columns will raise more specific errors when accessed.
    """

    columns: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.missing_required


def validate_summary(path: str | Path) -> SequencingSummarySchema:
    """Read the first line of `path` and validate column membership.

    Raises ValidationError only if the file cannot be opened or has no
    header. Missing columns are returned in the schema result, not raised
    — the caller decides whether to abort or continue.
    """
    p = Path(path)
    try:
        with p.open() as fh:
            header = fh.readline().rstrip("\n\r")
    except OSError as exc:
        raise ValidationError(f"Cannot read {p}: {exc}") from exc

    if not header:
        raise ValidationError(f"Empty header in {p}")

    columns = header.split("\t")
    col_set = set(columns)

    missing_required = sorted(REQUIRED_COLUMNS - col_set)
    missing_recommended = sorted(RECOMMENDED_COLUMNS - col_set)
    extra = sorted(col_set - REQUIRED_COLUMNS - RECOMMENDED_COLUMNS)

    return SequencingSummarySchema(
        columns=columns,
        missing_required=missing_required,
        missing_recommended=missing_recommended,
        extra_columns=extra,
    )

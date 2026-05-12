"""Length distribution analysis per end_reason category.

v0.1.0 STATUS: scaffold only. Full implementation deferred to v0.2.0.

Source script: `End_Reason_Manuscript/length_distribution_analysis.py`
(TOOL_SPECIFICATIONS.md analysis type 4).

Tracked in GitHub issue:
  https://github.com/Single-Molecule-Sequencing/ont-end-reason/issues
  (label `analysis`)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import AnalysisError


@dataclass
class LengthResult:
    """Per-end_reason length distribution result."""

    total_reads: int = 0
    per_class: dict[str, dict[str, float]] = field(default_factory=dict)
    # per_class[<end_reason>] = {n, mean, median, p50, p95, n50, std}


def length(source: str | Path, *, bins: int = 50, **kwargs: Any) -> LengthResult:
    """Compute per-end_reason length distributions.

    Not yet implemented in v0.1.0. Tracking issue:
    https://github.com/Single-Molecule-Sequencing/ont-end-reason/issues
    """
    raise NotImplementedError(
        "analyze.length is scheduled for v0.2.0. See TOOL_SPECIFICATIONS.md "
        "type 4; reference implementation lives in End_Reason_Manuscript@b47166a."
    )
    _ = AnalysisError  # keep imported for the eventual implementation

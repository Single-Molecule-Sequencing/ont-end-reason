"""SMA metrics delegate — bridges to the smaseq-qc package's metrics module.

v0.1.0 STATUS: scaffold only.
Source: TOOL_SPECIFICATIONS.md type 15. Delegates to `smaseq-qc.metrics` if
installed; raises NotImplementedError otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SmaMetricsResult:
    metrics: dict[str, float] = field(default_factory=dict)
    delegated_to: str = "smaseq-qc"


def sma_metrics(source: str | Path, **kwargs: Any) -> SmaMetricsResult:
    raise NotImplementedError(
        "analyze.sma_metrics is scheduled for v0.2.0. Will delegate to "
        "the `smaseq-qc` package if installed."
    )

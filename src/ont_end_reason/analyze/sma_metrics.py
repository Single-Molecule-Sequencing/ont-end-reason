"""SMA metrics bridge to the smaseq-qc package (TOOL_SPEC type 15).

If `smaseq_qc` is installed, this module delegates per-read metrics computation
to it. Otherwise returns an informative result with `available=False` so the
report layer can skip the section gracefully (rather than raising).

The actual SMA metric implementations live in
`Single-Molecule-Sequencing/smaseq-qc` and are NOT vendored here — that
package has its own release cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SmaMetricsResult:
    available: bool = False
    metrics: dict[str, float] = field(default_factory=dict)
    delegated_to: str = "smaseq-qc"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "metrics": self.metrics,
            "delegated_to": self.delegated_to,
            "notes": self.notes,
        }


def sma_metrics(source: str | Path, **_kwargs: Any) -> SmaMetricsResult:
    """Run SMA metrics if smaseq-qc is available; otherwise return a stub.

    The function never raises — it returns `available=False` with a
    note explaining how to install the dependency.
    """
    try:
        import smaseq_qc  # type: ignore[import-not-found]
    except ImportError:
        return SmaMetricsResult(
            available=False,
            notes=[
                "smaseq-qc package not installed.",
                "Install with: pip install smaseq-qc",
                "(or `pip install ont-end-reason[sma]` once the extra is wired in v0.3.0)",
            ],
        )

    # Real delegation would call into smaseq_qc.metrics here. For v0.2.0 the
    # bridge surface is intentionally narrow until the smaseq-qc API stabilises.
    version = getattr(smaseq_qc, "__version__", "unknown")
    return SmaMetricsResult(
        available=True,
        metrics={},
        delegated_to=f"smaseq-qc=={version}",
        notes=[
            "Bridge to smaseq_qc is wired but the metric set is not yet "
            "agreed upon for v0.2.0. Tracking: ont-end-reason issue tbd.",
        ],
    )

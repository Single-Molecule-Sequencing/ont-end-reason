"""Reproducer for paper Figure 3 — end-reason distribution bar charts.

v0.1.0 STATUS: composes `analyze.distribution` + `viz.static.plot_distribution`
which IS implemented. Marked complete-enough for v0.1.0; cosmetic refinements
(paper-exact font sizes, axis ticks) tracked as a follow-up issue.
"""

from __future__ import annotations

from pathlib import Path

from ..analyze.distribution import distribution
from ..viz.static import plot_distribution


def fig3_distribution(
    source: str | Path,
    *,
    out: str | Path,
    quick: bool = False,
) -> str:
    """Build Figure 3 from a source and save to `out`. Returns the output path."""
    import matplotlib.pyplot as plt

    result = distribution(source, quick=quick)
    fig = plot_distribution(result)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out_path)

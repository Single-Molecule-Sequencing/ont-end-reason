"""Reproducer for paper Figure 5 — Q-score violins per end_reason.

Composes `analyze.quality` + `viz.static.plot_quality_violins` to produce
a publication-ready PDF. Cosmetic refinements (paper-exact font sizes,
tick spacing) tracked as a follow-up issue; the core analysis is complete.
"""

from __future__ import annotations

from pathlib import Path

from ..analyze.quality import quality
from ..viz.static import plot_quality_violins


def fig5_violin(source: str | Path, *, out: str | Path) -> str:
    """Build Figure 5 and save to `out`. Returns the output path."""
    import matplotlib.pyplot as plt

    result = quality(source)
    fig = plot_quality_violins(result)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out_path)

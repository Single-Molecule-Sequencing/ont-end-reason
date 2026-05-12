"""Reproducer for paper Figure 6 — conceptual diagram of UMC truncation.

Renders a schematic showing: (a) observed truncated read length,
(b) inferred posterior over true length, (c) the lost-sequence "bonus".

This is a generated companion to the paper's hand-illustrated conceptual
figure. Uses umc_posterior output as the data source so the schematic
reflects the actual run rather than canned numbers.
"""

from __future__ import annotations

from pathlib import Path

from ..analyze.umc_posterior import umc_posterior
from ..viz.static import plot_umc_posterior


def fig6_conceptual(source: str | Path, *, out: str | Path) -> str:
    """Build Figure 6 from a sequencing_summary path. Returns the output path."""
    import matplotlib.pyplot as plt

    result = umc_posterior(source)
    fig = plot_umc_posterior(result)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out_path)

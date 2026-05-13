"""Reproducer for paper Figure 8 — cross-run end-reason atlas summary.

Composes `analyze.atlas` (cross-run aggregation) with `viz.static.plot_atlas_summary`
to emit a publication-ready per-flowcell summary PNG.

Spec section 6 — Phase 4 of the cross-run atlas design:
docs/superpowers/specs/2026-05-12-end-reason-atlas-design.md
"""

from __future__ import annotations

from pathlib import Path

from ..analyze.atlas import AtlasResult
from ..analyze.atlas import atlas as atlas_analyze
from ..viz.static import plot_atlas_summary


def atlas(
    *,
    out: str | Path,
    result: AtlasResult | None = None,
) -> str:
    """Build the atlas summary figure (fig8 style) and save to `out`.

    Parameters
    ----------
    out : str | Path
        Output path for the PNG.
    result : AtlasResult, optional
        Pre-computed atlas result. If None, calls `analyze.atlas.atlas()`
        with default parameters (empty store on a fresh install yields the
        friendly "no data" plot — never crashes).

    Returns
    -------
    str
        The output path as a string (mirrors fig3 / fig5 / fig6 contract).
    """
    import matplotlib.pyplot as plt

    if result is None:
        result = atlas_analyze()
    fig = plot_atlas_summary(result)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)  # MUST close after savefig — see lab feedback memory
    return str(out_path)

"""Reproducer for paper Figure 5 — Q-score violins per end_reason.

v0.1.0 STATUS: scaffold. Depends on `analyze.quality` which is also v0.2.0.
"""

from __future__ import annotations

from pathlib import Path


def fig5_violin(source: str | Path, *, out: str | Path) -> str:
    raise NotImplementedError(
        "fig5_violin needs analyze.quality (scheduled v0.2.0). "
        "Reference: end-reason-paper Figure 5 panel specifications."
    )

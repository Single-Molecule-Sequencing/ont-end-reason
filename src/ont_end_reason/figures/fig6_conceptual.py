"""Reproducer for paper Figure 6 — conceptual diagram.

v0.1.0 STATUS: scaffold. The figure is a hand-illustrated diagram in the
paper; this reproducer would emit a matplotlib version of it for slides
or web rendering. Low-priority in the v0.2.0 roadmap.
"""

from __future__ import annotations

from pathlib import Path


def fig6_conceptual(source: str | Path, *, out: str | Path) -> str:
    raise NotImplementedError(
        "fig6_conceptual is a conceptual diagram and is deferred to v0.3.0+. "
        "The paper figure itself is in source_artwork/ in end-reason-paper."
    )

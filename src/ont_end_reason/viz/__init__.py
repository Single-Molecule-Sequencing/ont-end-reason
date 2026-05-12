"""viz subpackage — static (matplotlib) + interactive (Plotly) plotters.

Static plotters live in `viz.static` and return `matplotlib.figure.Figure`.
Interactive plotters live in `viz.interactive` and return
`plotly.graph_objects.Figure`. Plotly is an OPTIONAL dependency installed
via `pip install ont-end-reason[interactive]`.

Each subpackage's functions follow the convention `plot_<analysis_name>`
so callers can mechanically swap static for interactive.
"""

from __future__ import annotations

__all__: list[str] = []  # subpackages are accessed directly: viz.static / viz.interactive

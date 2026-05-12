"""viz subpackage — static (matplotlib) + interactive (Plotly) plotters.

Static plotters live in `viz.static` and return `matplotlib.figure.Figure`.
Interactive plotters live in `viz.interactive` and return
`plotly.graph_objects.Figure`. Plotly is an OPTIONAL dependency installed
via `pip install ont-end-reason[interactive]`.

Each subpackage's functions follow the convention `plot_<analysis_name>`
so callers can mechanically swap static for interactive.
"""

from __future__ import annotations

# Eagerly import submodules so `from ont_end_reason import viz; viz.interactive`
# attribute access works. Static is always available (matplotlib is required);
# interactive is OPTIONAL — its functions raise OntIOError with an install hint
# if plotly is missing at call time, so importing the module is safe.
from . import interactive, static

__all__ = ["interactive", "static"]

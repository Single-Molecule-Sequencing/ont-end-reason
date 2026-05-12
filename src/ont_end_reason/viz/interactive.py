"""Plotly-backed interactive plotters returning `plotly.graph_objects.Figure`.

Plotly is an OPTIONAL dependency; install with
`pip install ont-end-reason[interactive]`. Functions in this module raise
`OntIOError` with a clear install hint if Plotly is missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..analyze.distribution import DistributionResult
from ..codes import CODES
from ..errors import IOError as OntIOError

if TYPE_CHECKING:
    from plotly.graph_objects import Figure


_CATEGORY_ORDER = [
    "signal_positive",
    "unblock_mux_change",
    "data_service_unblock_mux_change",
    "mux_change",
    "partial",
    "unknown",
    "signal_negative",
]

_PALETTE = {
    "signal_positive": "#2ca02c",
    "unblock_mux_change": "#ff7f0e",
    "data_service_unblock_mux_change": "#d62728",
    "mux_change": "#9467bd",
    "partial": "#8c564b",
    "unknown": "#7f7f7f",
    "signal_negative": "#1f77b4",
}


def _require_plotly() -> "type":
    try:
        import plotly.graph_objects as go
    except ImportError as exc:
        raise OntIOError(
            "Plotly is required for interactive visualisation. "
            "Install with: pip install 'ont-end-reason[interactive]'"
        ) from exc
    return go  # type: ignore[return-value]


def interactive_distribution(
    result: DistributionResult,
    *,
    title: str | None = None,
) -> "Figure":
    """Interactive bar chart of end-reason distribution with hover details."""
    go = _require_plotly()

    ordered_keys = [k for k in _CATEGORY_ORDER if k in result.counts]
    for k in result.counts:
        if k not in ordered_keys:
            ordered_keys.append(k)

    short = [CODES.get(k, k.upper()[:4]) for k in ordered_keys]
    counts = [result.counts[k] for k in ordered_keys]
    pcts = [result.percentages.get(k, 0.0) * 100 for k in ordered_keys]
    colours = [_PALETTE.get(k, "#cccccc") for k in ordered_keys]
    hover_text = [
        f"<b>{k}</b><br>{counts[i]:,} reads<br>{pcts[i]:.2f}%"
        for i, k in enumerate(ordered_keys)
    ]

    fig = go.Figure(
        data=[
            go.Bar(
                x=short,
                y=counts,
                marker_color=colours,
                text=[f"{p:.1f}%" for p in pcts],
                textposition="outside",
                hovertext=hover_text,
                hoverinfo="text",
            )
        ]
    )
    fig.update_layout(
        title=title
        or (
            f"End reason distribution — {result.quality_status}  "
            f"(n = {result.total_reads:,})"
        ),
        xaxis_title="End reason",
        yaxis_title="Read count",
        showlegend=False,
        plot_bgcolor="white",
        margin={"l": 60, "r": 20, "t": 60, "b": 60},
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="lightgrey")
    return fig

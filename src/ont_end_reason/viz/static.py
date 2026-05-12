"""matplotlib-backed plotters returning publication-ready `Figure` objects.

Each function accepts the corresponding analysis result dataclass and
returns a `matplotlib.figure.Figure`. The caller saves / shows / composes
as needed — these functions deliberately do NOT call `plt.show()` or
`fig.savefig()`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..analyze.distribution import DistributionResult
from ..analyze.length import LengthResult
from ..analyze.temporal import TemporalResult
from ..codes import CODES

if TYPE_CHECKING:
    from matplotlib.figure import Figure


# Canonical category ordering (most-kept on left → most-rejected on right)
_CATEGORY_ORDER = [
    "signal_positive",
    "unblock_mux_change",
    "data_service_unblock_mux_change",
    "mux_change",
    "partial",
    "unknown",
    "signal_negative",
]

# Canonical colour palette aligned with paper Figure 3.
_PALETTE = {
    "signal_positive": "#2ca02c",
    "unblock_mux_change": "#ff7f0e",
    "data_service_unblock_mux_change": "#d62728",
    "mux_change": "#9467bd",
    "partial": "#8c564b",
    "unknown": "#7f7f7f",
    "signal_negative": "#1f77b4",
}


def plot_distribution(
    result: DistributionResult,
    *,
    title: str | None = None,
    show_pct: bool = True,
) -> Figure:
    """Bar chart of end-reason distribution.

    Parameters
    ----------
    result : DistributionResult
        Output of `analyze.distribution(...)`.
    title : str, optional
        Plot title. Default includes the quality status.
    show_pct : bool
        Annotate bars with percentages. Default True.
    """
    import matplotlib.pyplot as plt  # local import keeps cold-start fast

    ordered_keys = [k for k in _CATEGORY_ORDER if k in result.counts]
    # Append any unexpected categories at the end
    for k in result.counts:
        if k not in ordered_keys:
            ordered_keys.append(k)

    values = [result.counts[k] for k in ordered_keys]
    short_labels = [CODES.get(k, k.upper()[:4]) for k in ordered_keys]
    colours = [_PALETTE.get(k, "#cccccc") for k in ordered_keys]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(short_labels, values, color=colours, edgecolor="black", linewidth=0.5)

    if show_pct:
        for bar, key, _count in zip(bars, ordered_keys, values, strict=True):
            pct = result.percentages.get(key, 0.0) * 100
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{pct:.1f}%",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax.set_ylabel("Read count")
    ax.set_xlabel("End reason")
    if title is None:
        title = f"End reason distribution — {result.quality_status}  (n = {result.total_reads:,})"
    ax.set_title(title)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return fig


def plot_length_distribution(
    result: LengthResult,
    *,
    title: str | None = None,
    log_x: bool = True,
) -> Figure:
    """Overlay histogram of read lengths per end_reason category.

    Default x-axis is log-scale because ONT read-length distributions
    typically span 2-3 orders of magnitude. Pass `log_x=False` for linear.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ordered = [k for k in _CATEGORY_ORDER if k in result.raw_lengths_by_class]
    for k in result.raw_lengths_by_class:
        if k not in ordered:
            ordered.append(k)

    bins = np.logspace(2, 6, 60) if log_x else 60
    for key in ordered:
        lengths = result.raw_lengths_by_class[key]
        if not lengths:
            continue
        ax.hist(
            lengths,
            bins=bins,
            alpha=0.55,
            label=f"{CODES.get(key, key)} (n={len(lengths):,})",
            color=_PALETTE.get(key, "#cccccc"),
            edgecolor="none",
        )

    if log_x:
        ax.set_xscale("log")
    ax.set_xlabel("Read length (bp)")
    ax.set_ylabel("Read count")
    ax.set_title(
        title or f"Read length distribution by end_reason (n = {result.total_reads:,})"
    )
    ax.legend(frameon=False, fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return fig


def plot_temporal(
    result: TemporalResult,
    *,
    title: str | None = None,
    show_fractions: bool = True,
) -> Figure:
    """Stacked-area plot of end_reason fractions over time.

    If `show_fractions=True` (default), the y-axis is per-bin fraction
    summing to 1.0. If False, raw counts are plotted (useful for spotting
    throughput drops).
    """
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(9, 4.5))
    centers = np.asarray(result.bin_centers, dtype=float)
    ordered = [k for k in _CATEGORY_ORDER if k in result.fractions_by_class]
    for k in result.fractions_by_class:
        if k not in ordered:
            ordered.append(k)

    data_dict = (
        result.fractions_by_class if show_fractions else result.counts_by_class
    )
    stack = np.array([data_dict[k] for k in ordered], dtype=float)
    colours = [_PALETTE.get(k, "#cccccc") for k in ordered]
    labels = [CODES.get(k, k) for k in ordered]
    ax.stackplot(centers, stack, labels=labels, colors=colours, alpha=0.85)

    ax.set_xlabel("Time since run start (hours)")
    ax.set_ylabel("Fraction of reads" if show_fractions else "Read count")
    ax.set_title(
        title or f"End reason rates over time  (n = {result.total_reads:,})"
    )
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if show_fractions:
        ax.set_ylim(0, 1.0)
    fig.tight_layout()
    return fig

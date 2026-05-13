"""Tests for figures/ subpackage — paper figure reproducers.

These exercise the composition layer that wires analyze.* → viz.* → PDF.
Each fig*() takes a sequencing_summary path and writes a publication-ready
plot; the test just asserts non-empty bytes land at the requested path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

from ont_end_reason.figures import (
    fig3_distribution,
    fig5_violin,
    fig6_conceptual,
    supplementary,
)

FIXTURE_SUMMARY = Path(__file__).parent.parent / "fixtures" / "sequencing_summary_synthetic.txt"


@pytest.mark.parametrize(
    ("name", "fig_fn", "ext"),
    [
        ("fig3_distribution", fig3_distribution, "png"),
        ("fig5_violin", fig5_violin, "png"),
        ("fig6_conceptual", fig6_conceptual, "png"),
    ],
)
def test_figure_reproducer_writes_nonempty_output(
    tmp_path: Path, name: str, fig_fn: object, ext: str
) -> None:
    out = tmp_path / f"{name}.{ext}"
    result_path = fig_fn(FIXTURE_SUMMARY, out=out)  # type: ignore[operator]
    assert Path(result_path) == out
    assert out.exists()
    assert out.stat().st_size > 1024


def test_fig3_distribution_quick_mode(tmp_path: Path) -> None:
    out = tmp_path / "fig3_quick.png"
    fig3_distribution(FIXTURE_SUMMARY, out=out, quick=True)
    assert out.exists()


def test_fig3_creates_parent_directory(tmp_path: Path) -> None:
    """fig*() must create missing parent directories."""
    out = tmp_path / "deep" / "nested" / "fig3.png"
    fig3_distribution(FIXTURE_SUMMARY, out=out)
    assert out.exists()


def test_supplementary_raises_with_pointer(tmp_path: Path) -> None:
    """Supplementary is still a scaffold — must raise with a useful message."""
    with pytest.raises(NotImplementedError, match=r"v0\.2\.0|TOOL_SPECIFICATIONS"):
        supplementary(FIXTURE_SUMMARY, out=tmp_path / "supp.png")


# ───────────────────────── atlas (fig8) reproducer ─────────────────────────


def test_atlas_figure_empty_store(tmp_path: Path, monkeypatch) -> None:
    """`figures.atlas()` on an empty atlas → friendly placeholder PNG.

    Forces the empty-state path by patching the atlas() function imported
    into the figures.atlas reproducer. This is the realistic CI case (no
    qc_baseline + no parquet cache) and must NOT crash.
    """
    import importlib

    # Get the module objects (the package __init__ rebinds the name `atlas`
    # to a function, so we can't `from ont_end_reason.analyze import atlas`).
    analyze_atlas_mod = importlib.import_module("ont_end_reason.analyze.atlas")
    figures_atlas_mod = importlib.import_module("ont_end_reason.figures.atlas")

    empty_result = analyze_atlas_mod.AtlasResult(
        n_internal=0,
        n_external=0,
        strata_keys=list(analyze_atlas_mod.DEFAULT_STRATA),
        per_stratum=[],
        outliers=[],
        interpretation="Empty atlas.",
        generated_at="2026-05-12T00:00:00+00:00",
    )
    # Patch the symbol the figures reproducer actually calls.
    monkeypatch.setattr(figures_atlas_mod, "atlas_analyze", lambda **kw: empty_result)

    out = tmp_path / "atlas_empty.png"
    result_path = figures_atlas_mod.atlas(out=out)
    assert Path(result_path) == out
    assert out.exists()
    assert out.stat().st_size > 1024


def test_atlas_figure_synthetic_result(tmp_path: Path) -> None:
    """Feeding a synthetic AtlasResult with 3 strata produces a non-trivial PNG."""
    import matplotlib.pyplot as plt

    from ont_end_reason.analyze.atlas import AtlasResult, StratumStats
    from ont_end_reason.viz.static import plot_atlas_summary

    per_stratum = [
        StratumStats(
            stratum=("PromethION", "R10.4.1", "True"),
            n_runs=8,
            metric_stats={
                "signal_positive_pct": {
                    "mean": 92.0,
                    "median": 92.5,
                    "std": 2.0,
                    "min": 88.0,
                    "max": 95.0,
                    "count": 8.0,
                },
                "unblock_mux_pct": {
                    "mean": 4.0,
                    "median": 4.0,
                    "std": 1.0,
                    "min": 2.0,
                    "max": 6.0,
                    "count": 8.0,
                },
                "data_service_pct": {
                    "mean": 2.0,
                    "median": 2.0,
                    "std": 0.5,
                    "min": 1.0,
                    "max": 3.0,
                    "count": 8.0,
                },
            },
        ),
        StratumStats(
            stratum=("MinION", "R10.4.1", "False"),
            n_runs=4,
            metric_stats={
                "signal_positive_pct": {
                    "mean": 85.0,
                    "median": 86.0,
                    "std": 3.0,
                    "min": 80.0,
                    "max": 90.0,
                    "count": 4.0,
                },
                "unblock_mux_pct": {
                    "mean": 8.0,
                    "median": 8.0,
                    "std": 1.5,
                    "min": 5.0,
                    "max": 11.0,
                    "count": 4.0,
                },
            },
        ),
        StratumStats(
            stratum=("GridION", "R9.4.1", "True"),
            n_runs=2,  # below min_stratum_size — should render with low-conf style
            metric_stats={
                "signal_positive_pct": {
                    "mean": 70.0,
                    "median": 70.0,
                    "std": 5.0,
                    "min": 65.0,
                    "max": 75.0,
                    "count": 2.0,
                },
            },
        ),
    ]
    result = AtlasResult(
        n_internal=12,
        n_external=2,
        strata_keys=["flowcell_type", "chemistry", "adaptive_sampling"],
        per_stratum=per_stratum,
        outliers=[],
        interpretation="Atlas spans 12 internal + 2 external runs; no outliers flagged.",
        generated_at="2026-05-12T00:00:00+00:00",
    )

    fig = plot_atlas_summary(result)
    # Figure has one axes and at least one bar (matplotlib stores bars as patches).
    assert len(fig.axes) == 1
    ax = fig.axes[0]
    # 3 strata × up-to 3 metrics with non-empty stats. Each `ax.bar(xi, ...)`
    # adds one Rectangle patch. Below: 3 + 2 + 1 = 6 metric-bars.
    patches = list(ax.patches)
    assert len(patches) >= 5, f"expected ≥5 bar patches, got {len(patches)}"
    # X-axis tick count == number of strata
    assert len(ax.get_xticks()) == 3
    # Title mentions the run counts
    title = ax.get_title()
    assert "12" in title and "2" in title and "3 strata" in title

    out = tmp_path / "atlas_synth.png"
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    assert out.exists()
    assert out.stat().st_size > 1024


def test_atlas_figure_via_real_analyze(tmp_path: Path) -> None:
    """End-to-end smoke: call `figures.atlas(out=...)` with no precomputed
    result. On a fresh CI runner the atlas store is empty so this exercises
    the placeholder path through the real analyze call — must produce a PNG.
    """
    from ont_end_reason.figures import atlas as fig_atlas

    out = tmp_path / "atlas_e2e.png"
    fig_atlas(out=out)
    assert out.exists()
    assert out.stat().st_size > 1024

"""Smoke tests for viz/static plotters + the composed HTML report.

These don't pixel-check the figures (that's brittle); they confirm each
plot function returns a matplotlib Figure with the expected number of
axes / lines, and the report renders an HTML file with the expected
section count.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless rendering in CI

import pytest

from ont_end_reason.analyze.distribution import distribution
from ont_end_reason.analyze.length import length
from ont_end_reason.analyze.quality import quality
from ont_end_reason.analyze.temporal import temporal
from ont_end_reason.analyze.umc_posterior import umc_posterior
from ont_end_reason.report.html import build_html_report
from ont_end_reason.viz.static import (
    plot_distribution,
    plot_length_distribution,
    plot_quality_violins,
    plot_temporal,
    plot_umc_posterior,
)

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sequencing_summary_synthetic.txt"


class TestStaticPlots:
    def test_plot_distribution_returns_figure(self) -> None:
        result = distribution(FIXTURE)
        fig = plot_distribution(result)
        assert hasattr(fig, "savefig")
        assert len(fig.axes) == 1

    def test_plot_length_distribution_returns_figure(self) -> None:
        result = length(FIXTURE)
        fig = plot_length_distribution(result)
        assert len(fig.axes) == 1

    def test_plot_quality_violins(self) -> None:
        result = quality(FIXTURE)
        fig = plot_quality_violins(result)
        assert len(fig.axes) == 1

    def test_plot_temporal(self) -> None:
        result = temporal(FIXTURE)
        fig = plot_temporal(result)
        assert len(fig.axes) == 1

    def test_plot_umc_posterior_two_panels(self) -> None:
        result = umc_posterior(FIXTURE)
        fig = plot_umc_posterior(result)
        # Two-panel layout for UMC posterior
        assert len(fig.axes) == 2

    def test_plots_save_to_pdf(self, tmp_path: Path) -> None:
        for analysis, plotter, suffix in [
            (distribution(FIXTURE), plot_distribution, "dist"),
            (length(FIXTURE), plot_length_distribution, "len"),
            (quality(FIXTURE), plot_quality_violins, "qual"),
            (temporal(FIXTURE), plot_temporal, "temp"),
            (umc_posterior(FIXTURE), plot_umc_posterior, "umc"),
        ]:
            fig = plotter(analysis)
            out = tmp_path / f"{suffix}.pdf"
            fig.savefig(out)
            assert out.exists()
            assert out.stat().st_size > 1000  # at least 1 KB


class TestHtmlReport:
    def test_report_renders_all_sections(self, tmp_path: Path) -> None:
        out = tmp_path / "report.html"
        result = build_html_report(FIXTURE, output_path=out)
        # All 6 sections should succeed against the fixture
        assert set(result.sections) == {
            "distribution", "length", "quality", "temporal",
            "umc_posterior", "hypothesis",
        }
        assert result.n_reads == 5000
        # File exists + non-trivial size
        assert out.exists()
        assert out.stat().st_size > 100_000  # > 100 KB with embedded Plotly

    def test_report_contains_section_headers(self, tmp_path: Path) -> None:
        out = tmp_path / "report.html"
        build_html_report(FIXTURE, output_path=out)
        text = out.read_text()
        for hdr in [
            "End reason distribution",
            "Read length distribution",
            "Q-score distribution",
            "Temporal patterns",
            "UMC posterior",
            "Statistical comparisons",
        ]:
            assert hdr in text

"""Tests for analyze.tables, analyze.sma_metrics, and analyze.signal_trace
(the signal_trace test is import-only since we have no POD5 fixture)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ont_end_reason.analyze.sma_metrics import sma_metrics
from ont_end_reason.analyze.signal_trace import signal_trace
from ont_end_reason.analyze.tables import generate_tables, render_all
from ont_end_reason.errors import AnalysisError

pytestmark = pytest.mark.fast

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sequencing_summary_synthetic.txt"


class TestTables:
    def test_summary_table(self) -> None:
        t = generate_tables(FIXTURE, name="summary")
        assert t.name == "summary"
        assert len(t.rows) == 1
        assert t.rows[0]["total_reads"] == 5000

    def test_per_class_table(self) -> None:
        t = generate_tables(FIXTURE, name="per_class")
        assert len(t.rows) == 5  # SP UMC DUMC MC SN
        sp_row = next(r for r in t.rows if r["end_reason"] == "signal_positive")
        assert sp_row["n"] == 4000

    def test_quality_table(self) -> None:
        t = generate_tables(FIXTURE, name="quality")
        assert len(t.rows) == 5
        sp_row = next(r for r in t.rows if r["end_reason"] == "signal_positive")
        assert 20.0 < sp_row["mean_q"] < 24.0

    def test_render_tsv(self) -> None:
        t = generate_tables(FIXTURE, name="summary", fmt="tsv")
        text = t.render()
        assert "total_reads" in text
        assert "\t" in text

    def test_render_markdown(self) -> None:
        t = generate_tables(FIXTURE, name="summary", fmt="markdown")
        text = t.render()
        assert "|" in text  # markdown table delimiter

    def test_unknown_name_raises(self) -> None:
        with pytest.raises(AnalysisError):
            generate_tables(FIXTURE, name="bogus")

    def test_render_all(self) -> None:
        out = render_all(FIXTURE)
        assert set(out) == {"summary", "per_class", "quality"}


class TestSmaMetrics:
    def test_returns_well_formed_result(self) -> None:
        """Whether smaseq_qc is installed or not, the result is well-formed."""
        result = sma_metrics(FIXTURE)
        assert isinstance(result.available, bool)
        assert "smaseq-qc" in result.delegated_to
        assert isinstance(result.notes, list)
        if result.available:
            assert result.delegated_to.startswith("smaseq-qc==")
        else:
            assert "install" in " ".join(result.notes).lower()

    def test_does_not_raise_on_bad_path(self) -> None:
        # Robustness contract: never raises even for nonexistent paths
        result = sma_metrics("/nonexistent/path")
        assert isinstance(result.available, bool)


class TestSignalTraceImport:
    def test_function_signature(self) -> None:
        # Smoke: function importable, raises clear error if no POD5 + read_id
        import inspect

        sig = inspect.signature(signal_trace)
        assert "read_id" in sig.parameters

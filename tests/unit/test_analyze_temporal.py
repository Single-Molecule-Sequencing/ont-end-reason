"""Tests for analyze.temporal against the synthetic fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from ont_end_reason.analyze.temporal import temporal
from ont_end_reason.errors import AnalysisError, IOError as OntIOError

pytestmark = pytest.mark.fast

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sequencing_summary_synthetic.txt"


class TestTemporal:
    def test_runs_on_fixture(self) -> None:
        result = temporal(FIXTURE)
        assert result.total_reads == 5000
        assert result.bin_seconds == 3600.0
        # Fixture covers 24h → ~24 bins
        assert 20 <= len(result.bin_centers) <= 28

    def test_counts_per_class_sum_to_total(self) -> None:
        result = temporal(FIXTURE)
        per_class_totals = {k: sum(v) for k, v in result.counts_by_class.items()}
        assert sum(per_class_totals.values()) == result.total_reads

    def test_fractions_sum_to_one_per_bin(self) -> None:
        result = temporal(FIXTURE)
        n_bins = len(result.bin_centers)
        for i in range(n_bins):
            bin_sum = sum(v[i] for v in result.fractions_by_class.values())
            # Some bins may be empty (sum = 0); others should sum to ~1.0
            assert 0.0 <= bin_sum <= 1.01

    def test_custom_bin_size(self) -> None:
        result = temporal(FIXTURE, bin_seconds=7200.0)
        # 24h with 2h bins → 12 bins
        assert 10 <= len(result.bin_centers) <= 14
        assert result.bin_seconds == 7200.0

    def test_signal_positive_dominates_globally(self) -> None:
        result = temporal(FIXTURE)
        sp_counts = sum(result.counts_by_class.get("signal_positive", []))
        total = result.total_reads
        # Fixture is 80% SP; allow slight rounding variation
        assert 0.75 < sp_counts / total < 0.85

    def test_to_dict_serialisable(self) -> None:
        import json

        result = temporal(FIXTURE)
        text = json.dumps(result.to_dict())
        round_trip = json.loads(text)
        assert round_trip["total_reads"] == 5000

    def test_non_summary_path_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "not_a_summary.txt"
        p.write_text("garbage")
        with pytest.raises((OntIOError, AnalysisError)):
            temporal(p)

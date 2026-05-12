"""analyze.length tests using the synthetic fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from ont_end_reason.analyze.length import _n50, length
from ont_end_reason.errors import AnalysisError

pytestmark = pytest.mark.fast

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sequencing_summary_synthetic.txt"


class TestN50:
    def test_simple(self) -> None:
        import numpy as np

        # 5 reads of 10 each: cumulative 50; half = 25; sorted-desc [10,10,10,10,10]
        # idx where cumsum >= 25 is 2 → length = 10
        assert _n50(np.array([10, 10, 10, 10, 10])) == 10

    def test_single(self) -> None:
        import numpy as np

        assert _n50(np.array([100])) == 100

    def test_empty(self) -> None:
        import numpy as np

        assert _n50(np.array([], dtype=int)) == 0

    def test_skewed(self) -> None:
        # One huge read dominates N50
        import numpy as np

        # 1 read of 1000, 9 reads of 10. Total = 1090; half = 545.
        # Sorted desc: [1000, 10, 10, ...]; cumsum first crosses 545 at idx 0.
        # So N50 = 1000.
        lengths = np.array([1000] + [10] * 9)
        assert _n50(lengths) == 1000


class TestLengthAnalysis:
    def test_runs_on_fixture(self) -> None:
        result = length(FIXTURE)
        assert result.total_reads == 5000
        # All five end_reasons present
        assert set(result.per_class) == {
            "signal_positive",
            "unblock_mux_change",
            "data_service_unblock_mux_change",
            "mux_change",
            "signal_negative",
        }

    def test_signal_positive_is_longest(self) -> None:
        """SP reads were generated with lognormal mean exp(8.5) ≈ 4914 bp.
        Median should be much longer than any other class."""
        result = length(FIXTURE)
        sp_median = result.per_class["signal_positive"].median
        umc_median = result.per_class["unblock_mux_change"].median
        sn_median = result.per_class["signal_negative"].median
        assert sp_median > umc_median > sn_median
        assert sp_median > 3000  # roughly exp(8.5)/1.3 generous lower bound

    def test_n50_per_class_positive(self) -> None:
        result = length(FIXTURE)
        for er, stats in result.per_class.items():
            assert stats.n50 > 0, f"{er} has zero N50"
            assert stats.n50 >= stats.median * 0.5, f"{er} N50 < half median"

    def test_to_dict_serialisable(self) -> None:
        import json

        result = length(FIXTURE)
        text = json.dumps(result.to_dict())
        round_trip = json.loads(text)
        assert round_trip["total_reads"] == 5000
        assert "signal_positive" in round_trip["per_class"]

    def test_raw_lengths_kept_for_viz(self) -> None:
        result = length(FIXTURE)
        # ~80% SP → ~4000 SP reads, all kept (cap is 50k)
        sp_raw = result.raw_lengths_by_class["signal_positive"]
        assert 3500 <= len(sp_raw) <= 4500
        # SN is only 1% → ~50 reads
        sn_raw = result.raw_lengths_by_class["signal_negative"]
        assert 30 <= len(sn_raw) <= 70

    def test_empty_source_raises(self, tmp_path: Path) -> None:
        # detect_format requires the filename start with sequencing_summary
        empty = tmp_path / "sequencing_summary_empty.txt"
        empty.write_text("read_id\tend_reason\tsequence_length_template\tmean_qscore_template\n")
        with pytest.raises(AnalysisError):
            length(empty)

    def test_records_iterable_mode(self) -> None:
        from ont_end_reason.io.manifest import ReadRecord

        records = [
            ReadRecord(read_id=f"r{i}", end_reason="signal_positive", length=1000 + i)
            for i in range(100)
        ]
        result = length(records)
        assert result.total_reads == 100
        assert result.per_class["signal_positive"].n == 100

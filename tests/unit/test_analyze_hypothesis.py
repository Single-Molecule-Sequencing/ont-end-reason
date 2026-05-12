"""Tests for analyze.hypothesis."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ont_end_reason.analyze.hypothesis import _cliffs_delta, hypothesis
from ont_end_reason.errors import AnalysisError

pytestmark = pytest.mark.fast

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sequencing_summary_synthetic.txt"


class TestCliffsDelta:
    def test_identical_distributions_delta_zero(self) -> None:
        rng = np.random.default_rng(0)
        x = rng.normal(0, 1, 200)
        d = _cliffs_delta(x.copy(), x.copy())
        assert abs(d) < 0.1  # close to zero

    def test_a_greater_than_b(self) -> None:
        d = _cliffs_delta(np.array([10, 11, 12]), np.array([1, 2, 3]))
        assert d > 0.9

    def test_b_greater_than_a(self) -> None:
        d = _cliffs_delta(np.array([1, 2, 3]), np.array([10, 11, 12]))
        assert d < -0.9


class TestHypothesis:
    def test_sp_vs_umc_length_significant(self) -> None:
        # In fixture, SP is much longer than UMC → MW should be very significant
        result = hypothesis(FIXTURE, a="SP", b="UMC", column="sequence_length_template")
        assert result.test == "mann-whitney"
        assert result.p_value < 1e-50
        assert result.effect_size > 0.5  # large positive (SP > UMC)
        assert result.median_a > result.median_b

    def test_sp_vs_umc_qscore_significant(self) -> None:
        result = hypothesis(FIXTURE, a="SP", b="UMC", column="mean_qscore_template")
        # SP qscores higher than UMC qscores
        assert result.median_a > result.median_b
        assert result.p_value < 1e-50

    def test_ks_alternative(self) -> None:
        result = hypothesis(FIXTURE, a="SP", b="UMC", test="ks")
        assert result.test == "ks"

    def test_full_name_resolution(self) -> None:
        result = hypothesis(
            FIXTURE, a="signal_positive", b="unblock_mux_change"
        )
        assert result.comparison == ("signal_positive", "unblock_mux_change")

    def test_unknown_test_raises(self) -> None:
        with pytest.raises(AnalysisError, match="Unknown test"):
            hypothesis(FIXTURE, a="SP", b="UMC", test="t-test")

    def test_unknown_class_raises(self) -> None:
        with pytest.raises(AnalysisError, match="Unknown end_reason"):
            hypothesis(FIXTURE, a="BOGUS", b="UMC")

    def test_to_dict_serialisable(self) -> None:
        import json

        result = hypothesis(FIXTURE, a="SP", b="UMC")
        text = json.dumps(result.to_dict())
        assert "mann-whitney" in text

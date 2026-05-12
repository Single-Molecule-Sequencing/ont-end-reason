"""Tests for analyze.quality including GMM fit."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ont_end_reason.analyze.quality import _fit_gmm_em, _select_best_gmm, quality

pytestmark = pytest.mark.fast

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sequencing_summary_synthetic.txt"


class TestGMM:
    def test_em_single_component_recovers_mean(self) -> None:
        rng = np.random.default_rng(0)
        x = rng.normal(loc=20.0, scale=2.0, size=500)
        components, _ = _fit_gmm_em(x, k=1)
        assert len(components) == 1
        assert abs(components[0].mean - 20.0) < 0.5
        assert abs(components[0].sd - 2.0) < 0.5

    def test_em_two_component_recovers_bimodal(self) -> None:
        rng = np.random.default_rng(0)
        x = np.concatenate(
            [rng.normal(loc=10.0, scale=1.0, size=300),
             rng.normal(loc=25.0, scale=1.0, size=300)]
        )
        components, _ = _fit_gmm_em(x, k=2)
        assert len(components) == 2
        # Components ordered by mean
        assert abs(components[0].mean - 10.0) < 1.0
        assert abs(components[1].mean - 25.0) < 1.0

    def test_select_best_prefers_smaller_k_for_unimodal(self) -> None:
        rng = np.random.default_rng(0)
        x = rng.normal(loc=22.0, scale=2.5, size=400)
        _components, k, _bic, _aic = _select_best_gmm(x, k_max=3)
        # BIC should prefer k=1 for clearly unimodal data
        assert k == 1

    def test_select_best_prefers_two_for_bimodal(self) -> None:
        rng = np.random.default_rng(0)
        x = np.concatenate(
            [rng.normal(loc=8.0, scale=1.5, size=400),
             rng.normal(loc=22.0, scale=2.5, size=400)]
        )
        _, k, _, _ = _select_best_gmm(x, k_max=3)
        assert k == 2


class TestQuality:
    def test_runs_on_fixture(self) -> None:
        result = quality(FIXTURE)
        assert result.total_reads == 5000
        assert "signal_positive" in result.per_class

    def test_signal_positive_mean_qscore_high(self) -> None:
        result = quality(FIXTURE)
        sp = result.per_class["signal_positive"]
        # Fixture generates SP qscores ~22; allow for randomness
        assert 21.0 < sp.mean < 23.0

    def test_signal_negative_mean_qscore_low(self) -> None:
        result = quality(FIXTURE)
        sn = result.per_class["signal_negative"]
        # Fixture generates SN qscores ~8
        assert 6.0 < sn.mean < 10.0

    def test_gmm_components_have_valid_weights(self) -> None:
        result = quality(FIXTURE)
        for er, stats in result.per_class.items():
            total_weight = sum(c.weight for c in stats.gmm_components)
            assert abs(total_weight - 1.0) < 0.01, f"{er} weights sum {total_weight}"

    def test_to_dict_serialisable(self) -> None:
        import json

        result = quality(FIXTURE)
        text = json.dumps(result.to_dict())
        assert "signal_positive" in text

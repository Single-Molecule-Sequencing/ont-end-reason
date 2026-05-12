"""Tests for analyze.umc_posterior — the paper's central novel analysis."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ont_end_reason.analyze.umc_posterior import (
    _fit_lognormal,
    _truncated_lognormal_moments,
    umc_posterior,
)
from ont_end_reason.errors import AnalysisError

pytestmark = pytest.mark.fast

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sequencing_summary_synthetic.txt"


class TestFitLognormal:
    def test_recovers_known_params(self) -> None:
        rng = np.random.default_rng(0)
        true_mu, true_sigma = 8.5, 0.6
        x = rng.lognormal(mean=true_mu, sigma=true_sigma, size=2000)
        mu, sigma = _fit_lognormal(x)
        assert abs(mu - true_mu) < 0.1
        assert abs(sigma - true_sigma) < 0.1

    def test_too_few_reads_raises(self) -> None:
        with pytest.raises(AnalysisError, match="at least 10"):
            _fit_lognormal(np.array([100.0, 200.0]))


class TestTruncatedMoments:
    def test_mean_at_zero_obs_equals_unconditional(self) -> None:
        mu, sigma = 8.0, 0.6
        # obs = 0 → posterior is unconditional lognormal → mean = exp(mu + sigma^2/2)
        unconditional = np.exp(mu + sigma**2 / 2)
        means, _, _, _ = _truncated_lognormal_moments(
            np.array([0.0001]), mu, sigma
        )
        assert abs(means[0] - unconditional) / unconditional < 0.01

    def test_mean_grows_with_obs(self) -> None:
        mu, sigma = 8.0, 0.6
        means, _, _, _ = _truncated_lognormal_moments(
            np.array([500.0, 5000.0, 50000.0]), mu, sigma
        )
        # The truncated mean must be >= the truncation threshold
        assert means[0] < means[1] < means[2]
        assert means[2] >= 50000.0


class TestUMCPosterior:
    def test_runs_on_fixture(self) -> None:
        result = umc_posterior(FIXTURE)
        # Fixture has 600 UMC reads
        assert result.n_umc_reads == 600

    def test_prior_recovers_known_lognormal(self) -> None:
        # SP reads in fixture: lognormal(mu=8.5, sigma=0.6)
        result = umc_posterior(FIXTURE)
        assert abs(result.prior_log_mu - 8.5) < 0.05
        assert abs(result.prior_log_sigma - 0.6) < 0.05

    def test_posterior_mean_at_or_above_observed_mean(self) -> None:
        # The posterior expected true length MUST be >= the observed length
        # (because the observation is a lower bound on the true length)
        result = umc_posterior(FIXTURE)
        assert result.posterior_expected_true_mean >= result.observed_mean

    def test_bonus_is_positive_on_average(self) -> None:
        result = umc_posterior(FIXTURE)
        assert result.posterior_bonus_mean > 0
        # Total bonus = mean × n
        assert result.posterior_bonus_total > 0

    def test_invalid_prior_class_raises(self) -> None:
        with pytest.raises(AnalysisError):
            umc_posterior(FIXTURE, prior_class="nonexistent_class")

    def test_to_dict_serialisable(self) -> None:
        import json

        result = umc_posterior(FIXTURE)
        text = json.dumps(result.to_dict())
        d = json.loads(text)
        assert d["n_umc_reads"] == 600
        assert d["prior_class"] == "signal_positive"

    def test_per_read_arrays_match_n(self) -> None:
        result = umc_posterior(FIXTURE)
        # Less than max_raw_per_class → arrays match n
        assert len(result.posterior_means_per_read) == 600
        assert len(result.bonus_per_read) == 600

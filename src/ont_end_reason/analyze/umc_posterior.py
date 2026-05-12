"""Posterior length model for UMC reads (TOOL_SPEC type 11).

This is the paper's central novel analysis. UMC ("unblock_mux_change") reads
are truncated at the adaptive-sampling unblock decision point, so the
observed length is a LOWER BOUND on the true (had-it-completed) length.

Bayesian framing:

  true_length L | end_reason=UMC  ~  prior(L)         (informed by SP reads)
  observed_length O = min(L, T_unblock)                where T_unblock is the
                                                        adaptive-sampling
                                                        decision time × translocation
  P(L | O=o)  ∝  P(O=o | L) · P(L)                    left-censored: L ≥ o

For v0.2.0 simple impl we make two operational choices:

  1. Prior on L is a lognormal fit to SP reads (the population that
     completed without intervention).
  2. Posterior given O=o is the prior truncated below at o, since the
     observed length is the maximum we know-for-sure the molecule had.

The result returns the per-UMC posterior expected true length, expected
"bonus" (true − observed), and a 95% credible interval. Aggregated over
all UMC reads, this gives the paper's estimate of how much sequence was
"lost" to adaptive-sampling truncation.

Implementation is scipy-only; runs in O(n) over the UMC reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import lognorm

from ..codes import NAMES
from ..errors import AnalysisError, IOError as OntIOError


@dataclass
class UMCPosteriorResult:
    """Posterior over true UMC length given observed truncation."""

    n_umc_reads: int = 0
    prior_class: str = "signal_positive"
    prior_log_mu: float = 0.0
    prior_log_sigma: float = 1.0
    observed_mean: float = 0.0
    observed_median: float = 0.0
    posterior_expected_true_mean: float = 0.0
    posterior_expected_true_median: float = 0.0
    posterior_bonus_mean: float = 0.0
    posterior_bonus_total: float = 0.0
    credible_interval_95_per_read_mean: tuple[float, float] = (0.0, 0.0)
    # Per-read posterior summaries (capped at 50k for memory)
    posterior_means_per_read: list[float] = field(default_factory=list)
    bonus_per_read: list[float] = field(default_factory=list)
    source: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "n_umc_reads": self.n_umc_reads,
            "prior_class": self.prior_class,
            "prior_log_mu": round(self.prior_log_mu, 4),
            "prior_log_sigma": round(self.prior_log_sigma, 4),
            "observed_mean": round(self.observed_mean, 2),
            "observed_median": round(self.observed_median, 2),
            "posterior_expected_true_mean": round(self.posterior_expected_true_mean, 2),
            "posterior_expected_true_median": round(
                self.posterior_expected_true_median, 2
            ),
            "posterior_bonus_mean": round(self.posterior_bonus_mean, 2),
            "posterior_bonus_total": round(self.posterior_bonus_total, 2),
            "credible_interval_95_per_read_mean": [
                round(v, 2) for v in self.credible_interval_95_per_read_mean
            ],
            "source": self.source,
        }


def _fit_lognormal(lengths: np.ndarray) -> tuple[float, float]:
    """Fit lognormal to length array by MLE on log(lengths)."""
    if len(lengths) < 10:
        raise AnalysisError("Need at least 10 reads to fit a lognormal prior")
    log_x = np.log(lengths[lengths > 0])
    mu = float(np.mean(log_x))
    sigma = float(np.std(log_x, ddof=1))
    return mu, max(sigma, 1e-3)


def _truncated_lognormal_moments(
    obs: np.ndarray, mu: float, sigma: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (mean, median, lo95, hi95) of L | L >= obs, with L ~ Lognormal(mu, sigma).

    Vectorised over `obs`. Uses scipy's lognorm and a small numerical
    integration trick: the truncated mean has a closed form via the
    normal-CDF Mills ratio.
    """
    # scipy parameterisation: lognorm(s=sigma, scale=exp(mu))
    rv = lognorm(s=sigma, scale=float(np.exp(mu)))
    # P(L >= obs) = 1 - F(obs)
    one_minus_F = rv.sf(obs)
    one_minus_F = np.clip(one_minus_F, 1e-15, 1.0)

    # E[L | L >= obs] for lognormal:
    #   E[L | L>=o] = exp(mu + sigma^2 / 2) * Phi(-(log(o) - mu - sigma^2)/sigma) / (1 - F(o))
    # where Phi is the standard-normal CDF
    from scipy.stats import norm

    z = (np.log(np.maximum(obs, 1e-9)) - mu) / sigma
    # Numerator term: Phi((mu + sigma^2 - log(o)) / sigma) = Phi(sigma - z)
    num = norm.cdf(sigma - z)
    mean_truncated = float(np.exp(mu + sigma**2 / 2)) * (num / one_minus_F)

    # Median: F^{-1}(0.5 * (1 + F(obs))) — pointwise via scipy
    p_med = 0.5 * (1.0 + rv.cdf(obs))
    med_truncated = rv.ppf(np.clip(p_med, 1e-9, 1 - 1e-9))

    # 95% CI of the per-read posterior: from the truncated dist
    p_lo = 0.025 * (1.0 - rv.cdf(obs)) + rv.cdf(obs)
    p_hi = 0.975 * (1.0 - rv.cdf(obs)) + rv.cdf(obs)
    lo95 = rv.ppf(np.clip(p_lo, 1e-9, 1 - 1e-9))
    hi95 = rv.ppf(np.clip(p_hi, 1e-9, 1 - 1e-9))

    return mean_truncated, med_truncated, lo95, hi95


def _stream_lengths_by_class(
    path: Path,
) -> dict[str, np.ndarray]:
    by_class: dict[str, list[np.ndarray]] = {}
    try:
        for chunk in pd.read_csv(
            path,
            sep="\t",
            usecols=["end_reason", "sequence_length_template"],
            chunksize=200_000,
        ):
            chunk = chunk[chunk["sequence_length_template"] > 0]
            for er, grp in chunk.groupby("end_reason"):
                by_class.setdefault(str(er), []).append(
                    grp["sequence_length_template"].to_numpy(dtype=np.float64)
                )
    except (OSError, ValueError, KeyError) as exc:
        raise OntIOError(f"Failed to stream {path}: {exc}") from exc
    return {k: np.concatenate(v) for k, v in by_class.items()}


def umc_posterior(
    source: str | Path,
    *,
    prior_class: str = "signal_positive",
    max_raw_per_class: int = 50_000,
) -> UMCPosteriorResult:
    """Estimate posterior over true UMC read length.

    Parameters
    ----------
    source : path-like
        sequencing_summary.txt
    prior_class : str
        End reason whose length distribution provides the prior on the
        completed-read length. Default "signal_positive" (the population
        that wasn't truncated).
    """
    path = Path(source)
    if not path.is_file():
        raise OntIOError(f"umc_posterior requires a sequencing_summary file: {path}")

    if prior_class.upper() in NAMES:
        prior_class = NAMES[prior_class.upper()]

    arrays = _stream_lengths_by_class(path)
    if "unblock_mux_change" not in arrays or len(arrays["unblock_mux_change"]) == 0:
        raise AnalysisError("No unblock_mux_change reads in source")
    if prior_class not in arrays:
        raise AnalysisError(f"Prior class {prior_class!r} not in source")

    obs = arrays["unblock_mux_change"]
    prior_lengths = arrays[prior_class]

    mu, sigma = _fit_lognormal(prior_lengths)

    means, meds, lo95, hi95 = _truncated_lognormal_moments(obs, mu, sigma)

    # Cap per-read arrays for memory
    rng = np.random.default_rng(0)
    if len(obs) > max_raw_per_class:
        idx = rng.choice(len(obs), size=max_raw_per_class, replace=False)
        means_keep = means[idx]
        bonus_keep = (means - obs)[idx]
    else:
        means_keep = means
        bonus_keep = means - obs

    return UMCPosteriorResult(
        n_umc_reads=int(len(obs)),
        prior_class=prior_class,
        prior_log_mu=mu,
        prior_log_sigma=sigma,
        observed_mean=float(np.mean(obs)),
        observed_median=float(np.median(obs)),
        posterior_expected_true_mean=float(np.mean(means)),
        posterior_expected_true_median=float(np.median(meds)),
        posterior_bonus_mean=float(np.mean(means - obs)),
        posterior_bonus_total=float(np.sum(means - obs)),
        credible_interval_95_per_read_mean=(float(np.mean(lo95)), float(np.mean(hi95))),
        posterior_means_per_read=means_keep.tolist(),
        bonus_per_read=bonus_keep.tolist(),
        source=str(path),
    )

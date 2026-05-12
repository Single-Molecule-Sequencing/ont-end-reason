"""Q-score distribution analysis with Gaussian Mixture Model fitting (TOOL_SPEC 5).

For each end_reason class, computes Q-score summary stats AND fits a
1-to-N component Gaussian Mixture Model via the EM algorithm. Reports BIC,
AIC, and the chosen model's component means / sds / weights.

The paper's Figure 5 violin plot is a downstream consumer of this analysis.

Implementation uses scipy + numpy directly (no sklearn dependency) to keep
the install footprint small. The EM loop is vectorised and converges fast
even on 100k+ reads per class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from ..errors import AnalysisError
from ..errors import IOError as OntIOError


@dataclass
class GMMComponent:
    weight: float
    mean: float
    sd: float


@dataclass
class QualityStats:
    """Per-end_reason Q-score summary + GMM fit."""

    n: int
    mean: float
    median: float
    std: float
    min: float
    max: float
    p25: float
    p50: float
    p75: float
    p95: float
    gmm_components: list[GMMComponent] = field(default_factory=list)
    gmm_chosen_k: int = 1
    gmm_bic: float = float("nan")
    gmm_aic: float = float("nan")


@dataclass
class QualityResult:
    """Per-end_reason Q-score distributions + GMM fits + raw values for viz."""

    total_reads: int = 0
    per_class: dict[str, QualityStats] = field(default_factory=dict)
    raw_qscores_by_class: dict[str, list[float]] = field(default_factory=dict)
    source: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "total_reads": self.total_reads,
            "per_class": {
                k: {
                    "n": s.n,
                    "mean": round(s.mean, 3),
                    "median": round(s.median, 3),
                    "std": round(s.std, 3),
                    "p25": round(s.p25, 3),
                    "p75": round(s.p75, 3),
                    "p95": round(s.p95, 3),
                    "gmm_chosen_k": s.gmm_chosen_k,
                    "gmm_bic": round(s.gmm_bic, 3),
                    "gmm_components": [
                        {
                            "weight": round(c.weight, 4),
                            "mean": round(c.mean, 3),
                            "sd": round(c.sd, 3),
                        }
                        for c in s.gmm_components
                    ],
                }
                for k, s in self.per_class.items()
            },
            "source": self.source,
        }


# ─── EM-based GMM fitter ────────────────────────────────────────────────────


def _fit_gmm_em(
    x: np.ndarray, k: int, *, max_iter: int = 200, tol: float = 1e-4
) -> tuple[list[GMMComponent], float]:
    """Fit a k-component Gaussian Mixture via EM. Returns (components, log_likelihood)."""
    n = len(x)
    if n == 0 or k <= 0:
        return [], float("-inf")

    # K-means-style init: quantile-based component means, equal weights
    qs = np.linspace(0.1, 0.9, k)
    means = np.quantile(x, qs)
    sds = np.full(k, max(np.std(x), 1e-3))
    weights = np.full(k, 1.0 / k)

    prev_ll = float("-inf")
    for _ in range(max_iter):
        # E-step: responsibilities
        log_resp = np.zeros((n, k))
        for j in range(k):
            log_resp[:, j] = np.log(weights[j] + 1e-300) + norm.logpdf(
                x, loc=means[j], scale=sds[j] + 1e-6
            )
        max_l = log_resp.max(axis=1, keepdims=True)
        log_sum = max_l.squeeze(-1) + np.log(np.sum(np.exp(log_resp - max_l), axis=1))
        ll = float(log_sum.sum())
        if abs(ll - prev_ll) < tol * abs(ll + 1e-9):
            break
        prev_ll = ll

        resp = np.exp(log_resp - log_sum[:, None])
        # M-step
        nk = resp.sum(axis=0)
        weights = nk / n
        means = (resp * x[:, None]).sum(axis=0) / np.maximum(nk, 1e-9)
        # variance per component
        diff = x[:, None] - means[None, :]
        var = (resp * diff * diff).sum(axis=0) / np.maximum(nk, 1e-9)
        sds = np.sqrt(np.maximum(var, 1e-6))

    # Order by mean so output is canonical (helps with reporting / plot legends)
    order = np.argsort(means)
    components = [
        GMMComponent(weight=float(weights[i]), mean=float(means[i]), sd=float(sds[i]))
        for i in order
    ]
    return components, prev_ll


def _bic(log_likelihood: float, k: int, n: int) -> float:
    """BIC for a k-component univariate GMM: 3k - 1 free params (k means + k sds + k-1 weights)."""
    p = 3 * k - 1
    return float(p * np.log(n) - 2 * log_likelihood)


def _aic(log_likelihood: float, k: int) -> float:
    p = 3 * k - 1
    return float(2 * p - 2 * log_likelihood)


def _select_best_gmm(
    x: np.ndarray, *, k_max: int = 3
) -> tuple[list[GMMComponent], int, float, float]:
    """Try k in 1..k_max, return components for the BIC-minimal one."""
    best_bic = float("inf")
    best_k = 1
    best_components: list[GMMComponent] = []
    best_aic_val = float("inf")
    n = len(x)
    if n < 10:
        # Too few points: skip GMM, return point summary as a 1-component model
        return (
            [GMMComponent(weight=1.0, mean=float(np.mean(x)), sd=float(np.std(x)))],
            1,
            float("nan"),
            float("nan"),
        )

    for k in range(1, min(k_max, max(1, n // 50)) + 1):
        components, ll = _fit_gmm_em(x, k)
        if not components:
            continue
        bic = _bic(ll, k, n)
        aic = _aic(ll, k)
        if bic < best_bic:
            best_bic = bic
            best_aic_val = aic
            best_k = k
            best_components = components

    return best_components, best_k, best_bic, best_aic_val


def _stream_qscore_pairs(path: Path) -> dict[str, np.ndarray]:
    """Stream (end_reason, mean_qscore_template) from sequencing_summary."""
    by_class: dict[str, list[np.ndarray]] = {}
    try:
        for chunk in pd.read_csv(
            path,
            sep="\t",
            usecols=["end_reason", "mean_qscore_template"],
            chunksize=200_000,
        ):
            chunk = chunk.dropna(subset=["end_reason", "mean_qscore_template"])
            for er, grp in chunk.groupby("end_reason"):
                by_class.setdefault(str(er), []).append(
                    grp["mean_qscore_template"].to_numpy(dtype=np.float64)
                )
    except (OSError, ValueError, KeyError) as exc:
        raise OntIOError(f"Failed to stream {path}: {exc}") from exc
    return {k: np.concatenate(v) for k, v in by_class.items()}


def quality(
    source: str | Path,
    *,
    gmm_components: int = 3,
    max_raw_per_class: int = 50_000,
) -> QualityResult:
    """Per-end_reason Q-score summary + GMM fit (BIC-selected up to k=gmm_components).

    Pass a sequencing_summary.txt path. POD5 inputs would need their own
    Q-score extraction layer (not implemented in v0.2.0).
    """
    path = Path(source)
    if not path.is_file():
        raise OntIOError(f"quality requires a sequencing_summary file: {path}")

    arrays_by_class = _stream_qscore_pairs(path)
    n_total = sum(len(v) for v in arrays_by_class.values())
    if n_total == 0:
        raise AnalysisError(f"No qscore rows in {path}")

    per_class: dict[str, QualityStats] = {}
    raw: dict[str, list[float]] = {}
    rng = np.random.default_rng(0)

    for er, qs in arrays_by_class.items():
        if len(qs) == 0:
            continue
        components, k, bic, aic = _select_best_gmm(qs, k_max=gmm_components)
        per_class[er] = QualityStats(
            n=len(qs),
            mean=float(np.mean(qs)),
            median=float(np.median(qs)),
            std=float(np.std(qs)),
            min=float(np.min(qs)),
            max=float(np.max(qs)),
            p25=float(np.percentile(qs, 25)),
            p50=float(np.percentile(qs, 50)),
            p75=float(np.percentile(qs, 75)),
            p95=float(np.percentile(qs, 95)),
            gmm_components=components,
            gmm_chosen_k=k,
            gmm_bic=bic,
            gmm_aic=aic,
        )
        if len(qs) > max_raw_per_class:
            idx = rng.choice(len(qs), size=max_raw_per_class, replace=False)
            raw[er] = qs[idx].tolist()
        else:
            raw[er] = qs.tolist()

    return QualityResult(
        total_reads=n_total,
        per_class=per_class,
        raw_qscores_by_class=raw,
        source=str(path),
    )

"""Statistical hypothesis tests between end_reason populations (TOOL_SPEC 10).

Compares two end_reason populations on either their length or qscore
distributions, returning:

  - Mann-Whitney U test (default; non-parametric, robust to ONT outliers)
  - Kolmogorov-Smirnov 2-sample test (alternative; sensitive to shape)
  - Cliff's delta effect size (non-parametric; robust)

Use for questions like "are unblock_mux_change reads significantly shorter
than signal_positive reads?" — the paper's Figure 5 row uses this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, mannwhitneyu

from ..codes import CODES, NAMES
from ..errors import AnalysisError, IOError as OntIOError


@dataclass
class HypothesisResult:
    test: str = ""
    statistic: float = 0.0
    p_value: float = 1.0
    effect_size: float = 0.0  # Cliff's delta
    n_a: int = 0
    n_b: int = 0
    comparison: tuple[str, str] = ("", "")
    column: str = "sequence_length_template"
    median_a: float = 0.0
    median_b: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "test": self.test,
            "statistic": round(self.statistic, 4),
            "p_value": self.p_value,
            "effect_size": round(self.effect_size, 4),
            "n_a": self.n_a,
            "n_b": self.n_b,
            "comparison": list(self.comparison),
            "column": self.column,
            "median_a": round(self.median_a, 3),
            "median_b": round(self.median_b, 3),
            "notes": self.notes,
        }


def _cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """Robust effect-size measure: P(A>B) − P(A<B), bounded [-1, 1]."""
    a = np.sort(a)
    b = np.sort(b)
    n_b = len(b)
    if n_b == 0 or len(a) == 0:
        return 0.0
    # Vectorised pairwise comparison via searchsorted
    lt = np.searchsorted(b, a, side="left").sum()  # b elements strictly less than a-elements
    gt = (n_b - np.searchsorted(b, a, side="right")).sum()
    n_total = len(a) * n_b
    return float((lt - gt) / n_total)


def _normalise(end_reason_or_code: str) -> str:
    """Coerce SP / signal_positive to the canonical full name."""
    s = end_reason_or_code.strip()
    if s.lower() in CODES:
        return s.lower()
    if s.upper() in NAMES:
        return NAMES[s.upper()]
    raise AnalysisError(f"Unknown end_reason: {end_reason_or_code!r}")


def _load_two_classes(
    path: Path, *, a: str, b: str, column: str
) -> tuple[np.ndarray, np.ndarray]:
    """Stream the column for two end_reason classes."""
    a_full = _normalise(a)
    b_full = _normalise(b)
    bins_a: list[np.ndarray] = []
    bins_b: list[np.ndarray] = []
    try:
        for chunk in pd.read_csv(
            path, sep="\t", usecols=["end_reason", column], chunksize=200_000
        ):
            chunk = chunk.dropna(subset=["end_reason", column])
            mask_a = chunk["end_reason"].astype(str).str.lower() == a_full
            mask_b = chunk["end_reason"].astype(str).str.lower() == b_full
            if mask_a.any():
                bins_a.append(chunk.loc[mask_a, column].to_numpy(dtype=np.float64))
            if mask_b.any():
                bins_b.append(chunk.loc[mask_b, column].to_numpy(dtype=np.float64))
    except (OSError, ValueError, KeyError) as exc:
        raise OntIOError(f"Failed to stream {path}: {exc}") from exc
    arr_a = np.concatenate(bins_a) if bins_a else np.array([])
    arr_b = np.concatenate(bins_b) if bins_b else np.array([])
    return arr_a, arr_b


def hypothesis(
    source: str | Path,
    *,
    a: str = "SP",
    b: str = "UMC",
    test: str = "mann-whitney",
    column: str = "sequence_length_template",
) -> HypothesisResult:
    """Run a non-parametric two-sample test between two end_reason populations.

    Parameters
    ----------
    source : path-like
        sequencing_summary.txt
    a, b : str
        End reason short codes or full names. Default: SP vs UMC.
    test : str
        "mann-whitney" or "ks". Default Mann-Whitney U.
    column : str
        "sequence_length_template" (default) or "mean_qscore_template".
    """
    path = Path(source)
    if not path.is_file():
        raise OntIOError(f"hypothesis requires a sequencing_summary file: {path}")

    arr_a, arr_b = _load_two_classes(path, a=a, b=b, column=column)
    if len(arr_a) < 5 or len(arr_b) < 5:
        raise AnalysisError(
            f"Too few reads to test: n({a})={len(arr_a)}, n({b})={len(arr_b)}"
        )

    test_norm = test.lower().replace("_", "-")
    notes: list[str] = []
    if test_norm in ("mann-whitney", "mw", "u"):
        stat, p = mannwhitneyu(arr_a, arr_b, alternative="two-sided")
        test_used = "mann-whitney"
    elif test_norm in ("ks", "kolmogorov-smirnov"):
        stat, p = ks_2samp(arr_a, arr_b, alternative="two-sided")
        test_used = "ks"
    else:
        raise AnalysisError(f"Unknown test: {test!r}. Choose mann-whitney or ks.")

    delta = _cliffs_delta(arr_a, arr_b)
    abs_d = abs(delta)
    if abs_d < 0.15:
        notes.append("Effect size negligible (|Δ| < 0.15)")
    elif abs_d < 0.33:
        notes.append("Effect size small (|Δ| < 0.33)")
    elif abs_d < 0.47:
        notes.append("Effect size medium (|Δ| < 0.47)")
    else:
        notes.append("Effect size large (|Δ| ≥ 0.47)")

    return HypothesisResult(
        test=test_used,
        statistic=float(stat),
        p_value=float(p),
        effect_size=float(delta),
        n_a=int(len(arr_a)),
        n_b=int(len(arr_b)),
        comparison=(_normalise(a), _normalise(b)),
        column=column,
        median_a=float(np.median(arr_a)),
        median_b=float(np.median(arr_b)),
        notes=notes,
    )

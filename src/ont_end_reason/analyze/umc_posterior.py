"""Posterior length model for unblock_mux_change (UMC) reads.

v0.1.0 STATUS: scaffold only.
Source: TOOL_SPECIFICATIONS.md type 11. The paper's key novel analysis —
Bayesian posterior over read length given truncation by adaptive sampling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class UMCPosteriorResult:
    posterior_samples: np.ndarray = field(default_factory=lambda: np.array([]))
    map_estimate: float = 0.0
    credible_interval_95: tuple[float, float] = (0.0, 0.0)
    n_umc_reads: int = 0
    convergence_diagnostics: dict[str, float] = field(default_factory=dict)


def umc_posterior(source: str | Path, **kwargs: Any) -> UMCPosteriorResult:
    raise NotImplementedError(
        "analyze.umc_posterior is scheduled for v0.2.0. See TOOL_SPECIFICATIONS.md type 11."
    )

"""Statistical hypothesis tests comparing end_reason populations.

v0.1.0 STATUS: scaffold only.
Source: TOOL_SPECIFICATIONS.md type 10. Mann-Whitney U, Kolmogorov-Smirnov,
permutation tests between e.g. SP vs UMC Q-score distributions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HypothesisResult:
    test: str = ""
    statistic: float = 0.0
    p_value: float = 1.0
    effect_size: float = 0.0
    n_a: int = 0
    n_b: int = 0
    comparison: tuple[str, str] = ("", "")
    notes: list[str] = field(default_factory=list)


def hypothesis(
    source: str | Path,
    *,
    test: str = "mann-whitney",
    a: str = "SP",
    b: str = "UMC",
    **kwargs: Any,
) -> HypothesisResult:
    raise NotImplementedError(
        "analyze.hypothesis is scheduled for v0.2.0. See TOOL_SPECIFICATIONS.md type 10."
    )

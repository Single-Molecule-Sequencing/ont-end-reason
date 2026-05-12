"""Raw signal trace extraction + visualisation for individual reads.

v0.1.0 STATUS: scaffold only.
Source: TOOL_SPECIFICATIONS.md type 3. Reads POD5 raw current and extracts
per-sample signal aligned to mux-change / unblock events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class SignalTraceResult:
    read_id: str = ""
    signal: np.ndarray = field(default_factory=lambda: np.array([]))
    samples_per_second: int = 0
    end_reason: str = "unknown"


def signal_trace(pod5_path: str | Path, *, read_id: str, **kwargs: Any) -> SignalTraceResult:
    raise NotImplementedError(
        "analyze.signal_trace is scheduled for v0.2.0. See TOOL_SPECIFICATIONS.md type 3."
    )

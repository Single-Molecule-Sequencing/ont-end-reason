"""Raw signal trace extraction for a single POD5 read (TOOL_SPEC type 3).

Pulls the raw current samples for a given `read_id` from a POD5 file and
returns them as a numpy array, annotated with the read's end_reason +
sample rate. The CLI also writes a quick line-plot of the trace.

Used by the paper's Figure 7 (decision tree visualisation) and Figure 9
(unblock-event signal characterisation) panels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..codes import CODES
from ..errors import AnalysisError
from ..errors import IOError as OntIOError
from ..io.readers import _normalise_end_reason


@dataclass
class SignalTraceResult:
    read_id: str = ""
    signal: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.int16))
    samples_per_second: int = 0
    end_reason: str = "unknown"
    end_reason_short: str | None = None
    n_samples: int = 0
    duration_seconds: float = 0.0
    source_file: str | None = None

    def to_dict(self) -> dict[str, object]:
        # The full signal array is too large for JSON; return summary stats only.
        return {
            "read_id": self.read_id,
            "samples_per_second": self.samples_per_second,
            "end_reason": self.end_reason,
            "end_reason_short": self.end_reason_short,
            "n_samples": self.n_samples,
            "duration_seconds": round(self.duration_seconds, 3),
            "signal_mean": round(float(np.mean(self.signal)), 3) if self.n_samples else 0.0,
            "signal_std": round(float(np.std(self.signal)), 3) if self.n_samples else 0.0,
            "signal_min": int(np.min(self.signal)) if self.n_samples else 0,
            "signal_max": int(np.max(self.signal)) if self.n_samples else 0,
            "source_file": self.source_file,
        }


def signal_trace(pod5_path: str | Path, *, read_id: str) -> SignalTraceResult:
    """Extract the raw current trace for `read_id` from `pod5_path`.

    Parameters
    ----------
    pod5_path : path-like
        Path to a POD5 file or directory containing POD5 files.
    read_id : str
        UUID of the read to extract.

    Raises
    ------
    OntIOError
        If pod5 library missing or file unreadable.
    AnalysisError
        If `read_id` not found in any of the POD5 files at `pod5_path`.
    """
    try:
        from pod5 import Reader as Pod5Reader  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OntIOError("signal_trace requires the `pod5` package: pip install pod5") from exc

    p = Path(pod5_path)
    files = sorted(p.rglob("*.pod5")) if p.is_dir() else [p]
    if not files:
        raise OntIOError(f"No POD5 files under {p}")

    for f in files:
        try:
            with Pod5Reader(str(f)) as reader:
                for read in reader.reads():
                    if str(read.read_id) != read_id:
                        continue
                    raw = read.signal
                    sample_rate = int(getattr(read.run_info, "sample_rate", 4000))
                    er = _normalise_end_reason(getattr(read, "end_reason", "unknown"))
                    return SignalTraceResult(
                        read_id=read_id,
                        signal=np.asarray(raw, dtype=np.int16),
                        samples_per_second=sample_rate,
                        end_reason=er,
                        end_reason_short=CODES.get(er),
                        n_samples=len(raw),
                        duration_seconds=float(len(raw) / max(sample_rate, 1)),
                        source_file=str(f),
                    )
        except Exception as exc:
            raise OntIOError(f"Failed to read POD5 {f}: {exc}") from exc

    raise AnalysisError(f"read_id {read_id!r} not found in POD5 files under {p}")

"""Temporal pattern analysis — end_reason rates over sequencing-run time.

Reads `start_time` and `end_reason` columns from sequencing_summary.txt (in
seconds since run-start), bins them, and computes per-end_reason counts +
fraction per bin. Surfaces flowcell-degradation signatures: e.g. a rising
unblock_mux_change fraction late in the run.

Implementation notes:
  - Streaming-safe (chunked pandas) for PromethION-scale summaries.
  - Default bin size: 1 hour. Configurable via `--bin-seconds` or `bin_seconds`.
  - Returns a TemporalResult with per-bin counts and per-end_reason counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..errors import AnalysisError
from ..errors import IOError as OntIOError


@dataclass
class TemporalResult:
    """Per-time-bin end_reason counts and fractions."""

    total_reads: int = 0
    bin_seconds: float = 3600.0
    bin_edges: list[float] = field(default_factory=list)  # seconds, length = n_bins + 1
    bin_centers: list[float] = field(default_factory=list)  # midpoints, hours
    # counts_by_class[end_reason] = [n_reads_in_bin_0, n_reads_in_bin_1, ...]
    counts_by_class: dict[str, list[int]] = field(default_factory=dict)
    # fractions_by_class is counts normalised by total reads in each bin
    fractions_by_class: dict[str, list[float]] = field(default_factory=dict)
    source: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "total_reads": self.total_reads,
            "bin_seconds": self.bin_seconds,
            "bin_centers_hours": [round(c, 3) for c in self.bin_centers],
            "counts_by_class": self.counts_by_class,
            "fractions_by_class": {
                k: [round(v, 4) for v in vs] for k, vs in self.fractions_by_class.items()
            },
            "source": self.source,
        }


def _stream_pairs(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Stream (start_time, end_reason) pairs from sequencing_summary."""
    times: list[np.ndarray] = []
    ers: list[np.ndarray] = []
    try:
        for chunk in pd.read_csv(
            path,
            sep="\t",
            usecols=["start_time", "end_reason"],
            chunksize=200_000,
        ):
            chunk = chunk.dropna(subset=["start_time", "end_reason"])
            times.append(chunk["start_time"].to_numpy(dtype=np.float64))
            ers.append(chunk["end_reason"].astype(str).to_numpy())
    except (OSError, ValueError, KeyError) as exc:
        raise OntIOError(f"Failed to stream {path}: {exc}") from exc
    if not times:
        return np.array([]), np.array([])
    return np.concatenate(times), np.concatenate(ers)


def temporal(source: str | Path, *, bin_seconds: float = 3600.0) -> TemporalResult:
    """Bin reads by start_time and report end_reason counts per bin.

    Parameters
    ----------
    source : path-like
        Path to sequencing_summary.txt. POD5 inputs not supported here
        (start_time is in the summary, not the POD5 header).
    bin_seconds : float
        Bin width in seconds. Default 3600 (1 hour).
    """
    path = Path(source)
    if not path.is_file():
        raise OntIOError(f"temporal requires a sequencing_summary file: {path}")

    times, ers = _stream_pairs(path)
    if len(times) == 0:
        raise AnalysisError(f"No (start_time, end_reason) rows in {path}")

    t_max = float(np.max(times))
    n_bins = max(1, int(np.ceil(t_max / bin_seconds)))
    edges = np.arange(n_bins + 1) * bin_seconds
    edges[-1] = max(edges[-1], t_max + 1e-6)
    centers_hours = ((edges[:-1] + edges[1:]) / 2.0) / 3600.0

    bin_idx = np.clip(np.floor(times / bin_seconds).astype(np.int64), 0, n_bins - 1)

    unique_ers = np.unique(ers)
    counts_by_class: dict[str, list[int]] = {er: [0] * n_bins for er in unique_ers}
    for i, er in zip(bin_idx, ers, strict=True):
        counts_by_class[str(er)][int(i)] += 1

    # Per-bin totals for fractions
    per_bin_total = np.zeros(n_bins, dtype=np.int64)
    for arr in counts_by_class.values():
        per_bin_total += np.asarray(arr, dtype=np.int64)

    fractions_by_class: dict[str, list[float]] = {}
    for er, counts in counts_by_class.items():
        fracs = []
        for c, tot in zip(counts, per_bin_total, strict=True):
            fracs.append(c / tot if tot > 0 else 0.0)
        fractions_by_class[er] = fracs

    return TemporalResult(
        total_reads=len(times),
        bin_seconds=float(bin_seconds),
        bin_edges=edges.tolist(),
        bin_centers=centers_hours.tolist(),
        counts_by_class=counts_by_class,
        fractions_by_class=fractions_by_class,
        source=str(path),
    )

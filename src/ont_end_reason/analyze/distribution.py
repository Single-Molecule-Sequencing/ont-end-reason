"""End-reason distribution analysis — the v0.1.0 fully-implemented analysis.

Computes per-end_reason counts and percentages, then applies a quality gate
based on the canonical paper thresholds:

  signal_positive >= 75%  → OK
  signal_positive <  75%  → CHECK
  signal_positive <  50%  → FAIL

This is the workhorse analysis equivalent to `/end-reason analyze` in the lab
ecosystem. It accepts any iterable of `ReadRecord` (typically from
`io.extract_from_*`) or any Manifest produced by `io.discover`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..codes import CODES, NAMES
from ..errors import AnalysisError
from ..io.manifest import Manifest, ReadRecord
from ..io.readers import (
    detect_format,
    extract_from_fast5,
    extract_from_pod5,
    extract_from_summary,
)


@dataclass
class DistributionResult:
    """Structured result of an end-reason distribution analysis.

    `counts` is keyed by the canonical lower-case full name
    (`signal_positive`, `unblock_mux_change`, ...). `percentages` mirrors
    counts as ratios of `total_reads`.
    """

    total_reads: int
    counts: dict[str, int] = field(default_factory=dict)
    percentages: dict[str, float] = field(default_factory=dict)
    quality_status: str = "OK"  # OK | CHECK | FAIL
    signal_positive_pct: float = 0.0
    unblock_mux_pct: float = 0.0
    data_service_pct: float = 0.0
    interpretation: str = ""
    source_format: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "total_reads": self.total_reads,
            "quality_status": self.quality_status,
            "signal_positive_pct": round(self.signal_positive_pct, 2),
            "unblock_mux_pct": round(self.unblock_mux_pct, 2),
            "data_service_pct": round(self.data_service_pct, 2),
            "counts": self.counts,
            "percentages": {k: round(v, 4) for k, v in self.percentages.items()},
            "interpretation": self.interpretation,
            "source_format": self.source_format,
        }


def _aggregate(records: Iterable[ReadRecord]) -> tuple[int, dict[str, int]]:
    counts: dict[str, int] = {}
    total = 0
    for r in records:
        total += 1
        key = r.end_reason or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return total, counts


def _interpretation(percentages: Mapping[str, float]) -> str:
    sp_pct = percentages.get("signal_positive", 0.0) * 100
    umc_pct = percentages.get("unblock_mux_change", 0.0) * 100
    parts = []
    if sp_pct >= 95:
        parts.append(f"Excellent: {sp_pct:.1f}% complete reads (top of expected range).")
    elif sp_pct >= 80:
        parts.append(f"Healthy: {sp_pct:.1f}% complete reads.")
    elif sp_pct >= 75:
        parts.append(f"Acceptable: {sp_pct:.1f}% complete reads (lower bound of OK).")
    elif sp_pct >= 50:
        parts.append(f"Concerning: {sp_pct:.1f}% complete reads (below 75% threshold).")
    else:
        parts.append(f"Failed: {sp_pct:.1f}% complete reads (below 50% threshold).")
    if umc_pct >= 10:
        parts.append(f"Adaptive sampling rejection rate is {umc_pct:.1f}%.")
    return " ".join(parts)


def distribution(
    source: str | Path | Manifest | Iterable[ReadRecord],
    *,
    quick: bool = False,
    max_reads: int = 10_000,
) -> DistributionResult:
    """Compute end-reason distribution for any acceptable input.

    Accepts:

    - A file path (POD5/Fast5/sequencing_summary.txt) — auto-detects format
    - A directory path — uses the first viable format found
    - A `Manifest` — concatenates all summaries in it
    - An iterable of `ReadRecord` — direct mode for in-memory analysis

    With `quick=True`, only the first `max_reads` are read. Useful for
    fast preview on multi-million-read POD5 sets.
    """
    src_format: str | None = None
    records: Iterable[ReadRecord]

    if isinstance(source, Manifest):
        if source.summaries:
            src_format = "summary"
            records = list(
                extract_from_summary(source.summaries[0].path, quick=quick, max_reads=max_reads)
            )
        elif source.pod5:
            src_format = "pod5"
            records = extract_from_pod5(source.pod5[0].path, quick=quick, max_reads=max_reads)
        elif source.fast5:
            src_format = "fast5"
            records = extract_from_fast5(source.fast5[0].path, quick=quick, max_reads=max_reads)
        else:
            raise AnalysisError("Manifest has no POD5/Fast5/summary files")
    elif isinstance(source, (str, Path)):
        src_format = detect_format(source)
        if src_format == "pod5":
            records = extract_from_pod5(source, quick=quick, max_reads=max_reads)
        elif src_format == "fast5":
            records = extract_from_fast5(source, quick=quick, max_reads=max_reads)
        elif src_format == "summary":
            records = list(extract_from_summary(source, quick=quick, max_reads=max_reads))
        else:  # pragma: no cover — detect_format raises otherwise
            raise AnalysisError(f"Unsupported format: {src_format}")
    else:
        records = source  # raw iterable

    total, counts = _aggregate(records)
    if total == 0:
        raise AnalysisError("No reads found in source")

    # Normalise keys to canonical lower-case full names. Unknown values pass through.
    norm_counts: dict[str, int] = {}
    for key, count in counts.items():
        canonical = key.lower() if key.lower() in CODES else key
        # Allow short codes too: 'SP' → 'signal_positive'
        if canonical.upper() in NAMES:
            canonical = NAMES[canonical.upper()]
        norm_counts[canonical] = norm_counts.get(canonical, 0) + count

    percentages = {k: v / total for k, v in norm_counts.items()}

    sp_pct = percentages.get("signal_positive", 0.0) * 100
    umc_pct = percentages.get("unblock_mux_change", 0.0) * 100
    dumc_pct = percentages.get("data_service_unblock_mux_change", 0.0) * 100

    if sp_pct < 50:
        status = "FAIL"
    elif sp_pct < 75:
        status = "CHECK"
    else:
        status = "OK"

    return DistributionResult(
        total_reads=total,
        counts=norm_counts,
        percentages=percentages,
        quality_status=status,
        signal_positive_pct=sp_pct,
        unblock_mux_pct=umc_pct,
        data_service_pct=dumc_pct,
        interpretation=_interpretation(percentages),
        source_format=src_format,
    )

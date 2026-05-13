"""Cross-run end-reason atlas — aggregates QC results across all known runs.

Pulls per-run end-reason distributions from two sources:

  1. **Internal peers**  — the lab's `~/.ont-qc-baselines/` QCBaselineStore
     (populated by `analyze distribution --baseline-store` on registry-known
     experiments).
  2. **External peers** — public ONT datasets (GIAB, hereditary-cancer, etc.)
     cached as Parquet fingerprints at `~/.ont-qc-baselines/external_peers/`,
     refreshed by the `/ont-public-data` skill.

Both sources are stratified by `(flowcell_type, chemistry, adaptive_sampling)`
and combined into per-stratum baseline statistics. Runs whose composite
anomaly_score (max |z_i| across end_reason metrics) exceeds a threshold are
flagged.

The library imports `lib.qc_baseline` from the ont-ecosystem repo via the
shared `_lab_bridge.import_lab_module` helper (which in turn bridges to
lab-papers' canonical `cross_repo_import.import_lab_module`). If
ont-ecosystem isn't checked out, `atlas()` degrades to external-peers-only
with a clear interpretation message — never crashes.

Spec: docs/superpowers/specs/2026-05-12-end-reason-atlas-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from .._lab_bridge import import_lab_module

log = structlog.get_logger(__name__)

DEFAULT_STRATA: tuple[str, ...] = ("flowcell_type", "chemistry", "adaptive_sampling")
DEFAULT_EXTERNAL_PEERS_DIR = Path.home() / ".ont-qc-baselines" / "external_peers"
END_REASON_METRIC_KEYS: tuple[str, ...] = (
    "signal_positive_pct",
    "unblock_mux_pct",
    "data_service_pct",
    "mux_change_pct",
    "signal_negative_pct",
)


@dataclass
class StratumStats:
    """Baseline statistics for one stratum × all end-reason metrics."""

    stratum: tuple[str, ...]
    n_runs: int
    metric_stats: dict[str, dict[str, float]] = field(default_factory=dict)
    # metric_stats[metric_name] = {"mean": ..., "median": ..., "std": ...,
    #                              "min": ..., "max": ..., "count": ...}


@dataclass
class OutlierRecord:
    """A run flagged as a cross-run outlier."""

    experiment_id: str
    source: str  # "internal" | "external"
    stratum: tuple[str, ...]
    metric_z_scores: dict[str, float]
    anomaly_score: float


@dataclass
class AtlasResult:
    """Structured result of an atlas() call.

    Mirrors the shape of DistributionResult etc. — to_dict() emits a JSON-safe
    payload that the CLI, dashboard, and figure regenerator all consume.
    """

    n_internal: int
    n_external: int
    strata_keys: list[str]
    per_stratum: list[StratumStats] = field(default_factory=list)
    outliers: list[OutlierRecord] = field(default_factory=list)
    interpretation: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_internal": self.n_internal,
            "n_external": self.n_external,
            "strata_keys": list(self.strata_keys),
            "per_stratum": [
                {
                    "stratum": list(s.stratum),
                    "n_runs": s.n_runs,
                    "metric_stats": s.metric_stats,
                }
                for s in self.per_stratum
            ],
            "outliers": [
                {
                    "experiment_id": o.experiment_id,
                    "source": o.source,
                    "stratum": list(o.stratum),
                    "metric_z_scores": o.metric_z_scores,
                    "anomaly_score": round(o.anomaly_score, 3),
                }
                for o in self.outliers
            ],
            "interpretation": self.interpretation,
            "generated_at": self.generated_at,
        }


def _load_external_peers(peers_dir: Path) -> list[dict[str, Any]]:
    """Load external peer fingerprints from a directory of Parquet files.

    Each Parquet row is expected to have columns: experiment_id,
    flowcell_type, chemistry, adaptive_sampling, signal_positive_pct,
    unblock_mux_pct, data_service_pct, mux_change_pct, signal_negative_pct.
    Returns a list of dicts (one per row). Missing dir or missing columns
    degrades to []  with a warning log.
    """
    if not peers_dir.exists():
        return []
    try:
        import pandas as pd
    except ImportError:
        log.warning("pandas not available; external peers skipped")
        return []
    rows: list[dict[str, Any]] = []
    for parquet in sorted(peers_dir.glob("*.parquet")):
        try:
            df = pd.read_parquet(parquet)
        except Exception as exc:
            log.warning("failed to read external peer parquet", path=str(parquet), error=str(exc))
            continue
        for record in df.to_dict(orient="records"):
            sp = record.get("signal_positive_pct")
            # pandas fills missing columns with NaN — exclude those
            if sp is None or (isinstance(sp, float) and sp != sp):
                continue
            rows.append(record)
    return rows


def _stratum_key_from_record(record: dict[str, Any], strata_keys: list[str]) -> tuple[str, ...]:
    """Compute stratum tuple from a flat dict (used for external peers)."""
    out = []
    for k in strata_keys:
        v = record.get(k)
        out.append("unknown" if v is None else str(v))
    return tuple(out)


def _summarize_metrics(values: list[float]) -> dict[str, float]:
    """Inline mean/median/std/min/max so we don't depend on numpy here."""
    if not values:
        return {}
    n = len(values)
    mean = sum(values) / n
    sorted_v = sorted(values)
    mid = n // 2
    median = sorted_v[mid] if n % 2 else (sorted_v[mid - 1] + sorted_v[mid]) / 2
    std = (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5 if n >= 2 else 0.0
    return {
        "count": float(n),
        "mean": mean,
        "median": median,
        "std": std,
        "min": min(values),
        "max": max(values),
    }


def _interpretation(n_internal: int, n_external: int, n_outliers: int) -> str:
    if n_internal == 0 and n_external == 0:
        return (
            "Empty atlas: no runs in qc_baseline store or external peer cache. "
            "Populate by running `ont-end-reason analyze distribution` on lab "
            "experiments, or `scripts/atlas_backfill.py` to seed from the registry."
        )
    if n_internal == 0:
        return (
            f"External-only atlas ({n_external} public peer runs). "
            "Internal lab cohort is empty — run `scripts/atlas_backfill.py` to "
            "populate from the ONT registry."
        )
    pieces = [f"Atlas spans {n_internal} internal + {n_external} external runs"]
    if n_outliers:
        pieces.append(f"{n_outliers} run(s) flagged as outliers")
    else:
        pieces.append("no outliers flagged")
    return "; ".join(pieces) + "."


def atlas(
    *,
    include_internal: bool = True,
    include_external: bool = True,
    strata: tuple[str, ...] = DEFAULT_STRATA,
    z_threshold: float = 2.0,
    external_peers_dir: Path = DEFAULT_EXTERNAL_PEERS_DIR,
    min_stratum_size: int = 3,
) -> AtlasResult:
    """Build a cross-run end-reason atlas.

    Returns an AtlasResult that never raises on empty / missing data — empty
    atlas is a valid degraded state. Consumers check `n_internal + n_external`
    to detect it. See module docstring for sources and behavior.
    """
    strata_list = list(strata)

    # --- INTERNAL PEERS ---------------------------------------------------
    internal_records: list[dict[str, Any]] = []
    internal_outliers: list[OutlierRecord] = []
    per_stratum: list[StratumStats] = []
    qc = (
        import_lab_module("qc_baseline", repo="ont-ecosystem", lib_subdir="lib")
        if include_internal
        else None
    )
    if qc is not None:
        try:
            for r in qc.get_end_reason_results():
                rec = {
                    "experiment_id": r.metadata.experiment_id,
                    **r.metadata.to_dict(),
                    **r.metrics,
                }
                internal_records.append(rec)
            internal_outlier_records = qc.compute_atlas_outliers(
                strata_list, z_threshold=z_threshold, min_stratum_size=min_stratum_size
            )
            for o in internal_outlier_records:
                internal_outliers.append(
                    OutlierRecord(
                        experiment_id=o.experiment_id,
                        source="internal",
                        stratum=o.stratum,
                        metric_z_scores=dict(o.metric_z_scores),
                        anomaly_score=o.anomaly_score,
                    )
                )
        except Exception as exc:
            log.warning("qc_baseline query failed; internal cohort skipped", error=str(exc))

    # --- EXTERNAL PEERS ---------------------------------------------------
    external_records: list[dict[str, Any]] = (
        _load_external_peers(external_peers_dir) if include_external else []
    )

    # --- COMBINED PER-STRATUM STATS ---------------------------------------
    all_records = internal_records + external_records
    by_stratum: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for rec in all_records:
        key = _stratum_key_from_record(rec, strata_list)
        by_stratum.setdefault(key, []).append(rec)

    for key, group in sorted(by_stratum.items()):
        metric_stats = {}
        for m in END_REASON_METRIC_KEYS:
            values = [float(r[m]) for r in group if m in r and r[m] is not None]
            if values:
                metric_stats[m] = _summarize_metrics(values)
        per_stratum.append(StratumStats(stratum=key, n_runs=len(group), metric_stats=metric_stats))

    # --- EXTERNAL OUTLIERS (z-score against combined per-stratum stats) ---
    external_outliers: list[OutlierRecord] = []
    stratum_lookup = {s.stratum: s for s in per_stratum}
    for rec in external_records:
        key = _stratum_key_from_record(rec, strata_list)
        s = stratum_lookup.get(key)
        if s is None or s.n_runs < min_stratum_size:
            continue
        z_scores: dict[str, float] = {}
        for m in END_REASON_METRIC_KEYS:
            metric_stat = s.metric_stats.get(m)
            if metric_stat is None or metric_stat["std"] in (0, 0.0):
                continue
            value = rec.get(m)
            if value is None:
                continue
            z_scores[m] = (float(value) - metric_stat["mean"]) / metric_stat["std"]
        if z_scores:
            anomaly = max(abs(z) for z in z_scores.values())
            if anomaly >= z_threshold:
                external_outliers.append(
                    OutlierRecord(
                        experiment_id=str(rec.get("experiment_id", "<unknown>")),
                        source="external",
                        stratum=key,
                        metric_z_scores=z_scores,
                        anomaly_score=anomaly,
                    )
                )

    outliers = sorted(
        internal_outliers + external_outliers,
        key=lambda o: o.anomaly_score,
        reverse=True,
    )

    return AtlasResult(
        n_internal=len(internal_records),
        n_external=len(external_records),
        strata_keys=strata_list,
        per_stratum=per_stratum,
        outliers=outliers,
        interpretation=_interpretation(len(internal_records), len(external_records), len(outliers)),
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
    )

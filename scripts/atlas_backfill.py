#!/usr/bin/env python3
"""One-time backfill: populate qc_baseline from the ONT registry.

Walks `~/.ont-registry/experiments.yaml`, runs `ont-end-reason analyze
distribution` on every experiment whose data is locally accessible AND
above `MIN_GB`, and stores each result in qc_baseline. Idempotent —
re-runnable; existing results dedupe by `experiment_id+timestamp`.

Spec: docs/superpowers/specs/2026-05-12-end-reason-atlas-design.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REGISTRY_PATH = Path.home() / ".ont-registry" / "experiments.yaml"
MIN_GB = 0.1


def _load_registry() -> list[dict]:
    try:
        import yaml
    except ImportError:
        sys.exit("pyyaml is required: pip install pyyaml")
    if not REGISTRY_PATH.exists():
        sys.exit(f"Registry not found at {REGISTRY_PATH}")
    data = yaml.safe_load(REGISTRY_PATH.read_text()) or {}
    return data.get("experiments", [])


def _is_eligible(exp: dict) -> bool:
    size = exp.get("total_size_gb") or 0.0
    if size < MIN_GB:
        return False
    loc = exp.get("location") or exp.get("permanent_location")
    if not loc:
        return False
    return Path(loc).exists()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="List eligible experiments without running analyses.",
    )
    ap.add_argument(
        "--quick",
        action="store_true",
        help="Pass --quick to analyze distribution (sample up to 10k reads).",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N experiments (for testing).",
    )
    args = ap.parse_args()

    experiments = _load_registry()
    eligible = [e for e in experiments if _is_eligible(e)]
    print(
        f"Registry: {len(experiments)} entries; eligible (>= {MIN_GB} GB on disk): {len(eligible)}"
    )

    if args.limit:
        eligible = eligible[: args.limit]

    if args.dry_run:
        print("\n--dry-run: would process the following experiments:")
        for e in eligible:
            print(f"  {e['id']:<40}  {e.get('total_size_gb', 0):.1f} GB  {e['location']}")
        return 0

    # Lazy import — distribution() needs pysam/pod5 etc.
    try:
        from ont_end_reason.analyze.distribution import (
            distribution as do_distribution,
        )
    except ImportError as exc:
        sys.exit(f"ont-end-reason not importable: {exc}")

    try:
        from ont_end_reason.analyze.distribution import maybe_store_baseline
    except ImportError:
        maybe_store_baseline = None

    n_ok = 0
    n_fail = 0
    n_stored = 0
    for i, exp in enumerate(eligible, 1):
        loc = exp["location"]
        eid = exp["id"]
        print(f"\n[{i}/{len(eligible)}] {eid}  ({exp.get('total_size_gb', 0):.1f} GB)")
        try:
            result = do_distribution(loc, quick=args.quick)
        except Exception as exc:
            print(f"  FAIL: {type(exc).__name__}: {exc}")
            n_fail += 1
            continue
        print(
            f"  total_reads={result.total_reads:,}  "
            f"SP={result.signal_positive_pct:.1f}%  "
            f"status={result.quality_status}"
        )
        n_ok += 1
        if maybe_store_baseline is not None:
            try:
                stored = maybe_store_baseline(result, loc, write=True)
                if stored:
                    n_stored += 1
                    print("  → stored in qc_baseline")
            except Exception as exc:
                print(f"  ! baseline store failed: {exc}")

    print(
        f"\nBackfill complete — {n_ok} succeeded, {n_fail} failed, {n_stored} stored in qc_baseline"
    )
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

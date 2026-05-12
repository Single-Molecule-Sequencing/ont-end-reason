"""Generate a synthetic sequencing_summary.txt fixture with realistic distributions.

Run once to regenerate `tests/fixtures/sequencing_summary_synthetic.txt`. The
output is deterministic (seeded RNG) so tests can assert exact statistics.

Distributions chosen to match published ONT R10 runs:
  - 80% signal_positive (SP) — log-normal mean ~5kb, sd ~0.6 in log-space
  - 12% unblock_mux_change (UMC) — log-normal mean ~800 bp (truncated)
  -  5% data_service_unblock_mux_change (DUMC) — truncated, similar to UMC
  -  2% mux_change (MC) — wider length distribution
  -  1% signal_negative (SN) — very short, low qscore
  -  0% partial (PART), 0% unknown (UNK) — left out for cleaner SP/UMC tests

Q-scores: SP centered at 22, UMC at 18, SN at 8. Time evenly distributed
across a 24-hour run.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

RNG = np.random.default_rng(42)
N_READS = 5_000

DIST = {
    "signal_positive": 0.80,
    "unblock_mux_change": 0.12,
    "data_service_unblock_mux_change": 0.05,
    "mux_change": 0.02,
    "signal_negative": 0.01,
}

LENGTH_PARAMS = {
    # mean_log, sd_log (lognormal in nt)
    "signal_positive": (8.5, 0.6),                       # ~5 kb
    "unblock_mux_change": (6.7, 0.5),                    # ~800 bp
    "data_service_unblock_mux_change": (6.5, 0.5),       # ~700 bp
    "mux_change": (7.5, 0.8),                            # ~1.8 kb, wider
    "signal_negative": (5.5, 0.4),                       # ~240 bp
}

QUALITY_PARAMS = {
    # mean_q, sd_q
    "signal_positive": (22.0, 2.5),
    "unblock_mux_change": (18.0, 3.0),
    "data_service_unblock_mux_change": (17.5, 3.0),
    "mux_change": (20.0, 2.8),
    "signal_negative": (8.0, 2.5),
}


def _gen_reads() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    rid_counter = 0
    for end_reason, frac in DIST.items():
        n = int(round(frac * N_READS))
        m, s = LENGTH_PARAMS[end_reason]
        lengths = np.clip(
            RNG.lognormal(mean=m, sigma=s, size=n).astype(int),
            50,
            500_000,
        )
        qm, qs = QUALITY_PARAMS[end_reason]
        qscores = np.clip(RNG.normal(loc=qm, scale=qs, size=n), 0.0, 50.0)
        # Spread reads uniformly across a 24h run (in seconds)
        start_times = RNG.uniform(0.0, 24 * 3600.0, size=n)
        durations = lengths / 250.0  # ~250 bp/sec translocation
        channels = RNG.integers(1, 513, size=n)  # MinION 512 channels
        for length, qscore, st, dur, ch in zip(
            lengths, qscores, start_times, durations, channels, strict=True
        ):
            rid_counter += 1
            rows.append(
                {
                    "read_id": f"{rid_counter:08x}-0000-4000-8000-000000000000",
                    "end_reason": end_reason,
                    "sequence_length_template": int(length),
                    "mean_qscore_template": round(float(qscore), 3),
                    "start_time": round(float(st), 3),
                    "duration": round(float(dur), 3),
                    "channel": int(ch),
                    "mux": int(RNG.integers(1, 5)),
                }
            )
    # Shuffle so end_reasons aren't grouped
    RNG.shuffle(rows)
    return rows


def main() -> None:
    rows = _gen_reads()
    columns = [
        "read_id",
        "end_reason",
        "sequence_length_template",
        "mean_qscore_template",
        "start_time",
        "duration",
        "channel",
        "mux",
    ]
    out = Path(__file__).parent / "sequencing_summary_synthetic.txt"
    with out.open("w") as fh:
        fh.write("\t".join(columns) + "\n")
        for row in rows:
            fh.write("\t".join(str(row[c]) for c in columns) + "\n")
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()

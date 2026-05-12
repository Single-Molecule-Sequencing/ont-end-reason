"""Pre-render all example outputs for the dashboard.

Runs every implemented analysis on the synthetic fixture, then writes:
  - JSON results (one file per analysis) under docs/examples/json/
  - Plotly chart HTML fragments under docs/examples/charts/
  - matplotlib PNG figures under docs/figures/

Re-run any time the fixture or analyses change so the dashboard stays
in sync. The dashboard (docs/index.html) reads these as static assets —
no backend needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from ont_end_reason.analyze.distribution import distribution
from ont_end_reason.analyze.hypothesis import hypothesis
from ont_end_reason.analyze.length import length
from ont_end_reason.analyze.quality import quality
from ont_end_reason.analyze.temporal import temporal
from ont_end_reason.analyze.umc_posterior import umc_posterior
from ont_end_reason.viz.interactive import interactive_distribution
from ont_end_reason.viz.static import (
    plot_distribution,
    plot_length_distribution,
    plot_quality_violins,
    plot_temporal,
    plot_umc_posterior,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "sequencing_summary_synthetic.txt"
JSON_DIR = REPO / "docs" / "examples" / "json"
CHART_DIR = REPO / "docs" / "examples" / "charts"
FIG_DIR = REPO / "docs" / "figures"

for d in (JSON_DIR, CHART_DIR, FIG_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _save_chart(fig, name: str) -> None:
    """Save Plotly figure as an HTML snippet that the dashboard can include."""
    html = fig.to_html(include_plotlyjs=False, full_html=False, div_id=f"plot-{name}")
    (CHART_DIR / f"{name}.html").write_text(html)


def _save_png(fig, name: str) -> None:
    (FIG_DIR / f"{name}.png").write_text("")  # placeholder so chmod works
    fig.savefig(FIG_DIR / f"{name}.png", dpi=120, bbox_inches="tight")


def _save_json(data: dict, name: str) -> None:
    (JSON_DIR / f"{name}.json").write_text(json.dumps(data, indent=2))


def main() -> None:
    print(f"Generating examples from {FIXTURE}")

    # 1. Distribution
    print("  distribution...")
    dist = distribution(FIXTURE)
    _save_json(dist.to_dict(), "distribution")
    _save_chart(interactive_distribution(dist), "distribution")
    _save_png(plot_distribution(dist), "distribution")

    # 2. Length
    print("  length...")
    lr = length(FIXTURE)
    _save_json(lr.to_dict(), "length")
    _save_png(plot_length_distribution(lr), "length")

    # 3. Quality
    print("  quality...")
    qr = quality(FIXTURE)
    _save_json(qr.to_dict(), "quality")
    _save_png(plot_quality_violins(qr), "quality")

    # 4. Temporal
    print("  temporal...")
    tr = temporal(FIXTURE)
    _save_json(tr.to_dict(), "temporal")
    _save_png(plot_temporal(tr), "temporal")

    # 5. UMC posterior
    print("  umc_posterior...")
    ur = umc_posterior(FIXTURE)
    _save_json(ur.to_dict(), "umc_posterior")
    _save_png(plot_umc_posterior(ur), "umc_posterior")

    # 6. Hypothesis
    print("  hypothesis...")
    hr_len = hypothesis(FIXTURE, a="SP", b="UMC", column="sequence_length_template")
    hr_q = hypothesis(FIXTURE, a="SP", b="UMC", column="mean_qscore_template")
    _save_json(
        {
            "length_test": hr_len.to_dict(),
            "qscore_test": hr_q.to_dict(),
        },
        "hypothesis",
    )

    # 7. Headline numbers for the dashboard hero
    print("  hero...")
    _save_json(
        {
            "tool_version": "0.2.0a1",
            "fixture_reads": dist.total_reads,
            "fixture_status": dist.quality_status,
            "fixture_signal_positive_pct": dist.signal_positive_pct,
            "fixture_umc_pct": dist.unblock_mux_pct,
            "umc_reads": ur.n_umc_reads,
            "umc_observed_mean": round(ur.observed_mean, 1),
            "umc_posterior_mean": round(ur.posterior_expected_true_mean, 1),
            "umc_bonus_per_read": round(ur.posterior_bonus_mean, 1),
            "umc_bonus_total": round(ur.posterior_bonus_total, 0),
        },
        "hero",
    )

    print(
        f"Wrote {len(list(JSON_DIR.iterdir()))} JSON, "
        f"{len(list(CHART_DIR.iterdir()))} charts, "
        f"{len(list(FIG_DIR.iterdir()))} PNGs."
    )


if __name__ == "__main__":
    main()

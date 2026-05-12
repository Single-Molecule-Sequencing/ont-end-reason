"""Composed multi-section interactive HTML report.

Sections (each conditional on available data + analyses):
  1. End reason distribution     — analyze.distribution
  2. Length distribution         — analyze.length
  3. Q-score distribution        — analyze.quality (with GMM components)
  4. Temporal patterns           — analyze.temporal
  5. UMC posterior length        — analyze.umc_posterior (paper's key analysis)
  6. Statistical comparisons     — analyze.hypothesis (SP vs UMC on length + qscore)

Each chart uses Plotly via the optional `interactive` extra. If Plotly is
missing, the section falls back to a static matplotlib figure embedded as
inline PNG.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..analyze.distribution import DistributionResult, distribution
from ..errors import AnalysisError, IOError as OntIOError
from ..io.manifest import Manifest


@dataclass
class HtmlReport:
    """Result of `build_html_report()`."""

    output_path: str
    sections: list[str] = field(default_factory=list)
    n_reads: int = 0


_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       max-width: 1200px; margin: 2em auto; padding: 0 1em;
       color: #1a1a1a; background: #fafafa; }
h1 { border-bottom: 2px solid #333; padding-bottom: 0.3em; }
h2 { margin-top: 2.5em; color: #333; border-bottom: 1px solid #ddd; padding-bottom: 0.2em; }
.status-OK { color: #2ca02c; font-weight: bold; }
.status-CHECK { color: #ff7f0e; font-weight: bold; }
.status-FAIL { color: #d62728; font-weight: bold; }
table { border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid #ddd; padding: 0.4em 0.8em; }
th { background: #eee; text-align: left; }
.meta { color: #666; font-size: 0.9em; }
.interp { background: #f0f4f8; padding: 1em; border-left: 4px solid #4a7298;
          margin: 1em 0; }
.toc { background: #f5f5f5; padding: 1em 1em 1em 2em; border-radius: 4px;
       border-left: 4px solid #999; }
.toc li { margin: 0.3em 0; }
.section-error { color: #999; font-style: italic; padding: 1em;
                 background: #fafafa; border-left: 4px solid #d62728; }
img.fallback { max-width: 100%; }
"""


def _fig_to_html(fig) -> str:
    """Convert any plotly or matplotlib Figure to a self-contained HTML snippet."""
    # Plotly path
    if hasattr(fig, "to_html"):
        return fig.to_html(include_plotlyjs="cdn", full_html=False)
    # matplotlib fallback — embed as inline PNG
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode()
    return f'<img class="fallback" src="data:image/png;base64,{encoded}">'


def _resolve_source(source: str | Path | Manifest) -> tuple[str, str]:
    """Return (analysis_source_path, display_root)."""
    if isinstance(source, Manifest):
        if not source.summaries:
            raise OntIOError("Manifest has no sequencing_summary files")
        return source.summaries[0].path, source.root
    path = Path(source)
    if path.is_file() and path.suffix == ".json":
        m = Manifest.from_json(path)
        if not m.summaries and not m.pod5:
            raise OntIOError("Manifest has no analyzable inputs")
        chosen = m.summaries[0].path if m.summaries else m.pod5[0].path
        return chosen, m.root
    return str(path), str(path)


# ─── Section builders. Each returns (heading, body_html) or None ────────────


def _distribution_section(analysis_source: str, *, quick: bool) -> tuple[DistributionResult, str]:
    from .. import viz

    result = distribution(analysis_source, quick=quick)
    try:
        fig = viz.interactive.interactive_distribution(result)
    except OntIOError:
        from ..viz.static import plot_distribution

        fig = plot_distribution(result)
    chart = _fig_to_html(fig)
    rows = "\n".join(
        f"<tr><td>{k}</td><td>{v:,}</td><td>{result.percentages[k] * 100:.2f}%</td></tr>"
        for k, v in result.counts.items()
    )
    body = f"""
      <p>Quality status: <span class="status-{result.quality_status}">{result.quality_status}</span> &middot;
         Total reads: {result.total_reads:,}</p>
      <div class="interp">{result.interpretation}</div>
      {chart}
      <table>
        <tr><th>End reason</th><th>Count</th><th>%</th></tr>
        {rows}
      </table>
    """
    return result, body


def _length_section(analysis_source: str) -> str:
    from ..analyze.length import length
    from ..viz.static import plot_length_distribution

    result = length(analysis_source)
    fig = plot_length_distribution(result)
    chart = _fig_to_html(fig)
    rows = "\n".join(
        f"<tr><td>{er}</td><td>{s.n:,}</td><td>{s.median:,.0f}</td>"
        f"<td>{s.p95:,.0f}</td><td>{s.n50:,}</td></tr>"
        for er, s in sorted(result.per_class.items(), key=lambda kv: -kv[1].n)
    )
    return f"""
      <p>Per-end_reason read-length summary (n={result.total_reads:,}).</p>
      {chart}
      <table>
        <tr><th>End reason</th><th>n</th><th>Median</th><th>p95</th><th>N50</th></tr>
        {rows}
      </table>
    """


def _quality_section(analysis_source: str) -> str:
    from ..analyze.quality import quality
    from ..viz.static import plot_quality_violins

    result = quality(analysis_source)
    fig = plot_quality_violins(result)
    chart = _fig_to_html(fig)
    rows = "\n".join(
        f"<tr><td>{er}</td><td>{s.n:,}</td><td>{s.mean:.2f}</td>"
        f"<td>{s.median:.2f}</td><td>{s.gmm_chosen_k}</td></tr>"
        for er, s in sorted(result.per_class.items(), key=lambda kv: -kv[1].n)
    )
    return f"""
      <p>Per-end_reason Q-score summary with GMM-fit components.</p>
      {chart}
      <table>
        <tr><th>End reason</th><th>n</th><th>Mean Q</th><th>Median Q</th><th>GMM k</th></tr>
        {rows}
      </table>
    """


def _temporal_section(analysis_source: str) -> str:
    from ..analyze.temporal import temporal
    from ..viz.static import plot_temporal

    result = temporal(analysis_source)
    fig = plot_temporal(result)
    chart = _fig_to_html(fig)
    return f"""
      <p>End_reason fractions binned across {len(result.bin_centers)} time bins
         (bin width {result.bin_seconds / 3600:.1f}h).</p>
      {chart}
    """


def _umc_posterior_section(analysis_source: str) -> str:
    from ..analyze.umc_posterior import umc_posterior
    from ..viz.static import plot_umc_posterior

    result = umc_posterior(analysis_source)
    fig = plot_umc_posterior(result)
    chart = _fig_to_html(fig)
    return f"""
      <p>Bayesian posterior over true UMC read length given adaptive-sampling
         truncation. Prior: lognormal fit to <code>{result.prior_class}</code>
         (log μ={result.prior_log_mu:.3f}, log σ={result.prior_log_sigma:.3f}).</p>
      <ul>
        <li>UMC reads: <strong>{result.n_umc_reads:,}</strong></li>
        <li>Observed mean length: <strong>{result.observed_mean:,.0f} bp</strong></li>
        <li>Posterior expected true mean: <strong>{result.posterior_expected_true_mean:,.0f} bp</strong></li>
        <li>Posterior bonus per read: <strong>{result.posterior_bonus_mean:,.0f} bp</strong></li>
        <li>Posterior bonus total (sequence lost to truncation): <strong>{result.posterior_bonus_total:,.0f} bp</strong></li>
      </ul>
      {chart}
    """


def _hypothesis_section(analysis_source: str) -> str:
    from ..analyze.hypothesis import hypothesis

    rows = []
    for column in ("sequence_length_template", "mean_qscore_template"):
        r = hypothesis(analysis_source, a="SP", b="UMC", column=column)
        rows.append(
            f"<tr><td>{column}</td><td>{r.test}</td>"
            f"<td>{r.statistic:.3g}</td><td>{r.p_value:.3g}</td>"
            f"<td>{r.effect_size:+.3f}</td>"
            f"<td>{r.median_a:.2f}</td><td>{r.median_b:.2f}</td></tr>"
        )
    return f"""
      <p>Two-sample Mann-Whitney U tests between signal_positive (SP) and
         unblock_mux_change (UMC), with Cliff's Δ effect size.</p>
      <table>
        <tr><th>Column</th><th>Test</th><th>Statistic</th><th>p-value</th>
            <th>Cliff's Δ</th><th>Median SP</th><th>Median UMC</th></tr>
        {"".join(rows)}
      </table>
    """


def build_html_report(
    source: str | Path | Manifest,
    *,
    output_path: str | Path,
    quick: bool = False,
) -> HtmlReport:
    """Build a multi-section HTML report from a Manifest or path."""
    from .. import __version__

    analysis_source, root_str = _resolve_source(source)

    sections_built: list[str] = []
    section_html: list[str] = []

    # Section 1 — distribution (mandatory; everything else can fail gracefully)
    result, body = _distribution_section(analysis_source, quick=quick)
    section_html.append(f"<h2>1. End reason distribution</h2>{body}")
    sections_built.append("distribution")

    # Sections 2-6 — try each; on failure, render a small error block instead
    section_attempts = [
        ("length", "2. Read length distribution", _length_section),
        ("quality", "3. Q-score distribution (with GMM)", _quality_section),
        ("temporal", "4. Temporal patterns", _temporal_section),
        ("umc_posterior", "5. UMC posterior length — adaptive-sampling truncation", _umc_posterior_section),
        ("hypothesis", "6. Statistical comparisons (SP vs UMC)", _hypothesis_section),
    ]
    for key, heading, fn in section_attempts:
        try:
            section_body = fn(analysis_source)
            section_html.append(f"<h2>{heading}</h2>{section_body}")
            sections_built.append(key)
        except (AnalysisError, OntIOError, ValueError, KeyError) as exc:
            section_html.append(
                f"<h2>{heading}</h2><div class='section-error'>"
                f"Section unavailable: {exc}</div>"
            )

    toc_items = "\n".join(
        f"<li>{i + 1}. {name}</li>" for i, name in enumerate(sections_built)
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ont-end-reason report — {root_str}</title>
  <style>{_CSS}</style>
</head>
<body>
  <h1>ont-end-reason report</h1>
  <p class="meta"><strong>Source:</strong> {root_str}<br>
     <strong>Generated:</strong> {datetime.now(tz=timezone.utc).isoformat()}<br>
     <strong>Tool version:</strong> {__version__}</p>

  <div class="toc">
    <strong>Sections in this report:</strong>
    <ul>{toc_items}</ul>
  </div>

  {"".join(section_html)}

  <h2>About</h2>
  <p class="meta">Generated by
     <a href="https://github.com/Single-Molecule-Sequencing/ont-end-reason">
     ont-end-reason</a> {__version__}. Companion to the end-reason paper.</p>
</body>
</html>
"""

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)

    return HtmlReport(
        output_path=str(out_path),
        sections=sections_built,
        n_reads=result.total_reads,
    )

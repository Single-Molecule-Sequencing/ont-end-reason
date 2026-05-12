"""ont-end-reason — command-line interface.

Single click-based dispatcher with one subcommand per capability. Heavy
subpackages (pysam, plotly, matplotlib) are lazy-imported inside the command
bodies so cold start is fast and `--help` works without optional dependencies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn

import click
import structlog

from . import __version__
from .codes import CODES, FAILED, RECOMMENDED_KEEP, TRUNCATED
from .errors import OntEndReasonError


def _configure_logging(*, debug: bool, quiet: bool) -> None:
    import logging

    level = logging.DEBUG if debug else logging.WARNING if quiet else logging.INFO
    logging.basicConfig(format="%(message)s", level=level, stream=sys.stderr)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


def _die(message: str) -> NoReturn:
    click.echo(f"[error] {message}", err=True)
    sys.exit(1)


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.version_option(__version__, prog_name="ont-end-reason")
@click.option("--debug", is_flag=True, help="Enable DEBUG-level structured logging.")
@click.option("--quiet", is_flag=True, help="Suppress INFO logs; only errors.")
@click.option(
    "--strict",
    is_flag=True,
    help="Escalate warnings to errors (useful in CI).",
)
@click.pass_context
def main(ctx: click.Context, debug: bool, quiet: bool, strict: bool) -> None:
    """Comprehensive CLI for Oxford Nanopore end_reason analysis."""
    if debug and quiet:
        _die("--debug and --quiet are mutually exclusive")
    _configure_logging(debug=debug, quiet=quiet)
    ctx.ensure_object(dict)
    ctx.obj["strict"] = strict
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ───────────────────────── discovery ─────────────────────────


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--recursive/--no-recursive", default=True, show_default=True)
@click.option(
    "--manifest",
    "manifest_out",
    type=click.Path(file_okay=True, dir_okay=False),
    default=None,
    help="Write the manifest as JSON to this path.",
)
def discover(path: str, recursive: bool, manifest_out: str | None) -> None:
    """Walk PATH and inventory POD5/Fast5/sequencing_summary/BAM/FASTQ files."""
    from .io.discover import discover as do_discover

    try:
        manifest = do_discover(path, recursive=recursive)
    except OntEndReasonError as exc:
        _die(str(exc))
    click.echo(
        f"Found {manifest.total_files()} files "
        f"({manifest.total_size_gb():.2f} GB) under {manifest.root}"
    )
    click.echo(f"  POD5:      {len(manifest.pod5)}")
    click.echo(f"  Fast5:     {len(manifest.fast5)}")
    click.echo(f"  Summaries: {len(manifest.summaries)}")
    click.echo(f"  BAMs:      {len(manifest.bams)}")
    click.echo(f"  FASTQs:    {len(manifest.fastqs)}")
    if manifest_out:
        manifest.to_json(manifest_out)
        click.echo(f"Manifest written: {manifest_out}")


# ───────────────────────── filter operations ─────────────────────────


@main.command()
@click.option("--summary", required=True, type=click.Path(exists=True))
@click.option("--bam", required=True, type=click.Path(exists=True))
@click.option("--out", required=True, type=click.Path())
@click.option("--tag-name", default="ER", show_default=True)
def tag(summary: str, bam: str, out: str, tag_name: str) -> None:
    """Tag BAM reads with end_reason from sequencing_summary.txt."""
    from .filter.tag import tag_bam

    try:
        result = tag_bam(summary, bam, out, tag_name=tag_name)
    except OntEndReasonError as exc:
        _die(str(exc))
    click.echo(
        f"Tagged {result.tagged_reads:,} / {result.input_reads:,} reads "
        f"(missing: {result.missing_reads:,}); wrote {out}"
    )


@main.command()
@click.option("--bam", required=True, type=click.Path(exists=True))
@click.option("--out", required=True, type=click.Path())
@click.option(
    "--keep",
    required=True,
    help="End reason codes to keep, comma-separated (e.g. SP or SP,UMC).",
)
@click.option("--tag-name", default="ER", show_default=True)
@click.option("--threads", default=1, type=int, show_default=True)
def filter(bam: str, out: str, keep: str, tag_name: str, threads: int) -> None:
    """Filter a tagged BAM by end_reason."""
    from .filter.filter import filter_bam

    try:
        result = filter_bam(bam, out, keep, tag_name=tag_name, threads=threads)
    except OntEndReasonError as exc:
        _die(str(exc))
    click.echo(
        f"Kept {result.kept_reads:,} / {result.input_reads:,} reads "
        f"(dropped: {result.dropped_reads:,}); wrote {out}"
    )


@main.command(name="export-fastq")
@click.option("--bam", required=True, type=click.Path(exists=True))
@click.option("--fastq", required=True, type=click.Path())
@click.option("--compress", is_flag=True, help="gzip the output.")
def export_fastq(bam: str, fastq: str, compress: bool) -> None:
    """Export a (filtered) BAM to FASTQ for NanoPack tools."""
    from .filter.export import export_fastq as do_export

    try:
        result = do_export(bam, fastq, compress=compress)
    except OntEndReasonError as exc:
        _die(str(exc))
    click.echo(
        f"Wrote {result.reads_written:,} reads ({result.bytes_written:,} bytes) "
        f"to {result.output_path}"
    )


# ───────────────────────── analyze (group) ─────────────────────────


@main.group()
def analyze() -> None:
    """Run a paper-grade analysis on POD5/Fast5/summary input."""


@analyze.command("distribution")
@click.argument("source", type=click.Path(exists=True))
@click.option("--quick", is_flag=True, help="Sample up to 10k reads.")
@click.option("--max-reads", default=10_000, type=int, show_default=True)
@click.option("--json", "json_out", type=click.Path(), default=None)
@click.option("--plot", "plot_out", type=click.Path(), default=None)
def analyze_distribution(
    source: str,
    quick: bool,
    max_reads: int,
    json_out: str | None,
    plot_out: str | None,
) -> None:
    """End-reason distribution + OK/CHECK/FAIL quality gate."""
    from .analyze.distribution import distribution as do_distribution

    try:
        result = do_distribution(source, quick=quick, max_reads=max_reads)
    except OntEndReasonError as exc:
        _die(str(exc))

    click.echo(f"Total reads:  {result.total_reads:,}")
    click.echo(f"Status:       {result.quality_status}")
    click.echo(f"Signal+ %:    {result.signal_positive_pct:.2f}")
    click.echo(f"UMC %:        {result.unblock_mux_pct:.2f}")
    click.echo(f"DUMC %:       {result.data_service_pct:.2f}")
    click.echo(f"Interpretation: {result.interpretation}")

    if json_out:
        Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(json_out).write_text(json.dumps(result.to_dict(), indent=2))
        click.echo(f"JSON: {json_out}")

    if plot_out:
        from .viz.static import plot_distribution

        fig = plot_distribution(result)
        Path(plot_out).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(plot_out, dpi=300, bbox_inches="tight")
        click.echo(f"Plot: {plot_out}")


# Scaffolded analyses — each calls its NotImplementedError counterpart and
# the CLI gets a clean error message.


def _scaffold_analyze(cli_name: str, module_name: str) -> click.Command:
    @click.command(cli_name)
    @click.argument("source", type=click.Path(exists=True))
    def cmd(source: str) -> None:
        from importlib import import_module

        mod = import_module(f"ont_end_reason.analyze.{module_name}")
        func = getattr(mod, module_name)
        try:
            func(source)
        except NotImplementedError as exc:
            click.echo(f"[v0.2.0-roadmap] {exc}", err=True)
            sys.exit(2)

    return cmd


analyze.add_command(_scaffold_analyze("quality", "quality"))
analyze.add_command(_scaffold_analyze("temporal", "temporal"))
analyze.add_command(_scaffold_analyze("hypothesis", "hypothesis"))
analyze.add_command(_scaffold_analyze("umc-posterior", "umc_posterior"))
analyze.add_command(_scaffold_analyze("sma-metrics", "sma_metrics"))


@analyze.command("length")
@click.argument("source", type=click.Path(exists=True))
@click.option("--json", "json_out", type=click.Path(), default=None)
@click.option("--plot", "plot_out", type=click.Path(), default=None)
def analyze_length(source: str, json_out: str | None, plot_out: str | None) -> None:
    """Per-end_reason length distribution: n, mean, median, percentiles, N50."""
    from .analyze.length import length as do_length

    try:
        result = do_length(source)
    except OntEndReasonError as exc:
        _die(str(exc))

    click.echo(f"Total reads:  {result.total_reads:,}")
    click.echo(f"{'End reason':<35}{'n':>8}{'median':>9}{'p95':>9}{'N50':>9}")
    for er, s in sorted(result.per_class.items(), key=lambda kv: -kv[1].n):
        click.echo(f"  {er:<33}{s.n:>8,d}{s.median:>9,.0f}{s.p95:>9,.0f}{s.n50:>9,d}")

    if json_out:
        Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(json_out).write_text(json.dumps(result.to_dict(), indent=2))
        click.echo(f"JSON: {json_out}")

    if plot_out:
        from .viz.static import plot_length_distribution

        fig = plot_length_distribution(result)
        Path(plot_out).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(plot_out, dpi=300, bbox_inches="tight")
        click.echo(f"Plot: {plot_out}")


@analyze.command("signal-trace")
@click.argument("pod5", type=click.Path(exists=True))
@click.option("--read-id", required=True)
def analyze_signal_trace(pod5: str, read_id: str) -> None:
    """[v0.2.0] Extract and visualise the raw signal trace for a single read."""
    from .analyze.signal_trace import signal_trace

    try:
        signal_trace(pod5, read_id=read_id)
    except NotImplementedError as exc:
        click.echo(f"[v0.2.0-roadmap] {exc}", err=True)
        sys.exit(2)


# ───────────────────────── figure (group) ─────────────────────────


@main.group()
def figure() -> None:
    """Reproduce a named paper figure (fig3, fig5, fig6, supplementary)."""


@figure.command("fig3")
@click.argument("source", type=click.Path(exists=True))
@click.option("--out", required=True, type=click.Path())
@click.option("--quick", is_flag=True)
def figure_fig3(source: str, out: str, quick: bool) -> None:
    """Paper Figure 3 — end-reason distribution bar chart."""
    from .figures.fig3_distribution import fig3_distribution

    try:
        path = fig3_distribution(source, out=out, quick=quick)
    except OntEndReasonError as exc:
        _die(str(exc))
    click.echo(f"Figure 3 written: {path}")


@figure.command("fig5")
@click.argument("source", type=click.Path(exists=True))
@click.option("--out", required=True, type=click.Path())
def figure_fig5(source: str, out: str) -> None:
    """[v0.2.0] Paper Figure 5 — Q-score violins per end_reason."""
    from .figures.fig5_violin import fig5_violin

    try:
        fig5_violin(source, out=out)
    except NotImplementedError as exc:
        click.echo(f"[v0.2.0-roadmap] {exc}", err=True)
        sys.exit(2)


@figure.command("fig6")
@click.argument("source", type=click.Path(exists=True))
@click.option("--out", required=True, type=click.Path())
def figure_fig6(source: str, out: str) -> None:
    """[v0.3.0] Paper Figure 6 — conceptual diagram."""
    from .figures.fig6_conceptual import fig6_conceptual

    try:
        fig6_conceptual(source, out=out)
    except NotImplementedError as exc:
        click.echo(f"[v0.3.0-roadmap] {exc}", err=True)
        sys.exit(2)


@figure.command("supplementary")
@click.argument("source", type=click.Path(exists=True))
@click.option("--out", required=True, type=click.Path())
def figure_supplementary(source: str, out: str) -> None:
    """[v0.2.0] Paper supplementary figures."""
    from .figures.supplementary import supplementary

    try:
        supplementary(source, out=out)
    except NotImplementedError as exc:
        click.echo(f"[v0.2.0-roadmap] {exc}", err=True)
        sys.exit(2)


# ───────────────────────── report (group) ─────────────────────────


@main.group()
def report() -> None:
    """Build composed multi-analysis reports."""


@report.command("interactive")
@click.argument("source", type=click.Path(exists=True))
@click.option("--out", required=True, type=click.Path())
@click.option("--quick", is_flag=True)
def report_interactive(source: str, out: str, quick: bool) -> None:
    """Self-contained interactive HTML report with Plotly figures."""
    from .report.html import build_html_report

    try:
        result = build_html_report(source, output_path=out, quick=quick)
    except OntEndReasonError as exc:
        _die(str(exc))
    click.echo(
        f"HTML report ({result.n_reads:,} reads, "
        f"sections: {', '.join(result.sections)}): {result.output_path}"
    )


@report.command("static")
@click.argument("source", type=click.Path(exists=True))
@click.option("--out", required=True, type=click.Path())
def report_static(source: str, out: str) -> None:
    """[v0.2.0] PDF report composing all analyses."""
    click.echo(
        "[v0.2.0-roadmap] Static PDF report is scheduled for v0.2.0. "
        "Use `report interactive` for the current functionality.",
        err=True,
    )
    sys.exit(2)


# ───────────────────────── utility ─────────────────────────


@main.command()
def codes() -> None:
    """Print the end_reason abbreviation taxonomy."""
    click.echo("End reason codes (canonical lab taxonomy)\n")
    click.echo(f"{'Code':<6}{'Full name':<40}{'Class':<15}")
    click.echo("─" * 61)
    for full, short in CODES.items():
        if short in RECOMMENDED_KEEP:
            cls = "keep"
        elif short in TRUNCATED:
            cls = "truncated"
        elif short in FAILED:
            cls = "failed"
        else:
            cls = "unknown"
        click.echo(f"{short:<6}{full:<40}{cls:<15}")


@main.command()
def schema() -> None:
    """Print the canonical sequencing_summary column set."""
    from .io.schema import RECOMMENDED_COLUMNS, REQUIRED_COLUMNS

    click.echo("sequencing_summary.txt schema (required + recommended columns)\n")
    click.echo("Required:")
    for c in sorted(REQUIRED_COLUMNS):
        click.echo(f"  - {c}")
    click.echo("\nRecommended:")
    for c in sorted(RECOMMENDED_COLUMNS):
        click.echo(f"  - {c}")


@main.command()
@click.option("--summary", required=True, type=click.Path(exists=True))
@click.option("--out", type=click.Path(), default=None)
@click.option("--json", "json_out", type=click.Path(), default=None)
def stats(summary: str, out: str | None, json_out: str | None) -> None:
    """Streaming QC for PromethION-scale sequencing_summary.txt.

    v0.1.0 ships a minimal implementation; the canonical version with
    additional metrics is scheduled for v0.2.0.
    """
    from .analyze.distribution import distribution as do_distribution

    try:
        result = do_distribution(summary)
    except OntEndReasonError as exc:
        _die(str(exc))

    text = (
        f"sequencing_summary stats — {summary}\n"
        f"  total_reads:        {result.total_reads:,}\n"
        f"  quality_status:     {result.quality_status}\n"
        f"  signal_positive_%:  {result.signal_positive_pct:.2f}\n"
        f"  unblock_mux_%:      {result.unblock_mux_pct:.2f}\n"
        f"  data_service_%:     {result.data_service_pct:.2f}\n"
    )
    if out:
        Path(out).write_text(text)
        click.echo(f"Wrote {out}")
    else:
        click.echo(text)

    if json_out:
        Path(json_out).write_text(json.dumps(result.to_dict(), indent=2))
        click.echo(f"Wrote {json_out}")


if __name__ == "__main__":
    main()

# ont-end-reason

[![CI](https://github.com/Single-Molecule-Sequencing/ont-end-reason/actions/workflows/ci.yml/badge.svg)](https://github.com/Single-Molecule-Sequencing/ont-end-reason/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ont-end-reason.svg)](https://pypi.org/project/ont-end-reason/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

> **Comprehensive CLI for Oxford Nanopore `end_reason` analysis.**
> Discover data files (POD5, Fast5, sequencing_summary.txt), tag BAMs with
> end_reason metadata, filter by end_reason category, analyse, and produce
> publication-quality static figures + interactive HTML reports.

Companion to the [end-reason paper](https://github.com/Single-Molecule-Sequencing/end-reason-paper)
from the [Athey Lab](https://github.com/Single-Molecule-Sequencing) at the
University of Michigan.

## Why end_reason matters

Oxford Nanopore sequencers tag every read with an `end_reason` explaining why
sequencing stopped. **A read can have high base quality (Q>20) and still be
truncated or rejected by adaptive sampling** — filtering by Q-score alone is
not enough for accurate downstream analysis.

This tool unifies discovery, tagging, filtering, analysis, and visualisation
of `end_reason` metadata into a single CLI.

## Install

```bash
pip install ont-end-reason                      # static figures only
pip install "ont-end-reason[interactive]"       # + Plotly for interactive HTML
```

From source (development):

```bash
git clone https://github.com/Single-Molecule-Sequencing/ont-end-reason.git
cd ont-end-reason
pip install -e ".[dev,interactive]"
```

## Quickstart

```bash
# 1. Discover what's in a sequencing-run directory
ont-end-reason discover /path/to/run --manifest run.json

# 2. Tag a BAM with end_reason from sequencing_summary.txt
ont-end-reason tag --summary sequencing_summary.txt --bam aligned.bam --out tagged.bam

# 3. Filter to complete reads only (signal_positive)
ont-end-reason filter --bam tagged.bam --keep SP --out complete.bam

# 4. Analyse end_reason distribution
ont-end-reason analyze distribution complete.bam --json results.json

# 5. Generate the canonical paper figures
ont-end-reason figure fig3 sequencing_summary.txt --out fig3.pdf

# 6. Build an interactive HTML report combining everything
ont-end-reason report interactive run.json --out report.html
```

## End_reason taxonomy

| Code | Full name | Class | Action |
|---|---|---|---|
| `SP` | signal_positive | **keep** | Complete read — always keep |
| `UMC` | unblock_mux_change | truncated | Filter unless studying artifacts |
| `MC` | mux_change | truncated | Filter |
| `DUMC` | data_service_unblock_mux_change | truncated | Filter |
| `PART` | partial | truncated | Filter |
| `SN` | signal_negative | **failed** | Always filter |
| `UNK` | unknown | unknown | Investigate distribution |

Print the table from the CLI:

```bash
ont-end-reason codes
```

## CLI surface

```
ont-end-reason <subcommand>
├── discover     find POD5/Fast5/summary files; emit a manifest
├── tag          tag a BAM with end_reason from sequencing_summary
├── filter       filter a tagged BAM by end_reason
├── export-fastq convert a filtered BAM to FASTQ for NanoPack tools
├── stats        streaming QC for PromethION-scale sequencing_summary
├── analyze      eight analysis types (distribution/length/quality/temporal/...)
├── figure       reproduce paper figures (fig3, fig5, fig6, supplementary)
├── report       composed static or interactive HTML reports
├── codes        print the end_reason taxonomy
└── schema       print the canonical sequencing_summary columns
```

Each subcommand has its own `--help` with full flag documentation.

## Python API

```python
from ont_end_reason import discover, analyze, plot
from ont_end_reason.viz.static import plot_distribution
from ont_end_reason.viz.interactive import interactive_distribution

manifest = discover("/path/to/run")
result = analyze.distribution(manifest.summaries[0])
fig = plot_distribution(result)
fig.savefig("dist.pdf")
```

Every analysis function returns a typed dataclass with structured fields.
Every plot function returns either `matplotlib.figure.Figure` or
`plotly.graph_objects.Figure` so callers can compose, embed, or save in
whatever form they need.

## Status — v0.1.0 alpha

- ✅ Discovery, tagging, filtering, FASTQ export, streaming QC
- ✅ End-reason distribution analysis + bar charts
- ✅ Interactive HTML reports
- 🚧 Length / Q-score GMM / temporal / signal-trace analyses
  (scaffolded — see [issues labelled `analysis`](https://github.com/Single-Molecule-Sequencing/ont-end-reason/issues?q=label%3Aanalysis))
- 🚧 Paper-figure reproducers (fig3/5/6 + supplementary)
- ⏳ Reproducibility CI against end-reason-paper claim atoms

See [docs/superpowers/specs/2026-05-12-ont-end-reason-design.md](docs/superpowers/specs/2026-05-12-ont-end-reason-design.md)
for the full design, scope contract, and roadmap.

## How this relates to the lab's skills

The `/end-reason` and `/end-reason-filter` Claude Code skills in
[ont-ecosystem](https://github.com/Single-Molecule-Sequencing/ont-ecosystem)
are thin wrappers that `pip install` this package and delegate to its CLI.
Same code path internal and external, one source of truth.

## Citation

If you use this tool, please cite the companion paper (see [`CITATION.cff`](CITATION.cff)).

## License

MIT — see [`LICENSE`](LICENSE).

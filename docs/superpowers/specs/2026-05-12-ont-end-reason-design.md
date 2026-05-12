# ont-end-reason — design spec

**Date:** 2026-05-12
**Status:** approved (user-authorized for implementation 2026-05-12)
**Repo:** `Single-Molecule-Sequencing/ont-end-reason`
**Package:** `ont-end-reason` (PyPI), `ont_end_reason` (import)
**CLI:** `ont-end-reason`

## Motivation

The Athey Lab end-reason paper requires a reproducible, publicly-installable
tool that external readers can use to verify every claim atom. Today the
functionality is scattered across:

- `/end-reason` skill — 685 LOC analysis
- `/end-reason-filter` skill — 1684 LOC (4 scripts: tag, filter, export-fastq,
  streaming-qc) promoted from the archived `End_Reason_Manuscript`
- `End_Reason_Manuscript/docs/reference/TOOL_SPECIFICATIONS.md` — 15 analysis
  types the paper's figures depend on, partially implemented

This spec consolidates that surface into a single PyPI/conda-forge package
shipping alongside the paper.

## Decisions locked during brainstorming

| Decision | Choice | Why |
|---|---|---|
| Motivation | Public release alongside paper | External labs need to reproduce claim atoms; aligns with `barbell` precedent (lab tool on crates.io) |
| Skill relationship | Skills become thin wrappers | One source of truth, no drift; lab UX preserved |
| Name | `ont-end-reason` | Follows ont-* convention used by Nanopore's own tools |
| Visualization | matplotlib (static) + Plotly (interactive HTML) via extras | Different audiences: paper PDFs vs lab QC dashboards |
| v1 scope | Paper-complete (all 15 TOOL_SPECIFICATIONS analyses) | Reproducibility ships at v1 |
| Architecture | Layered subpackages (Approach A) | Standard scientific-Python shape; maps 1:1 to feature list |

## Repository layout

```
ont-end-reason/
├── pyproject.toml
├── README.md
├── LICENSE                  (MIT)
├── CITATION.cff
├── docs/
│   ├── superpowers/specs/   ← this spec
│   ├── tutorials/
│   ├── cli-reference.md     (auto-generated)
│   ├── api-reference.md     (auto-generated)
│   └── paper-figures/       (one .md per figure with exact reproducer commands)
├── src/ont_end_reason/
│   ├── __init__.py          (__version__, public API)
│   ├── __main__.py          (`python -m ont_end_reason`)
│   ├── cli.py               (click dispatcher, lazy-imports subpackages)
│   ├── codes.py             (SP/UMC/MC/SN/DUMC/UNK/PART taxonomy SSOT)
│   ├── errors.py            (OntEndReasonError + subclasses)
│   ├── io/                  (discover + readers + schema)
│   ├── filter/              (tag + filter + export-fastq)
│   ├── analyze/             (15 analysis modules)
│   ├── viz/                 (static + interactive)
│   ├── figures/             (paper-figure reproducers)
│   └── report/              (composed HTML reports)
├── tests/{unit,integration,reproducibility,fixtures}/
└── .github/workflows/{ci,reproducibility,release,docs}.yml
```

## CLI surface

```bash
ont-end-reason --help / --version / --debug / --quiet / --strict

# Discovery
ont-end-reason discover <path> [--recursive] [--validate-schema] [--manifest <out.json>]

# Filter ops (ports of er-filter)
ont-end-reason tag --summary <s.txt> --bam <in.bam> --out <tagged.bam>
ont-end-reason filter --bam <in.bam> --keep SP[,UMC] --out <out.bam> [--threads N]
ont-end-reason export-fastq --bam <in.bam> --fastq <out.fq.gz>

# Analysis (one subcommand per TOOL_SPECIFICATIONS type)
ont-end-reason analyze distribution <input>
ont-end-reason analyze length <input>
ont-end-reason analyze quality <input> [--gmm-components N]
ont-end-reason analyze temporal <input>
ont-end-reason analyze signal-trace <pod5> --read-id <id>
ont-end-reason analyze hypothesis <input> [--test mann-whitney|ks]
ont-end-reason analyze umc-posterior <input>
ont-end-reason analyze sma-metrics <input>

# Paper-figure reproducers
ont-end-reason figure fig3 <input> --out fig3.pdf
ont-end-reason figure fig5 <input> --out fig5.pdf
ont-end-reason figure fig6 <input> --out fig6.pdf
ont-end-reason figure supplementary <input> --out supp/

# Composed reports
ont-end-reason report static <manifest.json> --out report.pdf
ont-end-reason report interactive <manifest.json> --out report.html

# QC
ont-end-reason stats --summary <s.txt> --out qc.txt --json qc.json

# Utility
ont-end-reason codes
ont-end-reason schema
```

## Component interfaces (Python API)

External users do:

```python
from ont_end_reason import discover, classify, analyze, plot
from ont_end_reason.io import Manifest
from ont_end_reason.analyze import (
    DistributionResult, LengthResult, QualityResult,
    TemporalResult, SignalTraceResult, HypothesisResult,
    UMCPosteriorResult,
)
from ont_end_reason.viz.static import plot_distribution, plot_violin
from ont_end_reason.viz.interactive import interactive_distribution
from ont_end_reason.report import HtmlReport
```

Every analysis function returns a dataclass `AnalysisResult` with structured
fields, not a dict. `plot_*` functions return either `matplotlib.figure.Figure`
or `plotly.graph_objects.Figure` so callers can compose / save / display
however they want.

## Data flow

```
Path → discover()  →  Manifest        (io/discover.py)
                       │
                       ▼
                     readers()         (io/readers.py)
                       │
                       ▼
                   analyze.*()  →  AnalysisResult dataclass
                       │
                       ▼
                     viz.*()    →  Figure
                       │
                       ▼
                     save()     →  PDF/PNG/HTML/JSON
```

`sequencing_summary.txt` reading is **streaming** (chunked pandas) so
PromethION-scale files don't OOM. Hold <4 GB RAM regardless of file size.

A `Pipeline` helper composes the above for `report` subcommands:

```python
pipeline = Pipeline(manifest)
pipeline.add(analyze.distribution)
pipeline.add(analyze.length)
pipeline.add(analyze.quality)
report = pipeline.render(format="html")
```

## Error handling + observability

```python
class OntEndReasonError(Exception): ...
class IOError(OntEndReasonError): ...        # file not found, bad format
class AnalysisError(OntEndReasonError): ...  # analysis-level bug, bad input
class ValidationError(OntEndReasonError): ...# schema validation failure
```

CLI behaviour: catches `OntEndReasonError`, prints a clear `[error] <msg>`,
exits with code 1. Library callers see the exception raised normally.

Logging via `structlog`. `--debug` enables DEBUG-level structured logs.
`--quiet` suppresses INFO. `--strict` escalates warnings to errors (useful
in CI for catching new edge cases early).

## Testing strategy

- **pytest** with markers: `fast` / `slow` / `integration` / `reproducibility`
- Coverage gate: 80% line on `src/` (enforced in CI)
- **Reproducibility CI** (nightly): clones `end-reason-paper@<pinned-tag>`,
  reruns each claim atom, asserts bit-identical output vs pinned expected JSON
- **Property tests** for `codes.py` via Hypothesis (round-trip
  short↔long, parse_keep_list with random valid inputs)
- Tiny fixtures: 100-read POD5, 1k-read tagged BAM, 5k-row
  sequencing_summary.txt — all under tests/fixtures/

Test suites (defined in pyproject.toml `[tool.pytest.ini_options]`):

```toml
[tool.pytest.ini_options.markers]
fast = "Unit tests, <0.1s, no I/O"
slow = "Tests >0.5s or heavy I/O"
integration = "End-to-end CLI tests with fixtures"
reproducibility = "Re-runs end-reason-paper claim atoms"
```

## Packaging + release

`pyproject.toml`:

```toml
[project]
name = "ont-end-reason"
dynamic = ["version"]
requires-python = ">=3.10"
dependencies = ["click", "pysam", "pod5", "numpy", "pandas",
                "matplotlib", "scipy", "structlog"]

[project.optional-dependencies]
interactive = ["plotly", "kaleido"]
dev = ["pytest", "pytest-cov", "hypothesis", "ruff", "mypy"]

[project.scripts]
ont-end-reason = "ont_end_reason.cli:main"
```

Release flow:

- Tag `v0.x.y` → `release.yml` workflow builds wheel + sdist
- Uploads to PyPI via **OIDC trusted publishing** (no API token)
- After v0.1.0: manually open conda-forge feedstock PR
- Self-update via `bump-my-version` (configured in pyproject.toml)

## Migration path

1. **Phase 1 — v0.x development (this commit-set):** new repo built in
   parallel with `/end-reason-filter` skill. Both functional during transition.
2. **Phase 2 — v0.1.0 PyPI release:** publish to PyPI. Lab skills updated
   to thin wrappers (`pip install ont-end-reason && ont-end-reason <subcmd>`).
3. **Phase 3 — Paper atoms re-pin:** end-reason-paper's claim atoms
   (`results.alignment_rate_filtered`, `results.snv_f1_filtered`, etc.)
   migrate from "pinned to End_Reason_Manuscript@b47166a" to "pinned to
   ont-end-reason==0.1.0". Reproducibility CI verifies bit-identity.
4. **Phase 4 — conda-forge feedstock:** open feedstock PR, get on the
   bioconda channel for `mamba install ont-end-reason`.
5. **Phase 5 — public announcement:** when paper preprints, README links
   to the paper; paper Methods section cites the tool DOI (Zenodo).

End_Reason_Manuscript stays archived. All scripts in this repo carry a
provenance header crediting commit `b47166a` of the archived source.

## v0.1.0 scope contract

**MUST ship in v0.1.0 for release:**

- All 7 CLI groups working (`discover`, `tag`, `filter`, `export-fastq`,
  `analyze`, `figure`, `report`)
- Analysis subcommands wired and either fully implemented or producing
  clear `NotImplementedError` with TODO pointer + GitHub issue link
- All 5 ported scripts (er-filter contents + end_reason.py) functional
- `codes.py` complete with full test coverage
- CLI `--help` works end-to-end for every subcommand
- CI green on Python 3.10–3.13, Linux + macOS
- README with install + quickstart

**Deferred to v0.2.0 (or later):**

- Full implementation of all 15 analyses (5 ported + 10 paper-specific
  scaffolded with TODO)
- Reproducibility CI vs end-reason-paper claim atoms
- conda-forge feedstock
- Per-analysis tutorial pages in docs/

This is a deliberate "ship the structure, fill in the analyses" approach.
The structure is the hard part; the analyses are mechanical translations
of existing paper scripts once the harness exists.

## Open questions (filed as GitHub issues at repo creation)

- #1: Choose Zenodo DOI scheme (per-release vs per-repo)
- #2: Should `analyze sma-metrics` delegate to `smaseq-qc` package, or
  vendor that code?
- #3: Should report HTML embed Plotly via CDN or self-host?
- #4: pixi.toml in addition to pyproject.toml for cross-platform dev?

These do not block v0.1.0. Marked in repo issues as `decision-needed`.

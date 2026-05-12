# Changelog

All notable changes to ont-end-reason are documented here. Format adheres to
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[PEP 440](https://peps.python.org/pep-0440/).

## [0.2.0a1] — 2026-05-12

### Added — full implementations of every scaffolded v0.1.0 analysis

- `analyze.length` — per-end_reason length distributions with N50, percentiles,
  mean/median/std; streaming sequencing_summary reader; numpy-only.
- `analyze.temporal` — bin reads by `start_time` and report per-bin
  end_reason counts + fractions; stacked-area plot.
- `analyze.quality` — per-end_reason Q-score distributions with Gaussian
  Mixture Model fit (scipy-only EM, BIC-selected k); violin plot.
- `analyze.hypothesis` — Mann-Whitney U and Kolmogorov-Smirnov tests between
  two end_reason populations; Cliff's Δ effect size.
- `analyze.umc_posterior` — **paper's central novel analysis**: Bayesian
  posterior over true UMC read length given adaptive-sampling truncation.
  Fits a lognormal prior from signal_positive reads, computes truncated
  posterior per-read, returns mean / median / 95% credible interval / total
  "bonus" sequence lost to truncation.
- `analyze.signal_trace` — raw POD5 signal extraction for a single read with
  end_reason annotation.
- `analyze.sma_metrics` — bridge to the optional `smaseq-qc` package; returns
  `available=False` with install hint when missing, never raises.
- `analyze.tables` — composable table generator (summary / per_class /
  quality) rendering to TSV / CSV / markdown / LaTeX.
- `figures.fig5_violin` — real implementation (Q-score violins).
- `figures.fig6_conceptual` — real implementation (UMC posterior diagram).
- `viz.static.plot_length_distribution`, `plot_quality_violins`,
  `plot_temporal`, `plot_umc_posterior`, `plot_signal_trace`.
- Multi-section HTML report (`report.html.build_html_report`): now
  composes 6 sections (distribution + length + quality + temporal +
  umc_posterior + hypothesis). Graceful fallback to embedded PNG when
  Plotly is unavailable; per-section error rendering if data is missing.
- Synthetic `tests/fixtures/sequencing_summary_synthetic.txt` (5000 reads,
  realistic 80/12/5/2/1% SP/UMC/DUMC/MC/SN distribution with lognormal
  lengths + Gaussian Q-scores).
- 143 tests covering every implemented analysis + GMM EM correctness +
  Cliff's Δ properties + report rendering.

### Changed

- CLI: removed `[v0.2.0-roadmap]` scaffold guards from every analysis
  subcommand; all now fully wired with `--json` / `--plot` options.
- CI coverage gate raised from 40% to 60%.
- Reproducibility: SP/UMC posterior bonus on the synthetic fixture is
  ~4942 bp/read (~3 Mb total). Locks the analytic chain end-to-end.

### Internal

- POD5 enum normaliser fixed in 0.1.0 hot-fix path; tests now lock the
  pod5 NamedTuple repr shape.
- viz/__init__ eagerly imports `static` and `interactive` so attribute
  access works without explicit submodule import.

## [0.1.0a1] — 2026-05-12

Initial alpha. See [`docs/superpowers/specs/2026-05-12-ont-end-reason-design.md`](docs/superpowers/specs/2026-05-12-ont-end-reason-design.md)
for the full architecture.

### Added

- Repository scaffold: pyproject.toml, MIT LICENSE, README, CITATION.cff
- `codes.py` — SP/UMC/MC/SN/DUMC/UNK/PART taxonomy SSOT
- `errors.py` — `OntEndReasonError` hierarchy
- `io.discover` / `io.readers` / `io.schema` / `io.manifest` — filesystem
  walk, POD5/Fast5/summary readers, schema validation
- `filter.tag_bam` / `filter_bam` / `export_fastq` — ports of the
  `End_Reason_Manuscript@b47166a` pipeline scripts
- `analyze.distribution` — end_reason counts + OK/CHECK/FAIL gate
- `cli.py` — click dispatcher with 10 subcommands
- CI workflow matrix (Python 3.10–3.13 × Ubuntu/macOS)
- 82 tests (codes + errors + manifest + schema + discover + CLI integration)

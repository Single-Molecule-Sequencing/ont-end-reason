# Cross-run end-reason atlas — design

**Status:** approved (self-approved per user delegation 2026-05-12)
**Approach:** A — `ont-end-reason analyze atlas` subcommand + `lib/qc_baseline.py` extension
**Scope target:** one implementation cycle, complete vertical slice (library + CLI + dashboard section + figure regenerator + tests + push)

## Motivation

A run-level `/end-reason` analysis answers "is THIS run OK". It cannot answer "is this run normal compared to the lab's 11 prior runs" or "is this UMC rate within the range published in the GIAB ONT Open Data corpus". The atlas closes that gap by aggregating end_reason distributions across:
  - every internal lab experiment in `~/.ont-registry/`
  - selected public peers (GIAB, hereditary-cancer ONT Open Data) via the `/ont-public-data` skill

and exposing the result through one canonical surface (`ont-end-reason analyze atlas`) that the CLI, an embedded dashboard panel, and a paper-figure regenerator all consume.

## Non-goals (YAGNI cuts)

- **Not** a separate interactive web app. The atlas reuses the existing `docs/index.html` GitHub Pages site by adding a section.
- **Not** all 9 panels of paper fig7. Only the single per-flowcell summary view (fig8).
- **Not** a streaming/live-update system. Reads run on demand; results are recomputed each call. Internal peers come from a populated `qc_baseline` store; external peers come from a Parquet fingerprint cache refreshed by `/ont-public-data` separately.
- **Not** a new top-level skill. Lives as an `analyze` subcommand alongside distribution / length / quality / etc.

## Prior art reused (search-before-author compliance)

| Existing piece | Role in atlas |
|---|---|
| `~/repos/ont-ecosystem/lib/qc_baseline.py` (1,121 LOC) | Persistent QC store, similarity queries, z-score, outlier flagging |
| `/ont-public-data` skill | S3 streaming of public ONT datasets without full downloads |
| `~/repos/end-reason-paper/atoms/figures/fig8_public_validation_summary.fig.yaml` | Atom whose `build_recipe: manuscript/figures/validate_public_data.py` is aspirational (file missing). The atlas's figure regenerator fills this gap. |
| `ont-end-reason analyze distribution` | Per-run input — the atlas aggregates over its results |
| `ont-end-reason` `docs/index.html` | Existing dashboard. Atlas adds a section, not a new page. |

## Architecture

Four layers stacked on existing infrastructure:

```
┌──────────────────────────────────────────────────────────────┐
│  Consumers                                                    │
│   • CLI:   ont-end-reason analyze atlas --json out.json       │
│   • Dashboard: docs/index.html  (new "Atlas" section, Plotly) │
│   • Figure: figures/atlas.py  (reproduces fig8-style summary) │
└────────────────────┬─────────────────────────────────────────┘
                     │ consumes AtlasResult JSON
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  Atlas aggregation library     [NEW]                          │
│   src/ont_end_reason/analyze/atlas.py                         │
│     atlas() → AtlasResult                                     │
│       • Pulls internal peers from qc_baseline store           │
│       • Pulls external peers from peer-fingerprint cache      │
│       • Stratifies by (flowcell_type, chemistry, adaptive)    │
│       • Computes per-stratum baseline stats + per-run z-scores│
│       • Flags outliers (composite anomaly_score = max(|z_i|)) │
└────────┬──────────────────────┬──────────────────────────────┘
         │                      │
         ▼                      ▼
┌──────────────────┐  ┌──────────────────────────────────────┐
│ qc_baseline      │  │ external peer fingerprint cache       │
│ (existing,       │  │  ~/.ont-qc-baselines/external_peers/  │
│  but empty)      │  │  *.parquet (refreshed via             │
│                  │  │   /ont-public-data, weekly)           │
└────────▲─────────┘  └──────────────────────────────────────┘
         │
         │ NEW: auto-populate on every run
         │
┌──────────────────────────────────────────────────────────────┐
│  /end-reason analyze distribution      [EXTENDED]             │
│   Optionally stores result in qc_baseline via                 │
│   `--baseline-store` flag (default: on if registry-known      │
│   experiment, off if standalone)                              │
└──────────────────────────────────────────────────────────────┘
```

## Components

### 1. `src/ont_end_reason/analyze/atlas.py` — aggregation library [NEW, ~250 LOC]

Public API:

```python
def atlas(
    *,
    include_internal: bool = True,
    include_external: bool = True,
    strata: Iterable[str] = ("flowcell_type", "chemistry", "adaptive_sampling"),
    z_threshold: float = 2.0,
) -> AtlasResult:
    """Build a cross-run end-reason atlas.

    Aggregates per-run end_reason distributions across the qc_baseline store
    (internal peers) and the external_peers/ Parquet cache, stratifies by
    `strata`, computes per-stratum baseline statistics, and flags outlier
    runs whose composite anomaly_score >= z_threshold.
    """
```

`AtlasResult` dataclass:

```python
@dataclass
class AtlasResult:
    n_internal: int
    n_external: int
    strata_keys: list[str]
    per_stratum: dict[tuple, StratumStats]  # (flowcell_type, chem, adaptive) → stats
    outliers: list[OutlierRecord]  # runs with anomaly_score >= z_threshold
    generated_at: str  # ISO-8601 UTC
```

Helpers (private):
  - `_load_internal_peers()` — queries `qc_baseline.get_all_qc_results()`, filters to those with `signal_positive_pct` in metrics
  - `_load_external_peers()` — reads Parquet files from `~/.ont-qc-baselines/external_peers/*.parquet`
  - `_stratify(rows, strata)` — group-by helper
  - `_compute_stratum_stats(rows)` — mean/median/IQR for the standard metrics (signal_positive_pct, unblock_mux_pct, data_service_pct, mux_change_pct, signal_negative_pct)
  - `_score_outliers(rows, per_stratum, z_threshold)` — per-metric z-score, composite max
  - `to_json(result, path)` — canonical JSON dump

### 2. `lib/qc_baseline.py` extension [EDIT, ~40 LOC added]

Add three helpers for atlas-style queries:

```python
def get_end_reason_results() -> list[QCResult]:
    """Filter get_all_qc_results() to those with signal_positive_pct metric."""

def get_stratum_stats(strata_keys: list[str]) -> dict[tuple, BaselineStatistics]:
    """Group results by strata and compute baseline stats per group."""

def compute_atlas_outliers(results: list[QCResult], strata_keys: list[str],
                          z_threshold: float = 2.0) -> list[OutlierRecord]:
    """Per-stratum, per-metric z-score; composite anomaly_score = max(|z_i|)."""
```

These live in qc_baseline.py because they're general "baseline atlas" operations — same module, same dependency footprint. Other consumers (e.g. `/qc-advisor`) can reuse them.

### 3. CLI surface: `ont-end-reason analyze atlas` [NEW click command, ~30 LOC]

```bash
ont-end-reason analyze atlas \
    --json out.json \
    [--include-internal/--no-include-internal] \
    [--include-external/--no-include-external] \
    [--strata flowcell_type,chemistry,adaptive_sampling] \
    [--z-threshold 2.0] \
    [--plot atlas.png]
```

`--plot` emits the fig8-style summary PNG using `viz.static.plot_atlas_summary()` (new).

### 4. Auto-population: `/end-reason analyze distribution` writes to qc_baseline [EDIT, ~25 LOC]

When `analyze distribution` runs with a path that resolves to a registry-known experiment, the result is auto-stored in `qc_baseline` with `ExperimentMetadata` reconstructed from the registry entry. Opt-out flag `--no-baseline-store`. Idempotent: a duplicate `experiment_id+timestamp` is deduped at the qc_baseline layer.

This fixes the "store is empty" bug — every future `/end-reason` run populates the atlas data source.

### 5. Dashboard section: `docs/index.html` [EDIT, ~80 LOC]

Add a new `<section id="atlas">` after the existing sections:
  - Embedded Plotly visualization of per-stratum end_reason distributions
  - Outliers table (top 10 by anomaly_score)
  - Link to `atlas.json` (generated by CI from synthetic-fixture run for the static deploy)

### 6. Figure regenerator: `src/ont_end_reason/figures/atlas.py` [NEW, ~60 LOC]

```python
def atlas(*, out: str | Path) -> str:
    """Reproduces the fig8-style per-flowcell end-reason summary."""
    result = atlas_analyze()
    fig = plot_atlas_summary(result)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out)
```

Wires the existing `figures/` subpackage. The paper-side atom `fig8_public_validation_summary.fig.yaml` can then point its `build_recipe` at `ont-end-reason figure atlas`.

### 7. Backfill helper: `scripts/atlas_backfill.py` [NEW, ~50 LOC]

One-time tool that walks the ONT registry and runs `analyze distribution` on every experiment with data (>0.1 GB), populating the qc_baseline store. Idempotent — re-runnable. Lives in `scripts/` (not part of the package distribution).

## Data flow

```
qc_baseline store (~/.ont-qc-baselines/)
  └── results/  ← /end-reason analyze distribution writes here
                   (new auto-population code path, opt-out flag)
external_peers/
  └── *.parquet ← /ont-public-data refreshes weekly (existing infra)

ont-end-reason analyze atlas
  ↓ reads
analyze/atlas.py::atlas() → AtlasResult (dataclass)
  ↓ to_json
out.json
  ↓ consumed by:
  • CLI (prints summary table, optional --plot)
  • Dashboard (Plotly section in docs/index.html)
  • Figure regenerator (figures/atlas.py → fig8-style PNG)
```

## Error handling

- **Empty qc_baseline store:** atlas() returns AtlasResult with n_internal=0 and a clear interpretation message ("Run scripts/atlas_backfill.py to populate the internal cohort"). Does NOT raise.
- **Empty external_peers cache:** same pattern — n_external=0 with a hint to run `/ont-public-data` to refresh.
- **Both empty:** returns a degraded result with a single-line summary. The CLI exits 0 (not an error — empty atlas is a valid state for a fresh install).
- **Single-member stratum:** baseline stats compute but z-score for the member itself is undefined (only one point). Outlier detection skips strata with N < 3.
- **External peer fetch failure:** caught at the `/ont-public-data` boundary; atlas() degrades to internal-only and logs a warning. Never crashes.

## Testing

Mandatory tests (all must pass before push):

1. **`tests/unit/test_atlas.py`** — happy path on a synthetic fixture (mock 10 QCResults across 3 strata, assert per-stratum stats and outlier detection)
2. **`tests/unit/test_atlas.py::test_empty_store`** — empty qc_baseline → AtlasResult with n_internal=0, no crash
3. **`tests/unit/test_atlas.py::test_single_member_stratum`** — N=1 stratum is skipped in outlier scoring, not crashed on
4. **`tests/unit/test_atlas.py::test_outlier_detection`** — inject an SP=20% run into a cohort with SP_mean=95%, assert it's flagged with anomaly_score > 2.0
5. **`tests/integration/test_atlas_cli.py::test_cli_help_exposes_flags`** — all CLI options visible in `--help`
6. **`tests/integration/test_atlas_cli.py::test_cli_emits_json`** — full CLI invocation against synthetic-store fixture, JSON parses, has expected keys
7. **`tests/integration/test_figures.py::test_atlas_figure`** — `figures.atlas()` produces a non-empty PNG (reuses existing figures-test pattern)
8. **`tests/integration/test_distribution_writes_to_baseline.py`** — verify `analyze distribution` writes a QCResult when run on a registry-known path; verify opt-out flag

Coverage target: maintain 70%+ overall (gate at 71%). The new code is heavily testable (pure functions over dataclasses).

## Implementation phases

Each phase ends with a commit + push:

| Phase | What lands | Files touched |
|---|---|---|
| 1 | `lib/qc_baseline.py` extension (3 helper functions + tests) | ont-ecosystem/lib/qc_baseline.py, ont-ecosystem/tests/test_qc_baseline.py |
| 2 | `analyze/atlas.py` + unit tests | ont-end-reason/src/ont_end_reason/analyze/atlas.py, tests/unit/test_atlas.py |
| 3 | CLI: `analyze atlas` subcommand + integration tests | ont-end-reason/src/ont_end_reason/cli.py, tests/integration/test_atlas_cli.py |
| 4 | `figures/atlas.py` + viz helper + figure test | ont-end-reason/src/ont_end_reason/figures/atlas.py, src/ont_end_reason/viz/static.py |
| 5 | Auto-population: `analyze distribution` writes to qc_baseline + opt-out flag | ont-end-reason/src/ont_end_reason/analyze/distribution.py, tests/integration/test_distribution_writes_to_baseline.py |
| 6 | `scripts/atlas_backfill.py` + dashboard section in docs/index.html + README | ont-end-reason/scripts/atlas_backfill.py, docs/index.html, README.md |
| 7 | Paper-side hookup: point `fig8` atom build_recipe at `ont-end-reason figure atlas` | end-reason-paper/atoms/figures/fig8_public_validation_summary.fig.yaml |

After all 7 land: full suite pass on CI, coverage maintained, dashboard publishes, paper fig8 atom is no longer aspirational.

## Acceptance criteria

- [ ] `ont-end-reason analyze atlas --json out.json` returns a valid AtlasResult JSON, even on an empty store
- [ ] `ont-end-reason analyze atlas --plot atlas.png` produces a >50 KB PNG
- [ ] `ont-end-reason analyze distribution <registry-known-path>` writes to qc_baseline (verifiable via `get_baseline_statistics()`)
- [ ] `scripts/atlas_backfill.py --dry-run` lists every registry experiment that would be ingested
- [ ] Dashboard at silver-adventure-o322543.pages.github.io shows an Atlas section
- [ ] Paper fig8 atom's `build_recipe` resolves to a real script
- [ ] All 8 CI platform combinations green
- [ ] Coverage ≥ 71% (existing gate)

## Risks

| Risk | Mitigation |
|---|---|
| qc_baseline.py changes break `/qc-advisor` | Only adding new functions, not changing existing API. Test `/qc-advisor` smoke before push. |
| ont-end-reason cross-repo import of `lib.qc_baseline` is fragile | Use the existing lab pattern: `sys.path.insert(0, "~/repos/ont-ecosystem")` at the top of `analyze/atlas.py` with a graceful fallback that degrades to "no internal peers" if ont-ecosystem isn't checked out. Document this in the spec. |
| External peer Parquet schema drift | The atlas reads via the `/ont-public-data` skill's documented columns; if the skill changes schema we'd notice in the integration test. |
| Synthetic fixture doesn't capture real ONT distribution shape | Add a real-data smoke step that runs atlas against the AWG074 MinION run + auto-backfilled lab cohort (5+ experiments) and asserts non-trivial output. |

## Open questions (none blocking)

None — design is complete for implementation. Items deferred per YAGNI:
- Multi-metric anomaly scoring beyond max-|z| (e.g. Mahalanobis distance)
- Interactive filter UI on the dashboard
- Paper fig7's 9-panel breakdown (only the summary fig8 is in scope)

---

## Self-review

**Placeholder scan:** zero TBD/TODO/vague. Every section has concrete file paths, LOC estimates, and API signatures.

**Internal consistency:** the 7-phase plan covers every component listed in the Components section. The data flow diagram matches the component descriptions. The acceptance criteria are all testable via the listed tests.

**Scope check:** larger than typical (~600 LOC + 8 tests across 2 repos), but the user explicitly chose "all three in one spec" and authorized "write, design, plan, implement, test, etc the entire thing". The 7-phase decomposition lets each phase ship in a clean commit, so the spec stays implementable.

**Ambiguity check:** "registry-known experiment" is defined operationally: a path whose absolute resolution matches an experiment in `~/.ont-registry/experiments.yaml`. The auto-population logic falls back to NO writes if the path doesn't match an entry — no guessing.

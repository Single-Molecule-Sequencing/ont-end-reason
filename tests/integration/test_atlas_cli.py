"""CLI tests for `ont-end-reason analyze atlas`.

Covers the CLI surface added in Phase 3 of the atlas spec
(docs/superpowers/specs/2026-05-12-end-reason-atlas-design.md):

  - --help exposes all flags
  - degraded run (empty store, no peers) emits valid JSON
  - --include-internal/--no-include-internal flag controls qc_baseline path
  - --strata accepts comma-separated keys

--plot is tested in Phase 4's figures test.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from click.testing import CliRunner

from ont_end_reason.cli import main

atlas_mod = importlib.import_module("ont_end_reason.analyze.atlas")


def test_atlas_cli_help_exposes_all_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", "atlas", "--help"])
    assert result.exit_code == 0, result.output
    for flag in (
        "--json",
        "--plot",
        "--include-internal",
        "--no-include-internal",
        "--include-external",
        "--no-include-external",
        "--strata",
        "--z-threshold",
    ):
        assert flag in result.output, f"missing CLI flag: {flag}"


def test_atlas_cli_emits_json_on_empty_store(
    tmp_path: Path, monkeypatch
) -> None:
    """Empty store + no peers — still emits a well-formed JSON."""
    # Force atlas to degrade: no qc_baseline, no external peers
    monkeypatch.setattr(atlas_mod, "import_lab_module", lambda *a, **kw: None)
    monkeypatch.setattr(
        atlas_mod, "DEFAULT_EXTERNAL_PEERS_DIR", tmp_path / "no_peers"
    )

    json_out = tmp_path / "atlas.json"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "analyze",
            "atlas",
            "--json",
            str(json_out),
            "--no-include-internal",
            "--no-include-external",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json_out.exists()

    payload = json.loads(json_out.read_text())
    for key in ("n_internal", "n_external", "strata_keys", "per_stratum", "outliers"):
        assert key in payload, f"missing JSON key: {key}"
    assert payload["n_internal"] == 0
    assert payload["n_external"] == 0
    assert "Empty atlas" in payload["interpretation"]


def test_atlas_cli_custom_strata(tmp_path: Path, monkeypatch) -> None:
    """--strata controls the strata_keys field in the JSON output."""
    monkeypatch.setattr(atlas_mod, "import_lab_module", lambda *a, **kw: None)
    monkeypatch.setattr(
        atlas_mod, "DEFAULT_EXTERNAL_PEERS_DIR", tmp_path / "no_peers"
    )
    json_out = tmp_path / "atlas.json"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "analyze",
            "atlas",
            "--json",
            str(json_out),
            "--strata",
            "flowcell_type,chemistry",
            "--no-include-internal",
            "--no-include-external",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(json_out.read_text())
    assert payload["strata_keys"] == ["flowcell_type", "chemistry"]


def test_atlas_cli_z_threshold_passes_through(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """--z-threshold accepts a float and runs without error on degraded input."""
    monkeypatch.setattr(atlas_mod, "import_lab_module", lambda *a, **kw: None)
    monkeypatch.setattr(
        atlas_mod, "DEFAULT_EXTERNAL_PEERS_DIR", tmp_path / "no_peers"
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "analyze",
            "atlas",
            "--z-threshold",
            "3.5",
            "--no-include-internal",
            "--no-include-external",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Atlas:" in result.output

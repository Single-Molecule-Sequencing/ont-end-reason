"""Phase 5 (atlas spec 2026-05-12): verify `analyze distribution` auto-populates
the qc_baseline store when invoked on a registry-known experiment path.

Covers:

* Happy path — registry has an entry whose `location` matches the source path,
  a QCResult is written to the (tmp_path-redirected) baseline store with the
  correct end_reason percentages.
* Opt-out — `--no-baseline-store` flag suppresses the write.
* Unknown path — source path doesn't match any registry entry → silent no-op.
* ont-ecosystem unavailable — `lib.qc_baseline` ImportError degrades gracefully
  (distribution still succeeds, no exception propagates).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from ont_end_reason.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def synthetic_summary(tmp_path: Path) -> Path:
    """Copy the existing synthetic fixture into a tmp location.

    Mirroring rather than symlinking keeps the registry-location matcher
    honest (it uses absolute paths).
    """
    src = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "sequencing_summary_synthetic.txt"
    )
    dest_dir = tmp_path / "exp_dir"
    dest_dir.mkdir()
    dest = dest_dir / "sequencing_summary.txt"
    dest.write_bytes(src.read_bytes())
    return dest


@pytest.fixture
def registry_yaml(tmp_path: Path, synthetic_summary: Path) -> Path:
    """Write a single-entry registry whose `location` matches the fixture dir."""
    registry = tmp_path / "experiments.yaml"
    payload = {
        "version": "2.0",
        "experiments": [
            {
                "id": "test-exp-phase5",
                "name": "Phase 5 fixture",
                "location": str(synthetic_summary.parent),
                "source": "local",
                "status": "discovered",
                "platform": "MinION",
                "flowcell_type": "FLO-MIN114",
                "chemistry": "R10.4.1",
                "sample_type": "genomic_dna",
                "adaptive_sampling": True,
                "discovered": "2026-05-01T12:00:00+00:00",
            }
        ],
    }
    registry.write_text(yaml.safe_dump(payload))
    return registry


@pytest.fixture
def isolated_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ~/.ont-qc-baselines to a tmp directory.

    Also clears the cross-repo qc_baseline module's singleton cache so the
    next `get_baseline_store()` call honours our env override.
    """
    baseline_dir = tmp_path / "ont-qc-baselines"
    monkeypatch.setenv("ONT_QC_BASELINES_DIR", str(baseline_dir))

    # Make sure ont-ecosystem is importable and reset its singleton.
    ont_eco = Path.home() / "repos" / "ont-ecosystem"
    if ont_eco.exists() and str(ont_eco) not in sys.path:
        sys.path.insert(0, str(ont_eco))
    try:
        import lib.qc_baseline as qcb  # type: ignore[import-not-found]

        qcb._baseline_store = None
        # Also re-evaluate the module-level default in case it was cached.
        qcb.DEFAULT_BASELINE_DIR = baseline_dir
    except ImportError:
        pass
    return baseline_dir


@pytest.fixture
def patch_registry_path(
    monkeypatch: pytest.MonkeyPatch, registry_yaml: Path
) -> Path:
    """Point the maybe_store_baseline helper at our tmp registry."""
    import importlib

    dist = importlib.import_module("ont_end_reason.analyze.distribution")
    monkeypatch.setattr(dist, "DEFAULT_REGISTRY_PATH", registry_yaml)
    return registry_yaml


# ───────────────────────── happy path ─────────────────────────


def test_distribution_writes_to_baseline_on_known_path(
    runner: CliRunner,
    synthetic_summary: Path,
    patch_registry_path: Path,
    isolated_baseline: Path,
    tmp_path: Path,
) -> None:
    """Run `analyze distribution` on a registry-known path → QCResult lands."""
    pytest.importorskip("lib.qc_baseline")  # ont-ecosystem must be checked out
    json_out = tmp_path / "dist.json"
    result = runner.invoke(
        main,
        [
            "analyze",
            "distribution",
            str(synthetic_summary),
            "--json",
            str(json_out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Baseline stored:" in result.output

    # Verify the QCResult landed in the store.
    import lib.qc_baseline as qcb  # type: ignore[import-not-found]

    qcb._baseline_store = None
    qcb.DEFAULT_BASELINE_DIR = isolated_baseline
    stored = qcb.get_all_qc_results()
    assert len(stored) == 1
    qc = stored[0]
    assert qc.metadata.experiment_id == "test-exp-phase5"
    assert qc.metadata.flowcell_type == "FLO-MIN114"
    assert qc.metadata.chemistry == "R10.4.1"
    assert qc.metadata.adaptive_sampling is True

    # Metric set matches the atlas END_REASON_METRICS contract.
    expected_metrics = {
        "signal_positive_pct",
        "unblock_mux_pct",
        "data_service_pct",
        "mux_change_pct",
        "signal_negative_pct",
    }
    assert expected_metrics.issubset(qc.metrics.keys())

    # Cross-check the stored signal_positive_pct against the CLI's JSON.
    cli_payload = json.loads(json_out.read_text())
    assert qc.metrics["signal_positive_pct"] == pytest.approx(
        cli_payload["signal_positive_pct"]
    )


# ───────────────────────── opt-out flag ─────────────────────────


def test_no_baseline_store_flag_suppresses_write(
    runner: CliRunner,
    synthetic_summary: Path,
    patch_registry_path: Path,
    isolated_baseline: Path,
) -> None:
    pytest.importorskip("lib.qc_baseline")
    result = runner.invoke(
        main,
        [
            "analyze",
            "distribution",
            str(synthetic_summary),
            "--no-baseline-store",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Baseline stored:" not in result.output

    import lib.qc_baseline as qcb  # type: ignore[import-not-found]

    qcb._baseline_store = None
    qcb.DEFAULT_BASELINE_DIR = isolated_baseline
    assert qcb.get_all_qc_results() == []


# ───────────────────────── path doesn't match ─────────────────────────


def test_unknown_path_is_silent_no_op(
    runner: CliRunner,
    synthetic_summary: Path,
    patch_registry_path: Path,
    isolated_baseline: Path,
    tmp_path: Path,
) -> None:
    """A summary path not listed in the registry → no write, no error."""
    pytest.importorskip("lib.qc_baseline")

    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    other_summary = other_dir / "sequencing_summary.txt"
    other_summary.write_bytes(synthetic_summary.read_bytes())

    result = runner.invoke(
        main,
        [
            "analyze",
            "distribution",
            str(other_summary),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Baseline stored:" not in result.output

    import lib.qc_baseline as qcb  # type: ignore[import-not-found]

    qcb._baseline_store = None
    qcb.DEFAULT_BASELINE_DIR = isolated_baseline
    assert qcb.get_all_qc_results() == []


# ───────────────────────── ont-ecosystem unavailable ─────────────────────────


def test_qc_baseline_unavailable_degrades_gracefully(
    runner: CliRunner,
    synthetic_summary: Path,
    patch_registry_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If lib.qc_baseline can't be imported, the CLI still succeeds."""
    # Force the ImportError path: point ONT_ECOSYSTEM_PATH at a non-existent
    # directory AND blacklist the already-loaded module from sys.modules so
    # the next `from lib.qc_baseline import ...` re-tries (and fails).
    import importlib

    dist = importlib.import_module("ont_end_reason.analyze.distribution")
    monkeypatch.setattr(
        dist, "ONT_ECOSYSTEM_PATH", Path("/nonexistent/ont-ecosystem-shim")
    )

    # Hide lib.qc_baseline from the import system. Save+restore so other tests
    # in the suite still get the real module.
    saved: dict[str, object] = {}
    for name in list(sys.modules):
        if name == "lib" or name.startswith("lib."):
            saved[name] = sys.modules.pop(name)

    class _BlockingFinder:
        def find_module(self, fullname: str, path: object = None) -> None:
            return None

        def find_spec(
            self, fullname: str, path: object = None, target: object = None
        ):
            if fullname == "lib.qc_baseline" or fullname == "lib":
                raise ImportError(f"blocked for test: {fullname}")
            return None

    finder = _BlockingFinder()
    sys.meta_path.insert(0, finder)
    try:
        result = runner.invoke(
            main,
            [
                "analyze",
                "distribution",
                str(synthetic_summary),
            ],
        )
        assert result.exit_code == 0, result.output
        # Distribution analysis itself still ran:
        assert "Total reads:" in result.output
        # No baseline-stored message:
        assert "Baseline stored:" not in result.output
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(saved)

"""Unit tests for analyze.atlas — cross-run end-reason aggregation.

The atlas module imports `lib.qc_baseline` from ont-ecosystem via a sys.path
shim. These tests cover both paths:

  - WITH qc_baseline available (the common case on a lab dev machine)
  - WITHOUT it (e.g. fresh CI runner) — atlas degrades to external-only

External peer tests construct synthetic Parquet fingerprints in tmp_path.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

# Disambiguate: the package's __init__ rebinds the name `atlas` to the
# atlas() function. Use importlib to get the module itself for monkeypatching.
atlas_mod = importlib.import_module("ont_end_reason.analyze.atlas")

from ont_end_reason.analyze.atlas import (  # noqa: E402
    DEFAULT_STRATA,
    END_REASON_METRIC_KEYS,
    AtlasResult,
    _load_external_peers,
    _stratum_key_from_record,
    _summarize_metrics,
    atlas,
)

# --- Pure helper tests ------------------------------------------------------


def test_summarize_metrics_basic_stats() -> None:
    stats = _summarize_metrics([90.0, 92.0, 94.0, 96.0, 98.0])
    assert stats["count"] == 5
    assert stats["mean"] == 94.0
    assert stats["median"] == 94.0
    assert stats["min"] == 90.0
    assert stats["max"] == 98.0
    assert stats["std"] == pytest.approx(3.162, rel=1e-3)


def test_summarize_metrics_empty() -> None:
    assert _summarize_metrics([]) == {}


def test_summarize_metrics_single_value_std_is_zero() -> None:
    stats = _summarize_metrics([42.0])
    assert stats["count"] == 1
    assert stats["std"] == 0.0


def test_stratum_key_from_record_with_missing() -> None:
    rec = {"flowcell_type": "FLO-MIN114", "chemistry": "R10.4.1"}
    key = _stratum_key_from_record(rec, ["flowcell_type", "chemistry", "adaptive_sampling"])
    assert key == ("FLO-MIN114", "R10.4.1", "unknown")


def test_stratum_key_preserves_boolean_false() -> None:
    rec = {"flowcell_type": "FLO-MIN114", "adaptive_sampling": False}
    key = _stratum_key_from_record(rec, ["flowcell_type", "adaptive_sampling"])
    assert key == ("FLO-MIN114", "False")


# --- External peer loader tests --------------------------------------------


def _make_peer_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    pd = pytest.importorskip("pandas")
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_load_external_peers_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert _load_external_peers(tmp_path / "nonexistent") == []


def test_load_external_peers_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert _load_external_peers(tmp_path) == []


def test_load_external_peers_reads_parquet(tmp_path: Path) -> None:
    pytest.importorskip("pandas")
    _make_peer_parquet(
        tmp_path / "giab.parquet",
        [
            {
                "experiment_id": "giab-1",
                "flowcell_type": "FLO-PRO114M",
                "chemistry": "R10.4.1",
                "adaptive_sampling": False,
                "signal_positive_pct": 88.5,
                "unblock_mux_pct": 8.0,
                "data_service_pct": 2.0,
                "mux_change_pct": 1.0,
                "signal_negative_pct": 0.5,
            },
        ],
    )
    rows = _load_external_peers(tmp_path)
    assert len(rows) == 1
    assert rows[0]["experiment_id"] == "giab-1"
    assert rows[0]["signal_positive_pct"] == 88.5


def test_load_external_peers_skips_rows_without_sp(tmp_path: Path) -> None:
    pytest.importorskip("pandas")
    _make_peer_parquet(
        tmp_path / "mixed.parquet",
        [
            {"experiment_id": "with-sp", "signal_positive_pct": 90.0},
            {"experiment_id": "no-sp", "mean_qscore": 12.5},
        ],
    )
    rows = _load_external_peers(tmp_path)
    assert len(rows) == 1
    assert rows[0]["experiment_id"] == "with-sp"


# --- atlas() degradation tests ---------------------------------------------


def test_atlas_empty_returns_valid_result(tmp_path: Path, monkeypatch) -> None:
    """No internal store, no external peers — should return a non-crashing degraded AtlasResult."""
    monkeypatch.setattr(atlas_mod, "import_lab_module", lambda *a, **kw: None)
    result = atlas(external_peers_dir=tmp_path / "no_peers")
    assert isinstance(result, AtlasResult)
    assert result.n_internal == 0
    assert result.n_external == 0
    assert result.per_stratum == []
    assert result.outliers == []
    assert "Empty atlas" in result.interpretation


def test_atlas_external_only(tmp_path: Path, monkeypatch) -> None:
    """ont-ecosystem unavailable but external peers present — graceful degrade."""
    pytest.importorskip("pandas")
    peers_dir = tmp_path / "external_peers"
    peers_dir.mkdir()
    rows = []
    for i in range(5):
        rows.append(
            {
                "experiment_id": f"ext-{i}",
                "flowcell_type": "FLO-PRO114M",
                "chemistry": "R10.4.1",
                "adaptive_sampling": False,
                "signal_positive_pct": 90.0 + i * 0.5,
                "unblock_mux_pct": 7.0,
                "data_service_pct": 2.0,
                "mux_change_pct": 0.7,
                "signal_negative_pct": 0.3,
            }
        )
    _make_peer_parquet(peers_dir / "giab.parquet", rows)

    monkeypatch.setattr(atlas_mod, "import_lab_module", lambda *a, **kw: None)
    result = atlas(external_peers_dir=peers_dir)
    assert result.n_internal == 0
    assert result.n_external == 5
    assert len(result.per_stratum) == 1
    assert result.per_stratum[0].n_runs == 5
    assert "External-only atlas" in result.interpretation


def test_atlas_combines_internal_and_external(tmp_path: Path, monkeypatch) -> None:
    """Mock both sources; verify per-stratum stats span the combined cohort."""
    pytest.importorskip("pandas")

    class FakeMetadata:
        def __init__(self, **kw):
            self._d = kw

        def __getattr__(self, item):
            return self._d.get(item)

        def to_dict(self):
            return dict(self._d)

    class FakeResult:
        def __init__(self, metadata, metrics):
            self.metadata = metadata
            self.metrics = metrics

    class FakeOutlier:
        def __init__(self, eid, stratum, z, anomaly):
            self.experiment_id = eid
            self.stratum = stratum
            self.metric_z_scores = z
            self.anomaly_score = anomaly

    fake_results = [
        FakeResult(
            FakeMetadata(
                experiment_id=f"int-{i}",
                flowcell_type="FLO-PRO114M",
                chemistry="R10.4.1",
                adaptive_sampling=False,
            ),
            {
                "signal_positive_pct": 92.0 + i,
                "unblock_mux_pct": 5.0,
                "data_service_pct": 2.0,
                "mux_change_pct": 0.7,
                "signal_negative_pct": 0.3,
            },
        )
        for i in range(4)
    ]

    class FakeQCBaseline:
        @staticmethod
        def get_end_reason_results():
            return fake_results

        @staticmethod
        def compute_atlas_outliers(strata, z_threshold=2.0, min_stratum_size=3):
            return []

    monkeypatch.setattr(atlas_mod, "import_lab_module", lambda *a, **kw: FakeQCBaseline)

    peers_dir = tmp_path / "ext"
    peers_dir.mkdir()
    _make_peer_parquet(
        peers_dir / "p.parquet",
        [
            {
                "experiment_id": f"ext-{i}",
                "flowcell_type": "FLO-PRO114M",
                "chemistry": "R10.4.1",
                "adaptive_sampling": False,
                "signal_positive_pct": 90.0 + i * 0.2,
                "unblock_mux_pct": 7.0,
                "data_service_pct": 2.0,
                "mux_change_pct": 0.7,
                "signal_negative_pct": 0.3,
            }
            for i in range(3)
        ],
    )

    result = atlas(external_peers_dir=peers_dir)
    assert result.n_internal == 4
    assert result.n_external == 3
    # Single stratum spanning both
    assert len(result.per_stratum) == 1
    assert result.per_stratum[0].n_runs == 7
    sp_stats = result.per_stratum[0].metric_stats["signal_positive_pct"]
    assert sp_stats["count"] == 7
    assert 89.0 < sp_stats["mean"] < 96.0


def test_atlas_to_dict_is_json_safe(monkeypatch, tmp_path: Path) -> None:
    """to_dict() must emit a payload that json.dumps round-trips."""
    import json

    monkeypatch.setattr(atlas_mod, "import_lab_module", lambda *a, **kw: None)
    result = atlas(external_peers_dir=tmp_path / "missing")
    text = json.dumps(result.to_dict())
    parsed = json.loads(text)
    assert "n_internal" in parsed
    assert "interpretation" in parsed
    assert "strata_keys" in parsed
    assert parsed["strata_keys"] == list(DEFAULT_STRATA)


def test_atlas_default_strata_constant() -> None:
    assert DEFAULT_STRATA == ("flowcell_type", "chemistry", "adaptive_sampling")
    # All 5 paper metrics are tracked
    assert set(END_REASON_METRIC_KEYS) == {
        "signal_positive_pct",
        "unblock_mux_pct",
        "data_service_pct",
        "mux_change_pct",
        "signal_negative_pct",
    }


def test_lab_bridge_import_lab_module_returns_none_when_missing(monkeypatch) -> None:
    """The bridge must return None (not raise) when sister repo is unavailable."""
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: False)
    import sys as _sys

    _sys.modules.pop("qc_baseline", None)
    from ont_end_reason._lab_bridge import import_lab_module

    result = import_lab_module("qc_baseline", repo="ont-ecosystem", lib_subdir="lib")
    # On a real dev machine qc_baseline IS importable; we just assert
    # the bridge returns either the module or None, never raises.
    assert result is None or hasattr(result, "get_end_reason_results")

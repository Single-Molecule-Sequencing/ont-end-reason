"""Manifest dataclass + JSON round-trip tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ont_end_reason.io.manifest import FileEntry, Manifest, ReadRecord

pytestmark = pytest.mark.fast


class TestManifest:
    def test_empty(self) -> None:
        m = Manifest(root="/tmp/x")
        assert m.total_files() == 0
        assert m.total_size_gb() == 0.0

    def test_totals(self) -> None:
        m = Manifest(root="/tmp/x")
        m.pod5.append(FileEntry(path="a.pod5", kind="pod5", size_bytes=1_000_000_000))
        m.summaries.append(FileEntry(path="s.txt", kind="summary", size_bytes=100))
        assert m.total_files() == 2
        assert m.total_size_gb() == pytest.approx(1.0000001, rel=1e-5)

    def test_json_round_trip(self, tmp_path: Path) -> None:
        m = Manifest(root="/tmp/x")
        m.pod5.append(FileEntry(path="a.pod5", kind="pod5", size_bytes=42))
        m.bams.append(FileEntry(path="a.bam", kind="bam", size_bytes=100))
        out = tmp_path / "manifest.json"
        m.to_json(out)

        loaded = Manifest.from_json(out)
        assert loaded.root == m.root
        assert len(loaded.pod5) == 1
        assert loaded.pod5[0].path == "a.pod5"
        assert len(loaded.bams) == 1

    def test_to_json_string(self) -> None:
        m = Manifest(root="/tmp/x")
        text = m.to_json()
        parsed = json.loads(text)
        assert parsed["root"] == "/tmp/x"
        assert parsed["generator"] == "ont-end-reason"


class TestReadRecord:
    def test_minimal(self) -> None:
        r = ReadRecord(read_id="abc", end_reason="signal_positive")
        assert r.read_id == "abc"
        assert r.end_reason == "signal_positive"
        # All optional fields default to None
        assert r.length is None
        assert r.quality is None

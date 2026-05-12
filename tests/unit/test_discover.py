"""Discovery walk tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ont_end_reason.errors import IOError as OntIOError
from ont_end_reason.io.discover import discover

pytestmark = pytest.mark.fast


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


class TestDiscover:
    def test_empty_dir(self, tmp_path: Path) -> None:
        m = discover(tmp_path)
        assert m.total_files() == 0

    def test_finds_pod5(self, tmp_path: Path) -> None:
        _touch(tmp_path / "run.pod5")
        m = discover(tmp_path)
        assert len(m.pod5) == 1
        assert m.pod5[0].path.endswith("run.pod5")

    def test_finds_all_kinds(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.pod5")
        _touch(tmp_path / "b.fast5")
        _touch(tmp_path / "sequencing_summary.txt")
        _touch(tmp_path / "c.bam")
        _touch(tmp_path / "d.fastq.gz")
        m = discover(tmp_path)
        assert len(m.pod5) == 1
        assert len(m.fast5) == 1
        assert len(m.summaries) == 1
        assert len(m.bams) == 1
        assert len(m.fastqs) == 1

    def test_recursive(self, tmp_path: Path) -> None:
        _touch(tmp_path / "deep" / "deeper" / "a.pod5")
        m = discover(tmp_path, recursive=True)
        assert len(m.pod5) == 1

    def test_non_recursive(self, tmp_path: Path) -> None:
        _touch(tmp_path / "deep" / "a.pod5")
        _touch(tmp_path / "shallow.pod5")
        m = discover(tmp_path, recursive=False)
        assert len(m.pod5) == 1  # only the shallow one
        assert m.pod5[0].path.endswith("shallow.pod5")

    def test_missing_root_raises(self) -> None:
        with pytest.raises(OntIOError, match="does not exist"):
            discover("/does/not/exist/here")

    def test_file_root_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.pod5"
        _touch(f)
        with pytest.raises(OntIOError, match="not a directory"):
            discover(f)

    def test_ignores_non_ont_files(self, tmp_path: Path) -> None:
        _touch(tmp_path / "readme.md")
        _touch(tmp_path / "config.yaml")
        m = discover(tmp_path)
        assert m.total_files() == 0

    def test_summary_with_suffix(self, tmp_path: Path) -> None:
        # Real-world runs sometimes name the file `sequencing_summary_<runid>.txt`
        _touch(tmp_path / "sequencing_summary_abc123.txt")
        m = discover(tmp_path)
        assert len(m.summaries) == 1

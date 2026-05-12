"""Manifest dataclass — serializable inventory of a sequencing-run directory.

A Manifest is the output of `discover()` and the input to most downstream
analyses. It is JSON-serialisable so external tools can consume it without
needing to import this package.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ReadRecord:
    """One read's metadata after extraction from a POD5/Fast5/summary file."""

    read_id: str
    end_reason: str
    end_reason_short: str | None = None
    length: int | None = None
    quality: float | None = None
    channel: int | None = None
    mux: int | None = None
    start_time: float | None = None
    duration: float | None = None
    source_file: str | None = None
    source_format: str | None = None


@dataclass
class FileEntry:
    """One file discovered under the scan root."""

    path: str
    kind: str  # "pod5" | "fast5" | "summary" | "bam" | "fastq"
    size_bytes: int
    read_count: int | None = None  # None when not cheap to compute


@dataclass
class Manifest:
    """Top-level result of `discover()`.

    Holds inventories of POD5, Fast5, sequencing_summary, BAM, and FASTQ
    files found under the scan root, plus generation metadata.
    """

    root: str
    generated_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    generator: str = "ont-end-reason"
    pod5: list[FileEntry] = field(default_factory=list)
    fast5: list[FileEntry] = field(default_factory=list)
    summaries: list[FileEntry] = field(default_factory=list)
    bams: list[FileEntry] = field(default_factory=list)
    fastqs: list[FileEntry] = field(default_factory=list)

    def total_files(self) -> int:
        return (
            len(self.pod5)
            + len(self.fast5)
            + len(self.summaries)
            + len(self.bams)
            + len(self.fastqs)
        )

    def total_size_gb(self) -> float:
        all_entries = self.pod5 + self.fast5 + self.summaries + self.bams + self.fastqs
        return sum(e.size_bytes for e in all_entries) / 1_000_000_000

    def to_json(self, path: str | Path | None = None) -> str:
        """Serialise to JSON. If path is given, also writes to disk."""
        data: dict[str, Any] = asdict(self)
        text = json.dumps(data, indent=2)
        if path is not None:
            Path(path).write_text(text)
        return text

    @classmethod
    def from_json(cls, path: str | Path) -> Manifest:
        """Round-trip from a JSON file written by `to_json`."""
        data = json.loads(Path(path).read_text())

        def to_files(entries: list[dict[str, Any]]) -> list[FileEntry]:
            return [FileEntry(**e) for e in entries]

        return cls(
            root=data["root"],
            generated_at=data["generated_at"],
            generator=data.get("generator", "unknown"),
            pod5=to_files(data.get("pod5", [])),
            fast5=to_files(data.get("fast5", [])),
            summaries=to_files(data.get("summaries", [])),
            bams=to_files(data.get("bams", [])),
            fastqs=to_files(data.get("fastqs", [])),
        )

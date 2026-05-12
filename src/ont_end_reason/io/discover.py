"""Recursive filesystem walk → Manifest of POD5/Fast5/summary/BAM/FASTQ files.

External users invoke this through `ont-end-reason discover <path>`; library
users call `discover(path)` directly. Symlinks are not followed by default
(common WSL `/mnt/d/` setup creates cycles via Junctions to user dirs).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import structlog

from ..errors import IOError as OntIOError
from .manifest import FileEntry, Manifest

log = structlog.get_logger(__name__)

_POD5_EXT: Final[set[str]] = {".pod5"}
_FAST5_EXT: Final[set[str]] = {".fast5"}
_BAM_EXT: Final[set[str]] = {".bam"}
_FASTQ_EXT: Final[set[str]] = {".fastq", ".fq", ".fastq.gz", ".fq.gz"}


def _is_summary(name: str) -> bool:
    """sequencing_summary*.txt is the ONT convention."""
    return name.startswith("sequencing_summary") and name.endswith(".txt")


def _fastq_match(name: str) -> bool:
    lname = name.lower()
    return any(lname.endswith(ext) for ext in _FASTQ_EXT)


def discover(
    root: str | Path,
    *,
    recursive: bool = True,
    follow_symlinks: bool = False,
) -> Manifest:
    """Walk `root` and return a Manifest of every ONT-relevant file found.

    Parameters
    ----------
    root : path-like
        Directory to scan. May be a sequencing-run output, a project folder,
        or anything else with ONT files nested under it.
    recursive : bool
        Whether to recurse into subdirectories. Default True.
    follow_symlinks : bool
        Whether to follow symlinks during the walk. Default False (safer on
        WSL `/mnt/d/` setups where Windows Junctions can create cycles).

    Raises
    ------
    OntIOError
        If `root` does not exist or is not a directory.
    """
    root_path = Path(root)
    if not root_path.exists():
        raise OntIOError(f"discover root does not exist: {root_path}")
    if not root_path.is_dir():
        raise OntIOError(f"discover root is not a directory: {root_path}")

    manifest = Manifest(root=str(root_path.resolve()))

    iterator = root_path.rglob("*") if recursive else root_path.glob("*")
    n_scanned = 0
    for entry in iterator:
        n_scanned += 1
        if entry.is_symlink() and not follow_symlinks:
            continue
        if not entry.is_file():
            continue

        try:
            size = entry.stat().st_size
        except OSError as exc:
            log.warning("stat failed", path=str(entry), error=str(exc))
            continue

        name = entry.name
        suffix = entry.suffix.lower()
        path_str = str(entry)
        file_entry = FileEntry(path=path_str, kind="", size_bytes=size)

        if suffix in _POD5_EXT:
            file_entry.kind = "pod5"
            manifest.pod5.append(file_entry)
        elif suffix in _FAST5_EXT:
            file_entry.kind = "fast5"
            manifest.fast5.append(file_entry)
        elif _is_summary(name):
            file_entry.kind = "summary"
            manifest.summaries.append(file_entry)
        elif suffix in _BAM_EXT:
            file_entry.kind = "bam"
            manifest.bams.append(file_entry)
        elif _fastq_match(name):
            file_entry.kind = "fastq"
            manifest.fastqs.append(file_entry)

    log.info(
        "discover complete",
        root=str(root_path),
        pod5=len(manifest.pod5),
        fast5=len(manifest.fast5),
        summaries=len(manifest.summaries),
        bams=len(manifest.bams),
        fastqs=len(manifest.fastqs),
        scanned=n_scanned,
    )
    return manifest

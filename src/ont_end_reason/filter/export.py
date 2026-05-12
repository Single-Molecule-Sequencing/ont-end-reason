"""Export a BAM (typically filtered) to FASTQ for NanoPack tools.

Behaviour matches `End_Reason_Manuscript/pipeline/bin/export_filtered_fastq.py`
at commit b47166a.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path

import structlog

from ..errors import IOError as OntIOError

log = structlog.get_logger(__name__)


@dataclass
class ExportResult:
    """Outcome of `export_fastq()`."""

    reads_written: int
    bytes_written: int
    output_path: str


def export_fastq(
    bam_path: str | Path,
    fastq_path: str | Path,
    *,
    compress: bool = False,
) -> ExportResult:
    """Write the sequences and qualities from `bam_path` to FASTQ.

    Parameters
    ----------
    bam_path : path-like
        Input BAM (filtered or unfiltered; secondary/supplementary alignments
        are skipped).
    fastq_path : path-like
        Destination FASTQ. Add `.gz` and pass `compress=True` to gzip on the fly.
    compress : bool
        Wrap the output writer in gzip. Default False.
    """
    try:
        import pysam  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OntIOError("export_fastq requires pysam") from exc

    bam_path = Path(bam_path)
    fastq_path = Path(fastq_path)
    fastq_path.parent.mkdir(parents=True, exist_ok=True)

    n_written = 0
    open_fn = gzip.open if compress else open  # type: ignore[assignment]

    try:
        with pysam.AlignmentFile(str(bam_path), "rb", check_sq=False) as bam_in:
            with open_fn(str(fastq_path), "wt") as fh:  # type: ignore[arg-type]
                for read in bam_in.fetch(until_eof=True):
                    if read.is_secondary or read.is_supplementary:
                        continue
                    if read.query_sequence is None:
                        continue
                    qual = read.qual or "!" * len(read.query_sequence)
                    fh.write(f"@{read.query_name}\n{read.query_sequence}\n+\n{qual}\n")
                    n_written += 1
    except OSError as exc:
        raise OntIOError(f"BAM/FASTQ I/O failed: {exc}") from exc

    size = fastq_path.stat().st_size
    log.info("export complete", reads=n_written, bytes=size, path=str(fastq_path))
    return ExportResult(
        reads_written=n_written, bytes_written=size, output_path=str(fastq_path)
    )

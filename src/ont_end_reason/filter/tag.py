"""Tag a BAM with end_reason from sequencing_summary.txt.

The tag (default `ER`, 2-letter SAM tag with Z type) gets the short code
(`SP`/`UMC`/...) — that matches the lab's existing convention and what the
paper's filtering claim atoms expect.

Behaviour ports the canonical algorithm from
`End_Reason_Manuscript/pipeline/bin/join_end_reason.py` at commit b47166a:
  1. Stream sequencing_summary in chunks → dict[read_id -> end_reason short]
  2. Stream input BAM read-by-read, look up by read_id, set tag, write out
  3. Reads missing from the summary keep the tag absent (caller's choice)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import structlog

from ..codes import CODES, to_short
from ..errors import IOError as OntIOError

log = structlog.get_logger(__name__)


@dataclass
class TagResult:
    """Outcome of `tag_bam()`. Holds counts for the CLI to display."""

    input_reads: int
    tagged_reads: int
    missing_reads: int  # reads in BAM but not in summary
    tag_name: str


def _load_summary_map(summary_path: Path) -> dict[str, str]:
    """Build `read_id → end_reason_short` from sequencing_summary.txt.

    Uses pandas chunked TSV reader so PromethION-scale summaries don't OOM.
    """
    import pandas as pd

    out: dict[str, str] = {}
    try:
        for chunk in pd.read_csv(
            summary_path,
            sep="\t",
            usecols=["read_id", "end_reason"],
            chunksize=200_000,
            low_memory=False,
        ):
            for row in chunk.itertuples(index=False):
                er = str(row.end_reason).strip().lower()
                # Coerce to short. Unknown values stay as raw upper-case for visibility.
                short = CODES.get(er) or (er.upper() if er else "UNK")
                out[str(row.read_id)] = short
    except (OSError, ValueError) as exc:
        raise OntIOError(f"Failed to read summary {summary_path}: {exc}") from exc
    return out


def tag_bam(
    summary_path: str | Path,
    bam_path: str | Path,
    output_path: str | Path,
    *,
    tag_name: str = "ER",
) -> TagResult:
    """Tag every read in `bam_path` with the end_reason short code from `summary_path`.

    Parameters
    ----------
    summary_path : path-like
        Path to sequencing_summary.txt.
    bam_path : path-like
        Path to the input BAM (sorted or unsorted, indexed not required).
    output_path : path-like
        Path to the output tagged BAM. Parent dir is created if missing.
    tag_name : str
        Two-letter SAM tag for the end_reason short code. Default "ER".

    Returns
    -------
    TagResult
        Summary counts.

    Raises
    ------
    OntIOError
        On any I/O failure (BAM not found, summary unreadable, etc.).
    """
    try:
        import pysam  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OntIOError("tag_bam requires pysam") from exc

    if len(tag_name) != 2:
        raise ValueError(f"tag_name must be 2 chars, got {tag_name!r}")

    summary_path = Path(summary_path)
    bam_path = Path(bam_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("loading summary", path=str(summary_path))
    er_map = _load_summary_map(summary_path)
    log.info("summary loaded", reads=len(er_map))

    n_input = 0
    n_tagged = 0
    n_missing = 0

    try:
        with (
            pysam.AlignmentFile(str(bam_path), "rb", check_sq=False) as bam_in,
            pysam.AlignmentFile(str(output_path), "wb", template=bam_in) as bam_out,
        ):
            for read in bam_in.fetch(until_eof=True):
                n_input += 1
                read_id = read.query_name
                er_short = er_map.get(read_id)
                if er_short is not None:
                    read.set_tag(tag_name, er_short, value_type="Z")
                    n_tagged += 1
                else:
                    n_missing += 1
                bam_out.write(read)
    except OSError as exc:
        raise OntIOError(f"BAM I/O failed: {exc}") from exc

    log.info(
        "tag complete",
        input_reads=n_input,
        tagged=n_tagged,
        missing=n_missing,
    )
    return TagResult(
        input_reads=n_input,
        tagged_reads=n_tagged,
        missing_reads=n_missing,
        tag_name=tag_name,
    )


def supported_end_reasons() -> Iterable[str]:
    """Convenience accessor for CLI help text."""
    return sorted(CODES.values())


_ = to_short  # keep imported (used by callers in higher-level CLI)

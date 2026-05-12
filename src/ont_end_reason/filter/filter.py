"""Filter a tagged BAM by end_reason tag.

Behaviour matches `End_Reason_Manuscript/pipeline/bin/filter_reads.py` at
commit b47166a. The original supports parallel sharded processing for
multi-million-read BAMs; this v0.1 wrapper ships a sequential implementation
that delegates I/O threading to pysam. Parallel sharding is on the v0.2
roadmap (see issue tracker).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from ..codes import parse_keep_list
from ..errors import IOError as OntIOError

log = structlog.get_logger(__name__)


@dataclass
class FilterResult:
    """Outcome of `filter_bam()`."""

    input_reads: int
    kept_reads: int
    dropped_reads: int
    keep_codes: list[str]
    tag_name: str


def filter_bam(
    bam_path: str | Path,
    output_path: str | Path,
    keep: str | set[str],
    *,
    tag_name: str = "ER",
    threads: int = 1,
) -> FilterResult:
    """Keep reads whose `tag_name` tag value is in `keep`.

    Parameters
    ----------
    bam_path : path-like
        Path to the tagged input BAM (use `tag_bam()` first if not tagged).
    output_path : path-like
        Destination for the filtered BAM.
    keep : str or set[str]
        Either a comma-separated spec (e.g. "SP,UMC") or a set of short codes.
        Full names are also accepted ("signal_positive" is normalised to "SP").
    tag_name : str
        Two-letter SAM tag holding the end_reason short code. Default "ER".
    threads : int
        Number of I/O threads to pass to pysam. Default 1. Parallel shard
        processing is on the v0.2 roadmap.

    Returns
    -------
    FilterResult
        Summary counts and the resolved keep-list.
    """
    try:
        import pysam  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OntIOError("filter_bam requires pysam") from exc

    if isinstance(keep, str):
        keep_set = parse_keep_list(keep)
    else:
        keep_set = set(keep)
    if not keep_set:
        raise ValueError("keep is empty; nothing to retain")

    bam_path = Path(bam_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_input = 0
    n_kept = 0

    log.info("filter start", keep=sorted(keep_set), tag=tag_name, threads=threads)
    try:
        with pysam.AlignmentFile(
            str(bam_path), "rb", check_sq=False, threads=threads
        ) as bam_in:
            with pysam.AlignmentFile(
                str(output_path), "wb", template=bam_in, threads=threads
            ) as bam_out:
                for read in bam_in.fetch(until_eof=True):
                    n_input += 1
                    try:
                        er_value = read.get_tag(tag_name)
                    except KeyError:
                        # Read has no tag — drop by default. Use a separate
                        # `--keep-untagged` flag (future) to override.
                        continue
                    if str(er_value) in keep_set:
                        bam_out.write(read)
                        n_kept += 1
    except OSError as exc:
        raise OntIOError(f"BAM I/O failed: {exc}") from exc

    log.info("filter complete", input=n_input, kept=n_kept, dropped=n_input - n_kept)
    return FilterResult(
        input_reads=n_input,
        kept_reads=n_kept,
        dropped_reads=n_input - n_kept,
        keep_codes=sorted(keep_set),
        tag_name=tag_name,
    )

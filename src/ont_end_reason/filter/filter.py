"""Filter a tagged BAM by end_reason tag.

Behaviour matches `End_Reason_Manuscript/pipeline/bin/filter_reads.py` at
commit b47166a.

Two execution modes share the public `filter_bam()` entry point:

  - **threads <= 1** (default): sequential, with pysam I/O thread plumbing.
    Best for small/medium BAMs where worker setup overhead dominates.
  - **threads >= 2**: parallel sharded. Scans the input once to record
    BGZF virtual-offset boundaries at evenly-spaced read counts, then
    dispatches N workers via `ProcessPoolExecutor`. Each worker `seek()`s
    directly to its slice (O(1) positioning rather than the original
    O(N²/2) linear-skip), filters, and writes a per-shard temp BAM.
    Shards are concatenated to the final output via `pysam.cat`, which
    splices BGZF blocks without re-decompressing.

The parallel path is on by default whenever `threads >= 2` and the input
is large enough to be worth sharding (`MIN_READS_FOR_PARALLEL`). Below
that threshold the sequential path runs even with `threads >= 2`.

The BGZF shard partition itself lives in the lab-canonical
`lib.bam_shard` (ont-ecosystem) — imported here via `_lab_bridge`.
When the sister repo isn't on disk the inline fallback in `_lab_bridge`
keeps this module operational.
"""

from __future__ import annotations

import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import structlog

from .._lab_bridge import import_lab_module
from ..codes import parse_keep_list
from ..errors import IOError as OntIOError

log = structlog.get_logger(__name__)

_bam_shard = import_lab_module("bam_shard", repo="ont-ecosystem", lib_subdir="lib")

MIN_READS_FOR_PARALLEL = 50_000
DEFAULT_SHARD_SIZE = 100_000


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
    shard_size: int = DEFAULT_SHARD_SIZE,
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
        Worker count. `1` (default) runs sequential with pysam I/O threads.
        `>=2` engages the parallel sharded path on inputs over
        `MIN_READS_FOR_PARALLEL`.
    shard_size : int
        Target reads per shard when running parallel. Default 100k.

    Returns
    -------
    FilterResult
        Summary counts and the resolved keep-list.
    """
    keep_set = parse_keep_list(keep) if isinstance(keep, str) else set(keep)
    if not keep_set:
        raise ValueError("keep is empty; nothing to retain")

    bam_path = Path(bam_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if threads >= 2:
        if _bam_size_exceeds(bam_path, MIN_READS_FOR_PARALLEL):
            return _filter_parallel(
                bam_path,
                output_path,
                keep_set,
                tag_name=tag_name,
                threads=threads,
                shard_size=shard_size,
            )
        log.info(
            "small input — falling back to sequential",
            threads=threads,
            min_for_parallel=MIN_READS_FOR_PARALLEL,
        )

    return _filter_sequential(
        bam_path,
        output_path,
        keep_set,
        tag_name=tag_name,
        threads=max(1, threads),
    )


def _filter_sequential(
    bam_path: Path,
    output_path: Path,
    keep_set: set[str],
    *,
    tag_name: str,
    threads: int,
) -> FilterResult:
    from ._pysam_guard import require_pysam

    pysam = require_pysam()

    n_input = 0
    n_kept = 0

    log.info(
        "filter start", keep=sorted(keep_set), tag=tag_name, threads=threads, mode="sequential"
    )
    try:
        with (
            pysam.AlignmentFile(str(bam_path), "rb", check_sq=False, threads=threads) as bam_in,
            pysam.AlignmentFile(
                str(output_path), "wb", template=bam_in, threads=threads
            ) as bam_out,
        ):
            for read in bam_in.fetch(until_eof=True):
                n_input += 1
                try:
                    er_value = read.get_tag(tag_name)
                except KeyError:
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


def _bam_size_exceeds(bam_path: Path, min_reads: int) -> bool:
    """Cheap heuristic — assume ~200 bytes/read in compressed BAM."""
    try:
        return bam_path.stat().st_size > min_reads * 200
    except OSError:
        return False


def _worker_filter_shard(
    args: tuple[str, str, frozenset[str], str, int, int | None],
) -> tuple[str, int, int]:
    """Process a single shard. Module-level so the process pool can pickle it.

    Returns (shard_output_path, n_input, n_kept).
    """
    bam_path, out_path, keep_set, tag_name, start_voff, end_voff = args
    import pysam  # type: ignore[import-untyped]

    n_input = 0
    n_kept = 0
    bam_in = pysam.AlignmentFile(bam_path, "rb", check_sq=False)
    bam_in.seek(start_voff)
    try:
        bam_out = pysam.AlignmentFile(out_path, "wb", template=bam_in)
        for read in bam_in:
            # tell() reports the NEXT read's voff; the next worker's
            # seek(end_voff) lands on that record, so we stop here.
            if end_voff is not None and bam_in.tell() > end_voff:
                break
            n_input += 1
            try:
                er_value = read.get_tag(tag_name)
            except KeyError:
                continue
            if str(er_value) in keep_set:
                bam_out.write(read)
                n_kept += 1
        bam_out.close()
    finally:
        bam_in.close()
    return out_path, n_input, n_kept


def _filter_parallel(
    bam_path: Path,
    output_path: Path,
    keep_set: set[str],
    *,
    tag_name: str,
    threads: int,
    shard_size: int,
) -> FilterResult:
    from ._pysam_guard import require_pysam

    pysam = require_pysam()

    if _bam_shard is None:
        log.info("lib.bam_shard unavailable — falling back to sequential")
        return _filter_sequential(
            bam_path, output_path, keep_set, tag_name=tag_name, threads=threads
        )

    # Cap shard count generously — the scan stops once we hit the cap
    # OR run out of reads, whichever comes first. shard_size controls
    # the target reads-per-shard directly; no file-size estimation
    # (which mis-predicted by 30× on highly-compressed inputs).
    max_shards = max(2, threads * 4)
    boundaries, total_reads = _bam_shard.scan_with_count(
        bam_path, n_shards=max_shards, target_reads_per_shard=shard_size
    )
    log.info(
        "filter start",
        keep=sorted(keep_set),
        tag=tag_name,
        threads=threads,
        mode="parallel",
        shards=len(boundaries),
        shard_size=shard_size,
        total_reads=total_reads,
    )

    if len(boundaries) <= 1 or total_reads < MIN_READS_FOR_PARALLEL:
        return _filter_sequential(
            bam_path, output_path, keep_set, tag_name=tag_name, threads=threads
        )

    keep_frozen = frozenset(keep_set)
    with tempfile.TemporaryDirectory(prefix="ont_filter_") as tmp:
        tmp_path = Path(tmp)
        shard_args: list[tuple[str, str, frozenset[str], str, int, int | None]] = []
        for i, boundary in enumerate(boundaries):
            shard_out = tmp_path / f"shard_{i:04d}.bam"
            shard_args.append(
                (
                    str(bam_path),
                    str(shard_out),
                    keep_frozen,
                    tag_name,
                    boundary.start_voff,
                    boundary.end_voff,
                )
            )

        try:
            with ProcessPoolExecutor(max_workers=threads) as pool:
                results = list(pool.map(_worker_filter_shard, shard_args))
        except OSError as exc:
            raise OntIOError(f"parallel shard processing failed: {exc}") from exc

        n_input = sum(r[1] for r in results)
        n_kept = sum(r[2] for r in results)
        shard_files = [r[0] for r in results if Path(r[0]).exists()]

        try:
            pysam.cat("-o", str(output_path), *shard_files)
        except (pysam.SamtoolsError, OSError) as exc:
            raise OntIOError(f"BAM concatenation failed: {exc}") from exc

    log.info("filter complete", input=n_input, kept=n_kept, dropped=n_input - n_kept)
    return FilterResult(
        input_reads=n_input,
        kept_reads=n_kept,
        dropped_reads=n_input - n_kept,
        keep_codes=sorted(keep_set),
        tag_name=tag_name,
    )

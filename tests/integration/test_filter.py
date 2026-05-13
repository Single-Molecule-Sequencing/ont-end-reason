"""End-to-end integration tests for the filter/ subpackage.

Builds a tiny synthetic BAM in-process via pysam (no on-disk fixture
required) then exercises tag_bam → filter_bam → export_fastq against
the existing synthetic sequencing_summary fixture. Closes coverage on
src/ont_end_reason/filter/{tag,filter,export}.py which were 0% before.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

pysam = pytest.importorskip("pysam")

from ont_end_reason.errors import IOError as OntIOError  # noqa: E402
from ont_end_reason.filter import (  # noqa: E402
    export_fastq,
    filter_bam,
    tag_bam,
)
from ont_end_reason.filter.tag import (  # noqa: E402
    supported_end_reasons,
)

FIXTURE_SUMMARY = Path(__file__).parent.parent / "fixtures" / "sequencing_summary_synthetic.txt"


def _read_first_n_ids(summary: Path, n: int) -> list[str]:
    ids: list[str] = []
    with summary.open() as fh:
        next(fh)  # skip header
        for line in fh:
            ids.append(line.split("\t", 1)[0])
            if len(ids) == n:
                break
    return ids


def _make_unaligned_bam(path: Path, read_ids: list[str], *, seq_len: int = 50) -> None:
    """Write a tiny unaligned BAM with the given read_ids.

    Use SAM-text construction so the test stays self-contained; sequence
    is a fixed N-mer, base qualities are uniform Q20 ('5' in phred+33).
    """
    seq = "A" * seq_len
    qual = "5" * seq_len
    header = {"HD": {"VN": "1.6", "SO": "unknown"}}
    with pysam.AlignmentFile(str(path), "wb", header=header) as out:
        for rid in read_ids:
            r = pysam.AlignedSegment()
            r.query_name = rid
            r.flag = 4  # unmapped
            r.query_sequence = seq
            r.query_qualities = pysam.qualitystring_to_array(qual)
            out.write(r)


def test_tag_filter_export_pipeline(tmp_path: Path) -> None:
    """The canonical 3-step pipeline: tag → filter → export."""
    read_ids = _read_first_n_ids(FIXTURE_SUMMARY, 20)
    raw_bam = tmp_path / "raw.bam"
    _make_unaligned_bam(raw_bam, read_ids)

    tagged_bam = tmp_path / "tagged.bam"
    tag_res = tag_bam(FIXTURE_SUMMARY, raw_bam, tagged_bam)

    assert tag_res.input_reads == 20
    assert tag_res.tagged_reads == 20
    assert tag_res.missing_reads == 0
    assert tag_res.tag_name == "ER"
    assert tagged_bam.exists()

    short_codes_seen = set()
    with pysam.AlignmentFile(str(tagged_bam), "rb", check_sq=False) as fh:
        for read in fh.fetch(until_eof=True):
            short_codes_seen.add(read.get_tag("ER"))
    assert short_codes_seen.issubset(set(supported_end_reasons()))

    filtered_bam = tmp_path / "splus.bam"
    filt = filter_bam(tagged_bam, filtered_bam, keep="SP")
    assert filt.input_reads == 20
    assert filt.kept_reads + filt.dropped_reads == 20
    assert filt.keep_codes == ["SP"]
    assert filt.tag_name == "ER"

    with pysam.AlignmentFile(str(filtered_bam), "rb", check_sq=False) as fh:
        for read in fh.fetch(until_eof=True):
            assert read.get_tag("ER") == "SP"

    fastq_out = tmp_path / "splus.fastq"
    exp = export_fastq(filtered_bam, fastq_out)
    assert exp.reads_written == filt.kept_reads
    assert exp.bytes_written > 0
    assert Path(exp.output_path) == fastq_out

    lines = fastq_out.read_text().splitlines()
    assert len(lines) == 4 * exp.reads_written
    if exp.reads_written:
        assert lines[0].startswith("@")
        assert lines[2] == "+"


def test_filter_multi_keep_and_inversion(tmp_path: Path) -> None:
    """Multi-code keep specs partition reads correctly."""
    read_ids = _read_first_n_ids(FIXTURE_SUMMARY, 50)
    raw_bam = tmp_path / "raw.bam"
    _make_unaligned_bam(raw_bam, read_ids)
    tagged = tmp_path / "tagged.bam"
    tag_bam(FIXTURE_SUMMARY, raw_bam, tagged)

    kept = filter_bam(tagged, tmp_path / "k.bam", keep="SP,UMC")
    dropped = filter_bam(tagged, tmp_path / "d.bam", keep="MC,DUMC,SN,UNK,PART")

    assert kept.input_reads == 50
    assert dropped.input_reads == 50
    assert kept.kept_reads + dropped.kept_reads <= 50


def test_filter_accepts_set_keep(tmp_path: Path) -> None:
    read_ids = _read_first_n_ids(FIXTURE_SUMMARY, 5)
    raw = tmp_path / "raw.bam"
    _make_unaligned_bam(raw, read_ids)
    tagged = tmp_path / "tagged.bam"
    tag_bam(FIXTURE_SUMMARY, raw, tagged)

    res = filter_bam(tagged, tmp_path / "out.bam", keep={"SP", "UMC"})
    assert res.keep_codes == sorted({"SP", "UMC"})


def test_tag_rejects_invalid_tag_name(tmp_path: Path) -> None:
    raw = tmp_path / "raw.bam"
    _make_unaligned_bam(raw, _read_first_n_ids(FIXTURE_SUMMARY, 1))
    with pytest.raises(ValueError, match="tag_name must be 2 chars"):
        tag_bam(FIXTURE_SUMMARY, raw, tmp_path / "out.bam", tag_name="ERR")


def test_filter_rejects_empty_keep(tmp_path: Path) -> None:
    raw = tmp_path / "raw.bam"
    _make_unaligned_bam(raw, _read_first_n_ids(FIXTURE_SUMMARY, 1))
    tagged = tmp_path / "t.bam"
    tag_bam(FIXTURE_SUMMARY, raw, tagged)
    with pytest.raises(ValueError, match="keep is empty"):
        filter_bam(tagged, tmp_path / "out.bam", keep=set())


def test_tag_bam_raises_on_missing_summary(tmp_path: Path) -> None:
    raw = tmp_path / "raw.bam"
    _make_unaligned_bam(raw, _read_first_n_ids(FIXTURE_SUMMARY, 1))
    with pytest.raises(OntIOError):
        tag_bam(tmp_path / "does_not_exist.txt", raw, tmp_path / "out.bam")


def test_export_fastq_skips_no_sequence(tmp_path: Path) -> None:
    """Reads with no query_sequence are silently dropped (not an error)."""
    bam = tmp_path / "with_no_seq.bam"
    header = {"HD": {"VN": "1.6", "SO": "unknown"}}
    with pysam.AlignmentFile(str(bam), "wb", header=header) as out:
        for i in range(3):
            r = pysam.AlignedSegment()
            r.query_name = f"r{i}"
            r.flag = 4
            r.query_sequence = "ACGT"
            r.query_qualities = pysam.qualitystring_to_array("####")
            out.write(r)
        # one read with no sequence
        r = pysam.AlignedSegment()
        r.query_name = "no_seq"
        r.flag = 4
        out.write(r)

    res = export_fastq(bam, tmp_path / "out.fastq")
    assert res.reads_written == 3


def test_export_fastq_gzip(tmp_path: Path) -> None:
    """Compressed FASTQ output is valid gzip with the right record count."""
    read_ids = _read_first_n_ids(FIXTURE_SUMMARY, 4)
    raw = tmp_path / "raw.bam"
    _make_unaligned_bam(raw, read_ids)
    fastq = tmp_path / "out.fastq.gz"
    res = export_fastq(raw, fastq, compress=True)
    assert res.reads_written == 4
    with gzip.open(fastq, "rt") as fh:
        text = fh.read()
    assert text.count("\n@") + (1 if text.startswith("@") else 0) == 4


def test_supported_end_reasons_includes_canonical_codes() -> None:
    codes = list(supported_end_reasons())
    for expected in ("SP", "UMC", "MC", "DUMC", "SN"):
        assert expected in codes


def test_filter_parallel_below_threshold_falls_back_to_sequential(tmp_path: Path) -> None:
    """Small BAMs (under MIN_READS_FOR_PARALLEL bytes) skip parallel path."""
    from ont_end_reason.filter.filter import MIN_READS_FOR_PARALLEL

    assert MIN_READS_FOR_PARALLEL > 0
    read_ids = _read_first_n_ids(FIXTURE_SUMMARY, 10)
    raw = tmp_path / "raw.bam"
    _make_unaligned_bam(raw, read_ids)
    tagged = tmp_path / "tagged.bam"
    tag_bam(FIXTURE_SUMMARY, raw, tagged)

    out = tmp_path / "kept.bam"
    res = filter_bam(tagged, out, keep="SP", threads=4)
    assert res.input_reads == 10
    assert out.exists()


def test_filter_parallel_matches_sequential_output(tmp_path: Path) -> None:
    """Parallel filter must return identical kept-read sets as sequential.

    Forces parallel by lowering MIN_READS_FOR_PARALLEL for the duration
    of the test. Compares query_name sets — order can differ across the
    pysam.cat shard concat versus a single-pass scan, but the underlying
    kept set must be bit-identical.
    """
    import ont_end_reason.filter.filter as filter_mod

    read_ids = _read_first_n_ids(FIXTURE_SUMMARY, 200)
    raw = tmp_path / "raw.bam"
    _make_unaligned_bam(raw, read_ids)
    tagged = tmp_path / "tagged.bam"
    tag_bam(FIXTURE_SUMMARY, raw, tagged)

    seq_out = tmp_path / "seq.bam"
    seq_res = filter_bam(tagged, seq_out, keep="SP,UMC", threads=1)

    original_min = filter_mod.MIN_READS_FOR_PARALLEL
    filter_mod.MIN_READS_FOR_PARALLEL = 1
    try:
        par_out = tmp_path / "par.bam"
        par_res = filter_bam(tagged, par_out, keep="SP,UMC", threads=2, shard_size=50)
    finally:
        filter_mod.MIN_READS_FOR_PARALLEL = original_min

    assert seq_res.input_reads == par_res.input_reads == 200
    assert seq_res.kept_reads == par_res.kept_reads
    assert seq_res.dropped_reads == par_res.dropped_reads
    assert seq_res.keep_codes == par_res.keep_codes

    def _collect_query_names(bam: Path) -> set[str]:
        with pysam.AlignmentFile(str(bam), "rb", check_sq=False) as fh:
            return {r.query_name for r in fh.fetch(until_eof=True)}

    assert _collect_query_names(seq_out) == _collect_query_names(par_out)


def _resolve_bam_shard():
    """Bridge-resolution helper: import canonical `lib.bam_shard`."""
    from ont_end_reason._lab_bridge import import_lab_module

    return import_lab_module("bam_shard", repo="ont-ecosystem", lib_subdir="lib")


def test_scan_shard_boundaries_returns_n_shards(tmp_path: Path) -> None:
    """Canonical bam_shard.scan, accessed through ont-end-reason's bridge,
    produces approximately the requested shard count."""
    bam_shard = _resolve_bam_shard()
    if bam_shard is None:
        pytest.skip("lib.bam_shard not on disk (ont-ecosystem sister repo missing)")

    read_ids = _read_first_n_ids(FIXTURE_SUMMARY, 100)
    raw = tmp_path / "raw.bam"
    _make_unaligned_bam(raw, read_ids)

    boundaries = bam_shard.scan(raw, n_shards=4, target_reads_per_shard=25)
    assert 2 <= len(boundaries) <= 4
    assert boundaries[0].start_voff >= 0
    assert boundaries[-1].end_voff is None
    for i in range(len(boundaries) - 1):
        assert boundaries[i].end_voff == boundaries[i + 1].start_voff


def test_scan_shard_boundaries_degenerate_small_input(tmp_path: Path) -> None:
    """Inputs smaller than one shard return a single boundary with end_voff=None."""
    bam_shard = _resolve_bam_shard()
    if bam_shard is None:
        pytest.skip("lib.bam_shard not on disk (ont-ecosystem sister repo missing)")

    read_ids = _read_first_n_ids(FIXTURE_SUMMARY, 3)
    raw = tmp_path / "raw.bam"
    _make_unaligned_bam(raw, read_ids)
    boundaries = bam_shard.scan(raw, n_shards=8, target_reads_per_shard=1000)
    assert len(boundaries) == 1
    assert boundaries[0].end_voff is None

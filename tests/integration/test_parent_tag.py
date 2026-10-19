"""Actual small POD5/BAM fixtures; no lab-data traversal."""

from datetime import datetime, timezone
from uuid import UUID

import numpy as np
import pod5
import pysam
import pytest
from click.testing import CliRunner

from ont_end_reason.cli import main
from ont_end_reason.errors import IOError as OntIOError
from ont_end_reason.filter.filter import _worker_filter_shard, filter_bam
from ont_end_reason.filter.parent_tag import tag_pod5

P = "00000000-0000-0000-0000-000000000001"
C = "00000000-0000-0000-0000-000000000002"
X = "00000000-0000-0000-0000-000000000003"


def raw(path, rows):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    info = pod5.RunInfo(
        "acq",
        now,
        8191,
        -8192,
        {},
        "synthetic",
        "FC",
        "FLO",
        "protocol",
        "run",
        now,
        "sample",
        4000,
        "kit",
        "pos",
        "type",
        "soft",
        "system",
        "type",
        {},
    )
    with pod5.Writer(path) as writer:
        for rid, reason in rows:
            writer.add_read(
                pod5.Read(
                    UUID(rid),
                    pod5.Pore(1, 1, "pore"),
                    pod5.Calibration(0, 1),
                    1,
                    0,
                    0,
                    pod5.EndReason(getattr(pod5.EndReasonEnum, reason.upper()), False),
                    info,
                    signal=np.array([0, 1], dtype=np.int16),
                )
            )
    return path


def bam(path, rows):
    with pysam.AlignmentFile(str(path), "wb", header={"HD": {"VN": "1.6"}}) as sink:
        for rid, tags in rows:
            r = pysam.AlignedSegment()
            r.query_name = rid
            r.flag = 4
            r.query_sequence = "ACGT"
            r.query_qualities = pysam.qualitystring_to_array("IIII")
            for k, v in tags.items():
                r.set_tag(k, v)
            sink.write(r)
    return path


def records(path):
    with pysam.AlignmentFile(str(path), "rb", check_sq=False) as f:
        return list(f.fetch(until_eof=True))


def test_parent_inheritance_preserves_native_and_filter(tmp_path):
    p = raw(tmp_path / "raw.pod5", [(P, "signal_positive")])
    b = bam(
        tmp_path / "in.bam",
        [(P, {"er": "signal_positive", "dx": 0}), (C, {"pi": P, "er": "unknown", "dx": 0})],
    )
    o = tmp_path / "tagged.bam"
    r = tag_pod5(p, b, o)
    assert (r.input_reads, r.tagged_reads, r.inherited_reads, r.native_unknown_resolved) == (
        2,
        2,
        1,
        1,
    )
    assert [x.get_tag("ER") for x in records(o)] == ["SP", "SP"]
    assert records(o)[1].get_tag("er") == "unknown"
    assert filter_bam(o, tmp_path / "keep.bam", "SP").kept_reads == 2


@pytest.mark.parametrize(
    "tags,match",
    [
        ({"pi": X}, "missing"),
        ({"pi": "bad"}, "UUID"),
        ({"pi": 4}, "UUID"),
        ({"pi": P, "er": "mux_change"}, "conflict"),
        ({"pi": P, "ER": "MC"}, "conflict"),
        ({"pi": P, "dx": 1}, "duplex"),
        ({"pi": P, "er": "bogus"}, "Unknown"),
    ],
)
def test_refusal_never_publishes(tmp_path, tags, match):
    p = raw(tmp_path / "raw.pod5", [(P, "signal_positive")])
    b = bam(tmp_path / "in.bam", [(P, {}), (C, tags)])
    o = tmp_path / "out.bam"
    before = b.read_bytes()
    with pytest.raises((OntIOError, ValueError), match=match):
        tag_pod5(p, b, o)
    assert not o.exists() and b.read_bytes() == before


def test_missing_own_id_no_fallback(tmp_path):
    p = raw(tmp_path / "raw.pod5", [(P, "signal_positive")])
    b = bam(tmp_path / "in.bam", [(C, {"er": "signal_positive"})])
    with pytest.raises(OntIOError, match="missing"):
        tag_pod5(p, b, tmp_path / "out.bam")


def test_source_duplicates_and_conflicts(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    raw(d / "a.pod5", [(P, "signal_positive")])
    raw(d / "b.pod5", [(P, "signal_positive")])
    b = bam(tmp_path / "in.bam", [(C, {"pi": P})])
    assert tag_pod5(d, b, tmp_path / "ok.bam").duplicate_source_ids == 1
    raw(d / "c.pod5", [(P, "mux_change")])
    with pytest.raises(OntIOError, match=r"[Cc]onflict"):
        tag_pod5(d, b, tmp_path / "bad.bam")
    assert not (tmp_path / "bad.bam").exists()


def test_output_collision_preserves_bytes(tmp_path):
    p = raw(tmp_path / "raw.pod5", [(P, "signal_positive")])
    b = bam(tmp_path / "in.bam", [(P, {})])
    before = b.read_bytes()
    with pytest.raises((OntIOError, FileExistsError)):
        tag_pod5(p, b, b)
    assert b.read_bytes() == before


def test_cli_pod5_and_legacy_help(tmp_path):
    p = raw(tmp_path / "raw.pod5", [(P, "signal_positive")])
    b = bam(tmp_path / "in.bam", [(C, {"pi": P})])
    o = tmp_path / "out.bam"
    r = CliRunner().invoke(main, ["tag-pod5", "--pod5", str(p), "--bam", str(b), "--out", str(o)])
    assert r.exit_code == 0, r.output
    assert records(o)[0].get_tag("ER") == "SP"
    assert CliRunner().invoke(main, ["tag", "--help"]).exit_code == 0


@pytest.mark.parametrize("keep", ["SP", {"signal_positive"}, {"sp"}])
def test_filter_normalizes_native_and_set(tmp_path, keep):
    b = bam(tmp_path / "in.bam", [(P, {"er": "signal_positive"}), (C, {"er": "UNK"})])
    r = filter_bam(b, tmp_path / "out.bam", keep, tag_name="er")
    assert r.kept_reads == 1 and r.keep_codes == ["SP"]


def test_shard_normalizes(tmp_path):
    b = bam(tmp_path / "in.bam", [(P, {"er": "signal_positive"}), (C, {"er": "unknown"})])
    with pysam.AlignmentFile(str(b), "rb", check_sq=False) as f:
        start = f.tell()
    _, n, k = _worker_filter_shard(
        (str(b), str(tmp_path / "out.bam"), frozenset({"SP"}), "er", start, None)
    )
    assert (n, k) == (2, 1)


@pytest.mark.parametrize("tags", [{}, {"er": "bogus"}, {"er": 4}])
def test_filter_missing_invalid_refuses_without_output(tmp_path, tags):
    b = bam(tmp_path / "in.bam", [(P, {"er": "signal_positive"}), (C, tags)])
    o = tmp_path / "out.bam"
    with pytest.raises((ValueError, OntIOError)):
        filter_bam(b, o, "SP", tag_name="er")
    assert not o.exists()


def test_filter_bad_set_and_collision(tmp_path):
    b = bam(tmp_path / "in.bam", [(P, {"ER": "SP"})])
    before = b.read_bytes()
    with pytest.raises(ValueError):
        filter_bam(b, tmp_path / "bad.bam", {"bogus"})
    with pytest.raises((OntIOError, FileExistsError)):
        filter_bam(b, b, "SP")
    assert b.read_bytes() == before


def test_empty_sources_and_bam(tmp_path):
    p = raw(tmp_path / "raw.pod5", [])
    b = bam(tmp_path / "in.bam", [(P, {})])
    with pytest.raises(OntIOError, match="zero"):
        tag_pod5(p, b, tmp_path / "empty-source.bam")
    p2 = raw(tmp_path / "good.pod5", [(P, "signal_positive")])
    b2 = bam(tmp_path / "empty.bam", [])
    with pytest.raises(OntIOError, match="zero"):
        tag_pod5(p2, b2, tmp_path / "empty-output.bam")


def test_raw_child_parent_ambiguity(tmp_path):
    p = raw(tmp_path / "raw.pod5", [(P, "signal_positive"), (C, "signal_positive")])
    b = bam(tmp_path / "in.bam", [(C, {"pi": P})])
    with pytest.raises(OntIOError, match="Conflicting raw"):
        tag_pod5(p, b, tmp_path / "out.bam")


def test_source_change_refuses(tmp_path, monkeypatch):
    import ont_end_reason.filter.parent_tag as mod

    p = raw(tmp_path / "raw.pod5", [(P, "signal_positive")])
    b = bam(tmp_path / "in.bam", [(P, {})])
    original = mod.iter_pod5_metadata

    def changed(path):
        yield from original(path)
        path.touch()

    monkeypatch.setattr(mod, "iter_pod5_metadata", changed)
    with pytest.raises(OntIOError, match="changed"):
        tag_pod5(p, b, tmp_path / "out.bam")
    assert not (tmp_path / "out.bam").exists()


def test_exclusive_publish_race(tmp_path):
    from ont_end_reason.filter.output import new_output

    o = tmp_path / "out.bam"
    with pytest.raises(OntIOError, match="publish"), new_output(o) as staged:
        staged.write_bytes(b"ours")
        o.write_bytes(b"other")
    assert o.read_bytes() == b"other"


def test_unknown_parent_remains_unknown(tmp_path):
    p = raw(tmp_path / "raw.pod5", [(P, "unknown")])
    b = bam(tmp_path / "in.bam", [(C, {"pi": P, "er": "unknown"})])
    o = tmp_path / "out.bam"
    r = tag_pod5(p, b, o)
    assert r.unknown_parent_reads == 1 and records(o)[0].get_tag("ER") == "UNK"
    assert filter_bam(o, tmp_path / "keep.bam", "SP").kept_reads == 0


def test_payload_tags_and_qualities_preserved(tmp_path):
    from array import array

    p = raw(tmp_path / "raw.pod5", [(P, "signal_positive")])
    tags = {
        "pi": P,
        "er": "unknown",
        "MM": "C+m,0;",
        "ML": array("B", [200]),
        "mv": array("b", [6, 1, 0]),
        "RG": "synthetic",
    }
    b = bam(tmp_path / "in.bam", [(C, tags), (C, tags)])
    o = tmp_path / "out.bam"
    result = tag_pod5(p, b, o)
    assert result.input_reads == 2
    for before, after in zip(records(b), records(o), strict=True):
        assert before.query_sequence == after.query_sequence
        assert before.query_qualities == after.query_qualities
        assert before.flag == after.flag
        assert dict(before.get_tags()) == {k: v for k, v in after.get_tags() if k != "ER"}


def test_native_parallel_matches_sequential(tmp_path, monkeypatch):
    import ont_end_reason.filter.filter as mod

    assert mod._bam_shard is not None, (
        "This control requires the official bam_shard import on PYTHONPATH"
    )
    b = bam(
        tmp_path / "in.bam",
        [
            (P if i % 2 else C, {"er": "signal_positive" if i % 2 else "unknown"})
            for i in range(100)
        ],
    )
    monkeypatch.setattr(mod, "MIN_READS_FOR_PARALLEL", 1)
    one = filter_bam(b, tmp_path / "one.bam", {"signal_positive"}, tag_name="er")
    many = filter_bam(b, tmp_path / "many.bam", {"sp"}, tag_name="er", threads=2, shard_size=20)
    assert one == many
    assert [r.to_string() for r in records(tmp_path / "one.bam")] == [
        r.to_string() for r in records(tmp_path / "many.bam")
    ]

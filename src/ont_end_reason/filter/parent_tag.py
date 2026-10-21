"""Strict simplex POD5 parent tagging. Missing lineage is an error, not UNK.

POD5 metadata is authoritative. Native er is retained, and canonical ER receives
the parent's normalized reason. A native UNK may be resolved, but a known reason
conflicting with raw metadata refuses publication. No summary child-ID heuristic.
"""

import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from ..codes import to_short
from ..errors import IOError as OntIOError
from ..io.readers import iter_pod5_metadata
from ._pysam_guard import require_pysam
from .output import new_output


@dataclass
class ParentTagResult:
    input_reads: int
    tagged_reads: int
    inherited_reads: int
    native_unknown_resolved: int
    duplicate_source_ids: int
    source_unique_ids: int
    unknown_parent_reads: int
    tag_name: str = "ER"


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise OntIOError(f"Invalid UUID identity: {value!r}")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise OntIOError(f"Invalid UUID identity: {value!r}") from exc


def _stamp(path: Path) -> tuple[int, int, int, int, int]:
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def _files(path: Path) -> list[Path]:
    return sorted(path.rglob("*.pod5")) if path.is_dir() else [path]


def tag_pod5(
    pod5_path: str | Path,
    bam_path: str | Path,
    output_path: str | Path,
    *,
    scratch_dir: str | Path | None = None,
) -> ParentTagResult:
    """Tag every BAM record through raw parent UUID, failing closed on ambiguity.

    Supports simplex (dx absent, 0 or -1); duplex dx=1 is unsupported. pi must
    identify an actual raw record. Same-ID source duplicates must agree. Temporary
    SQLite defaults beside the output; explicit scratch_dir relocates only the
    temporary index. Atomic BAM staging always remains beside the output.
    Existing output paths are refused. No records are dropped or deduplicated.
    Source metadata must remain stable; full source hash manifests are the caller's
    execution-provenance responsibility.
    """
    pysam = require_pysam()
    source, bam_path, output_path = map(Path, (pod5_path, bam_path, output_path))
    files = _files(source)
    if not files or any(not p.is_file() for p in files):
        raise OntIOError("No readable POD5 source files")
    stamps = {p: _stamp(p) for p in files}
    bam_stamp = _stamp(bam_path)
    with (
        new_output(output_path) as staged,
        tempfile.TemporaryDirectory(
            prefix="parent-index-",
            dir=Path(scratch_dir) if scratch_dir is not None else staged.parent,
        ) as tmp,
        closing(sqlite3.connect(Path(tmp) / "parents.sqlite")) as db,
    ):
        db.execute("PRAGMA cache_size=-65536")
        db.execute("CREATE TABLE parents (id TEXT PRIMARY KEY, reason TEXT NOT NULL) WITHOUT ROWID")
        duplicates = 0
        for p in files:
            for row in iter_pod5_metadata(p):
                rid, reason = _uuid(row.read_id), to_short(row.end_reason)
                old = db.execute("SELECT reason FROM parents WHERE id=?", (rid,)).fetchone()
                if old:
                    if old[0] != reason:
                        raise OntIOError(f"Conflicting source end_reason for {rid}")
                    duplicates += 1
                else:
                    db.execute("INSERT INTO parents VALUES (?,?)", (rid, reason))
            db.commit()
        unique = db.execute("SELECT count(*) FROM parents").fetchone()[0]
        if unique == 0:
            raise OntIOError("POD5 source contains zero reads")
        total = inherited = resolved = unknown = 0
        with (
            pysam.AlignmentFile(str(bam_path), "rb", check_sq=False) as src,
            pysam.AlignmentFile(str(staged), "wb", template=src) as dst,
        ):
            for read in src.fetch(until_eof=True):
                total += 1
                dx = read.get_tag("dx") if read.has_tag("dx") else 0
                if not isinstance(dx, int) or dx not in (-1, 0):
                    raise OntIOError(f"Unsupported duplex/ambiguous dx: {dx!r}")
                rid = _uuid(read.query_name)
                parent = _uuid(read.get_tag("pi")) if read.has_tag("pi") else rid
                if (
                    parent != rid
                    and db.execute("SELECT 1 FROM parents WHERE id=?", (rid,)).fetchone()
                ):
                    raise OntIOError(f"Conflicting raw child and pi identities: {rid}")
                row = db.execute("SELECT reason FROM parents WHERE id=?", (parent,)).fetchone()
                if row is None:
                    raise OntIOError(f"Raw parent missing for {rid}: {parent}")
                reason = row[0]
                for tag in ("er", "ER"):
                    if read.has_tag(tag):
                        value = read.get_tag(tag)
                        if not isinstance(value, str):
                            raise OntIOError(f"Invalid {tag} value for {rid}")
                        native = to_short(value)
                        if native != reason and native != "UNK":
                            raise OntIOError(
                                f"Known end_reason conflict for {rid}: {tag}={native}, raw={reason}"
                            )
                        if tag == "er" and native == "UNK" and reason != "UNK":
                            resolved += 1
                inherited += parent != rid
                unknown += reason == "UNK"
                read.set_tag("ER", reason, value_type="Z")
                dst.write(read)
        if not total:
            raise OntIOError("BAM contains zero records")
        if (
            files != _files(source)
            or any(_stamp(p) != stamps[p] for p in files)
            or _stamp(bam_path) != bam_stamp
        ):
            raise OntIOError("Input changed during parent tagging")
        result = ParentTagResult(total, total, inherited, resolved, duplicates, unique, unknown)
    return result

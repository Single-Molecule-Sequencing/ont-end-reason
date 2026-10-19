"""Publish a new BAM only after complete success; never replace existing data."""

import os
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from ..errors import IOError as OntIOError


@contextmanager
def new_output(output_path: str | Path, *, inputs: Sequence[Path] = ()) -> Iterator[Path]:
    stamps = {Path(p): Path(p).stat() for p in inputs}
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() or output_path.is_symlink():
        raise OntIOError(f"Output already exists: {output_path}")
    with tempfile.TemporaryDirectory(prefix=".ont-end-reason-", dir=output_path.parent) as tmp:
        staging = Path(tmp) / "output.bam"
        yield staging
        for p, before in stamps.items():
            after = p.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise OntIOError(f"Input changed during filtering: {p}")
        try:
            os.link(staging, output_path)
        except OSError as exc:
            raise OntIOError(f"Could not publish new output {output_path}: {exc}") from exc

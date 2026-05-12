"""Table generation for the paper's tables + supplementary tables.

v0.1.0 STATUS: scaffold only.
Source: TOOL_SPECIFICATIONS.md types 12 and 13.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TableResult:
    name: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    format: str = "tsv"  # tsv | csv | latex | markdown
    path: str | None = None


def generate_tables(source: str | Path, *, name: str, **kwargs: Any) -> TableResult:
    raise NotImplementedError(
        "analyze.generate_tables is scheduled for v0.2.0. See TOOL_SPECIFICATIONS.md "
        "types 12 (main tables) and 13 (supplementary data)."
    )

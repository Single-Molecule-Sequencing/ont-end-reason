"""Schema validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ont_end_reason.errors import ValidationError
from ont_end_reason.io.schema import (
    RECOMMENDED_COLUMNS,
    REQUIRED_COLUMNS,
    validate_summary,
)


pytestmark = pytest.mark.fast


def _write_header(tmp_path: Path, columns: list[str], name: str = "sequencing_summary.txt") -> Path:
    p = tmp_path / name
    p.write_text("\t".join(columns) + "\nbody-line-1\n")
    return p


class TestValidateSummary:
    def test_minimal_valid(self, tmp_path: Path) -> None:
        path = _write_header(tmp_path, sorted(REQUIRED_COLUMNS))
        schema = validate_summary(path)
        assert schema.is_valid
        assert not schema.missing_required

    def test_full_valid(self, tmp_path: Path) -> None:
        path = _write_header(
            tmp_path, sorted(REQUIRED_COLUMNS | RECOMMENDED_COLUMNS)
        )
        schema = validate_summary(path)
        assert schema.is_valid
        assert not schema.missing_recommended

    def test_missing_required(self, tmp_path: Path) -> None:
        path = _write_header(tmp_path, ["read_id"])  # missing end_reason
        schema = validate_summary(path)
        assert not schema.is_valid
        assert "end_reason" in schema.missing_required

    def test_extra_columns_reported(self, tmp_path: Path) -> None:
        cols = sorted(REQUIRED_COLUMNS) + ["mystery_extra_column"]
        path = _write_header(tmp_path, cols)
        schema = validate_summary(path)
        assert "mystery_extra_column" in schema.extra_columns

    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.txt"
        p.write_text("")
        with pytest.raises(ValidationError, match="Empty header"):
            validate_summary(p)

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="Cannot read"):
            validate_summary(tmp_path / "does-not-exist.txt")

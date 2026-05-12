"""Exception hierarchy tests."""

from __future__ import annotations

import pytest

from ont_end_reason.errors import (
    AnalysisError,
    IOError as OntIOError,
    OntEndReasonError,
    ValidationError,
)


pytestmark = pytest.mark.fast


class TestHierarchy:
    def test_io_is_ont(self) -> None:
        assert issubclass(OntIOError, OntEndReasonError)

    def test_analysis_is_ont(self) -> None:
        assert issubclass(AnalysisError, OntEndReasonError)

    def test_validation_is_ont(self) -> None:
        assert issubclass(ValidationError, OntEndReasonError)

    def test_subclasses_not_io_builtin(self) -> None:
        # Our IOError must NOT be the Python builtin; it's a separate type.
        assert OntIOError is not __builtins__["IOError"] if isinstance(__builtins__, dict) else OntIOError is not __builtins__.IOError  # type: ignore[union-attr]

    def test_catch_via_base(self) -> None:
        with pytest.raises(OntEndReasonError):
            raise OntIOError("test")
        with pytest.raises(OntEndReasonError):
            raise AnalysisError("test")
        with pytest.raises(OntEndReasonError):
            raise ValidationError("test")

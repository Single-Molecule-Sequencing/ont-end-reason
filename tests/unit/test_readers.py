"""Reader-level tests — focus on the end_reason normalisation function.

The POD5 library returns end_reason as a NamedTuple with an Enum field,
so `str(value)` produces things like
`"(<EndReason.signal_positive: 4>, forced=False)"`. This test pins the
normalisation behaviour so we never regress that smoke-test bug.
"""

from __future__ import annotations

from enum import IntEnum
from pathlib import Path

import pytest

from ont_end_reason.errors import IOError as OntIOError
from ont_end_reason.io.readers import _normalise_end_reason, extract_from_summary

pytestmark = pytest.mark.fast


class _MockEnum(IntEnum):
    signal_positive = 4
    unblock_mux_change = 2


class TestNormaliseEndReason:
    def test_clean_string(self) -> None:
        assert _normalise_end_reason("signal_positive") == "signal_positive"

    def test_enum_dotted(self) -> None:
        assert _normalise_end_reason("EndReason.signal_positive") == "signal_positive"

    def test_pod5_repr(self) -> None:
        # The actual shape pod5 returns on this lab's workstation
        raw = "(<EndReason.signal_positive: 4>, forced=False)"
        assert _normalise_end_reason(raw) == "signal_positive"

    def test_angle_repr(self) -> None:
        assert _normalise_end_reason("<EndReason.unblock_mux_change: 2>") == "unblock_mux_change"

    def test_actual_enum_member(self) -> None:
        # Real enum with a .name — should use it directly
        assert _normalise_end_reason(_MockEnum.signal_positive) == "signal_positive"

    def test_none(self) -> None:
        assert _normalise_end_reason(None) == "unknown"

    @pytest.mark.parametrize(
        "reason", ["bogus_reason", "EndReason.bogus_reason", "<EndReason.bogus_reason: 99>"]
    )
    def test_unrecognized_reason_raises(self, reason: str) -> None:
        with pytest.raises(ValueError, match="Unknown end_reason"):
            _normalise_end_reason(reason)

    def test_unrecognized_enum_raises(self) -> None:
        class UnknownReason(IntEnum):
            bogus_reason = 99

        with pytest.raises(ValueError, match="Unknown end_reason"):
            _normalise_end_reason(UnknownReason.bogus_reason)

    @pytest.mark.parametrize("reason", ["device_data_error", "analysis_config_change"])
    def test_additional_recorded_reasons(self, reason: str) -> None:
        assert _normalise_end_reason(reason) == reason

    def test_uppercase_normalised(self) -> None:
        assert _normalise_end_reason("SIGNAL_POSITIVE") == "signal_positive"


def test_summary_rejects_unrecognized_reason(tmp_path: Path) -> None:
    summary = tmp_path / "sequencing_summary.txt"
    summary.write_text("read_id\tend_reason\nr0\tbogus_reason\n", encoding="utf-8")
    with pytest.raises(OntIOError, match=r"Unknown end_reason.*bogus_reason"):
        list(extract_from_summary(summary))

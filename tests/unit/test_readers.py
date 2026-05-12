"""Reader-level tests — focus on the end_reason normalisation function.

The POD5 library returns end_reason as a NamedTuple with an Enum field,
so `str(value)` produces things like
`"(<EndReason.signal_positive: 4>, forced=False)"`. This test pins the
normalisation behaviour so we never regress that smoke-test bug.
"""

from __future__ import annotations

from enum import IntEnum

import pytest

from ont_end_reason.io.readers import _normalise_end_reason

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

    def test_unknown_passes_through(self) -> None:
        # Unrecognised values stay lowercased so downstream can flag them
        assert _normalise_end_reason("custom_value") == "custom_value"

    def test_uppercase_normalised(self) -> None:
        assert _normalise_end_reason("SIGNAL_POSITIVE") == "signal_positive"

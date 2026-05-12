"""SSOT taxonomy tests with Hypothesis property tests."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ont_end_reason.codes import (
    CODES,
    FAILED,
    NAMES,
    RECOMMENDED_KEEP,
    TRUNCATED,
    UNKNOWN_STATES,
    classify,
    parse_keep_list,
    to_full,
    to_short,
)


pytestmark = pytest.mark.fast


class TestCanonicalSet:
    def test_exactly_seven_codes(self) -> None:
        assert len(CODES) == 7
        assert len(NAMES) == 7

    def test_codes_and_names_are_bijective(self) -> None:
        for full, short in CODES.items():
            assert NAMES[short] == full
        for short, full in NAMES.items():
            assert CODES[full] == short

    def test_recommended_keep_is_signal_positive_only(self) -> None:
        # If you change this you are changing the paper's filtering policy.
        # Read the paper, bump the claim atoms, then update this test.
        assert RECOMMENDED_KEEP == frozenset({"SP"})

    def test_failed_is_signal_negative_only(self) -> None:
        assert FAILED == frozenset({"SN"})

    def test_truncated_membership(self) -> None:
        assert TRUNCATED == frozenset({"UMC", "MC", "DUMC", "PART"})

    def test_class_disjoint(self) -> None:
        # Every code belongs to exactly one class.
        all_codes = set(NAMES)
        classes = (RECOMMENDED_KEEP, TRUNCATED, FAILED, UNKNOWN_STATES)
        for c in all_codes:
            in_classes = sum(c in cls for cls in classes)
            assert in_classes == 1, f"{c} appears in {in_classes} classes"


class TestParseKeepList:
    def test_short_upper(self) -> None:
        assert parse_keep_list("SP") == {"SP"}

    def test_short_lower(self) -> None:
        assert parse_keep_list("sp") == {"SP"}

    def test_full_name(self) -> None:
        assert parse_keep_list("signal_positive") == {"SP"}

    def test_comma(self) -> None:
        assert parse_keep_list("SP,UMC") == {"SP", "UMC"}

    def test_whitespace(self) -> None:
        assert parse_keep_list("SP UMC MC") == {"SP", "UMC", "MC"}

    def test_mixed(self) -> None:
        assert parse_keep_list("SP,unblock_mux_change") == {"SP", "UMC"}

    def test_empty(self) -> None:
        assert parse_keep_list("") == set()

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown end_reason"):
            parse_keep_list("BOGUS")


class TestCoercion:
    def test_to_short_idempotent(self) -> None:
        assert to_short("SP") == "SP"
        assert to_short(to_short("signal_positive")) == "SP"

    def test_to_full_idempotent(self) -> None:
        assert to_full("signal_positive") == "signal_positive"
        assert to_full(to_full("SP")) == "signal_positive"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError):
            to_short("BOGUS")
        with pytest.raises(ValueError):
            to_full("BOGUS")


class TestClassify:
    def test_sp_keep(self) -> None:
        assert classify("SP") == "keep"
        assert classify("signal_positive") == "keep"

    def test_umc_truncated(self) -> None:
        assert classify("UMC") == "truncated"

    def test_sn_failed(self) -> None:
        assert classify("SN") == "failed"

    def test_unk_unknown(self) -> None:
        assert classify("UNK") == "unknown"


# ─── Property tests via Hypothesis ──────────────────────────────────────────


@given(st.sampled_from(list(NAMES)))
def test_property_round_trip_short_full(short: str) -> None:
    assert to_short(to_full(short)) == short


@given(st.sampled_from(list(CODES)))
def test_property_round_trip_full_short(full: str) -> None:
    assert to_full(to_short(full)) == full


@given(st.sampled_from(list(NAMES)))
def test_property_classify_returns_valid_class(short: str) -> None:
    assert classify(short) in {"keep", "truncated", "failed", "unknown"}


@given(
    st.lists(
        st.sampled_from(list(NAMES) + list(CODES)),
        min_size=1,
        max_size=7,
        unique=True,
    )
)
def test_property_parse_keep_list_round_trip(items: list[str]) -> None:
    spec = ",".join(items)
    result = parse_keep_list(spec)
    # Every result must be a valid short code
    assert result.issubset(set(NAMES))
    # Every original item must map to something in the result
    for it in items:
        assert to_short(it) in result

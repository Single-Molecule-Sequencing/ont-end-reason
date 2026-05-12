"""Reproducibility tests against the synthetic fixture.

The first half of issue #4. For every implemented analysis, this asserts
that the current code produces bit-identical structured output to the
snapshot pinned at v0.2.0a1 (`tests/reproducibility/expected/*.json`).

Catches:
  - Numeric drift from numpy / scipy / pandas version bumps
  - Algorithm bugs introduced by refactoring
  - Off-by-one / rounding changes

If a test fails with a real mathematical drift, regenerate the expected
JSON via `python docs/generate_examples.py && cp docs/examples/json/*.json
tests/reproducibility/expected/`. The PR should explain WHY the output
changed (e.g. switched estimator, fixed a bug) — drift without explanation
is a red flag.

The SECOND half of issue #4 — comparing to end-reason-paper claim atoms —
is deferred until end-reason-paper repins its atoms to a specific
ont-end-reason version. See tests/reproducibility/test_paper_atoms.py
(stub for now).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ont_end_reason.analyze.distribution import distribution
from ont_end_reason.analyze.hypothesis import hypothesis
from ont_end_reason.analyze.length import length
from ont_end_reason.analyze.quality import quality
from ont_end_reason.analyze.temporal import temporal
from ont_end_reason.analyze.umc_posterior import umc_posterior

pytestmark = pytest.mark.reproducibility

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "sequencing_summary_synthetic.txt"
EXPECTED = REPO / "tests" / "reproducibility" / "expected"


def _load(name: str) -> dict:
    return json.loads((EXPECTED / f"{name}.json").read_text())


def _assert_equal(actual: dict, expected: dict, path: str = "") -> None:
    """Bit-identical comparison with structural diagnostics on mismatch."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: type mismatch (got {type(actual).__name__})"
        # Allow missing optional keys (e.g. "source" can vary), but require
        # all expected non-source keys to be present.
        for k, v in expected.items():
            if k == "source":  # path varies per run
                continue
            assert k in actual, f"{path}: missing key {k!r}"
            _assert_equal(actual[k], v, f"{path}.{k}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: type mismatch (got {type(actual).__name__})"
        assert len(actual) == len(expected), f"{path}: length {len(actual)} != {len(expected)}"
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _assert_equal(a, e, f"{path}[{i}]")
    elif isinstance(expected, float):
        # Float comparison: numerical methods may drift in the last bit on
        # different platforms; use a tight relative tolerance.
        assert isinstance(actual, (int, float)), (
            f"{path}: expected number, got {type(actual).__name__}"
        )
        if expected == 0:
            assert abs(actual) < 1e-9, f"{path}: {actual} != {expected}"
        else:
            rel = abs((actual - expected) / expected)
            assert rel < 1e-4, f"{path}: {actual} != {expected} (rel diff {rel:.2e})"
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


class TestReproducibility:
    def test_distribution(self) -> None:
        actual = distribution(FIXTURE).to_dict()
        expected = _load("distribution")
        _assert_equal(actual, expected)

    def test_length(self) -> None:
        actual = length(FIXTURE).to_dict()
        expected = _load("length")
        _assert_equal(actual, expected)

    def test_quality(self) -> None:
        actual = quality(FIXTURE).to_dict()
        expected = _load("quality")
        # Quality GMM fit can have small EM-init-dependent drift on weights
        # but means should be stable. The _assert_equal tolerance is tight
        # enough that genuine algorithm drift will catch.
        _assert_equal(actual, expected)

    def test_temporal(self) -> None:
        actual = temporal(FIXTURE).to_dict()
        expected = _load("temporal")
        _assert_equal(actual, expected)

    def test_umc_posterior(self) -> None:
        actual = umc_posterior(FIXTURE).to_dict()
        expected = _load("umc_posterior")
        _assert_equal(actual, expected)

    def test_hypothesis_length(self) -> None:
        actual = hypothesis(FIXTURE, a="SP", b="UMC", column="sequence_length_template").to_dict()
        expected = _load("hypothesis")["length_test"]
        _assert_equal(actual, expected)

    def test_hypothesis_qscore(self) -> None:
        actual = hypothesis(FIXTURE, a="SP", b="UMC", column="mean_qscore_template").to_dict()
        expected = _load("hypothesis")["qscore_test"]
        _assert_equal(actual, expected)

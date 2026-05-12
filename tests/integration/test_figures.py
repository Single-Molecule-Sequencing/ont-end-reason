"""Tests for figures/ subpackage — paper figure reproducers.

These exercise the composition layer that wires analyze.* → viz.* → PDF.
Each fig*() takes a sequencing_summary path and writes a publication-ready
plot; the test just asserts non-empty bytes land at the requested path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

from ont_end_reason.figures import (
    fig3_distribution,
    fig5_violin,
    fig6_conceptual,
    supplementary,
)

FIXTURE_SUMMARY = Path(__file__).parent.parent / "fixtures" / "sequencing_summary_synthetic.txt"


@pytest.mark.parametrize(
    ("name", "fig_fn", "ext"),
    [
        ("fig3_distribution", fig3_distribution, "png"),
        ("fig5_violin", fig5_violin, "png"),
        ("fig6_conceptual", fig6_conceptual, "png"),
    ],
)
def test_figure_reproducer_writes_nonempty_output(
    tmp_path: Path, name: str, fig_fn: object, ext: str
) -> None:
    out = tmp_path / f"{name}.{ext}"
    result_path = fig_fn(FIXTURE_SUMMARY, out=out)  # type: ignore[operator]
    assert Path(result_path) == out
    assert out.exists()
    assert out.stat().st_size > 1024


def test_fig3_distribution_quick_mode(tmp_path: Path) -> None:
    out = tmp_path / "fig3_quick.png"
    fig3_distribution(FIXTURE_SUMMARY, out=out, quick=True)
    assert out.exists()


def test_fig3_creates_parent_directory(tmp_path: Path) -> None:
    """fig*() must create missing parent directories."""
    out = tmp_path / "deep" / "nested" / "fig3.png"
    fig3_distribution(FIXTURE_SUMMARY, out=out)
    assert out.exists()


def test_supplementary_raises_with_pointer(tmp_path: Path) -> None:
    """Supplementary is still a scaffold — must raise with a useful message."""
    with pytest.raises(NotImplementedError, match=r"v0\.2\.0|TOOL_SPECIFICATIONS"):
        supplementary(FIXTURE_SUMMARY, out=tmp_path / "supp.png")

"""Pytest helpers for asserting click CLI flag exposure.

VENDORED COPY — do not edit in this repo.
==========================================

Canonical source: `lab-papers/scripts/utils/test_cli_surface.py`
(github.com/Single-Molecule-Sequencing/lab-papers, private repo).

The lab-papers repo is private, so we vendor a snapshot rather than
import via raw URL (same pattern as scripts/distribute/check_channels.py).
To refresh:

    cp ~/repos/lab-papers/scripts/utils/test_cli_surface.py \\
       tests/_lab_helpers/cli_surface.py

Re-verify after refresh:
    pytest tests/integration/test_cli.py::TestCanonicalCliSurfaceContract

Drift risk is bounded because the canonical helper is small (~60 LOC),
stable, and the function signatures are exercised by ont-end-reason's
own test class — any signature drift fails CI immediately.

Memory entries:
- feedback_cli_vs_api_drift.md
- feedback_dogfood_from_source_paper.md

Catches the CLI-vs-API drift bug class: a Python function gains a new
kwarg but the corresponding `@click.option` decorator is forgotten, so
unit tests that call the function directly pass while real users see
`Error: No such option: --new-flag`.
"""

from __future__ import annotations

from collections.abc import Iterable


def assert_subcommand_help_ok(runner, cli_entry, args: Iterable[str]) -> None:
    """Assert `<cli> <args> --help` exits 0 and prints something."""
    result = runner.invoke(cli_entry, [*list(args), "--help"])
    assert result.exit_code == 0, (
        f"`{' '.join(args)} --help` exited {result.exit_code}: {result.output}"
    )
    assert result.output, f"`{' '.join(args)} --help` produced no output"


def assert_flag_exposed(
    runner,
    cli_entry,
    subcommand: Iterable[str],
    flag: str,
) -> None:
    """Assert that `flag` (e.g. `--shard-size`) is listed in subcommand help.

    Regression test for the CLI-vs-API drift pattern: any Python kwarg
    on a click-CLI-exposed function MUST also have a `@click.option` —
    otherwise the kwarg is invisible at the CLI layer.
    """
    if not flag.startswith("--"):
        raise ValueError(f"flag must be long-form (e.g. --foo); got {flag!r}")

    result = runner.invoke(cli_entry, [*list(subcommand), "--help"])
    assert result.exit_code == 0, (
        f"`{' '.join(subcommand)} --help` exited {result.exit_code}: {result.output}"
    )
    assert flag in result.output, (
        f"flag {flag!r} not exposed by `{' '.join(subcommand)} --help`.\n"
        f"This usually means a Python kwarg was added without the "
        f"corresponding @click.option decorator. See feedback_cli_vs_api_drift.md.\n"
        f"Help output:\n{result.output}"
    )


__all__ = ["assert_flag_exposed", "assert_subcommand_help_ok"]

"""End-to-end CLI tests using click's CliRunner."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from ont_end_reason import __version__
from ont_end_reason.cli import main

pytestmark = pytest.mark.integration


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestTopLevel:
    def test_help(self, runner: CliRunner) -> None:
        # Note: when invoked via CliRunner the program name comes from the
        # function's __name__, not the entry-point script — so we check for
        # the description text + subcommand names rather than "ont-end-reason".
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Oxford Nanopore" in result.output
        assert "end_reason" in result.output
        for cmd in ["analyze", "filter", "discover", "tag", "report", "figure", "codes", "stats"]:
            assert cmd in result.output, f"missing {cmd} in help"

    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_debug_and_quiet_conflict(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--debug", "--quiet", "codes"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


class TestCodes:
    def test_codes_prints_all_seven(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["codes"])
        assert result.exit_code == 0
        for code in ["SP", "UMC", "MC", "SN", "DUMC", "UNK", "PART"]:
            assert code in result.output


class TestSchema:
    def test_schema_prints_required(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["schema"])
        assert result.exit_code == 0
        assert "read_id" in result.output
        assert "end_reason" in result.output


class TestDiscover:
    def test_empty_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(main, ["discover", str(tmp_path)])
        assert result.exit_code == 0
        assert "Found 0 files" in result.output

    def test_discover_writes_manifest(self, runner: CliRunner, tmp_path: Path) -> None:
        (tmp_path / "a.pod5").write_bytes(b"x")
        manifest_path = tmp_path / "manifest.json"
        result = runner.invoke(
            main,
            ["discover", str(tmp_path), "--manifest", str(manifest_path)],
        )
        assert result.exit_code == 0
        assert manifest_path.exists()
        assert "Manifest written" in result.output


class TestSubcommandHelp:
    @pytest.mark.parametrize(
        "args",
        [
            ["tag", "--help"],
            ["filter", "--help"],
            ["export-fastq", "--help"],
            ["analyze", "--help"],
            ["analyze", "distribution", "--help"],
            ["figure", "--help"],
            ["figure", "fig3", "--help"],
            ["report", "--help"],
            ["report", "interactive", "--help"],
            ["stats", "--help"],
        ],
    )
    def test_help_works(self, runner: CliRunner, args: list[str]) -> None:
        result = runner.invoke(main, args)
        assert result.exit_code == 0, f"`ont-end-reason {' '.join(args)}` failed: {result.output}"


class TestFilterCLISurface:
    """Catches CLI-vs-API drift on the filter subcommand."""

    def test_shard_size_is_exposed(self, runner: CliRunner) -> None:
        """--shard-size must be a real flag, not just a Python kwarg.

        Regression test for a real bug: the parallel sharded filter was
        shipped with --shard-size on filter_bam() but the click decorator
        didn't expose it, so the CLI rejected the flag. Caught during
        real-data validation on AWG074.
        """
        result = runner.invoke(main, ["filter", "--help"])
        assert result.exit_code == 0
        assert "--shard-size" in result.output
        assert "--threads" in result.output

    def test_filter_rejects_unknown_keep_codes(self, runner: CliRunner, tmp_path: Path) -> None:
        """An obviously-bad --keep value should fail fast rather than silently
        drop every read."""
        empty_bam = tmp_path / "empty.bam"
        empty_bam.touch()
        result = runner.invoke(
            main,
            ["filter", "--bam", str(empty_bam), "--out", str(tmp_path / "o.bam"), "--keep", ""],
        )
        assert result.exit_code != 0


class TestAllAnalysesImplemented:
    """Every analyze subcommand is now wired (no more v0.2.0 scaffolds)."""

    def test_no_scaffolds_remain(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["analyze", "--help"])
        assert result.exit_code == 0
        # Every analysis subcommand should appear by name
        for cmd in [
            "distribution",
            "length",
            "quality",
            "temporal",
            "hypothesis",
            "umc-posterior",
            "signal-trace",
            "sma-metrics",
            "tables",
        ]:
            assert cmd in result.output


class TestErrorHandling:
    def test_missing_path(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["discover", "/does/not/exist"])
        # click validates exists=True before our code runs, so exit_code is 2
        assert result.exit_code != 0


class TestCanonicalCliSurfaceContract:
    """Exercises every public click subcommand through the lab-canonical
    `assert_flag_exposed` / `assert_subcommand_help_ok` helpers, vendored
    from `lab-papers/scripts/utils/test_cli_surface.py` into
    `tests/_lab_helpers/cli_surface.py` (see that file's header for the
    refresh recipe).

    Catches the CLI-vs-API drift bug class documented in
    `feedback_cli_vs_api_drift.md` — adding a new Python kwarg without
    a matching @click.option silently strands the kwarg at the CLI layer.
    Each row below is one Python kwarg → click option contract.
    """

    def test_top_level_help_ok(self, runner: CliRunner) -> None:
        from tests._lab_helpers.cli_surface import assert_subcommand_help_ok

        assert_subcommand_help_ok(runner, main, [])

    def test_every_subcommand_help_ok(self, runner: CliRunner) -> None:
        from tests._lab_helpers.cli_surface import assert_subcommand_help_ok

        for sub in (
            ["discover"],
            ["tag"],
            ["filter"],
            ["export-fastq"],
            ["codes"],
            ["schema"],
            ["stats"],
            ["analyze"],
            ["analyze", "distribution"],
            ["analyze", "length"],
            ["analyze", "quality"],
            ["analyze", "temporal"],
            ["analyze", "hypothesis"],
            ["analyze", "umc-posterior"],
            ["analyze", "signal-trace"],
            ["analyze", "sma-metrics"],
            ["analyze", "tables"],
            ["analyze", "atlas"],
        ):
            assert_subcommand_help_ok(runner, main, sub)

    def test_filter_exposes_parallel_flags(self, runner: CliRunner) -> None:
        """Regression for the AWG074 incident: --shard-size was a Python
        kwarg on filter_bam() but the click decorator didn't expose it."""
        from tests._lab_helpers.cli_surface import assert_flag_exposed

        assert_flag_exposed(runner, main, ["filter"], "--shard-size")
        assert_flag_exposed(runner, main, ["filter"], "--threads")
        assert_flag_exposed(runner, main, ["filter"], "--keep")
        assert_flag_exposed(runner, main, ["filter"], "--tag-name")

    def test_tag_exposes_summary_and_out_flags(self, runner: CliRunner) -> None:
        from tests._lab_helpers.cli_surface import assert_flag_exposed

        assert_flag_exposed(runner, main, ["tag"], "--summary")
        assert_flag_exposed(runner, main, ["tag"], "--bam")
        assert_flag_exposed(runner, main, ["tag"], "--out")
        assert_flag_exposed(runner, main, ["tag"], "--tag-name")

    def test_export_fastq_exposes_compress(self, runner: CliRunner) -> None:
        from tests._lab_helpers.cli_surface import assert_flag_exposed

        assert_flag_exposed(runner, main, ["export-fastq"], "--bam")
        assert_flag_exposed(runner, main, ["export-fastq"], "--fastq")
        assert_flag_exposed(runner, main, ["export-fastq"], "--compress")

    def test_analyze_distribution_exposes_quick_and_max_reads(
        self, runner: CliRunner
    ) -> None:
        from tests._lab_helpers.cli_surface import assert_flag_exposed

        assert_flag_exposed(runner, main, ["analyze", "distribution"], "--quick")
        assert_flag_exposed(runner, main, ["analyze", "distribution"], "--max-reads")

    def test_global_logging_flags_exposed(self, runner: CliRunner) -> None:
        """--debug / --quiet / --version are on the top-level group."""
        from tests._lab_helpers.cli_surface import assert_flag_exposed

        assert_flag_exposed(runner, main, [], "--debug")
        assert_flag_exposed(runner, main, [], "--quiet")
        assert_flag_exposed(runner, main, [], "--version")

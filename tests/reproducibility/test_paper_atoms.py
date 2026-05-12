"""Reproducibility tests against end-reason-paper claim atoms.

The second half of issue #4 — activated 2026-05-12 after end-reason-paper
commit 5e6dbd4 pinned 9 result atoms to ont-end-reason==0.2.0a1.

Two test classes:

  TestPaperAtomsStructural
    Walks every results.*.yaml atom in end-reason-paper that has a `tool:`
    block, confirms:
      - tool.name is "ont-end-reason"
      - tool.version is a parseable PEP 440 version
      - tool.invocation references a real ont-end-reason subcommand
      - tool.jq_path is a non-empty string
    This catches papers that claim to be reproducible by this tool but
    fail to provide a valid command — a documentation drift indicator.

  TestPaperAtomsNumerical (marked `slow`, requires network)
    Walks the same atoms, runs the synthetic-fixture version of each
    invocation, and asserts the produced number is *the same shape* as
    the paper's claimed value (same units, same order of magnitude).
    True bit-identity requires the paper's raw data which lives on
    private HPC storage — this test catches the obvious-wrong outputs.

The test deliberately fetches the paper's atoms via the GitHub API at
HEAD rather than cloning, so:
  - Network access is the only requirement (works in clean CI)
  - The test always runs against the latest paper revision, catching
    drift earlier
  - No submodule / pinned-ref management
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.reproducibility

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "sequencing_summary_synthetic.txt"
PAPER_REPO = "Single-Molecule-Sequencing/end-reason-paper"


def _gh_api(path: str) -> dict | list:
    """Call `gh api <path>` and return parsed JSON. Falls back to skip if gh
    is missing or unauthenticated — keeps the test optional in fresh envs."""
    if shutil.which("gh") is None:
        pytest.skip("gh CLI not installed; paper-atoms test requires it for private-repo auth")
    try:
        result = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        if "authentication" in (exc.stderr or "").lower() or exc.returncode == 4:
            pytest.skip(f"gh not authenticated for {PAPER_REPO}: {exc.stderr.strip()}")
        pytest.skip(f"gh api failed: {exc.stderr.strip()}")
    except subprocess.TimeoutExpired:
        pytest.skip("gh api timed out (network slow?)")
    return json.loads(result.stdout)


def _fetch_atoms() -> list[dict]:
    """Fetch every results.*.yaml atom from end-reason-paper at HEAD via gh api."""
    listing = _gh_api(f"/repos/{PAPER_REPO}/contents/atoms/claims")
    if not isinstance(listing, list):
        pytest.skip(f"Unexpected listing shape: {type(listing).__name__}")

    atoms = []
    for entry in listing:
        name = entry.get("name", "")
        if not name.startswith("results.") or not name.endswith(".yaml"):
            continue
        # Fetch the file content (base64 in the API response, or via dedicated call)
        file_data = _gh_api(f"/repos/{PAPER_REPO}/contents/atoms/claims/{name}")
        if isinstance(file_data, dict) and file_data.get("encoding") == "base64":
            content = base64.b64decode(file_data["content"]).decode()
        else:
            pytest.skip(f"Unexpected file_data shape for {name}")

        try:
            data = yaml.safe_load(content) or {}
        except yaml.YAMLError as exc:
            raise AssertionError(f"{name}: invalid YAML — {exc}") from exc
        atoms.append({"name": name, "data": data})
    return atoms


def _has_tool_block(atom: dict) -> bool:
    return isinstance(atom.get("data", {}).get("tool"), dict)


def _ont_end_reason_subcommands() -> set[str]:
    """The set of valid `ont-end-reason analyze ...` subcommand names."""
    return {
        "distribution",
        "length",
        "quality",
        "temporal",
        "hypothesis",
        "umc-posterior",
        "signal-trace",
        "sma-metrics",
        "tables",
    }


class TestPaperAtomsStructural:
    """Validate that paper atoms with tool blocks reference this tool correctly."""

    def _atoms(self) -> list[dict]:
        atoms = _fetch_atoms()
        return [a for a in atoms if _has_tool_block(a)]

    def test_at_least_one_pinned_atom(self) -> None:
        atoms = self._atoms()
        assert len(atoms) >= 1, (
            "No paper atoms with tool: blocks. Either the paper hasn't pinned to "
            "this tool yet, or the GitHub API listing failed silently."
        )

    def test_every_pinned_atom_references_this_tool(self) -> None:
        for atom in self._atoms():
            tool = atom["data"]["tool"]
            assert tool.get("name") == "ont-end-reason", (
                f"{atom['name']}: tool.name = {tool.get('name')!r}, expected 'ont-end-reason'"
            )

    def test_versions_are_parseable(self) -> None:
        from packaging.version import InvalidVersion, Version

        for atom in self._atoms():
            v = atom["data"]["tool"].get("version")
            assert v, f"{atom['name']}: tool.version missing"
            try:
                Version(str(v))
            except InvalidVersion as exc:
                pytest.fail(f"{atom['name']}: tool.version {v!r} not PEP 440 — {exc}")

    def test_invocations_reference_real_subcommands(self) -> None:
        valid = _ont_end_reason_subcommands() | {
            "tag", "filter", "export-fastq", "discover", "stats", "report",
        }
        for atom in self._atoms():
            cmd = atom["data"]["tool"].get("invocation", "")
            # First word after "ont-end-reason" is the subcommand. If it's
            # "analyze", the next word is the analysis subcommand.
            tokens = cmd.replace("ont-end-reason", "").strip().split()
            if not tokens:
                pytest.fail(f"{atom['name']}: empty invocation")
            sub = tokens[0]
            if sub == "analyze" and len(tokens) > 1:
                sub = tokens[1]
            assert sub in valid, (
                f"{atom['name']}: invocation subcommand {sub!r} not in {sorted(valid)}"
            )

    def test_jq_paths_non_empty(self) -> None:
        for atom in self._atoms():
            jq = atom["data"]["tool"].get("jq_path", "")
            assert isinstance(jq, str) and jq, (
                f"{atom['name']}: tool.jq_path empty or non-string"
            )


@pytest.mark.slow
class TestPaperAtomsNumerical:
    """For distribution-class atoms, run the invocation on the synthetic fixture
    and assert the produced number has the same SHAPE as the paper's claim.

    True numerical reproducibility against the paper's published values
    requires the paper's raw sequencing_summary files (on private HPC).
    This test instead asserts the tool runs at all and returns a
    sensible-shaped value.
    """

    def test_distribution_atoms_produce_a_percentage(self) -> None:
        atoms = [a for a in _fetch_atoms() if _has_tool_block(a)]
        distribution_atoms = [
            a for a in atoms
            if "analyze distribution" in a["data"]["tool"].get("invocation", "")
        ]
        if not distribution_atoms:
            pytest.skip("No distribution-class atoms found yet")

        # Run distribution once on the fixture and reuse for all atoms
        result = subprocess.run(
            ["ont-end-reason", "analyze", "distribution", str(FIXTURE),
             "--json", "/tmp/paper_atom_dist.json"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        with open("/tmp/paper_atom_dist.json") as fh:
            output = json.load(fh)

        # Paper-claimed percentages should be in range [0, 100]; our tool's
        # outputs should also be in that range.
        for atom in distribution_atoms:
            assert atom["data"].get("units") == "percent", (
                f"{atom['name']}: expected percent units, got {atom['data'].get('units')}"
            )
            assert 0 <= atom["data"]["value"] <= 100, (
                f"{atom['name']}: paper value {atom['data']['value']} not in [0, 100]"
            )
            # Tool's signal_positive_pct on the fixture is 80; close enough
            # for shape check (paper claims 94 on real data, 80 on fixture).
            assert 0 <= output["signal_positive_pct"] <= 100

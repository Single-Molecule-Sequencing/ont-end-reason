"""Reproducibility tests against end-reason-paper claim atoms.

The SECOND half of issue #4 — scheduled to activate once end-reason-paper
repins its claim atoms to a specific ont-end-reason version.

Today, end-reason-paper's claim atoms (results.alignment_rate_filtered,
results.snv_f1_filtered, etc.) pin to the archived End_Reason_Manuscript
commit b47166a. After the paper team repins them to e.g.
`ont-end-reason==0.1.0`, this test suite will:

  1. Clone Single-Molecule-Sequencing/end-reason-paper at the version
     pinned in `tests/reproducibility/paper_pin.yaml`
  2. For each atom in atoms/claims/results.*.yaml that references this
     tool, run the corresponding analysis and assert the produced value
     matches the atom's pinned expected value
  3. Block main-branch merges if any atom drifts

For now the test is skipped — the paper-side pin doesn't exist yet.
The scaffolding lives here so the workflow is well-defined when the
paper team is ready to make the switch.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.reproducibility


@pytest.mark.skip(reason="Paper-side ont-end-reason version pin not yet in place; tracked in issue #4")
def test_paper_claim_atoms_reproducible() -> None:
    """Re-run every paper claim atom and assert bit-identity."""
    # Implementation outline:
    #   1. Read tests/reproducibility/paper_pin.yaml for the paper-version + tool-version pair
    #   2. gh api repos/Single-Molecule-Sequencing/end-reason-paper/contents/atoms/claims @ <ref>
    #   3. For each results.*.yaml atom that references this tool:
    #        - Run the corresponding analysis (atom.tool_invocation field)
    #        - Compare atom.expected_value to the run output
    #   4. Aggregate failures with full diagnostic table
    raise NotImplementedError(
        "Activate once end-reason-paper has repinned its atoms. See issue #4."
    )

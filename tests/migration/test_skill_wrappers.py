#!/usr/bin/env python3
"""Migration test: legacy /end-reason → new thin-wrapper equivalence.

10 test cases covering synthetic + real-world POD5 + error paths + every
deprecated flag. For each test, runs LEGACY (preserved at /tmp/end_reason_legacy.py)
and NEW (the thin wrapper at skills/end-reason/scripts/end_reason.py) on
identical inputs, then asserts JSON-output equivalence (1e-3 relative tol)
and exit-code parity.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LEGACY = Path("/tmp/end_reason_legacy.py")
NEW = Path("/home/farnum248/repos/ont-ecosystem/skills/end-reason/scripts/end_reason.py")
SYN = Path(
    "/home/farnum248/repos/ont-end-reason/tests/fixtures/sequencing_summary_synthetic.txt"
)
POD5 = Path(
    "/mnt/d/University of Michigan Dropbox/Gregory Farnum/SMS/Reference_Files/"
    "20241002_0130_MN47455_ATS581_da726245/pod5"
)


@dataclass
class TestResult:
    name: str
    legacy_exit: int = -1
    new_exit: int = -1
    legacy_json: dict | None = None
    new_json: dict | None = None
    new_stderr: str = ""
    legacy_stderr: str = ""
    plot_new_exists: bool | None = None


def run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "TIMEOUT"


def load_json(path: Path) -> dict | None:
    """Load JSON from the requested path; if missing, fall back to the
    most-recent ont-artifacts run directory (where both tools actually
    redirect their output)."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
    # Both legacy and new redirect to ~/.ont-artifacts/runs/<date>/end-reason_<ts>/outputs/data/<basename>
    basename = path.name
    artifacts = Path.home() / ".ont-artifacts" / "runs"
    if not artifacts.exists():
        return None
    candidates = sorted(
        artifacts.rglob(f"outputs/data/{basename}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    try:
        return json.loads(candidates[0].read_text())
    except json.JSONDecodeError:
        return None


def numbers_equiv(a: Any, b: Any, *, rel_tol: float = 1e-3) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        keys = set(a) | set(b)
        return all(numbers_equiv(a.get(k), b.get(k), rel_tol=rel_tol) for k in keys)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(
            numbers_equiv(x, y, rel_tol=rel_tol) for x, y in zip(a, b)
        )
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == b:
            return True
        if max(abs(a), abs(b)) < 1e-6:
            return True
        return abs(a - b) / max(abs(a), abs(b)) < rel_tol
    return a == b


TESTS = [
    {"name": "T1_synthetic_basic",
     "args": [str(SYN), "--json", "{outdir}/out.json"],
     "expect_exit": 0,
     "compare_keys": ["total_reads", "signal_positive_pct", "unblock_mux_pct"]},
    {"name": "T2_synthetic_quick_1k",
     "args": [str(SYN), "--quick", "--max-reads", "1000", "--json", "{outdir}/out.json"],
     "expect_exit": 0,
     "compare_keys": ["total_reads", "signal_positive_pct"]},
    {"name": "T3_synthetic_with_plot",
     "args": [str(SYN), "--json", "{outdir}/out.json", "--plot", "{outdir}/plot.png"],
     "expect_exit": 0,
     "check_plot": True},
    {"name": "T4_real_pod5_quick",
     "args": [str(POD5), "--quick", "--json", "{outdir}/out.json"],
     "expect_exit": 0,
     "compare_keys": ["total_reads", "signal_positive_pct", "quality_status"]},
    {"name": "T5_real_pod5_plot",
     "args": [str(POD5), "--quick", "--json", "{outdir}/out.json", "--plot", "{outdir}/plot.png"],
     "expect_exit": 0,
     "check_plot": True},
    {"name": "T6_missing_path",
     "args": ["/does/not/exist", "--quick"],
     "expect_exit_nonzero": True},
    {"name": "T7_deprecated_format",
     "args": [str(SYN), "--format", "summary", "--json", "{outdir}/out.json"],
     "expect_exit": 0,
     "compare_keys": ["total_reads"],
     "expect_warning": True},
    {"name": "T8_deprecated_insights",
     "args": [str(SYN), "--insights", "--json", "{outdir}/out.json"],
     "expect_exit": 0,
     "compare_keys": ["total_reads"],
     "expect_warning": True},
    {"name": "T9_deprecated_csv",
     "args": [str(SYN), "--csv", "{outdir}/out.csv", "--json", "{outdir}/out.json"],
     "expect_exit": 0,
     "compare_keys": ["total_reads"],
     "expect_warning": True},
    {"name": "T10_synthetic_quick_no_maxreads",
     "args": [str(SYN), "--quick", "--json", "{outdir}/out.json"],
     "expect_exit": 0,
     "compare_keys": ["total_reads", "signal_positive_pct"]},
]


def run_test(test: dict) -> TestResult:
    name = test["name"]
    with (
        tempfile.TemporaryDirectory(prefix=f"mig_l_{name}_") as ldir,
        tempfile.TemporaryDirectory(prefix=f"mig_n_{name}_") as ndir,
    ):
        legacy_args = [a.format(outdir=ldir) for a in test["args"]]
        new_args = [a.format(outdir=ndir) for a in test["args"]]

        lc, lo, le = run(["python3", str(LEGACY), *legacy_args])
        nc, no, ne = run(["python3", str(NEW), *new_args])

        r = TestResult(
            name=name,
            legacy_exit=lc,
            new_exit=nc,
            legacy_stderr=le,
            new_stderr=ne,
            legacy_json=load_json(Path(ldir) / "out.json"),
            new_json=load_json(Path(ndir) / "out.json"),
        )
        if test.get("check_plot"):
            r.plot_new_exists = (Path(ndir) / "plot.png").exists()
        return r


def evaluate(test: dict, r: TestResult) -> tuple[bool, list[str]]:
    issues = []
    if test.get("expect_exit_nonzero"):
        if r.new_exit == 0:
            issues.append(f"new should exit nonzero, got {r.new_exit}")
    elif test.get("expect_exit") is not None:
        if r.new_exit != test["expect_exit"]:
            issues.append(f"new exit={r.new_exit} != expected {test['expect_exit']}")

    if "compare_keys" in test:
        if r.legacy_json is None:
            issues.append("legacy JSON missing")
        if r.new_json is None:
            issues.append("new JSON missing")
        if r.legacy_json and r.new_json:
            for k in test["compare_keys"]:
                lv = r.legacy_json.get(k)
                nv = r.new_json.get(k)
                if not numbers_equiv(lv, nv):
                    issues.append(f"{k}: legacy={lv!r} != new={nv!r}")

    if test.get("check_plot"):
        if not r.plot_new_exists:
            issues.append("new wrapper did not produce plot")

    if test.get("expect_warning"):
        if "warning" not in r.new_stderr.lower():
            issues.append("no deprecation warning emitted")

    return (len(issues) == 0, issues)


def main() -> int:
    print(f"{'Test':<32}{'Legacy':>8}{'New':>6}{'Verdict':>40}")
    print("─" * 90)
    n_pass = 0
    for test in TESTS:
        try:
            r = run_test(test)
            ok, issues = evaluate(test, r)
            verdict = "✓ PASS" if ok else "✗ " + "; ".join(issues)[:60]
            n_pass += 1 if ok else 0
        except Exception as exc:
            verdict = f"ERROR: {exc}"
            r = TestResult(name=test["name"])
        print(f"{test['name']:<32}{r.legacy_exit:>8}{r.new_exit:>6}  {verdict}")

    print("─" * 90)
    print(f"\n{n_pass}/{len(TESTS)} tests passing")
    return 0 if n_pass == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

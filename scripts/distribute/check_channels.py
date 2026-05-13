#!/usr/bin/env python3
"""Pre-submission preflight: verify every dependency resolves on a target conda channel.

VENDORED COPY — do not edit in this repo.
==========================================

Canonical source: `lab-papers/scripts/distribute/check_channels.py`
(github.com/Single-Molecule-Sequencing/lab-papers, private repo).

The lab-papers repo is private, so we can't `curl` the raw URL from a
public CI job (release.yml runs unauthenticated). This vendored snapshot
mirrors the canonical script verbatim. To refresh:

    cp ~/repos/lab-papers/scripts/distribute/check_channels.py \\
       scripts/distribute/check_channels.py

Re-verify after refresh: `python scripts/distribute/check_channels.py \\
    --pyproject pyproject.toml --target bioconda --verbose`.

This is the same "vendored snapshot" pattern lab-papers paper-template uses
for `.lab-papers/` (per `lab-papers/CLAUDE.md` "vendored orchestrator
snapshot — no PAT needed"). Drift risk is bounded because the canonical
script is small and stable; the adoption-dashboard `check_channels`
detector grep hits this file the same way it would hit the canonical
import path, so the dogfood metric is preserved.

Memory entries:
- `feedback_public_repo_cant_call_private_reusable_workflow.md`
- `feedback_bioconda_vs_conda_forge_channel_selection.md`

Usage
-----
    python scripts/distribute/check_channels.py \\
        --pyproject /path/to/pyproject.toml \\
        --target {bioconda|conda-forge}

Exit codes
----------
    0 — every runtime dependency is available on the target channel
    1 — one or more dependencies are missing (printed to stderr)
    2 — bad arguments / unreadable pyproject

Origin
------
Caught the bioconda PR #33317 incident on 2026-05-12: ont-end-reason
was submitted to conda-forge but its runtime deps (pod5, pysam) are
bioconda-only. Builds failed on all 3 platforms. conda-forge's linter
PASSED (recipe metadata is fine), so the failure wasn't caught
pre-submission. This script makes that gap a 30-second check.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path

# Map PyPI canonical → bioconda canonical when they differ (most match
# 1:1; this dict handles the exceptions documented in
# bioconda-recipes/recipes/README.md).
_PYPI_TO_BIOCONDA_RENAME = {
    "matplotlib": "matplotlib-base",  # bioconda alias
    "numpy": "numpy",
    "scipy": "scipy",
    "pandas": "pandas",
    "click": "click",
    "structlog": "structlog",
    "pyyaml": "pyyaml",
    "jinja2": "jinja2",
    "tabulate": "tabulate",
    "pysam": "pysam",
    "pod5": "pod5",
}


def parse_pyproject_run_deps(pyproject_path: Path) -> list[str]:
    """Return `dependencies = [...]` entries from PEP 621 [project]."""
    text = pyproject_path.read_text(encoding="utf-8")
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[import-not-found]
        except ImportError:
            sys.exit("tomllib (Py3.11+) or tomli (Py<3.11) is required")
    data = tomllib.loads(text)
    deps = (data.get("project") or {}).get("dependencies") or []
    if not isinstance(deps, list):
        sys.exit(f"Unexpected [project.dependencies] shape: {type(deps).__name__}")
    return list(deps)


_PKG_NAME_RE = re.compile(r"^([A-Za-z0-9_.-]+)")


def package_name(dep_spec: str) -> str:
    """Strip version spec from `pkg>=1.0,<2` etc."""
    match = _PKG_NAME_RE.match(dep_spec.strip())
    return match.group(1) if match else dep_spec.strip()


def _probe(pkg: str, channel: str) -> bool:
    url = f"https://api.anaconda.org/package/{channel}/{pkg}"
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        return exc.code == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def resolve_on_channel(pkg: str, channel: str) -> bool:
    """Probe anaconda.org for `pkg` on `channel` + permitted fallbacks.

    bioconda recipes resolve against `bioconda + conda-forge + defaults`
    (the bioconda channel-policy default), so a dep that lives on
    conda-forge resolves fine in a bioconda recipe.

    conda-forge recipes resolve against `conda-forge + defaults` only —
    no bioconda fallback (channel-purity policy).
    """
    if channel == "bioconda":
        target = _PYPI_TO_BIOCONDA_RENAME.get(pkg, pkg)
        if _probe(target, "bioconda"):
            return True
        return _probe(pkg, "conda-forge")
    if channel == "conda-forge":
        return _probe(pkg, "conda-forge")
    return _probe(pkg, channel)


def check(pyproject: Path, target: str, *, verbose: bool = False) -> int:
    deps = parse_pyproject_run_deps(pyproject)
    if not deps:
        print(f"{pyproject}: no runtime dependencies declared.")
        return 0

    missing: list[str] = []
    for dep in deps:
        pkg = package_name(dep)
        if pkg in {"python"}:
            continue
        ok = resolve_on_channel(pkg, target)
        if verbose:
            print(f"  [{'✓' if ok else '✗'}] {pkg:<30} on {target}")
        if not ok:
            missing.append(pkg)

    if missing:
        print(
            f"\nFAIL — {len(missing)} dep(s) missing on '{target}':",
            file=sys.stderr,
        )
        for m in missing:
            print(f"  • {m}", file=sys.stderr)
        if target == "conda-forge":
            print(
                "\nHint: if these are bioinformatics packages (pysam, pod5, samtools, "
                "minimap2, ...), submit to bioconda-recipes instead.",
                file=sys.stderr,
            )
        return 1

    print(f"\nOK — all {len(deps)} dependencies resolve on '{target}'.")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml (default: ./pyproject.toml)",
    )
    ap.add_argument(
        "--target",
        choices=("bioconda", "conda-forge"),
        default="bioconda",
        help="Channel to check against",
    )
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if not args.pyproject.is_file():
        print(f"not found: {args.pyproject}", file=sys.stderr)
        return 2

    return check(args.pyproject, args.target, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())

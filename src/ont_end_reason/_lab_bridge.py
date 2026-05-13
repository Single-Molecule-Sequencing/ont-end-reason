"""Bridge to lab-papers' canonical `cross_repo_import` helper.

ont-end-reason consumes two pieces of lab-canonical infrastructure that
live in sister repos:

  * `lib.bam_shard` (ont-ecosystem) — BGZF virtual-offset shard partition
  * `lib.qc_baseline` (ont-ecosystem) — cross-run QC store + atlas helpers

The lab's canonical helper for importing sister-repo modules is
`lab-papers/scripts/utils/cross_repo_import.py::import_lab_module`. This
module bootstraps that helper from lab-papers when available, falling back
to an inline reimplementation when lab-papers isn't on disk.

Why a bridge module: it's the one piece that has to know where the lab's
canonical homes live. After this bridge runs, both `filter/filter.py` and
`analyze/atlas.py` import sister-repo modules through the same canonical
`import_lab_module` API rather than copy-pasting sys.path dances.

Spec: `lab-papers/docs/IMPROVEMENT-VERIFICATION-2026-05-12-tier2-promotions.md`
Companion memory: `feedback_dogfood_from_source_paper.md`
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Optional


def _inline_import_lab_module(
    module_name: str,
    *,
    repo: str,
    lib_subdir: Optional[str] = "lib",
    repos_root: Optional[Path] = None,
) -> Optional[ModuleType]:
    """Fallback identical to lab-papers' `cross_repo_import.import_lab_module`.

    Used only when lab-papers itself isn't cloned. Stays in sync with the
    canonical signature so consumers don't branch on which path was taken.
    """
    try:
        return __import__(module_name)
    except ImportError:
        pass
    root = repos_root or (Path.home() / "repos")
    sister = root / repo
    if not sister.is_dir():
        return None
    target = sister / lib_subdir if lib_subdir else sister
    target_str = str(target)
    inserted = False
    if target_str not in sys.path:
        sys.path.insert(0, target_str)
        inserted = True
    try:
        return __import__(module_name)
    except ImportError:
        if inserted:
            try:
                sys.path.remove(target_str)
            except ValueError:
                pass
        return None


def _load_canonical_importer():
    """Try to load lab-papers' `cross_repo_import.import_lab_module`.

    Returns the canonical callable, or our inline fallback when lab-papers
    isn't reachable. Either way, callers get a function with the same
    signature as `scripts.utils.cross_repo_import.import_lab_module`.
    """
    candidate = Path.home() / "repos" / "lab-papers" / "scripts" / "utils"
    if candidate.is_dir():
        candidate_str = str(candidate)
        inserted = False
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
            inserted = True
        try:
            from cross_repo_import import import_lab_module  # type: ignore[import-not-found]

            return import_lab_module
        except ImportError:
            if inserted:
                try:
                    sys.path.remove(candidate_str)
                except ValueError:
                    pass
    return _inline_import_lab_module


import_lab_module = _load_canonical_importer()


__all__ = ["import_lab_module"]

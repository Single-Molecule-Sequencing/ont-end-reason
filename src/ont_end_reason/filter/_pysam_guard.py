"""Centralised import guard for the filter subpackage.

pysam has no Windows wheel (htslib doesn't ship one upstream), so the
filter / tag / export subcommands cannot run on Windows. This helper makes
the failure mode obvious and actionable rather than dumping a bare
``ImportError`` traceback.
"""

from __future__ import annotations

import platform
from typing import Any

from ..errors import IOError as OntIOError

_HPC_HINT = (
    "Two options on Windows:\n"
    "\n"
    "  (1) Run locally via the bundled Docker wrapper (Docker Desktop required):\n"
    "        python <repo>/docker/ont-end-reason-docker.py <subcommand> [args...]\n"
    "      First run builds a ~320 MB Linux image with pysam pre-installed;\n"
    "      subsequent runs are instant. Bind-mounts cwd to /data automatically.\n"
    "\n"
    "  (2) Run on Great Lakes HPC:\n"
    "        ssh gregfar@greatlakes.arc-ts.umich.edu\n"
    "        module load Bioinformatics samtools && conda activate ont-bio\n"
    "        ont-end-reason <subcommand> ...\n"
    "\n"
    "Or use the lab `ont-bio` conda env on any Linux/macOS host."
)

_POSIX_HINT = (
    "Install with the filter extra to enable pysam-backed subcommands:\n"
    "    pip install -e '.[filter]'\n"
    "(or `pip install 'ont-end-reason[filter]'` for a non-editable install)."
)


def require_pysam() -> Any:
    """Import and return ``pysam`` or raise OntIOError with a useful hint.

    Returns
    -------
    module
        The imported ``pysam`` module.

    Raises
    ------
    OntIOError
        With OS-aware remediation guidance if pysam is unavailable.
    """
    try:
        import pysam  # type: ignore[import-untyped]
    except ImportError as exc:
        hint = _HPC_HINT if platform.system() == "Windows" else _POSIX_HINT
        raise OntIOError(
            "pysam is required for tag / filter / export-fastq subcommands "
            "but is not installed.\n\n" + hint
        ) from exc
    return pysam

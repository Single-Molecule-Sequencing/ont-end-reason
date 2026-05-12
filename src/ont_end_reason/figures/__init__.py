"""figures subpackage — paper-figure reproducers.

Each function in this subpackage produces a single named figure from the
end-reason paper. They compose `analyze.*` and `viz.*` internally and emit
publication-ready PDFs.

v0.1.0 STATUS: scaffold only. Each function raises NotImplementedError with
a pointer to the source. Fill-in is v0.2.0+ work tracked in GitHub issues.
"""

from __future__ import annotations

from .fig3_distribution import fig3_distribution
from .fig5_violin import fig5_violin
from .fig6_conceptual import fig6_conceptual
from .supplementary import supplementary

__all__ = ["fig3_distribution", "fig5_violin", "fig6_conceptual", "supplementary"]

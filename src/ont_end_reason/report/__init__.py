"""report subpackage — composed multi-analysis reports.

Two output modes:

  static (PDF)       → matplotlib-backed, deterministic, archive-quality
  interactive (HTML) → Plotly-backed, self-contained single .html file

Both compose `analyze.*` and `viz.*` results into a single artefact suitable
for sharing or paper supplementary materials.
"""

from __future__ import annotations

from .html import HtmlReport, build_html_report

__all__ = ["HtmlReport", "build_html_report"]

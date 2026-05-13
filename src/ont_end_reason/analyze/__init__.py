"""analyze subpackage — 8 analysis modules covering the paper's 15 TOOL_SPEC types.

v0.1.0 scope contract (see docs/superpowers/specs/2026-05-12-design.md):

  Module           v0.1   Description
  ---------------  -----  -----------------------------------------------------
  distribution     FULL   End-reason counts, percentages, OK/CHECK/FAIL gate
  length           STUB   Length distributions per end_reason (TOOL_SPEC 4)
  quality          STUB   GMM Q-score fitting (TOOL_SPEC 5)
  temporal         STUB   Temporal pattern analysis (TOOL_SPEC 6)
  signal_trace     STUB   Raw signal extraction + viz (TOOL_SPEC 3)
  hypothesis       STUB   Statistical hypothesis tests (TOOL_SPEC 10)
  umc_posterior    STUB   Posterior length model for UMC reads (TOOL_SPEC 11)
  sma_metrics      STUB   SMA metrics delegate (TOOL_SPEC 15)
  tables           STUB   Table generation (TOOL_SPEC 12/13)

STUB modules ship with the full Python API surface and dataclass return
types, raising `NotImplementedError` with a pointer to the originating
paper script. Filling them in is v0.2.0+ work.
"""

from __future__ import annotations

from .atlas import AtlasResult, OutlierRecord, StratumStats, atlas
from .distribution import DistributionResult, distribution
from .hypothesis import HypothesisResult, hypothesis
from .length import LengthResult, length
from .quality import QualityResult, quality
from .signal_trace import SignalTraceResult, signal_trace
from .sma_metrics import SmaMetricsResult, sma_metrics
from .tables import TableResult, generate_tables
from .temporal import TemporalResult, temporal
from .umc_posterior import UMCPosteriorResult, umc_posterior

__all__ = [
    "AtlasResult",
    "DistributionResult",
    "HypothesisResult",
    "LengthResult",
    "OutlierRecord",
    "QualityResult",
    "SignalTraceResult",
    "SmaMetricsResult",
    "StratumStats",
    "TableResult",
    "TemporalResult",
    "UMCPosteriorResult",
    # full
    "atlas",
    "distribution",
    "generate_tables",
    "hypothesis",
    # scaffolds
    "length",
    "quality",
    "signal_trace",
    "sma_metrics",
    "temporal",
    "umc_posterior",
]

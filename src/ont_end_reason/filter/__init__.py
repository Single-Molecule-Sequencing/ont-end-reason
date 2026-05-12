"""filter subpackage — BAM tagging, filtering, FASTQ export.

Public surface:

    from ont_end_reason.filter import (
        tag_bam,           # add end_reason tags from sequencing_summary
        filter_bam,        # keep/drop reads by end_reason tag
        export_fastq,      # write filtered BAM as FASTQ
    )

Behaviour matches the original `End_Reason_Manuscript/pipeline/bin/` scripts
at commit b47166a (preserved for paper reproducibility).
"""

from __future__ import annotations

from .export import export_fastq
from .filter import filter_bam
from .tag import tag_bam

__all__ = ["tag_bam", "filter_bam", "export_fastq"]

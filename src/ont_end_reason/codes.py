"""End reason code taxonomy — single source of truth.

The lab uses 7 standard 2-4 letter abbreviations across all filtering and
analysis tools. This module is the SSOT for the full-name ↔ abbreviation
mapping and the keep/truncated/failed/unknown classification.

Reference: end-reason-paper Table 1 (in preparation) and the canonical
tutorial at:
  Single-Molecule-Sequencing/End_Reason_Manuscript/docs/tutorials/
  02-end-reason-filtering.md
"""

from __future__ import annotations

from typing import Final

# Full ONT name → short code (used in BAM tags, atom YAML, CLI args)
CODES: Final[dict[str, str]] = {
    "signal_positive": "SP",
    "unblock_mux_change": "UMC",
    "mux_change": "MC",
    "signal_negative": "SN",
    "data_service_unblock_mux_change": "DUMC",
    "unknown": "UNK",
    "partial": "PART",
}

# Reverse: short code → full name (for human-readable output)
NAMES: Final[dict[str, str]] = {short: full for full, short in CODES.items()}

# Recommended-keep set per the canonical paper (Table 1). UMC may be kept for
# artefact studies but is filtered by default for any quantitative downstream.
RECOMMENDED_KEEP: Final[frozenset[str]] = frozenset({"SP"})

# Reads with these end_reasons are usable but truncated; keep only if you
# explicitly want to study what was rejected.
TRUNCATED: Final[frozenset[str]] = frozenset({"UMC", "MC", "DUMC", "PART"})

# Reads with these end_reasons should ALWAYS be filtered.
FAILED: Final[frozenset[str]] = frozenset({"SN"})

# Reason was not recorded — investigate, don't auto-filter.
UNKNOWN_STATES: Final[frozenset[str]] = frozenset({"UNK"})


def parse_keep_list(spec: str) -> set[str]:
    """Parse `--keep SP,UMC` into a set of validated short codes.

    Accepts either short codes (SP) or full names (signal_positive) in any
    case, comma- or whitespace-separated. Raises ValueError on unknown codes
    so callers fail fast rather than silently dropping reads.

    >>> sorted(parse_keep_list("SP,UMC"))
    ['SP', 'UMC']
    >>> sorted(parse_keep_list("signal_positive unblock_mux_change"))
    ['SP', 'UMC']
    >>> parse_keep_list("")
    set()
    """
    if not spec:
        return set()
    out: set[str] = set()
    for token in spec.replace(",", " ").split():
        t = token.strip()
        if not t:
            continue
        if t.upper() in NAMES:
            out.add(t.upper())
        elif t.lower() in CODES:
            out.add(CODES[t.lower()])
        else:
            raise ValueError(
                f"Unknown end_reason code: {t!r}. "
                f"Valid: {sorted(NAMES)} or full names {sorted(CODES)}"
            )
    return out


def to_short(name_or_code: str) -> str:
    """Coerce either a full name or short code to the short code form.

    >>> to_short("signal_positive")
    'SP'
    >>> to_short("sp")
    'SP'
    """
    s = name_or_code.strip()
    if s.upper() in NAMES:
        return s.upper()
    if s.lower() in CODES:
        return CODES[s.lower()]
    raise ValueError(f"Unknown end_reason: {name_or_code!r}")


def to_full(name_or_code: str) -> str:
    """Coerce either a full name or short code to the full ONT name.

    >>> to_full("SP")
    'signal_positive'
    >>> to_full("signal_positive")
    'signal_positive'
    """
    s = name_or_code.strip()
    if s.lower() in CODES:
        return s.lower()
    if s.upper() in NAMES:
        return NAMES[s.upper()]
    raise ValueError(f"Unknown end_reason: {name_or_code!r}")


def classify(code: str) -> str:
    """Return the class of an end_reason code: keep / truncated / failed / unknown."""
    short = to_short(code)
    if short in RECOMMENDED_KEEP:
        return "keep"
    if short in TRUNCATED:
        return "truncated"
    if short in FAILED:
        return "failed"
    return "unknown"

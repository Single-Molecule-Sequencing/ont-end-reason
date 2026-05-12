"""Allow `python -m ont_end_reason` invocation in addition to the entry point."""

from __future__ import annotations

from ont_end_reason.cli import main

if __name__ == "__main__":
    main()

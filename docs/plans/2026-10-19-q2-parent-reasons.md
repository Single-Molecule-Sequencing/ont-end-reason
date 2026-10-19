# Q2 parent end-reason repair

Extend the official ont-end-reason package, preserving its summary-only tag command.
Add `tag-pod5`: stream existing POD5 metadata semantics into a disk-backed ID map;
resolve split reads through valid UUID pi, otherwise their own raw UUID. Refuse
missing parents, conflicting source IDs and known conflicting tags. Preserve native
tags, write canonical ER and count unknown native tags resolved through raw metadata.
The raw parent is authoritative; child unknown is not a biological disagreement.
Duplicate identical source IDs are counted; conflicting duplicates refuse.

Normalize filter values and keep-set members through the existing code taxonomy
in sequential and parallel execution. Missing or invalid selected tags refuse;
UNK is a measured category, retained only when explicitly requested. Write new
outputs exclusively after full success, preserving originals and refusing collisions.

Tests: tiny actual POD5/BAM fixtures, pi inheritance, native/canonical normalization,
missing/invalid/conflicting identities, duplicate sources, empty input, source drift,
original preservation, sequential/shard equivalence, CLI and legacy regressions.
Validate bounded real metadata only; this scope does not authorize a full run.
Retain source-bound workflow comparison, merge/deployment and executed controls.

Implementation and review by Codex. Current method validation does not prove any
historical Q2 processing. Root reviews exact diff before canonical landing.

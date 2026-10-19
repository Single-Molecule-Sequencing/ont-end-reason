# POD5 parent-aware end-reason tagging

`ont-end-reason tag-pod5 --pod5 RAW --bam INPUT.bam --out NEW.bam`
adds canonical `ER` short codes from raw POD5 metadata. RAW is one POD5 file or
a directory searched recursively. Metadata streams into a disk-backed lookup
beside the output; signal arrays are not decoded. Run production-sized work in
the lab's bounded Great Lakes workflow, with output and temporary storage on Turbo.

For a split simplex read, `pi` must be a UUID found in the raw source. Without
`pi`, the read's own UUID must be found. No filename, summary child-ID overlap,
or multi-hop ancestry inference is used. Duplex (`dx=1`) and ambiguous `dx`
values are refused; absent `dx`, 0 and -1 describe supported simplex records.
An ID simultaneously present as a raw child and a different raw parent is refused.
Identical duplicate source IDs are counted; conflicting reasons refuse the run.
Every BAM record is retained, including repeated IDs and alignment flags.

The native lowercase `er` is preserved. A native or prior canonical `UNK` may be
resolved from the raw parent, but a known disagreement with the raw reason refuses
the output. Malformed tags and missing raw parents refuse the output too. An actual
raw `unknown` remains `ER=UNK`, never `SP`. The command reports input/tagged counts,
inherited records, resolved native unknowns, duplicate and unique source IDs, and
records whose raw reason is unknown. These counts are not a biological accuracy claim.

`ont-end-reason filter --bam NEW.bam --out SP.bam --keep SP` uses the same taxonomy
for native long names and canonical short codes in both sequential and parallel
paths. Set-valued API keep lists are normalized too. The selected tag defaults to
`ER`; choose `--tag-name er` only when deliberately filtering native tags. Missing
or invalid selected tags now refuse filtering instead of silently dropping records.
`UNK` is a valid category and is retained only if explicitly included in `--keep`.

Both operations publish a new output only after successful traversal. Existing
destinations, including the input path, are refused; a late failure leaves no final
output. Source metadata stability is checked. The execution wrapper remains
responsible for full input/output checksums, raw-run identity, resources and receipts.
The legacy `tag --summary ...` command remains summary read-ID matching only and is
not a substitute for this parent-aware method.

This method repair was validated with tiny synthetic POD5/BAM fixtures. It does not
establish that a historical run was filtered, and does not authorize or claim a new
full-run filtering execution.

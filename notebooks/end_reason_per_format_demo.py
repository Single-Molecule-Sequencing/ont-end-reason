"""end_reason_per_format_demo.py — verified, runnable demonstrations.

Pulls a tiny real file (or fixture) for each ONT data format and runs
the canonical readers from `ont_end_reason.io.readers`. Surfaces both
successes and the bugs discovered during the 2026-05-15 audit.

Run:
    python notebooks/end_reason_per_format_demo.py

Outputs:
    notebooks/_runs/<timestamp>/per_format_results.json
    notebooks/_runs/<timestamp>/per_format_dashboard.html

The dashboard auto-opens in your default browser on Windows / macOS.
"""

from __future__ import annotations

import datetime
import json
import platform
import subprocess
import sys
import urllib.request
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ont_end_reason.codes import CODES  # noqa: E402
from ont_end_reason.io.readers import (  # noqa: E402
    detect_format,
    extract_from_fast5,
    extract_from_pod5,
    extract_from_summary,
)

NS = "https://ont-open-data.s3.amazonaws.com"

# Reproducible per-format sources. Pinned by full URL so a single run is
# byte-identical day to day.
SOURCES = {
    "pod5": {
        "url": f"{NS}/compost_mgx_2026.04/raw/20240723_1746_4B_PAW53533_f802c0cd/pod5_skip/PAW53533_skip_f802c0cd_17e0d854_17.pod5",
        "filename": "sample.pod5",
        "fetch_bytes": None,  # full file (18 KB)
        "notes": (
            "Tiny adaptive-sampling 'skip' pod5 from compost_mgx_2026.04. "
            "One read, signal_positive."
        ),
    },
    "multi-fast5": {
        "url": f"{NS}/gm24385_mod_2021.09/flowcells/20210510_1127_X4_FAQ32498_b90eaed8/fast5_fail/FAQ32498_fail_09083b73_17.fast5",
        "filename": "sample_multi.fast5",
        "fetch_bytes": None,  # 27 MB — small enough
        "notes": (
            "GM24385 fail-bin multi-fast5, Guppy 4.0.11. 271 reads. "
            "EXPOSES INTEGER-CODE LEAK BUG (see results)."
        ),
    },
    "summary": {
        "url": f"{NS}/gm24385_2020.09/analysis/r10.3/20200914_1356_6F_PAF26223_da14221a/guppy_v4.0.11_r10.3_hac_prom/sequencing_summary.txt",
        "filename": "sequencing_summary_demo.txt",
        "fetch_bytes": 50 * 1024 * 1024,  # 50 MB slice ≈ 122k reads
        "notes": (
            "First 50 MB of a 948 MB summary; trimmed to last newline so no "
            "partial row. Filename MUST start with 'sequencing_summary' or "
            "detect_format() rejects it."
        ),
    },
    # single-fast5 and bulk-fast5 are synthesized from local material because
    # ont-open-data hasn't shipped either format in any prefix sampled
    # 2026-05-15.
    "single-fast5": {
        "synthesize_from": "multi-fast5",
        "filename": "sample_single.fast5",
        "notes": (
            "Synthesized by copying ONE group from the multi-fast5 fixture. "
            "Structurally valid single-read fast5."
        ),
    },
    "bulk-fast5": {
        "synthesize": "bulk",
        "filename": "sample_bulk.fast5",
        "notes": (
            "Synthesized to canonical MinKNOW bulk layout (UniqueGlobalKey, "
            "IntermediateData/Channel_N/Reads, Raw/Channel_N/Signal). "
            "Demonstrates that detect_format() silently mis-classifies bulk "
            "as 'fast5' and extract_from_fast5 returns 0 records — no error."
        ),
    },
}


def fetch_url(url: str, dest: Path, byte_limit: int | None = None) -> None:
    """Download `url` to `dest`. If `byte_limit` is set, fetch a Range slice
    and trim to the last newline (so no partial row at EOF).
    """
    if dest.exists() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url)
    if byte_limit is not None:
        req.add_header("Range", f"bytes=0-{byte_limit - 1}")
    with urllib.request.urlopen(req) as r:
        data = r.read()
    if byte_limit is not None:
        # Trim to last full line — required for sequencing_summary.txt slices.
        last_nl = data.rfind(b"\n")
        if last_nl >= 0:
            data = data[: last_nl + 1]
    dest.write_bytes(data)


def synthesize_single_fast5(src: Path, dst: Path) -> None:
    """Copy the first read group out of a multi-fast5 to make a 1-read fast5."""
    import h5py

    with h5py.File(src, "r") as fin, h5py.File(dst, "w") as fout:
        for k, v in fin.attrs.items():
            fout.attrs[k] = v
        first = list(fin.keys())[0]
        fin.copy(first, fout, name="read")


def synthesize_bulk_fast5(dst: Path) -> None:
    """Build a structurally canonical bulk-fast5 (no per-read end_reason)."""
    import h5py
    import numpy as np

    with h5py.File(dst, "w") as f:
        f.attrs["file_type"] = b"bulk"
        f.attrs["file_version"] = b"1.0"
        gk = f.create_group("UniqueGlobalKey")
        tid = gk.create_group("tracking_id")
        tid.attrs["device_id"] = b"GA10000"
        tid.attrs["flow_cell_id"] = b"FAQ32498"
        tid.attrs["protocol_run_id"] = b"09083b73-2971-28b4-f95c-d6a85079a8a0"
        tid.attrs["sample_id"] = b"gm24385"
        tid.attrs["exp_start_time"] = b"2021-05-10T11:27:00Z"
        ctx = gk.create_group("context_tags")
        ctx.attrs["sequencing_kit"] = b"sqk-lsk109"
        ctx.attrs["flowcell_type"] = b"FLO-MIN106"
        interm = f.create_group("IntermediateData")
        for ch in (1, 2, 3):
            cg = interm.create_group(f"Channel_{ch}")
            states = cg.create_group("Reads")
            states.create_dataset("read_start", data=np.array([100, 500, 1200], dtype="i8"))
            states.create_dataset("read_length", data=np.array([400, 700, 300], dtype="i8"))
        raw = f.create_group("Raw")
        for ch in (1, 2, 3):
            rcg = raw.create_group(f"Channel_{ch}")
            rcg.create_dataset("Signal", data=np.random.randint(50, 200, size=2000, dtype="i2"))


def run_extraction(fmt: str, path: Path) -> dict:
    """Run the canonical reader for `fmt` against `path`; capture outcome."""
    out: dict = {"format": fmt, "path": str(path), "size_bytes": path.stat().st_size}
    try:
        out["detect_format"] = detect_format(path)
    except Exception as exc:  # noqa: BLE001
        out["detect_format_error"] = repr(exc)
        return out
    try:
        if fmt == "pod5":
            recs = extract_from_pod5(path, quick=True, max_reads=10_000)
        elif fmt in {"multi-fast5", "single-fast5", "bulk-fast5"}:
            recs = extract_from_fast5(path, quick=True, max_reads=10_000)
        elif fmt == "summary":
            recs = list(extract_from_summary(path, quick=True, max_reads=10_000))
        else:
            raise ValueError(f"unknown fmt {fmt}")
    except Exception as exc:  # noqa: BLE001
        out["extraction_error"] = repr(exc)
        return out
    out["n_records"] = len(recs)
    if recs:
        er_counts = Counter(r.end_reason for r in recs)
        out["end_reason_counts"] = dict(er_counts.most_common())
        out["short_code_seen"] = sorted({r.end_reason_short for r in recs if r.end_reason_short})
        out["short_code_missing"] = sum(1 for r in recs if r.end_reason_short is None)
        first = recs[0]
        out["first_record"] = {
            "read_id": str(first.read_id)[:48],
            "end_reason": first.end_reason,
            "end_reason_short": first.end_reason_short,
            "source_format": first.source_format,
            "length": getattr(first, "length", None),
            "quality": getattr(first, "quality", None),
        }
    return out


def render_dashboard(results: list[dict], out_html: Path) -> None:
    """Self-contained HTML dashboard with one panel per format + a bug list."""
    rows = []
    for r in results:
        fmt = r["format"]
        size = r.get("size_bytes", 0)
        n = r.get("n_records", "—")
        er = r.get("end_reason_counts", {})
        er_str = ", ".join(f"<code>{k}</code>:{v}" for k, v in er.items()) or "—"
        short = r.get("short_code_seen", [])
        short_str = ", ".join(f"<code>{s}</code>" for s in short) or "—"
        missing = r.get("short_code_missing", 0)
        detect = r.get("detect_format", r.get("detect_format_error", "—"))
        first = r.get("first_record", {})
        first_str = (
            f"<small>read_id=<code>{first.get('read_id', '')}</code>, "
            f"end_reason=<code>{first.get('end_reason', '')}</code>, "
            f"short=<code>{first.get('end_reason_short')}</code></small>"
            if first
            else "—"
        )
        notes = SOURCES.get(fmt, {}).get("notes", "")
        warn = ""
        if r.get("extraction_error"):
            warn = f"<div class='bad'>EXTRACTION ERROR: <code>{r['extraction_error']}</code></div>"
        elif missing and n != "—" and n > 0:
            warn = (
                f"<div class='warn'>WARNING: {missing}/{n} reads have no short-code "
                f"mapping — normaliser leaked raw upstream values</div>"
            )
        elif n == 0:
            warn = (
                "<div class='warn'>WARNING: 0 records extracted — reader ran but "
                "found nothing (bulk-fast5 silent-misdetection pattern)</div>"
            )
        rows.append(f"""
        <section>
          <h2>{fmt}</h2>
          <div class='meta'>{notes}</div>
          <table>
            <tr><th>file size</th><td>{size:,} bytes</td></tr>
            <tr><th>detect_format()</th><td><code>{detect}</code></td></tr>
            <tr><th>records read</th><td>{n}</td></tr>
            <tr><th>end_reason counts</th><td>{er_str}</td></tr>
            <tr><th>short codes seen</th><td>{short_str}</td></tr>
            <tr><th>first record</th><td>{first_str}</td></tr>
          </table>
          {warn}
        </section>
        """)
    body = "\n".join(rows)
    css = """
      body{font-family:-apple-system,Segoe UI,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#222}
      h1{border-bottom:2px solid #444;padding-bottom:6px}
      section{margin:24px 0;padding:14px 18px;border:1px solid #ddd;border-radius:8px;background:#fafafa}
      h2{margin-top:0;color:#0a4d8c}
      .meta{font-size:.9em;color:#555;margin-bottom:10px}
      table{border-collapse:collapse;width:100%;margin:8px 0}
      th{text-align:left;padding:4px 8px;background:#eef;width:30%;vertical-align:top}
      td{padding:4px 8px;vertical-align:top}
      code{background:#eee;padding:1px 5px;border-radius:3px;font-size:.9em}
      .warn{color:#a06200;background:#fff3e0;padding:8px;border-left:4px solid #d97706;margin-top:8px;border-radius:4px}
      .bad{color:#a01616;background:#fde2e2;padding:8px;border-left:4px solid #b91c1c;margin-top:8px;border-radius:4px}
      .bugs{background:#fff7d6;border:1px solid #d4a700;padding:14px;border-radius:6px}
    """
    bugs_html = """
    <section class='bugs'>
      <h2>Bugs surfaced by this demonstration (2026-05-15)</h2>
      <ol>
        <li><strong>Integer end_reason codes leak through <code>_normalise_end_reason</code>.</strong>
            Guppy 4.x multi-fast5 stores <code>end_reason</code> as int (e.g. 5, 3, 6).
            The current normaliser only handles strings + enum members.
            Fix: add a numeric→name table to <code>codes.py</code> and call it
            from <code>_normalise_end_reason</code> when input is an int / np.integer.</li>
        <li><strong>Multi-fast5 read_id has stray <code>read_</code> prefix.</strong>
            <code>readers.py</code> falls back to the HDF5 group name when
            <code>grp.attrs['read_id']</code> is missing — but the canonical
            <code>read_id</code> lives in the <code>Raw</code> subgroup attrs.
            Fix: try <code>grp['Raw'].attrs.get('read_id')</code> before the
            group-name fallback.</li>
        <li><strong>bulk-fast5 is silently mis-detected as 'fast5'</strong> and
            <code>extract_from_fast5</code> returns 0 records with no warning.
            Fix: in <code>detect_format</code> or the reader, probe for
            <code>UniqueGlobalKey/tracking_id</code> + absence of
            <code>read_*</code> top groups → raise
            <code>OntIOError("bulk-fast5 has no per-read end_reason; re-basecall first")</code>.</li>
        <li><strong><code>sequencing_summary</code> detection is filename-only.</strong>
            A summary file renamed to anything not starting with
            <code>sequencing_summary</code> fails detect_format. Already
            documented; consider content-sniffing as a fallback.</li>
      </ol>
    </section>
    """
    html = f"""<!doctype html>
    <html><head><meta charset='utf-8'><title>ont-end-reason: per-format demo</title>
    <style>{css}</style></head><body>
    <h1>End-reason extraction — per-format demonstration</h1>
    <p class='meta'>Generated {datetime.datetime.now().isoformat(timespec='seconds')}.
    All five formats run against real or canonically-structured fixtures.
    Canonical readers in <code>ont_end_reason.io.readers</code>.</p>
    {body}
    {bugs_html}
    </body></html>"""
    out_html.write_text(html, encoding="utf-8")


def main() -> int:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "notebooks" / "_runs" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    fixtures = out_dir / "fixtures"
    fixtures.mkdir(exist_ok=True)

    # 1. Fetch / synthesize fixtures.
    for fmt, spec in SOURCES.items():
        dest = fixtures / spec["filename"]
        if "url" in spec:
            print(f"[{fmt}] fetching {spec['url'][:80]}...")
            fetch_url(spec["url"], dest, spec.get("fetch_bytes"))
        elif spec.get("synthesize_from") == "multi-fast5":
            src = fixtures / SOURCES["multi-fast5"]["filename"]
            print(f"[{fmt}] synthesizing single-fast5 from multi-fast5")
            synthesize_single_fast5(src, dest)
        elif spec.get("synthesize") == "bulk":
            print(f"[{fmt}] synthesizing canonical bulk-fast5")
            synthesize_bulk_fast5(dest)
        else:
            raise RuntimeError(f"unhandled source spec: {fmt}")

    # 2. Run extractions and collect outcomes.
    results = []
    for fmt in SOURCES:
        dest = fixtures / SOURCES[fmt]["filename"]
        print(f"[{fmt}] extracting from {dest.name}...")
        results.append(run_extraction(fmt, dest))

    # 3. Persist machine-readable results.
    (out_dir / "per_format_results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )

    # 4. Render dashboard + open in browser.
    out_html = out_dir / "per_format_dashboard.html"
    render_dashboard(results, out_html)
    print(f"\nWrote: {out_html}")

    if platform.system() == "Windows":
        subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process '{out_html}'"])
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(out_html)])
    else:
        # Linux — xdg-open if available, else skip
        try:
            subprocess.Popen(["xdg-open", str(out_html)])
        except FileNotFoundError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""lab_scan_end_reason.py — sweep every registered lab ONT experiment.

For each experiment in ont-registry/experiments.yaml:
  - Resolve its `location` path through the platform path map
    (handles /mnt/d/ → D:/ and Dropbox-style cross-host translation).
  - Look for a sequencing_summary*.txt inside it.
  - If found, run the canonical end_reason extraction
    (per ont-ecosystem/skills/end-reason-extraction-by-format).
  - If not reachable from this host, queue for HPC follow-up.

Outputs:
  notebooks/lab_scans/<ts>/per_experiment_results.json
  notebooks/lab_scans/<ts>/lab_end_reason_dashboard.html
  notebooks/lab_scans/<ts>/hpc_todo.txt

Run:
    python notebooks/lab_scan_end_reason.py
"""

from __future__ import annotations

import datetime
import json
import platform
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    import yaml  # type: ignore
except ImportError:
    print("ERROR: PyYAML required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

from ont_end_reason.codes import CODES  # noqa: E402
from ont_end_reason.errors import IOError as OntIOError  # noqa: E402
from ont_end_reason.io.readers import (  # noqa: E402
    detect_format,
    extract_from_fast5,
    extract_from_pod5,
    extract_from_summary,
)

# Per the new end-reason-extraction-by-format skill: empirically-derived
# int→name table from Guppy 4.0.11 multi-fast5. Provisional per the skill's
# caveat — verify against ground truth before publishing.
_INT_TO_NAME = {
    1: "unknown",
    2: "partial",
    3: "mux_change",
    4: "unblock_mux_change",
    5: "signal_positive",
    6: "data_service_unblock_mux_change",
}


def _decode_int_codes(records):
    for r in records:
        v = r.end_reason
        if isinstance(v, str) and v.isdigit():
            name = _INT_TO_NAME.get(int(v), "unknown")
            r.end_reason = name
            r.end_reason_short = CODES.get(name)
    return records


def _is_bulk_fast5(path) -> bool:
    """Probe for MinKNOW bulk-fast5 (no per-read end_reason)."""
    try:
        import h5py
    except ImportError:
        return False
    try:
        with h5py.File(str(path), "r") as f:
            top = list(f.keys())
            has_bulk = "UniqueGlobalKey" in top and "IntermediateData" in top
            has_per_read = any(k.startswith("read_") for k in top)
            return has_bulk and not has_per_read
    except OSError:
        return False


def translate_path(p: str) -> Path:
    """Map registry paths (mostly Linux/WSL) to whatever resolves on this host.

    Tries, in order:
      1. ~/<...>  → expanduser
      2. /mnt/<letter>/Dropbox/...  → ~/<Dropbox path on this machine>
      3. /mnt/<letter>/...          → <letter>:/... (Windows drive)
      4. otherwise: literal path

    Returns the first candidate that exists; falls back to candidate (3)
    even if absent, so the dashboard still records the canonical mapping.
    """
    if p.startswith("~"):
        return Path(p).expanduser()
    m = re.match(r"^/mnt/([a-z])(/.*)?$", p)
    if m:
        rest = m.group(2) or ""
        # Dropbox / Google Drive cross-host paths
        dropbox_match = re.match(
            r"^/(University of Michigan Dropbox/[^/]+)(/.*)?$", rest
        )
        gdrive_match = re.match(r"^/Google_Drive_umich(/.*)?$", rest)
        candidates: list[Path] = []
        if dropbox_match:
            user_subpath = dropbox_match.group(1)
            tail = dropbox_match.group(2) or ""
            candidates.append(Path.home() / user_subpath / tail.lstrip("/"))
        if gdrive_match:
            tail = gdrive_match.group(1) or ""
            for hint in ("My Drive", "GoogleDrive", "Google Drive"):
                candidates.append(Path.home() / hint / tail.lstrip("/"))
        # Windows drive letter (always last-resort)
        candidates.append(Path(f"{m.group(1).upper()}:{rest}"))
        for c in candidates:
            if c.exists():
                return c
        return candidates[-1]
    return Path(p)


def _is_cloud_only(path: Path) -> bool:
    """True if the file is a Dropbox/OneDrive cloud-only placeholder.

    Modern cloud-sync uses FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS (0x00400000)
    on the file — observed on Dropbox-synced SMA-seq summary files
    (e.g. 13.8 GB) where bytes are not on disk. Reading raises Errno 22.
    The older FILE_ATTRIBUTE_OFFLINE (0x1000) covers legacy hierarchical
    storage / older OneDrive states.
    """
    if platform.system() != "Windows":
        return False
    try:
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        return bool(attrs & (0x1000 | 0x00400000))
    except Exception:  # noqa: BLE001
        return False


def find_summary(exp_dir: Path) -> Path | None:
    """Recursive shallow search (depth 4) for a sequencing_summary*.txt."""
    if not exp_dir.exists():
        return None
    # Quick first: direct children + 1 level deep
    for pattern in ("sequencing_summary*.txt", "**/sequencing_summary*.txt"):
        try:
            for hit in exp_dir.glob(pattern):
                if hit.is_file() and hit.stat().st_size > 0:
                    return hit
        except OSError:
            continue
    return None


def find_pod5_dir(exp_dir: Path) -> Path | None:
    """Find a pod5_pass or pod5 directory under exp_dir."""
    if not exp_dir.exists():
        return None
    for cand in ("pod5_pass", "pod5", "POD5"):
        candidate = exp_dir / cand
        if candidate.is_dir() and any(candidate.rglob("*.pod5")):
            return candidate
    # Fallback: any subdir containing pod5
    try:
        for sub in exp_dir.iterdir():
            if sub.is_dir() and any(sub.rglob("*.pod5")):
                return sub
    except OSError:
        return None
    return None


def extract_end_reason(path: Path, max_reads: int = 10_000) -> dict:
    """Canonical extraction per the end-reason-extraction-by-format skill."""
    suffix = path.suffix.lower()
    out: dict = {"path": str(path), "method": None, "n_records": 0}
    # Cloud-only detection — bail before triggering Dropbox/OneDrive hydration
    # (which can be many GB and stall the scan).
    if path.is_file() and _is_cloud_only(path):
        out["error"] = (
            "Dropbox/OneDrive cloud-only file — bytes not on disk. "
            "Right-click → 'Make available offline' (or open in Explorer to "
            "trigger hydration), then re-run."
        )
        out["cloud_only"] = True
        return out
    try:
        if path.is_dir():
            records = extract_from_pod5(path, quick=True, max_reads=max_reads)
            out["method"] = "extract_from_pod5(dir)"
        elif suffix == ".pod5":
            records = extract_from_pod5(path, quick=True, max_reads=max_reads)
            out["method"] = "extract_from_pod5"
        elif suffix == ".fast5":
            if _is_bulk_fast5(path):
                out["error"] = "bulk-fast5 — no per-read end_reason"
                return out
            records = extract_from_fast5(path, quick=True, max_reads=max_reads)
            records = _decode_int_codes(records)
            out["method"] = "extract_from_fast5 + decode_int_codes"
        elif path.name.startswith("sequencing_summary") or "summary" in path.name.lower():
            records = list(extract_from_summary(path, quick=True, max_reads=max_reads))
            out["method"] = "extract_from_summary"
        else:
            out["error"] = f"unknown format: {suffix}"
            return out
    except OntIOError as exc:
        out["error"] = repr(exc)
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    out["n_records"] = len(records)
    missing = sum(1 for r in records if r.end_reason_short is None)
    out["short_code_missing"] = missing
    if missing == 0 and records:
        counts = Counter(r.end_reason_short for r in records)
        out["distribution_short"] = dict(counts.most_common())
        out["sp_fraction"] = counts.get("SP", 0) / len(records)
        out["umc_fraction"] = (counts.get("UMC", 0) + counts.get("DUMC", 0)) / len(records)
    elif missing:
        out["error"] = f"normaliser leaked {missing}/{len(records)} reads — do not report"
    return out


def classify_status(extraction: dict) -> str:
    """OK / CHECK / FAIL gate per end_reason QC convention."""
    if extraction.get("cloud_only"):
        return "CLOUD_ONLY"
    if extraction.get("error") or "sp_fraction" not in extraction:
        return "ERROR"
    sp = extraction["sp_fraction"]
    if sp >= 0.75:
        return "OK"
    if sp >= 0.50:
        return "CHECK"
    return "FAIL"


def scan() -> dict:
    registry = Path.home() / "repos" / "ont-registry" / "experiments.yaml"
    if not registry.exists():
        print(f"ERROR: registry not found at {registry}", file=sys.stderr)
        sys.exit(2)
    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    exps = data.get("experiments", [])
    real = [e for e in exps if "/tmp/" not in str(e.get("location", "")) and "/workspace/" not in str(e.get("location", ""))]

    print(f"[scan] {len(real)} real experiments in registry (excluding test fixtures)")

    results = []
    for e in real:
        eid = e.get("id")
        loc = e.get("location", "")
        local_path = translate_path(loc)
        rec: dict = {
            "id": eid,
            "name": e.get("name", eid),
            "registry_location": loc,
            "local_path": str(local_path),
            "platform": e.get("platform", "unknown"),
            "reachable": local_path.exists(),
        }
        if not local_path.exists():
            rec["status"] = "UNREACHABLE"
            rec["note"] = f"path not present on this host ({platform.system()}); HPC follow-up needed"
            results.append(rec)
            continue

        # Reachable — try to find an end_reason source.
        summary = find_summary(local_path)
        pod5_dir = None if summary else find_pod5_dir(local_path)
        target = summary or pod5_dir

        if target is None:
            rec["status"] = "NO_SOURCE"
            rec["note"] = "directory present but no sequencing_summary.txt or pod5/ found"
            results.append(rec)
            continue

        rec["source"] = str(target)
        rec["source_kind"] = "sequencing_summary" if summary else "pod5_dir"
        print(f"[scan] {eid}: extracting from {target.name}")
        rec["extraction"] = extract_end_reason(target)
        rec["status"] = classify_status(rec["extraction"])
        results.append(rec)

    return {
        "scan_time": datetime.datetime.now().isoformat(timespec="seconds"),
        "registry": str(registry),
        "total_real": len(real),
        "experiments": results,
    }


def render_dashboard(scan_result: dict, out_html: Path) -> None:
    rows = []
    by_status: dict[str, int] = Counter()
    for r in scan_result["experiments"]:
        by_status[r["status"]] += 1

    for r in scan_result["experiments"]:
        status = r["status"]
        cls = {
            "OK": "ok", "CHECK": "warn", "FAIL": "bad",
            "ERROR": "bad", "UNREACHABLE": "muted",
            "NO_SOURCE": "muted", "CLOUD_ONLY": "warn",
        }.get(status, "muted")
        e = r.get("extraction", {})
        dist = e.get("distribution_short", {})
        dist_str = ", ".join(f"<code>{k}</code>:{v}" for k, v in dist.items()) or "—"
        sp_pct = f"{e['sp_fraction']*100:.1f}%" if "sp_fraction" in e else "—"
        umc_pct = f"{e['umc_fraction']*100:.1f}%" if "umc_fraction" in e else "—"
        n = e.get("n_records", "—")
        err = e.get("error", "") or r.get("note", "")
        source_kind = r.get("source_kind", "—")
        rows.append(f"""
          <tr class='{cls}'>
            <td>{r['id'][:40]}</td>
            <td><span class='badge {cls}'>{status}</span></td>
            <td>{source_kind}</td>
            <td>{n if n != "—" else "—"}</td>
            <td>{sp_pct}</td>
            <td>{umc_pct}</td>
            <td>{dist_str}</td>
            <td class='small'>{err}</td>
          </tr>
        """)

    summary_cells = " ".join(
        f"<span class='badge {k.lower() if k in {'OK','CHECK','FAIL','ERROR'} else 'muted'}'>{k}: {v}</span>"
        for k, v in sorted(by_status.items())
    )
    css = """
      body{font-family:-apple-system,Segoe UI,sans-serif;max-width:1200px;margin:24px auto;padding:0 16px;color:#222}
      h1{border-bottom:2px solid #444;padding-bottom:6px}
      .meta{color:#666;font-size:.9em}
      .summary{margin:16px 0;padding:14px;background:#f7f7f7;border-radius:6px}
      .badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.8em;font-weight:600;margin:0 6px 0 0}
      .badge.ok{background:#d4edda;color:#155724}
      .badge.warn{background:#fff3cd;color:#856404}
      .badge.bad{background:#f8d7da;color:#721c24}
      .badge.muted{background:#e2e3e5;color:#383d41}
      table{border-collapse:collapse;width:100%;margin:16px 0;font-size:.9em}
      th{background:#eef;padding:8px;text-align:left;border-bottom:2px solid #ccd}
      td{padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top}
      td.small{font-size:.85em;color:#555}
      tr.warn td:first-child::before{content:"⚠ ";color:#a06200}
      tr.bad td:first-child::before{content:"✗ ";color:#a01616}
      tr.ok td:first-child::before{content:"✓ ";color:#155724}
      code{background:#eee;padding:1px 5px;border-radius:3px;font-size:.9em}
    """
    body = f"""
    <h1>Lab end_reason scan — {scan_result['total_real']} experiments</h1>
    <div class='meta'>Scanned {scan_result['scan_time']} from registry
      <code>{scan_result['registry']}</code>. Canonical extraction per the
      <code>end-reason-extraction-by-format</code> skill (handles the three
      known reader bugs).</div>
    <div class='summary'>{summary_cells}</div>
    <table>
      <thead>
        <tr><th>experiment id</th><th>status</th><th>source</th><th>N</th>
            <th>SP%</th><th>UMC+DUMC%</th><th>distribution</th><th>note</th></tr>
      </thead>
      <tbody>
        {"".join(rows)}
      </tbody>
    </table>
    <p class='meta'>Status thresholds: OK = SP ≥ 75%, CHECK = 50-75%, FAIL = &lt; 50%.
      UNREACHABLE = registry path not present on this host (likely lives on HPC).
      NO_SOURCE = directory found but no <code>sequencing_summary*.txt</code> or
      <code>pod5/</code> dir inside.</p>
    """
    html = f"<!doctype html><html><head><meta charset='utf-8'><title>Lab end_reason scan</title><style>{css}</style></head><body>{body}</body></html>"
    out_html.write_text(html, encoding="utf-8")


def main() -> int:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "notebooks" / "lab_scans" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    result = scan()

    (out_dir / "per_experiment_results.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )

    # HPC follow-up list
    hpc_todo = [r for r in result["experiments"] if r["status"] == "UNREACHABLE"]
    (out_dir / "hpc_todo.txt").write_text(
        "# Experiments not reachable from this host.\n"
        "# Run the same scan on Great Lakes (or wherever paths resolve):\n"
        "#   ssh gregfar@greatlakes.arc-ts.umich.edu\n"
        "#   python ~/repos/ont-end-reason/notebooks/lab_scan_end_reason.py\n\n"
        + "\n".join(f"{r['id']}\t{r['registry_location']}" for r in hpc_todo),
        encoding="utf-8",
    )

    out_html = out_dir / "lab_end_reason_dashboard.html"
    render_dashboard(result, out_html)

    # Console summary
    by_status: dict[str, int] = Counter()
    for r in result["experiments"]:
        by_status[r["status"]] += 1
    print()
    print("=" * 60)
    print(f"Scanned {result['total_real']} experiments. Status counts:")
    for s, n in sorted(by_status.items()):
        print(f"  {s:>12}: {n}")
    print(f"\nDashboard: {out_html}")
    print(f"HPC TODO:  {out_dir / 'hpc_todo.txt'}")

    if platform.system() == "Windows":
        subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process '{out_html}'"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

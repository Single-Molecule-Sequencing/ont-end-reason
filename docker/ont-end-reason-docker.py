#!/usr/bin/env python3
"""Cross-platform wrapper that runs ont-end-reason inside a Docker container.

Use this on Windows where pysam has no native wheel. The wrapper:

  1. Ensures the `ont-end-reason:local` image exists (builds it if not).
  2. Bind-mounts the current working directory to `/data` in the container.
  3. Rewrites any host-absolute paths in the argv that fall under the cwd so
     they resolve inside the container.
  4. Forwards stdin, stdout, stderr, and exit code transparently.

Usage:

    python docker/ont-end-reason-docker.py filter --bam in.bam --keep 1 --out out.bam
    python docker/ont-end-reason-docker.py tag   --bam in.bam --summary summary.txt --out tagged.bam
    python docker/ont-end-reason-docker.py export-fastq --bam in.bam --fastq out.fastq.gz --compress

You can pass `--rebuild` as the FIRST argument to force `docker build` before
running. Pass `--shell` to drop into an interactive bash shell in the
container (useful for poking around).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

IMAGE = "ont-end-reason:local"
REPO_ROOT = Path(__file__).resolve().parent.parent


def have_image(image: str) -> bool:
    rv = subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return rv.returncode == 0


def build_image() -> None:
    print(f"[ont-end-reason-docker] building {IMAGE}", file=sys.stderr)
    subprocess.run(
        ["docker", "build", "-t", IMAGE, "-f", "docker/Dockerfile", "."],
        cwd=REPO_ROOT,
        check=True,
    )


_PATHLIKE_PREFIXES = ("./", ".\\", "../", "..\\", "/", "\\")


def _looks_like_path(tok: str) -> bool:
    """Heuristic: is this argv token a filesystem path the user typed?

    Subcommand names (`filter`, `tag`) and flags (`--bam`, `-h`) must NOT be
    rewritten even if a same-named file/dir happens to live in cwd. We only
    rewrite tokens with explicit path syntax: a separator, a leading dot-slash,
    a drive letter, or an absolute root.
    """
    if not tok or tok.startswith("-"):
        return False
    if tok.startswith(_PATHLIKE_PREFIXES):
        return True
    if "/" in tok or "\\" in tok:
        return True
    # Windows drive letter: C:..., D:\..., etc.
    return len(tok) >= 2 and tok[1] == ":" and tok[0].isalpha()


def rewrite_args(argv: list[str], cwd: Path) -> list[str]:
    """Map host paths under cwd to container paths under /data.

    Only tokens that look like filesystem paths (per `_looks_like_path`) and
    resolve under cwd are rewritten. Subcommand names and flags pass through
    untouched even if a same-named file lives in cwd.
    """
    rewritten = []
    for tok in argv:
        if not _looks_like_path(tok):
            rewritten.append(tok)
            continue
        try:
            resolved = Path(tok).resolve()
        except OSError:
            rewritten.append(tok)
            continue
        try:
            rel = resolved.relative_to(cwd)
        except ValueError:
            # Path is outside cwd; the user must bind-mount it explicitly,
            # or pass a path already in container-syntax (/data/...).
            rewritten.append(tok)
            continue
        rewritten.append("/data/" + rel.as_posix() if str(rel) != "." else "/data")
    return rewritten


def main() -> int:
    if shutil.which("docker") is None:
        print("[ont-end-reason-docker] docker not found in PATH", file=sys.stderr)
        return 127

    args = sys.argv[1:]
    rebuild = False
    if args and args[0] == "--rebuild":
        rebuild = True
        args = args[1:]

    if rebuild or not have_image(IMAGE):
        build_image()

    cwd = Path.cwd().resolve()
    cwd_str = str(cwd)
    # On Windows the docker CLI accepts both forms; native form is friendlier
    # in log output. WSL / Linux just uses cwd_str as-is.
    mount_src = cwd_str

    if args and args[0] == "--shell":
        cmd = [
            "docker", "run", "--rm", "-it",
            "-v", f"{mount_src}:/data",
            "--entrypoint", "/bin/bash",
            IMAGE,
        ]
        return subprocess.run(cmd).returncode

    container_args = rewrite_args(args, cwd)
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{mount_src}:/data",
        IMAGE,
        *container_args,
    ]
    rv = subprocess.run(cmd)
    return rv.returncode


if __name__ == "__main__":
    sys.exit(main())

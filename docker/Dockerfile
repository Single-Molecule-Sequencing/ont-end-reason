# syntax=docker/dockerfile:1.7
#
# ont-end-reason container for Windows hosts where pysam has no native wheel.
# Linux-only deps (pysam, htslib) are present here; the host machine just
# bind-mounts data in and runs `ont-end-reason ...` via the wrapper script.
#
# Build (from repo root):
#     docker build -t ont-end-reason:local -f docker/Dockerfile .
#
# Run (filter a BAM living under C:\data on Windows):
#     docker run --rm -v C:\data:/data ont-end-reason:local \
#         filter --bam /data/in.bam --keep 1 --out /data/out.bam
#
# Or use the wrapper at docker/ont-end-reason-docker.py.

FROM python:3.11-slim

# Tini gives us a real PID-1 (Ctrl-C semantics) without bringing in systemd.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the bits pip needs so cache layers stay tight on iteration.
COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir -e ".[filter]"

# Default mount point for bind-mounted host data.
WORKDIR /data

ENTRYPOINT ["/usr/bin/tini", "--", "ont-end-reason"]
CMD ["--help"]

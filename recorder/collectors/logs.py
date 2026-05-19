"""
Log-tail sampler.

Tails files under DR_LOG_DIR matching *.log; counts new ERROR/FATAL/
Exception lines since the last tick. Tracks per-file byte position so
log rotation is handled (position resets to 0 if file shrinks).

Cosmetic patterns from BUG_LOG.md §A are stripped before the count —
they are noise, not signal. The list is editable at runtime via the
COSMETIC_PATTERNS module constant.

For incident drill the daemon can also save the raw lines (Phase C
TUI need); the schema is in place but for Phase A we only persist the
count.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_ERROR_RE = re.compile(r"\b(ERROR|FATAL|Exception)\b")

# From BUG_LOG.md §A — known cosmetic patterns we suppress.
COSMETIC_PATTERNS = [
    re.compile(r"Could not find role row with:"),
    re.compile(r"Add object - could not find parent object \[\d+\] when creating type \[(WORK_BASKET|SAVED_SEARCH_QUERY|PROJECT_PREFERENCES)\]"),
    re.compile(r"Exception when canceling all requests for project"),
    re.compile(r"javax\.mail\.Session\.getProperty"),
    re.compile(r"SendEmail.*CAE_ERROR"),
    re.compile(r"Queue Polling Error: java\.lang\.InterruptedException"),
    re.compile(r"Creating a new queue for 192\.168\."),
    re.compile(r"getDataAreaCfgByOrg: org \[null\]"),
    re.compile(r"Invalid event of JOB_STATUS_UPDATE in state DIRECTORY_DELETE_JOB"),
    re.compile(r"Could Not execute StorageQuotaCheck"),
    re.compile(r"Invalid state found - negative numJobsCurrent"),
    re.compile(r"Invalid state found - negative"),
    re.compile(r"ChainOfCustodyFactory.*cp command exit code is"),
]

_positions: dict[Path, int] = {}


def _classify(line: str) -> str | None:
    """Return one of: 'error', 'warn', 'cosmetic', None."""
    if "ERROR" in line or "FATAL" in line or "Exception" in line:
        if any(p.search(line) for p in COSMETIC_PATTERNS):
            return "cosmetic"
        return "error"
    if "WARN" in line:
        return "warn"
    return None


def _active_files(log_dir: Path, max_age_sec: int = 600) -> Iterable[Path]:
    """Files modified within the last `max_age_sec` seconds."""
    import time as _t
    now = _t.time()
    for f in log_dir.glob("*.log"):
        try:
            if now - f.stat().st_mtime < max_age_sec:
                yield f
        except OSError:
            continue


def sample(log_dir: Path) -> dict[str, float]:
    """Return one tick of log-classification counts.

    Increments are scoped to the bytes added since the previous tick —
    so we only count *new* lines, not the entire file.
    """
    counts = {"err_new": 0, "warn_new": 0, "err_cosmetic_new": 0}

    for f in _active_files(log_dir):
        try:
            size = f.stat().st_size
        except OSError:
            continue

        prev = _positions.get(f, None)
        # On first sight, just remember position; don't scan history.
        if prev is None:
            _positions[f] = size
            continue
        # Log rotated / truncated
        if size < prev:
            _positions[f] = 0
            prev = 0

        if size == prev:
            continue

        try:
            with open(f, errors="replace") as fh:
                fh.seek(prev)
                for line in fh:
                    klass = _classify(line)
                    if klass == "error":
                        counts["err_new"] += 1
                    elif klass == "warn":
                        counts["warn_new"] += 1
                    elif klass == "cosmetic":
                        counts["err_cosmetic_new"] += 1
                _positions[f] = fh.tell()
        except OSError as e:
            logger.debug("read %s: %s", f, e)

    # Float-typed so they match the store's metric value type.
    return {k: float(v) for k, v in counts.items()}

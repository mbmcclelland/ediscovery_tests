"""
Digital Reef API sampler.

Polls listProjects + per-project tasks at each tick and reports:
  - total_projects     all projects in the org
  - running_projects   projects with at least one active task
  - running_tasks      sum of active tasks across all projects
  - docs_total         sum of corpora documentCount across all projects
  - indexing_rate      docs/min derived from delta vs prior tick

A single-org poller. Multi-org support is a future concern.

The poller maintains a long-lived EDiscoveryClient session; if the
session goes stale the next post() will re-login automatically.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from helpers.admin_ops import dashboard_snapshot
from helpers.api_client import EDiscoveryClient

logger = logging.getLogger(__name__)

ACTIVE_STATES = {"RUNNING", "QUEUED", "PENDING", "PROCESSING", "STARTING"}

# Module-level state for indexing-rate delta
_prev_docs: Optional[tuple[float, int]] = None  # (monotonic_time, docs_total)


def sample(client: EDiscoveryClient, org: str) -> dict[str, float]:
    """Return one tick of DR API metrics."""
    global _prev_docs
    out: dict[str, float] = {}

    try:
        snap = dashboard_snapshot(client, org)
    except Exception as e:
        logger.warning("dashboard_snapshot failed: %s", e)
        return out

    projects = snap.get("projects", [])
    running = snap.get("running", [])

    out["total_projects"] = float(len(projects))
    out["running_projects"] = float(sum(1 for p in projects if p.get("running")))
    out["running_tasks"] = float(len(running))

    docs_total = sum(int(p.get("doc_count", 0) or 0) for p in projects)
    out["docs_total"] = float(docs_total)

    # Indexing rate (docs/min) from delta
    now_t = time.monotonic()
    if _prev_docs is not None:
        prev_t, prev_docs = _prev_docs
        dt = max(now_t - prev_t, 0.001)
        delta = max(docs_total - prev_docs, 0)
        out["docs_per_min"] = (delta / dt) * 60.0
    _prev_docs = (now_t, docs_total)

    return out

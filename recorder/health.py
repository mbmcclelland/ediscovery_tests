"""
Composite traffic-light derivation.

Five signals, moderate philosophy (per design contract):

| signal         | green     | yellow         | red (critical) |
|----------------|-----------|----------------|----------------|
| cpu_pct        | <70       | 70-85          | >85            |
| mem_pct        | <70       | 70-85          | >85            |
| disk_await_ms  | <50       | 50-200         | >200           |
| err_new        | <1/min    | 1-10/min       | >10/min        |
| docs_per_min   | ≥80% 1hAvg| 50-80%         | <50% OR 0      |

Rules:
  GREEN  -> 0 or 1 signal degraded
  YELLOW -> 2+ signals degraded
  RED    -> 2+ critical OR indexing rate = 0 (stalled)

`err_new` is supplied per tick (not per minute); we convert assuming the
caller's tick is in `seconds_per_tick` (defaults to 10).

`docs_per_min` is supplied directly by the dr_api collector; we don't
know the 1h baseline at sample-time, so for Phase A we use a *fixed
proxy threshold* (configurable). Future: track the baseline in the
store and parameterize.
"""

from __future__ import annotations

from typing import Optional

_TICK_SEC = 10.0  # must match recorder.daemon._DEFAULT_TICK_SEC


def _classify(value: float, yellow_at: float, red_at: float) -> str:
    if value >= red_at:
        return "critical"
    if value >= yellow_at:
        return "degraded"
    return "ok"


def _classify_indexing(value: float, baseline_per_min: float) -> str:
    """Indexing rate degrades when it drops below a fraction of baseline."""
    if baseline_per_min <= 0:
        # No baseline yet — treat as ok unless completely stalled
        return "ok" if value > 0 else "degraded"
    ratio = value / baseline_per_min
    if ratio < 0.5:
        return "critical"
    if ratio < 0.8:
        return "degraded"
    return "ok"


def derive_health(
    samples: dict[str, float],
    *,
    indexing_baseline_per_min: float = 100.0,
    tick_sec: float = _TICK_SEC,
) -> Optional[str]:
    """Return 'green' / 'yellow' / 'red', or None if insufficient data."""
    states: list[str] = []

    if "cpu_pct" in samples:
        states.append(_classify(samples["cpu_pct"], 70, 85))
    if "mem_pct" in samples:
        states.append(_classify(samples["mem_pct"], 70, 85))
    if "disk_await_ms" in samples:
        states.append(_classify(samples["disk_await_ms"], 50, 200))
    if "err_new" in samples:
        per_min = (samples["err_new"] / tick_sec) * 60.0
        states.append(_classify(per_min, 1.0, 10.0))
    if "docs_per_min" in samples:
        # Indexing rate is special — only relevant when there should be activity.
        # If running_tasks == 0 we don't penalize a 0 rate.
        if samples.get("running_tasks", 0) > 0:
            states.append(_classify_indexing(samples["docs_per_min"], indexing_baseline_per_min))

    if not states:
        return None

    n_degraded = sum(1 for s in states if s in ("degraded", "critical"))
    n_critical = sum(1 for s in states if s == "critical")
    indexing_zero = (
        samples.get("running_tasks", 0) > 0 and samples.get("docs_per_min", -1) == 0
    )

    if n_critical >= 2 or indexing_zero:
        return "red"
    if n_degraded >= 2:
        return "yellow"
    return "green"

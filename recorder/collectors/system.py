"""
System-resource sampler (CPU / memory / disk).

Uses psutil. CPU% is the rolling average since the last call, so
`sample()` must be invoked on a steady cadence — the daemon's 10s tick
fits naturally.

Disk-I/O is reported as a *rate* (MB/s and iops) by diffing
psutil.disk_io_counters() across consecutive calls. The first call
returns rate=0 because there's no prior baseline.

For disk-await we read `/proc/diskstats` and compute weighted average
service time. Falls back to 0 if the parse fails.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

# Module-level state for diff-based metrics
_prev_io = None  # type: Optional[tuple[int, psutil._common.sdiskio]]


def _read_proc_diskstats(device_substring: str = "sd") -> Optional[float]:
    """Average service time (ms) across matching block devices.

    Returns 0 if no devices match or the file can't be read.
    """
    try:
        total_aveq = 0
        total_ios = 0
        with open("/proc/diskstats") as f:
            for line in f:
                fields = line.split()
                if len(fields) < 14:
                    continue
                name = fields[2]
                # only count whole disks (skip partitions like sda1, sda2)
                if device_substring not in name:
                    continue
                if any(c.isdigit() for c in name.replace(device_substring, "")):
                    continue
                reads_completed = int(fields[3])
                writes_completed = int(fields[7])
                aveq = int(fields[10])  # time spent doing I/O (ms)
                total_aveq += aveq
                total_ios += reads_completed + writes_completed
        if total_ios == 0:
            return 0.0
        return total_aveq / total_ios
    except (OSError, ValueError) as e:
        logger.debug("diskstats parse failed: %s", e)
        return None


def sample() -> dict[str, float]:
    """Return one tick of system metrics."""
    global _prev_io
    out: dict[str, float] = {}

    # CPU% — psutil keeps state across calls; first call returns 0.0
    try:
        out["cpu_pct"] = psutil.cpu_percent(interval=None)
    except Exception as e:
        logger.warning("cpu_percent: %s", e)

    # Memory
    try:
        vm = psutil.virtual_memory()
        out["mem_pct"] = vm.percent
        out["mem_used_gb"] = vm.used / 1024**3
    except Exception as e:
        logger.warning("virtual_memory: %s", e)

    # Disk space on root
    try:
        du = psutil.disk_usage("/")
        out["disk_used_gb"] = du.used / 1024**3
        out["disk_pct"] = du.percent
    except Exception as e:
        logger.warning("disk_usage: %s", e)

    # Disk I/O rate (diff across calls)
    try:
        now_t = time.monotonic()
        io = psutil.disk_io_counters()
        if io is not None and _prev_io is not None:
            prev_t, prev_io = _prev_io
            dt = max(now_t - prev_t, 0.001)
            d_bytes = (io.read_bytes + io.write_bytes) - (prev_io.read_bytes + prev_io.write_bytes)
            d_ios = (io.read_count + io.write_count) - (prev_io.read_count + prev_io.write_count)
            out["disk_io_mb_s"] = max(d_bytes / 1024**2 / dt, 0.0)
            out["disk_iops"] = max(d_ios / dt, 0.0)
        _prev_io = (now_t, io) if io is not None else None
    except Exception as e:
        logger.warning("disk_io_counters: %s", e)

    # Disk-await (ms)
    await_ms = _read_proc_diskstats()
    if await_ms is not None:
        out["disk_await_ms"] = await_ms

    # Load average (1-min)
    try:
        out["load_1m"] = psutil.getloadavg()[0]
    except (AttributeError, OSError):
        pass

    return out

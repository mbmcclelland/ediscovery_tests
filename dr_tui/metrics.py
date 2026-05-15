"""
Local-host metrics + log-tailing helpers for the dr_tui landing dashboard.

These are pure Python (psutil + stdlib) and don't talk to the DR REST
API — they read straight off the OS. dr_tui typically runs on the same
host as DR, so "local" metrics _are_ the DR node's metrics.

Public surface:

    sample_metrics(prev: MetricsSample | None) -> MetricsSample
        Read CPU / mem / net / disk-IOPS in one shot. The *prev* sample
        carries the previous net + disk counters so we can compute
        per-interval deltas; pass None on the first call.

    MetricsHistory(max_points=60)
        Rolling buffer that aggregates samples for spark-lines + peak /
        average reporting.

    top_processes(n=5) -> list[ProcessRow]
        Snapshot of the n CPU-hottest processes, mirroring ps aux.

    LogTailer(paths)
        Multi-file `tail -f` driver. Call `poll()` from a worker loop to
        fetch any new lines since the last call.
"""
from __future__ import annotations

import glob
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional

import psutil

# ----------------------------------------------------------------------------- types
@dataclass
class MetricsSample:
    """A single read of the four metric channels."""
    ts: float                # epoch seconds at sample time
    cpu_pct: float           # 0..100
    mem_pct: float           # 0..100
    mem_used_gb: float
    mem_total_gb: float
    # net byte counters (cumulative) + computed bytes/sec since prev sample
    net_rx_bytes: int
    net_tx_bytes: int
    net_rx_per_sec: float
    net_tx_per_sec: float
    # disk IOPS — cumulative read+write op counters + computed iops since prev
    disk_read_ops: int
    disk_write_ops: int
    disk_read_iops: float
    disk_write_iops: float


@dataclass
class ProcessRow:
    pid: int
    user: str
    cpu_pct: float
    mem_pct: float
    cmd: str


@dataclass
class LogLine:
    """One parsed log line — `level` is detected via regex.

    For lines that don't match a level pattern, `level` is `""` and the
    UI usually treats them as plain INFO when filters allow INFO.
    """
    file: str               # short label, e.g. "SERVER" from "..._SERVER.log"
    text: str
    level: str              # "INFO" | "WARN" | "ERROR" | ""


# ----------------------------------------------------------------------------- metrics
def sample_metrics(prev: Optional[MetricsSample] = None) -> MetricsSample:
    """Snapshot CPU / mem / net / disk in one shot.

    `cpu_percent(interval=None)` is the running average since the last
    call — first call returns 0 because psutil hasn't established a
    baseline yet. That's fine; the second sample onwards is meaningful.
    """
    now = time.monotonic()
    cpu = psutil.cpu_percent(interval=None)

    vm = psutil.virtual_memory()
    mem_pct = vm.percent
    mem_used_gb = vm.used / (1024 ** 3)
    mem_total_gb = vm.total / (1024 ** 3)

    net = psutil.net_io_counters()
    rx, tx = net.bytes_recv, net.bytes_sent

    disk = psutil.disk_io_counters()
    rops = disk.read_count if disk else 0
    wops = disk.write_count if disk else 0

    if prev is not None:
        dt = max(now - prev.ts, 1e-6)
        rx_ps = max(0.0, (rx - prev.net_rx_bytes) / dt)
        tx_ps = max(0.0, (tx - prev.net_tx_bytes) / dt)
        riops = max(0.0, (rops - prev.disk_read_ops) / dt)
        wiops = max(0.0, (wops - prev.disk_write_ops) / dt)
    else:
        rx_ps = tx_ps = riops = wiops = 0.0

    return MetricsSample(
        ts=now,
        cpu_pct=cpu,
        mem_pct=mem_pct,
        mem_used_gb=mem_used_gb,
        mem_total_gb=mem_total_gb,
        net_rx_bytes=rx, net_tx_bytes=tx,
        net_rx_per_sec=rx_ps, net_tx_per_sec=tx_ps,
        disk_read_ops=rops, disk_write_ops=wops,
        disk_read_iops=riops, disk_write_iops=wiops,
    )


class MetricsHistory:
    """Rolling buffer of MetricsSample for peak / average / sparkline UI."""

    def __init__(self, max_points: int = 60):
        self._samples: deque[MetricsSample] = deque(maxlen=max_points)

    def add(self, sample: MetricsSample) -> None:
        self._samples.append(sample)

    def __len__(self) -> int:
        return len(self._samples)

    def __iter__(self) -> Iterator[MetricsSample]:
        return iter(self._samples)

    @property
    def latest(self) -> Optional[MetricsSample]:
        return self._samples[-1] if self._samples else None

    def cpu_series(self) -> list[float]:
        return [s.cpu_pct for s in self._samples]

    def mem_series(self) -> list[float]:
        return [s.mem_pct for s in self._samples]

    def cpu_peak(self) -> float:
        return max((s.cpu_pct for s in self._samples), default=0.0)

    def cpu_avg(self) -> float:
        n = len(self._samples)
        return sum(s.cpu_pct for s in self._samples) / n if n else 0.0

    def mem_peak(self) -> float:
        return max((s.mem_pct for s in self._samples), default=0.0)

    def mem_avg(self) -> float:
        n = len(self._samples)
        return sum(s.mem_pct for s in self._samples) / n if n else 0.0


# ----------------------------------------------------------------------------- processes
def top_processes(n: int = 5) -> list[ProcessRow]:
    """Return the n CPU-hottest processes, ps-aux style.

    First call after process_iter() is cheap but reports cpu_percent=0
    until psutil has two measurements; we prime once at module init and
    let subsequent calls return real values.
    """
    rows: list[ProcessRow] = []
    for p in psutil.process_iter(
        attrs=["pid", "username", "cpu_percent", "memory_percent", "name", "cmdline"],
    ):
        info = p.info
        cpu = info.get("cpu_percent") or 0.0
        mem = info.get("memory_percent") or 0.0
        cmdline = info.get("cmdline") or []
        cmd = " ".join(cmdline) if cmdline else (info.get("name") or "?")
        # Truncate very long cmd lines so the table doesn't blow up.
        if len(cmd) > 90:
            cmd = cmd[:87] + "…"
        rows.append(ProcessRow(
            pid=int(info.get("pid") or 0),
            user=str(info.get("username") or "?"),
            cpu_pct=float(cpu),
            mem_pct=float(mem),
            cmd=cmd,
        ))
    rows.sort(key=lambda r: r.cpu_pct, reverse=True)
    return rows[:n]


# Prime psutil so the first top_processes() call has cpu_percent data.
def prime_cpu_percent() -> None:
    """Call once at startup. psutil's cpu_percent is differential."""
    for p in psutil.process_iter(["cpu_percent"]):
        try:
            _ = p.info["cpu_percent"]
        except Exception:
            pass


# ----------------------------------------------------------------------------- log tail
_LEVEL_PATTERN = re.compile(
    r"\b(INFO|WARN(?:ING)?|ERROR|ERR|FATAL|DEBUG|TRACE)\b", re.IGNORECASE,
)


def _detect_level(line: str) -> str:
    """Map a line to one of INFO / WARN / ERROR / '' (other)."""
    m = _LEVEL_PATTERN.search(line)
    if not m:
        return ""
    raw = m.group(1).upper()
    if raw.startswith("WARN"):
        return "WARN"
    if raw in ("ERROR", "ERR", "FATAL"):
        return "ERROR"
    if raw == "INFO":
        return "INFO"
    return ""


def _short_label(path: str) -> str:
    """Turn /home/auraria/AHS/output/192.168.58.128_SERVER.log → SERVER."""
    name = Path(path).stem
    # Strip the IP prefix if present (the AHS naming convention).
    parts = name.split("_", 1)
    if len(parts) == 2 and parts[0].count(".") == 3:
        name = parts[1]
    # And strip a trailing .N suffix (e.g. ARCHIVE.2 → ARCHIVE_2 → keep .2)
    return name


class LogTailer:
    """Multi-file `tail -f` driver.

    Construct with a list of glob patterns; call `poll()` from a worker
    loop to get the new lines that arrived since the previous poll.
    Robust against file rotation (re-opens on truncate / shrink) and
    silently skips files that disappear.
    """

    def __init__(self, paths: Iterable[str], *, start_from_end: bool = True,
                 max_line_bytes: int = 4096):
        self._patterns = list(paths)
        self._positions: dict[str, int] = {}
        self._start_from_end = start_from_end
        self._max_line_bytes = max_line_bytes

    def _resolve(self) -> list[str]:
        out: list[str] = []
        for pat in self._patterns:
            out.extend(glob.glob(pat))
        return sorted(set(out))

    def poll(self) -> list[LogLine]:
        """Return new lines (oldest first) seen since the previous poll."""
        results: list[LogLine] = []
        for path in self._resolve():
            try:
                st = os.stat(path)
            except FileNotFoundError:
                continue
            size = st.st_size
            pos = self._positions.get(path)
            if pos is None:
                # Newly-seen file: jump to end (so initial mount doesn't
                # dump the whole backlog) — unless caller wants from start.
                pos = size if self._start_from_end else 0
                self._positions[path] = pos
                continue
            if size < pos:
                # File was truncated / rotated — re-read from the start.
                pos = 0
            if size == pos:
                continue
            try:
                with open(path, "rb") as f:
                    f.seek(pos)
                    chunk = f.read(size - pos)
            except (OSError, ValueError):
                continue
            self._positions[path] = size
            label = _short_label(path)
            text = chunk.decode("utf-8", errors="replace")
            for raw in text.splitlines():
                # Defensive cap — log lines longer than max_line_bytes get
                # truncated so a runaway line can't blow up the renderer.
                if len(raw) > self._max_line_bytes:
                    raw = raw[: self._max_line_bytes - 1] + "…"
                results.append(LogLine(
                    file=label, text=raw, level=_detect_level(raw),
                ))
        return results

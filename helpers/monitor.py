"""
Background monitoring for dr-load test runs.

LogWatcher tails app log files and collects ERROR/WARN lines.
JobPoller polls Postgres for representation state transitions.
Monitor owns both threads and produces a MonitorResult at stop().

representation_state enum (from common.jar):
  0 = NONE  (in progress / not yet complete)
  1 = COMPLETE
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


@dataclass
class MonitorResult:
    error_count: int = 0
    warning_count: int = 0
    jobs_started: int = 0
    jobs_complete: int = 0
    jobs_incomplete: int = 0
    error_lines: List[str] = field(default_factory=list)


class LogWatcher(threading.Thread):
    """Tail active log files; collect ERROR/WARN/FATAL/Exception lines."""

    _SCAN_AGE_SECONDS = 600  # watch files modified in the last 10 minutes
    _POLL_SECONDS = 2

    def __init__(self, log_dir: str, result: MonitorResult, stop_event: threading.Event):
        super().__init__(daemon=True, name="LogWatcher")
        self._log_dir = Path(log_dir)
        self._result = result
        self._stop_event = stop_event
        self._positions: Dict[Path, int] = {}

    def _active_files(self) -> List[Path]:
        now = time.time()
        files = []
        for f in self._log_dir.glob("*.log"):
            try:
                if now - f.stat().st_mtime < self._SCAN_AGE_SECONDS:
                    files.append(f)
            except OSError:
                pass
        return files

    def run(self) -> None:
        # Start at EOF so we only see new lines written during this run
        for f in self._active_files():
            try:
                self._positions[f] = f.stat().st_size
            except OSError:
                self._positions[f] = 0

        while not self._stop_event.is_set():
            for f in self._active_files():
                if f not in self._positions:
                    self._positions[f] = 0
                try:
                    with open(f, errors="replace") as fh:
                        fh.seek(self._positions[f])
                        for line in fh:
                            self._process_line(f.name, line.rstrip())
                        self._positions[f] = fh.tell()
                except OSError:
                    pass
            self._stop_event.wait(timeout=self._POLL_SECONDS)

    def _process_line(self, filename: str, line: str) -> None:
        if "ERROR" in line or "FATAL" in line or "Exception" in line:
            self._result.error_count += 1
            self._result.error_lines.append(f"[{filename}] {line[:200]}")
        elif "WARN" in line:
            self._result.warning_count += 1


class JobPoller(threading.Thread):
    """
    Poll datamining_corpus_representation for state transitions.

    Snapshots existing handles at start so only handles created during
    the test run are counted.
    """

    _REP_STATE_COMPLETE = 1

    def __init__(self, pg_db: str, poll_interval: int, result: MonitorResult, stop_event: threading.Event):
        super().__init__(daemon=True, name="JobPoller")
        self._pg_db = pg_db
        self._interval = poll_interval
        self._result = result
        self._stop_event = stop_event

    def _query(self) -> Dict[str, int]:
        """Return {handle: representation_state} for all rows."""
        try:
            r = subprocess.run(
                [
                    "sudo", "-u", "auraria",
                    "psql", "-d", self._pg_db,
                    "-t", "-A", "-F", "|",
                    "-c",
                    "SELECT handle, representation_state "
                    "FROM datamining_corpus_representation",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode != 0:
                logger.warning("JobPoller psql exit %d: %s", r.returncode, r.stderr.strip())
                return {}
            rows: Dict[str, int] = {}
            for line in r.stdout.splitlines():
                line = line.strip()
                if "|" not in line:
                    continue
                parts = line.split("|", 1)
                if len(parts) == 2:
                    try:
                        rows[parts[0]] = int(parts[1])
                    except ValueError:
                        pass
            return rows
        except Exception as e:
            logger.warning("JobPoller query error: %s", e)
            return {}

    def run(self) -> None:
        baseline: Set[str] = set(self._query().keys())
        logger.info("JobPoller baseline: %d existing representations", len(baseline))

        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._interval)
            if self._stop_event.is_set():
                break
            current = self._query()
            new = {h: s for h, s in current.items() if h not in baseline}
            if new:
                complete = sum(1 for s in new.values() if s == self._REP_STATE_COMPLETE)
                running = sum(1 for s in new.values() if s != self._REP_STATE_COMPLETE)
                logger.info(
                    "JobPoller: %d new repr — %d complete, %d in progress",
                    len(new), complete, running,
                )

        # Final snapshot
        final = self._query()
        new = {h: s for h, s in final.items() if h not in baseline}
        self._result.jobs_started = len(new)
        self._result.jobs_complete = sum(1 for s in new.values() if s == self._REP_STATE_COMPLETE)
        self._result.jobs_incomplete = sum(1 for s in new.values() if s != self._REP_STATE_COMPLETE)
        logger.info(
            "JobPoller done: %d started, %d complete, %d incomplete",
            self._result.jobs_started,
            self._result.jobs_complete,
            self._result.jobs_incomplete,
        )


class Monitor:
    """Own LogWatcher + JobPoller threads for the duration of a Locust run."""

    def __init__(self, log_dir: str, pg_db: str, poll_interval: int):
        self._result = MonitorResult()
        self._stop = threading.Event()
        self._log_watcher = LogWatcher(log_dir, self._result, self._stop)
        self._job_poller = JobPoller(pg_db, poll_interval, self._result, self._stop)

    def start(self) -> None:
        self._log_watcher.start()
        self._job_poller.start()

    def stop(self) -> MonitorResult:
        """Signal stop and wait. Returns aggregated MonitorResult."""
        self._stop.set()
        self._log_watcher.join(timeout=5)
        self._job_poller.join(timeout=30)
        return self._result

"""
Recorder daemon main loop.

Run via `python -m recorder` or as a systemd ExecStart. Tick interval
defaults to 10s. SIGTERM / SIGINT trigger a graceful shutdown that
flushes any in-flight write and closes the SQLite connection.

This file deliberately knows nothing about CLI argument parsing — the
`dr-load record start` command imports `run()` directly.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import Optional

import urllib3

from config import Config, config as default_config
from helpers.api_client import EDiscoveryClient
from recorder.collectors import dr_api, logs, system
from recorder.health import derive_health
from recorder.store import Store

logger = logging.getLogger(__name__)


def _suppress_insecure_warnings_if_needed(cfg: Config) -> None:
    """One-shot suppression of urllib3 InsecureRequestWarning at daemon start.

    At a 5s tick against an N-project install, every HTTPS request to the
    self-signed SUT emits one warning line; recorder.log becomes unreadable
    within an hour. We mirror the test suite's conftest.py approach and
    suppress ONLY when the operator has already opted out of TLS verification
    (verify_ssl=False). On a properly-configured production install with
    verify_ssl=True we leave urllib3's warnings alone.
    """
    if not getattr(cfg, "verify_ssl", True):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_TICK_SEC = 10


class Daemon:
    """Owns the store, the API client, and the run loop."""

    def __init__(
        self,
        store: Store,
        cfg: Config,
        org: Optional[str] = None,
        tick_sec: int = _DEFAULT_TICK_SEC,
    ) -> None:
        self.store = store
        self.cfg = cfg
        # Target org for DR-API polling. Priority: explicit arg →
        # DR_ORG_ORGANIZATION env → cfg.organization (DRSysAdmin's home).
        self.org = org or os.getenv("DR_ORG_ORGANIZATION") or cfg.organization
        self.tick_sec = tick_sec
        self._client: Optional[EDiscoveryClient] = None
        self._running = False
        self._last_health: Optional[str] = None  # for transition detection

    # --- lifecycle ---

    def _ensure_client(self) -> EDiscoveryClient:
        if self._client is None:
            c = EDiscoveryClient(self.cfg)
            c.login()
            self._client = c
        return self._client

    def stop(self, *_args) -> None:  # signal-handler signature
        logger.info("recorder: stop signal received")
        self._running = False

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        # Suppress urllib3 InsecureRequestWarning ONCE per daemon lifetime,
        # only when verify_ssl=False. See BUG-3.
        _suppress_insecure_warnings_if_needed(self.cfg)

        self._running = True
        log_dir = Path(self.cfg.log_dir)
        logger.info(
            "recorder: store=%s org=%s tick=%ds log_dir=%s",
            self.store.path,
            self.org,
            self.tick_sec,
            log_dir,
        )

        self.store.write_event(
            "RECORDER_START",
            payload={
                "tick_sec": self.tick_sec,
                "org": self.org,
                "store": str(self.store.path),
            },
        )

        # Seed psutil + log positions with a throwaway sample before the
        # first real tick so diffs and CPU% are valid from t=0.
        system.sample()
        logs.sample(log_dir)

        while self._running:
            start = time.monotonic()
            ts = int(time.time())
            samples: dict[str, float] = {}

            # System always; never raises through to here.
            try:
                samples.update(system.sample())
            except Exception as e:
                logger.warning("system collector: %s", e)

            # Logs always.
            try:
                samples.update(logs.sample(log_dir))
            except Exception as e:
                logger.warning("logs collector: %s", e)

            # DR API requires a live client; tolerate transient failures.
            try:
                client = self._ensure_client()
                samples.update(dr_api.sample(client, self.org))
            except Exception as e:
                logger.warning("dr_api collector: %s — resetting client", e)
                self._client = None  # force re-login next tick

            self.store.write_metrics(ts, samples)

            # Health-light derivation + transition events
            health = derive_health(samples)
            if health and health != self._last_health:
                self.store.write_event(
                    health.upper(),
                    payload={"signals": _degraded_signals(samples)},
                    ts=ts,
                )
                logger.info(
                    "health transition: %s -> %s", self._last_health, health
                )
                self._last_health = health

            # Sleep the remainder of the tick interval
            elapsed = time.monotonic() - start
            sleep_for = max(self.tick_sec - elapsed, 0.0)
            # Interruptible sleep
            slept = 0.0
            while self._running and slept < sleep_for:
                time.sleep(min(0.5, sleep_for - slept))
                slept += 0.5

        self.store.write_event("RECORDER_STOP")
        self.store.close()
        logger.info("recorder: stopped cleanly")


def _degraded_signals(samples: dict[str, float]) -> dict:
    """Subset of samples relevant to the latest health transition."""
    keys = (
        "cpu_pct",
        "mem_pct",
        "disk_await_ms",
        "err_new",
        "docs_per_min",
    )
    return {k: samples[k] for k in keys if k in samples}


def run(
    store_path: Optional[Path] = None,
    cfg: Optional[Config] = None,
    org: Optional[str] = None,
    tick_sec: int = _DEFAULT_TICK_SEC,
) -> None:
    """Convenience entrypoint for `python -m recorder` and the CLI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    cfg = cfg or default_config
    store = Store(store_path)
    Daemon(store, cfg, org=org, tick_sec=tick_sec).run()

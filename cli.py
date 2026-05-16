"""
dr-load CLI — Digital Reef eDiscovery load tester.

Commands:
  dr-load preflight            Run preflight checks only.
  dr-load indexing [options]   Full indexing load test with monitoring.
  dr-load browsing [options]   Full browsing load test with monitoring.
"""

from __future__ import annotations

import csv
import logging
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import typer

from config import config as default_config
from helpers.monitor import Monitor
from helpers.preflight import run_orphan_sweep, run_preflight

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

app = typer.Typer(no_args_is_help=True, help="Digital Reef eDiscovery load tester.")

_HERE = Path(__file__).parent


def _locust_host(base_url: str) -> str:
    """Strip the REST path from DR_BASE_URL to get the Locust --host value."""
    p = urlparse(base_url)
    return f"{p.scheme}://{p.netloc}"


def _print_preflight(results, all_passed: bool) -> None:
    typer.echo("\nPreflight checks:")
    for r in results:
        mark = typer.style("PASS", fg=typer.colors.GREEN) if r.passed else typer.style("FAIL", fg=typer.colors.RED)
        typer.echo(f"  [{mark}] {r.name}: {r.detail}")
    typer.echo()


def _run_locust(locustfile: Path, host: str, users: int, spawn_rate: int, duration: str, csv_stem: str) -> int:
    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(locustfile),
        "--host", host,
        "--headless",
        "-u", str(users),
        "-r", str(spawn_rate),
        "--run-time", duration,
        "--csv", csv_stem,
    ]
    typer.echo("Running: " + " ".join(cmd) + "\n")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        typer.echo(line, nl=False)
    proc.wait()
    return proc.returncode


def _print_summary(result) -> None:
    typer.echo("\n=== Test Summary ===")
    typer.echo(f"  Log errors:               {result.error_count}")
    typer.echo(f"  Log warnings:             {result.warning_count}")
    typer.echo(f"  Indexing jobs started:    {result.jobs_started}")
    typer.echo(f"  Indexing jobs complete:   {result.jobs_complete}")
    typer.echo(f"  Indexing jobs incomplete: {result.jobs_incomplete}")
    if result.error_lines:
        typer.echo("\n  First 5 log errors:")
        for line in result.error_lines[:5]:
            typer.echo(f"    {line}")
    typer.echo()


def _write_report(report: Path, result, csv_stem: str) -> None:
    """Combine Locust CSV stats with monitor data into a single report CSV."""
    locust_rows: list[dict] = []
    stats_csv = Path(f"{csv_stem}_stats.csv")
    if stats_csv.exists():
        with open(stats_csv) as f:
            locust_rows = list(csv.DictReader(f))

    with open(report, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["section", "metric", "value"])
        writer.writerow(["monitor", "log_errors", result.error_count])
        writer.writerow(["monitor", "log_warnings", result.warning_count])
        writer.writerow(["monitor", "jobs_started", result.jobs_started])
        writer.writerow(["monitor", "jobs_complete", result.jobs_complete])
        writer.writerow(["monitor", "jobs_incomplete", result.jobs_incomplete])
        for row in locust_rows:
            for k, v in row.items():
                writer.writerow(["locust", k, v])

    typer.echo(f"Report written to {report}")


@app.command()
def preflight() -> None:
    """Run preflight checks and report pass/fail for each."""
    results, all_passed = run_preflight()
    _print_preflight(results, all_passed)
    raise SystemExit(0 if all_passed else 1)


@app.command()
def indexing(
    users: int = typer.Option(None, "--users", "-u", help="Concurrent users (default: DR_LOAD_TEST_USERS)"),
    duration: str = typer.Option(None, "--duration", "-d", help="Run time, e.g. 120s (default: DR_LOAD_TEST_DURATION)"),
    spawn_rate: int = typer.Option(None, "--spawn-rate", "-r", help="Users spawned per second (default: DR_LOAD_TEST_SPAWN_RATE)"),
    report: Path = typer.Option(None, "--report", help="Output CSV report path (default: DR_REPORT_OUTPUT)"),
) -> None:
    """Preflight → orphan sweep → indexing load test → report."""
    cfg = default_config
    u = users or cfg.load_test_users
    d = duration or f"{cfg.load_test_duration}s"
    r = spawn_rate or cfg.load_test_spawn_rate
    rpt = report or Path(cfg.report_output)

    results, all_passed = run_preflight(cfg)
    _print_preflight(results, all_passed)
    if not all_passed:
        typer.echo(typer.style("Preflight failed — aborting.", fg=typer.colors.RED), err=True)
        raise SystemExit(1)

    deleted = run_orphan_sweep(cfg)
    if deleted:
        typer.echo(f"Orphan sweep: removed {deleted} stale load-test-* project(s)\n")

    monitor = Monitor(cfg.log_dir, cfg.pg_db, cfg.poll_interval)
    monitor.start()

    csv_stem = str(rpt.with_suffix(""))
    locustfile = _HERE / "locustfile_indexing.py"
    host = _locust_host(cfg.base_url)

    try:
        rc = _run_locust(locustfile, host, u, r, d, csv_stem)
    finally:
        result = monitor.stop()

    _print_summary(result)
    _write_report(rpt, result, csv_stem)
    raise SystemExit(rc)


@app.command()
def browsing(
    users: int = typer.Option(None, "--users", "-u", help="Concurrent users (default: DR_LOAD_TEST_USERS)"),
    duration: str = typer.Option(None, "--duration", "-d", help="Run time, e.g. 120s (default: DR_LOAD_TEST_DURATION)"),
    spawn_rate: int = typer.Option(None, "--spawn-rate", "-r", help="Users spawned per second (default: DR_LOAD_TEST_SPAWN_RATE)"),
    report: Path = typer.Option(None, "--report", help="Output CSV report path (default: DR_REPORT_OUTPUT)"),
) -> None:
    """Preflight → browsing load test → report."""
    cfg = default_config
    u = users or cfg.load_test_users
    d = duration or f"{cfg.load_test_duration}s"
    r = spawn_rate or cfg.load_test_spawn_rate
    rpt = report or Path(cfg.report_output)

    results, all_passed = run_preflight(cfg)
    _print_preflight(results, all_passed)
    if not all_passed:
        typer.echo(typer.style("Preflight failed — aborting.", fg=typer.colors.RED), err=True)
        raise SystemExit(1)

    monitor = Monitor(cfg.log_dir, cfg.pg_db, cfg.poll_interval)
    monitor.start()

    csv_stem = str(rpt.with_suffix(""))
    locustfile = _HERE / "locustfile.py"
    host = _locust_host(cfg.base_url)

    try:
        rc = _run_locust(locustfile, host, u, r, d, csv_stem)
    finally:
        result = monitor.stop()

    _print_summary(result)
    _write_report(rpt, result, csv_stem)
    raise SystemExit(rc)


if __name__ == "__main__":
    app()

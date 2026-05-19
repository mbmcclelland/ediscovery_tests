"""
`dr-load record` — control the recorder daemon.

Subcommands:
  start   — fork the daemon as a background process, write PID file
  stop    — read PID file, send SIGTERM, wait for clean exit
  status  — show daemon state + recent samples
  tail    — stream events as they're written (for debugging)

PID file lives next to the SQLite store so a single store + daemon pair
shares one parent directory. Use `--store PATH` to override.

For production (systemd-managed), use the systemd unit; this CLI is for
ad-hoc operator runs.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer

from recorder.store import Store, default_db_path

app = typer.Typer(no_args_is_help=True, help="Recorder daemon control plane.")


def _pid_path(store_path: Path) -> Path:
    return store_path.parent / "recorder.pid"


def _read_pid(pid_path: Path) -> Optional[int]:
    try:
        return int(pid_path.read_text().strip())
    except (OSError, ValueError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours


def _resolve_store(store: Optional[Path]) -> Path:
    return Path(store) if store else default_db_path()


@app.command()
def start(
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
    tick: int = typer.Option(10, "--tick", help="Tick interval (seconds)"),
    org: Optional[str] = typer.Option(None, "--org", help="DR org to poll"),
    foreground: bool = typer.Option(False, "--foreground", "-f", help="Run in foreground (don't daemonize)"),
) -> None:
    """Start the recorder daemon."""
    store_path = _resolve_store(store)
    pid_path = _pid_path(store_path)

    existing = _read_pid(pid_path)
    if existing and _alive(existing):
        typer.echo(typer.style(f"Recorder already running (pid={existing}).", fg=typer.colors.YELLOW))
        raise SystemExit(2)

    if foreground:
        # Direct in-process run — Ctrl-C to stop.
        from recorder.daemon import run as run_daemon
        run_daemon(store_path=store_path, org=org, tick_sec=tick)
        return

    # Fork the daemon via `python -m recorder` with stdout/stderr to a log file.
    log_path = store_path.parent / "recorder.log"
    cmd = [
        sys.executable, "-m", "recorder",
        "--store", str(store_path),
        "--tick", str(tick),
    ]
    if org:
        cmd.extend(["--org", org])

    log_fh = open(log_path, "a")
    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        cwd=Path(__file__).parent.parent,
        start_new_session=True,
    )
    pid_path.write_text(str(proc.pid))

    # Wait briefly to confirm the daemon stayed up
    time.sleep(1.5)
    if proc.poll() is not None:
        typer.echo(typer.style(
            f"Daemon exited immediately (rc={proc.returncode}). Log: {log_path}",
            fg=typer.colors.RED,
        ))
        pid_path.unlink(missing_ok=True)
        raise SystemExit(1)

    typer.echo(typer.style("OK", fg=typer.colors.GREEN) + f" Recorder started (pid={proc.pid}).")
    typer.echo(f"   store: {store_path}")
    typer.echo(f"   log:   {log_path}")
    typer.echo(f"   tick:  {tick}s")


@app.command()
def stop(
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
    wait: int = typer.Option(15, "--wait", help="Seconds to wait for clean exit"),
) -> None:
    """Stop the recorder daemon."""
    store_path = _resolve_store(store)
    pid_path = _pid_path(store_path)

    pid = _read_pid(pid_path)
    if pid is None:
        typer.echo("No PID file. Recorder may not be running.")
        raise SystemExit(2)
    if not _alive(pid):
        typer.echo(f"PID {pid} is stale (no such process). Removing.")
        pid_path.unlink(missing_ok=True)
        raise SystemExit(2)

    os.kill(pid, signal.SIGTERM)
    for _ in range(wait * 2):
        if not _alive(pid):
            pid_path.unlink(missing_ok=True)
            typer.echo(typer.style("OK", fg=typer.colors.GREEN) + f" Recorder stopped (pid={pid}).")
            return
        time.sleep(0.5)

    typer.echo(typer.style(
        f"Recorder pid={pid} did not exit in {wait}s. Sending SIGKILL.",
        fg=typer.colors.YELLOW,
    ))
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    pid_path.unlink(missing_ok=True)


@app.command()
def status(
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
) -> None:
    """Show recorder status + recent samples."""
    store_path = _resolve_store(store)
    pid_path = _pid_path(store_path)

    pid = _read_pid(pid_path)
    if pid and _alive(pid):
        state = typer.style("RUNNING", fg=typer.colors.GREEN)
        info = f"pid={pid}"
    else:
        state = typer.style("STOPPED", fg=typer.colors.YELLOW)
        info = "no PID alive"

    typer.echo(f"Recorder: {state}  ({info})")
    typer.echo(f"   store: {store_path}")

    if not store_path.exists():
        typer.echo(typer.style("   store file missing — nothing recorded yet.", fg=typer.colors.YELLOW))
        return

    s = Store(store_path)
    typer.echo(f"   signals: {len(s.signals())}")

    # Show the latest few key metrics
    for sig in ("cpu_pct", "mem_pct", "disk_used_gb", "disk_io_mb_s", "docs_per_min", "running_tasks", "total_projects", "err_new"):
        latest = s.latest_metric(sig)
        if latest:
            ts, val = latest
            age = int(time.time()) - ts
            typer.echo(f"   {sig:<18} {val:>10.2f}   (t-{age}s)")

    # Active campaign + last few events
    camp = s.active_campaign()
    if camp:
        elapsed = int(time.time()) - camp["started_at"]
        typer.echo(f"\n   campaign: {camp['name']} ({camp.get('scenario') or '?'} @ {camp.get('current_users')} users, running {elapsed//60}m{elapsed%60:02d}s)")
    else:
        typer.echo("\n   campaign: (none active)")

    events = s.read_events(since=int(time.time()) - 3600)
    if events:
        typer.echo(f"\n   recent events (last hour): {len(events)}")
        for ev in events[-5:]:
            ts_str = time.strftime("%H:%M:%S", time.localtime(ev["ts"]))
            typer.echo(f"     {ts_str}  {ev['kind']:<14} {ev.get('campaign') or ''}")


@app.command()
def tail(
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
    interval: float = typer.Option(2.0, "--interval", help="Poll interval (seconds)"),
) -> None:
    """Stream new events as they're written (Ctrl-C to exit)."""
    store_path = _resolve_store(store)
    if not store_path.exists():
        typer.echo(typer.style("Store file missing.", fg=typer.colors.RED))
        raise SystemExit(2)

    s = Store(store_path)
    last_ts = int(time.time())
    typer.echo(f"Tailing {store_path}  (Ctrl-C to exit)\n")
    try:
        while True:
            evs = s.read_events(since=last_ts + 1)
            for ev in evs:
                ts_str = time.strftime("%H:%M:%S", time.localtime(ev["ts"]))
                line = f"{ts_str}  {ev['kind']:<14} {ev.get('campaign') or '-'}"
                if ev.get("payload"):
                    line += f"  {ev['payload']}"
                typer.echo(line)
                last_ts = max(last_ts, ev["ts"])
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\nstopped.")

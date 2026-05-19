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
from helpers.style import ok, warn, fail, info, header, col_headers, styled_state, styled_event_kind

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
        warn(f"Recorder already running (pid={existing}).")
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
        fail(f"Daemon exited immediately (rc={proc.returncode}). Log: {log_path}")
        pid_path.unlink(missing_ok=True)
        raise SystemExit(1)

    ok(f"Recorder started (pid={proc.pid}).")
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
            ok(f"Recorder stopped (pid={pid}).")
            return
        time.sleep(0.5)

    warn(f"Recorder pid={pid} did not exit in {wait}s. Sending SIGKILL.")
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    pid_path.unlink(missing_ok=True)


@app.command()
def status(
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
    rich_mode: bool = typer.Option(False, "--rich", help="Render a Rich panel (colors, boxes)."),
) -> None:
    """Show recorder status and recent samples."""
    store_path = _resolve_store(store)
    pid_path = _pid_path(store_path)

    pid = _read_pid(pid_path)
    is_running = pid and _alive(pid)

    if rich_mode:
        _status_rich(store_path, pid, is_running)
        return

    # Plain text (default — pipeable, grep-friendly)
    state_str = styled_state("RUNNING") if is_running else styled_state("STOPPED")
    daemon_info = f"pid={pid}" if is_running else "no PID alive"

    header("=== Recorder Status ===")
    typer.echo(f"   state:  {state_str}  ({daemon_info})")
    typer.echo(f"   store:  {store_path}")

    if not store_path.exists():
        warn("   Store file missing — nothing recorded yet.")
        return

    s = Store(store_path)
    typer.echo(f"   signals: {len(s.signals())}")
    typer.echo("")

    # Metrics table — two-column aligned: signal | latest value (age)
    col_headers(f"   {'SIGNAL':<20} {'LATEST':>10}   AGE")
    typer.echo(f"   {'-'*20} {'-'*10}   {'-'*6}")
    for sig in ("cpu_pct", "mem_pct", "disk_used_gb", "disk_io_mb_s",
                "docs_per_min", "running_tasks", "total_projects", "err_new"):
        latest = s.latest_metric(sig)
        if latest:
            ts, val = latest
            age = int(time.time()) - ts
            typer.echo(f"   {sig:<20} {val:>10.2f}   t-{age}s")

    typer.echo("")

    # Active campaign
    camp = s.active_campaign()
    if camp:
        elapsed = int(time.time()) - camp["started_at"]
        camp_line = (
            f"   campaign:  {typer.style(camp['name'], fg=typer.colors.CYAN, bold=True)}"
            f"  ({camp.get('scenario') or '?'} @ {camp.get('current_users')} users,"
            f" running {elapsed//60}m{elapsed%60:02d}s)"
        )
        typer.echo(camp_line)
    else:
        typer.echo("   campaign:  (none active)")

    # Recent events
    events = s.read_events(since=int(time.time()) - 3600)
    if events:
        typer.echo(f"\n   Recent events (last hour): {len(events)}")
        col_headers(f"     {'TIME':<10} {'KIND':<16} CAMPAIGN")
        for ev in events[-5:]:
            ts_str = time.strftime("%H:%M:%S", time.localtime(ev["ts"]))
            kind_styled = styled_event_kind(ev["kind"])
            typer.echo(f"     {ts_str}  {kind_styled} {ev.get('campaign') or ''}")


def _status_rich(store_path: Path, pid: Optional[int], is_running: bool) -> None:
    """Rich panel rendering for `record status --rich`."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()
    daemon_info = f"pid={pid}" if is_running else "no PID alive"
    state_label = Text("RUNNING", style="bold cyan") if is_running else Text("STOPPED", style="bold yellow")

    if not store_path.exists():
        console.print(Panel(
            Text.assemble(
                ("State:  ", "bold bright_blue"), state_label, f"  ({daemon_info})\n",
                ("Store:  ", "bold bright_blue"), str(store_path), "\n\n",
                ("Store file missing — nothing recorded yet.", "yellow"),
            ),
            title="[bold bright_blue]Recorder Status[/]",
            border_style="bright_blue",
        ))
        return

    s = Store(store_path)

    # Metrics table
    metrics_table = Table(show_header=True, header_style="bold bright_blue",
                          box=None, padding=(0, 2, 0, 0))
    metrics_table.add_column("SIGNAL", style="cyan", no_wrap=True, min_width=22)
    metrics_table.add_column("LATEST", justify="right", no_wrap=True, min_width=10)
    metrics_table.add_column("AGE", no_wrap=True)

    now = int(time.time())
    for sig in ("cpu_pct", "mem_pct", "disk_used_gb", "disk_io_mb_s",
                "docs_per_min", "running_tasks", "total_projects", "err_new"):
        latest = s.latest_metric(sig)
        if latest:
            ts, val = latest
            age = now - ts
            metrics_table.add_row(sig, f"{val:.2f}", f"t-{age}s")

    # Campaign summary
    camp = s.active_campaign()
    if camp:
        elapsed = now - camp["started_at"]
        camp_text = Text.assemble(
            (camp["name"], "bold cyan"),
            f"  ({camp.get('scenario') or '?'} @ {camp.get('current_users')} users,"
            f" running {elapsed//60}m{elapsed%60:02d}s)",
        )
    else:
        camp_text = Text("(none active)", style="dim")

    # Recent events table
    events = s.read_events(since=now - 3600)
    ev_table = Table(show_header=True, header_style="bold bright_blue",
                     box=None, padding=(0, 2, 0, 0))
    ev_table.add_column("TIME", no_wrap=True)
    ev_table.add_column("KIND", no_wrap=True, min_width=14)
    ev_table.add_column("CAMPAIGN")

    from helpers.style import HEALTH_COLORS, EVENT_KIND_COLORS
    for ev in events[-5:]:
        ts_str = time.strftime("%H:%M:%S", time.localtime(ev["ts"]))
        kind = ev["kind"]
        kind_color = EVENT_KIND_COLORS.get(kind.upper())
        kind_text = Text(kind, style=f"bold {kind_color}" if kind_color else "default")
        ev_table.add_row(ts_str, kind_text, ev.get("campaign") or "")

    from rich.console import Group
    from rich.text import Text as RText

    body = Group(
        Text.assemble(("State:  ", "bold bright_blue"), state_label, f"  ({daemon_info})"),
        Text.assemble(("Store:  ", "bold bright_blue"), str(store_path)),
        Text.assemble(("Signals:", "bold bright_blue"), f" {len(s.signals())}"),
        Text(""),
        Text("Metrics", style="bold bright_blue"),
        metrics_table,
        Text(""),
        Text.assemble(("Campaign:  ", "bold bright_blue"), camp_text),
    )
    if events:
        from rich.console import Group as RGroup
        body = RGroup(
            body,
            RText(""),
            RText(f"Recent events (last hour): {len(events)}", style="bold bright_blue"),
            ev_table,
        )

    console.print(Panel(
        body,
        title="[bold bright_blue]Recorder Status[/]",
        border_style="bright_blue",
        subtitle="[dim]dr-load record status[/]",
    ))


@app.command()
def tail(
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
    interval: float = typer.Option(2.0, "--interval", help="Poll interval (seconds)"),
) -> None:
    """Stream new events as they're written (Ctrl-C to exit)."""
    store_path = _resolve_store(store)
    if not store_path.exists():
        fail("Store file missing.")
        raise SystemExit(2)

    s = Store(store_path)
    last_ts = int(time.time())
    typer.echo(
        typer.style("Tailing ", fg=typer.colors.BRIGHT_BLUE, bold=True)
        + str(store_path)
        + typer.style("  (Ctrl-C to exit)", fg=typer.colors.BRIGHT_BLUE)
    )
    typer.echo("")
    try:
        while True:
            evs = s.read_events(since=last_ts + 1)
            for ev in evs:
                ts_str = time.strftime("%H:%M:%S", time.localtime(ev["ts"]))
                kind_styled = styled_event_kind(ev["kind"])
                camp = ev.get("campaign") or "-"
                line = f"{ts_str}  {kind_styled} {camp:<20}"
                if ev.get("payload"):
                    payload = ev["payload"]
                    if isinstance(payload, dict):
                        # Pretty-print k=v pairs, cap at 80 chars
                        kv = "  ".join(f"{k}={v}" for k, v in payload.items() if k != "text")
                        text = payload.get("text", "")
                        extra = kv
                        if text:
                            extra += f"  — {text}"
                    else:
                        extra = str(payload)[:80]
                    line += f"  {extra}"
                typer.echo(line)
                last_ts = max(last_ts, ev["ts"])
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo(typer.style("\nstopped.", fg=typer.colors.BRIGHT_BLUE))

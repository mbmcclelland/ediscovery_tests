"""
`dr-load campaign` — lifecycle + annotation of long-running campaigns.

A campaign is the unit a months-long soak/load run is organized around.
It has a name, a scenario, a current users dial, and an event log.

Subcommands:
  new NAME --scenario S --users N [--note T]
  adjust --users N [--note T]               (adjusts the *active* campaign)
  event TEXT                                (annotate the active campaign)
  end [--note T]
  list                                       (show all campaigns)
  show [NAME]                                (default: active campaign)

All writes go to the same SQLite store the recorder daemon writes to,
so campaign events appear inline with metric ticks in the report view.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import typer

from recorder.store import Store, default_db_path

app = typer.Typer(no_args_is_help=True, help="Campaign lifecycle and annotation.")


def _resolve_store(store: Optional[Path]) -> Store:
    return Store(store if store else default_db_path())


def _require_active(s: Store) -> dict:
    camp = s.active_campaign()
    if not camp:
        typer.echo(typer.style(
            "No active campaign. Start one with `dr-load campaign new NAME …`.",
            fg=typer.colors.RED,
        ))
        raise SystemExit(2)
    return camp


@app.command("new")
def cmd_new(
    name: str = typer.Argument(..., help="Campaign name (must be unique)"),
    scenario: str = typer.Option("indexing", "--scenario", help="Scenario tag"),
    users: int = typer.Option(1, "--users", help="Initial concurrent users"),
    note: Optional[str] = typer.Option(None, "--note", help="Free-form note"),
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
) -> None:
    """Start a new campaign."""
    s = _resolve_store(store)
    existing = s.active_campaign()
    if existing and existing["name"] != name:
        typer.echo(typer.style(
            f"Another campaign is active: {existing['name']}. End it first.",
            fg=typer.colors.RED,
        ))
        raise SystemExit(2)
    s.start_campaign(name=name, scenario=scenario, initial_users=users, notes=note)
    typer.echo(typer.style("OK", fg=typer.colors.GREEN) + f" Campaign '{name}' started.")
    typer.echo(f"   scenario: {scenario}")
    typer.echo(f"   users:    {users}")
    if note:
        typer.echo(f"   note:     {note}")


@app.command("adjust")
def cmd_adjust(
    users: int = typer.Option(..., "--users", help="New concurrent-user count"),
    note: Optional[str] = typer.Option(None, "--note", help="Why are you adjusting?"),
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
) -> None:
    """Adjust user count on the active campaign."""
    s = _resolve_store(store)
    camp = _require_active(s)
    prev = camp.get("current_users")
    s.adjust_campaign(camp["name"], users=users, note=note)
    typer.echo(
        typer.style("OK", fg=typer.colors.GREEN)
        + f" Campaign '{camp['name']}' users {prev} → {users}."
    )
    if note:
        typer.echo(f"   note: {note}")


@app.command("event")
def cmd_event(
    text: str = typer.Argument(..., help="Annotation text"),
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
) -> None:
    """Append a free-form annotation event to the active campaign."""
    s = _resolve_store(store)
    camp = _require_active(s)
    s.write_event("ANNOTATE", campaign=camp["name"], payload={"text": text})
    typer.echo(typer.style("OK", fg=typer.colors.GREEN) + " Event recorded.")


@app.command("end")
def cmd_end(
    note: Optional[str] = typer.Option(None, "--note", help="Closing note"),
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
) -> None:
    """End the active campaign."""
    s = _resolve_store(store)
    camp = _require_active(s)
    s.end_campaign(camp["name"], note=note)
    elapsed = int(time.time()) - camp["started_at"]
    h, m = divmod(elapsed // 60, 60)
    typer.echo(
        typer.style("OK", fg=typer.colors.GREEN)
        + f" Campaign '{camp['name']}' ended after {h}h{m:02d}m."
    )


@app.command("list")
def cmd_list(
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
) -> None:
    """List all campaigns (active and historical)."""
    s = _resolve_store(store)
    camps = s.all_campaigns()
    if not camps:
        typer.echo("No campaigns recorded yet.")
        return
    typer.echo(f"{'NAME':<25} {'SCENARIO':<12} {'USERS':>6} {'STATE':<10} {'STARTED':<20} {'ELAPSED'}")
    typer.echo("-" * 92)
    for c in camps:
        state = "active" if c["ended_at"] is None else "ended"
        elapsed = (c["ended_at"] or int(time.time())) - c["started_at"]
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        started = time.strftime("%Y-%m-%d %H:%M", time.localtime(c["started_at"]))
        typer.echo(
            f"{c['name']:<25} {c.get('scenario') or '-':<12} {str(c.get('current_users') or '-'):>6} "
            f"{state:<10} {started:<20} {h}h{m:02d}m"
        )


@app.command("show")
def cmd_show(
    name: Optional[str] = typer.Argument(None, help="Campaign name (default: active)"),
    events_limit: int = typer.Option(20, "--events", help="How many recent events to print"),
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
) -> None:
    """Show one campaign in detail (header + recent events)."""
    s = _resolve_store(store)
    camp = s.campaign(name) if name else s.active_campaign()
    if not camp:
        typer.echo("No such campaign." if name else "No active campaign.")
        raise SystemExit(2)

    started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(camp["started_at"]))
    elapsed = (camp["ended_at"] or int(time.time())) - camp["started_at"]
    h, m = divmod(elapsed // 60, 60)

    typer.echo(f"Campaign: {camp['name']}")
    typer.echo(f"  scenario:      {camp.get('scenario') or '-'}")
    typer.echo(f"  started:       {started}")
    typer.echo(f"  elapsed:       {h}h{m:02d}m")
    typer.echo(f"  state:         {'active' if camp['ended_at'] is None else 'ended'}")
    typer.echo(f"  initial users: {camp.get('initial_users')}")
    typer.echo(f"  current users: {camp.get('current_users')}")
    if camp.get("notes"):
        typer.echo(f"  notes:         {camp['notes']}")

    evs = s.read_events(campaign=camp["name"])
    if evs:
        recent = evs[-events_limit:]
        typer.echo(f"\nRecent events ({len(recent)} of {len(evs)}):")
        for ev in recent:
            ts_str = time.strftime("%m-%d %H:%M:%S", time.localtime(ev["ts"]))
            payload = ev.get("payload") or {}
            extra = " ".join(f"{k}={v}" for k, v in payload.items() if k != "text")
            text = payload.get("text", "")
            typer.echo(f"  {ts_str}  {ev['kind']:<14} {extra}{('  — ' + text) if text else ''}")

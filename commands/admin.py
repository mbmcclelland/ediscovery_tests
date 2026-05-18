"""
`dr-load admin` subcommands — bootstrap orgs, projects, and import jobs
without a browser, and schedule project lifetimes via at(1).

Operators pass names, not internal handles — the CLI resolves
connector/role/project handles via API. DRSysAdmin works against any
org it's been added to as Org Administrator; no separate org-user
credentials needed.

Endpoints used (verified live against build at 192.168.58.128:8443):
  realmManager/createSession, createOrganization, listOrganizations,
    initializeOrganization
  orgManager/listConnectors, listUsers, listTemplates, createDataArea,
    createCorpus, listProjects
  ecaManager/createCase
  projectManager/listCorpusSets, listTasks
  corpusSetManager/addCorpus
  corpusManager/createRepresentation
  adminOrgManager/requestProjectDelete, listDeletePendingProjects,
    approveProjectDeleteRequest
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import typer

from config import Config, config as default_config
from helpers import admin_ops as ops
from helpers.api_client import APIError, EDiscoveryClient

logger = logging.getLogger(__name__)

app = typer.Typer(
    no_args_is_help=True,
    help="Bootstrap orgs / projects / import jobs against a fresh install.",
)


# --------------------------------------------------------- shared utilities
def _client(cfg: Config | None = None) -> EDiscoveryClient:
    c = EDiscoveryClient(cfg or default_config)
    c.login()
    return c


def _ok(msg: str) -> None:
    typer.echo(typer.style("OK ", fg=typer.colors.GREEN, bold=True) + msg)


def _info(msg: str) -> None:
    typer.echo(typer.style("..  ", fg=typer.colors.BLUE) + msg)


def _fail(msg: str) -> None:
    typer.echo(typer.style("FAIL ", fg=typer.colors.RED, bold=True) + msg, err=True)


def _resolve_project_handle(client: EDiscoveryClient, org: str, name: str) -> str:
    """Resolve a project name to its handle, or exit with a clear error."""
    p = ops.find_project(client, org, name)
    if not p:
        _fail(f"No project named {name!r} in org {org!r}.")
        raise typer.Exit(2)
    handle = p.get("handle")
    if not handle:
        _fail(f"Project {name!r} has no handle field — server returned: {p}")
        raise typer.Exit(2)
    return str(handle)


def _resolve_connector_handle(client: EDiscoveryClient, org: str, name: str) -> str:
    c = ops.find_connector(client, org, name)
    if not c or not c.get("handle"):
        _fail(f"No connector named {name!r} visible in {org!r}. "
              f"Available: {[x.get('name') for x in ops.list_connectors(client, org)]}")
        raise typer.Exit(2)
    return str(c["handle"])


def _maybe_schedule_delete(name: str, org: str, lifetime: str | None) -> None:
    """If --lifetime was given, queue an at-job for delete-project."""
    if not lifetime:
        return
    try:
        seconds = ops.parse_duration(lifetime)
    except ValueError as e:
        _fail(str(e))
        raise typer.Exit(1)
    try:
        job_id = ops.schedule_delete(
            project_name=name, org=org, lifetime_seconds=seconds,
        )
    except Exception as e:
        _fail(f"Could not schedule auto-delete: {e}")
        raise typer.Exit(2)
    fire_time = datetime.now() + timedelta(seconds=seconds)
    _ok(f"Auto-delete scheduled: at-job {job_id} fires {fire_time:%Y-%m-%d %H:%M} "
        f"({lifetime} from now)")


# ------------------------------------------------------------------ commands
@app.command("create-org")
def create_org(
    name: str = typer.Argument(..., help="Organization name (e.g. 'training')"),
    description: str = typer.Option("", "--description", "-d"),
) -> None:
    """Create a new organization via realmManager/createOrganization.

    NOTE: Express Provisioning's "create the org admin user" step is a
    separate API not yet wired up — bootstrap admin users via the web UI
    or have DRSysAdmin added as Org Administrator to the new org.
    """
    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)
    try:
        if any(o.get("name") == name for o in ops.list_organizations(client)):
            _info(f"Organization '{name}' already exists — nothing to do.")
            return
        _info(f"Creating organization '{name}'...")
        handle = ops.create_organization(client, name, description)
        _ok(f"Created '{name}' (handle={handle}).")
        if not any(o.get("name") == name for o in ops.list_organizations(client)):
            _fail(f"Org '{name}' not found after create.")
            raise typer.Exit(3)
        _ok(f"Verified '{name}' present in realm.")
    finally:
        client.logout()


@app.command("list-connectors")
def list_connectors(
    org: str = typer.Argument(..., help="Organization name to list connectors for"),
) -> None:
    """List connectors in `org`.

    DRSysAdmin works as long as it has been added to `org` as Org
    Administrator (the default training setup). Older versions of this
    command required `-u/-p` for an org user because DRSysAdmin used to
    see zero connectors — that's no longer the case on this build.
    """
    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)
    try:
        ops.switch_to_org(client, org)
        connectors = ops.list_connectors(client, org)
        if not connectors:
            _info(f"No connectors visible in {org!r}.")
            return
        typer.echo(f"{'NAME':<40} {'TYPE':<10} HANDLE")
        for c in connectors:
            typer.echo(f"{c.get('name', ''):<40} "
                       f"{c.get('type', c.get('connectorType', '')):<10} "
                       f"{c.get('handle', '')}")
        _ok(f"{len(connectors)} connector(s) in {org!r}.")
    finally:
        client.logout()


@app.command("create-project")
def create_project(
    name: str = typer.Argument(None, help="Project name (auto-generated if omitted)"),
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION",
                            help="Target organization (e.g. 'training')"),
    description: str = typer.Option("", "--description", "-d"),
    lifetime: str = typer.Option(None, "--lifetime",
                                 help="Auto-delete after this duration. "
                                      "Examples: 1h, 30m, 7d, 90s, 2w"),
    role_handle: str = typer.Option(None, "--role-handle",
                                    help="Role handle override (rarely needed — "
                                         "auto-discovered from your user record by default). "
                                         "Deliberately NOT bound to an env var: a stale .env "
                                         "value would silently defeat auto-discovery."),
) -> None:
    """
    Create a project in `org` via ecaManager/createCase.

    Template attributes are discovered live; the role handle is looked
    up from the logged-in user's record in `org` (no need to know it).
    Pass --lifetime to schedule an auto-delete via the at(1) queue.
    """
    if not org:
        _fail("--org (or DR_ORG_ORGANIZATION) is required.")
        raise typer.Exit(1)
    proj_name = name or f"qa-{uuid.uuid4().hex[:8]}"
    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)
    try:
        _info(f"Creating project '{proj_name}' in '{org}'...")
        handle = ops.create_project(client, org=org, name=proj_name,
                                    role_handle=role_handle, description=description)
        _ok(f"Created project '{proj_name}' (handle={handle}).")
        match = ops.find_project(client, org, proj_name)
        if not match:
            _fail(f"Project '{proj_name}' not in listProjects after create.")
            raise typer.Exit(3)
        state = match.get("projectState") or match.get("state") or "UNKNOWN"
        _ok(f"Verified project present (state={state}).")
        _maybe_schedule_delete(proj_name, org, lifetime)
        typer.echo(f"\nproject_handle={handle}")
    finally:
        client.logout()


@app.command("create-import-job")
def create_import_job(
    project_name: str = typer.Argument(..., help="Project name (created already)"),
    connector: str = typer.Option(..., "--connector", "-c",
                                  help="Connector name (e.g. 'training-import-nfs-local')"),
    path: str = typer.Option(..., "--path", help="Source path within the connector"),
    name: str = typer.Option(None, "--name",
                             help="Data-area / corpus name (default: derived from --path)"),
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION"),
    lifetime: str = typer.Option(None, "--lifetime",
                                 help="Auto-delete the project after this duration. "
                                      "Examples: 1h, 30m, 7d"),
) -> None:
    """
    Submit the indexing pipeline against a project by name.

    Resolves the project and connector names to internal handles, then
    runs createDataArea → createCorpus → addCorpus → createRepresentation.
    """
    if not org:
        _fail("--org (or DR_ORG_ORGANIZATION) is required.")
        raise typer.Exit(1)
    short = name or Path(path).name or "import"
    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)
    try:
        ops.switch_to_org(client, org)
        project_handle = _resolve_project_handle(client, org, project_name)
        connector_handle = _resolve_connector_handle(client, org, connector)
        _info(f"Project   = {project_name} (handle={project_handle})")
        _info(f"Connector = {connector} (handle={connector_handle})")

        ops.switch_to_project(client, project_handle, org)
        _info(f"Running import pipeline (path={path!r})...")
        result = ops.create_import_job(
            client,
            project_handle=project_handle, org=org,
            connector_handle=connector_handle, path=path, name=short,
        )
        _ok(f"Data area: {result['data_area_handle']}")
        _ok(f"Corpus:    {result['corpus_handle']}")
        _ok(f"CorpusSet: {result['corpus_set_handle']}")
        _ok("Indexing pipeline submitted.")
        _maybe_schedule_delete(project_name, org, lifetime)
    finally:
        client.logout()


@app.command("delete-project")
def delete_project(
    project_name: str = typer.Argument(..., help="Project name to delete"),
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION"),
    handle: str = typer.Option(None, "--handle",
                               help="Skip listProjects lookup and delete by handle directly. "
                                    "Use when a half-failed createCase left the project in "
                                    "mgmtproject but hidden from listProjects (BUG_LOG B35). "
                                    "Get the handle from SERVER.log ('id : NNNN entityName: ...')."),
    cancel_schedule: bool = typer.Option(True, "--cancel-schedule/--keep-schedule",
                                         help="Also cancel any pending at-job for this project"),
) -> None:
    """
    Resolve project by name (or accept --handle directly), run the
    two-phase delete (requestProjectDelete → approveProjectDeleteRequest),
    and remove any pending scheduled delete for the same name from the
    at queue.

    --handle is the escape hatch for orphan projects that are invisible
    to listProjects but still exist server-side.
    """
    if not org:
        _fail("--org (or DR_ORG_ORGANIZATION) is required.")
        raise typer.Exit(1)
    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)
    try:
        ops.switch_to_org(client, org)
        if handle:
            project_handle = str(handle)
            _info(f"Deleting project '{project_name}' by --handle={project_handle} "
                  f"(skipping listProjects lookup)...")
        else:
            project_handle = _resolve_project_handle(client, org, project_name)
            _info(f"Deleting project '{project_name}' (handle={project_handle})...")
        ops.switch_to_project(client, project_handle, org)
        ok = ops.delete_project(client, project_handle=project_handle,
                                project_name=project_name,
                                system_org=default_config.organization)
        if not ok:
            _fail("Delete request submitted but approval did not land in time.")
            raise typer.Exit(2)
        _ok(f"Deleted '{project_name}'.")
        if cancel_schedule:
            cancelled = ops.cancel_scheduled_delete(project_name)
            if cancelled:
                _ok(f"Also cancelled pending at-job(s): {', '.join(cancelled)}")
    finally:
        client.logout()


@app.command("unschedule")
def unschedule(
    project_name: str = typer.Argument(..., help="Project name whose pending delete to cancel"),
) -> None:
    """Cancel any pending at-job that would auto-delete this project."""
    cancelled = ops.cancel_scheduled_delete(project_name)
    if not cancelled:
        _info(f"No pending at-job found for {project_name!r}.")
        return
    _ok(f"Cancelled at-job(s): {', '.join(cancelled)}")


@app.command("reschedule")
def reschedule(
    project_name: str = typer.Argument(..., help="Project name to (re-)arm auto-delete for"),
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION"),
    lifetime: str = typer.Option(..., "--lifetime",
                                 help="New duration before auto-delete. Examples: 30m, 1h, 7d"),
) -> None:
    """
    Re-arm auto-delete for an existing project (FR1).

    Cancels any prior dr-load-tagged at-job for this project (idempotent —
    a no-op if none exist), then queues a fresh at-job per --lifetime.
    Useful after `unschedule` or when an operator wants to extend a
    project's life without recreating it.
    """
    if not org:
        _fail("--org (or DR_ORG_ORGANIZATION) is required.")
        raise typer.Exit(1)

    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)
    try:
        # Verify the project actually exists before scheduling its deletion.
        ops.switch_to_org(client, org)
        if not ops.find_project(client, org, project_name):
            _fail(f"No project named {project_name!r} in org {org!r}. "
                  f"Nothing to reschedule.")
            raise typer.Exit(2)
    finally:
        client.logout()

    cancelled = ops.cancel_scheduled_delete(project_name)
    if cancelled:
        _info(f"Cancelled prior at-job(s): {', '.join(cancelled)}")
    _maybe_schedule_delete(project_name, org, lifetime)


@app.command("list")
def list_state(
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION",
                            help="Filter projects by org (omit for all visible orgs)"),
) -> None:
    """
    Combined view: live projects (from API) plus pending dr-load
    operations from the at queue. Run this when you want to see "what
    exists and what's scheduled to happen."
    """
    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)

    pending = {j["project_name"]: j for j in ops.list_scheduled_deletes() if j["project_name"]}

    try:
        orgs = [org] if org else [o.get("name") for o in ops.list_organizations(client)
                                  if o.get("name") not in (None, "super_system_customer")]

        typer.echo(f"\n{'PROJECT':<35} {'ORG':<22} {'STATE':<22} SCHEDULED-DELETE")
        typer.echo("-" * 105)
        total = 0
        for o in orgs:
            try:
                ops.switch_to_org(client, o)
                projs = client.post("orgManager/listProjects",
                                    extra_body={"contextHandle": o}).get("projects", [])
            except APIError:
                continue
            for p in projs:
                state = (p.get("projectActivationState") or p.get("projectState")
                         or p.get("state") or "?")
                raw_name = p.get("name") or ""
                # FR2: server returns name="" while a project is in
                # DELETE_PENDING. Render an explicit transitional marker
                # so operators can correlate by handle.
                if not raw_name and state == "DELETE_PENDING":
                    display_name = f"[deleting #{p.get('handle')}]"
                else:
                    display_name = raw_name or f"#{p.get('handle')}"
                sched = pending.get(raw_name, {}).get("scheduled_at", "—")
                typer.echo(f"{display_name:<35} {o:<22} {state:<22} {sched}")
                total += 1
        typer.echo("-" * 105)
        typer.echo(f"{total} project(s).")

        # List any scheduled jobs whose project name we did NOT see above
        # (i.e. the project was deleted manually or never created)
        orphan_sched = [j for j in pending.values()
                        if not any(j["project_name"] == p.get("name", "?")
                                   for o in orgs
                                   for p in client.post(
                                       "orgManager/listProjects",
                                       extra_body={"contextHandle": o},
                                       check=False,
                                   ).get("projects", []))]
        if orphan_sched:
            typer.echo("\nScheduled deletes with no matching project (consider unschedule):")
            for j in orphan_sched:
                typer.echo(f"  at-job {j['at_job_id']:>4}  fires {j['scheduled_at']}  "
                           f"target={j['project_name']!r} org={j['org']}")
    finally:
        client.logout()


def _state_color(state: str) -> str:
    """Map an operationState/projectState to a Rich color tag."""
    s = (state or "").upper()
    if s in ops.ACTIVE_TASK_STATES:
        return "yellow"
    if s == "SUCCESS":
        return "green"
    if s in ("FAILURE", "FAILED", "ERROR"):
        return "red"
    if s == "ACTIVE":
        return "green"
    if "DELETE" in s:
        return "magenta"
    return "white"


def _render_dashboard_rich(snap: dict, org: str):
    """Build a Rich renderable showing the four sections of a dashboard."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    # RUNNING JOBS
    running = Table(title=f"Running jobs ({len(snap['running'])})",
                    show_lines=False, header_style="bold yellow", expand=True)
    running.add_column("Project", style="cyan", no_wrap=True)
    running.add_column("Task", max_width=40, no_wrap=True, overflow="ellipsis")
    running.add_column("State", no_wrap=True)
    running.add_column("Docs", justify="right")
    running.add_column("Elapsed", justify="right", no_wrap=True)
    if snap["running"]:
        for r in snap["running"]:
            color = _state_color(r["state"])
            running.add_row(r["project"], r["task"],
                            Text(r["state"], style=color),
                            str(r["docs"]), ops._format_elapsed(r["elapsed"]))
    else:
        running.add_row(Text("(none)", style="dim"), "", "", "", "")

    # SCHEDULED JOBS
    scheduled = Table(title=f"Scheduled deletes ({len(snap['scheduled'])})",
                      show_lines=False, header_style="bold cyan", expand=True)
    scheduled.add_column("Project", style="cyan", no_wrap=True)
    scheduled.add_column("At-job", justify="right")
    scheduled.add_column("Fires at", no_wrap=True)
    if snap["scheduled"]:
        for s in snap["scheduled"]:
            scheduled.add_row(s["project"], str(s["at_job_id"]), s["scheduled_at"])
    else:
        scheduled.add_row(Text("(none)", style="dim"), "", "")

    # FINISHED JOBS
    finished = Table(title=f"Finished jobs (most recent first)",
                     show_lines=False, header_style="bold green", expand=True)
    finished.add_column("Project", style="cyan", no_wrap=True)
    finished.add_column("Task", max_width=40, no_wrap=True, overflow="ellipsis")
    finished.add_column("State", no_wrap=True)
    finished.add_column("Docs", justify="right")
    finished.add_column("Elapsed", justify="right", no_wrap=True)
    finished.add_column("Completed", no_wrap=True, style="dim")
    if snap["finished"]:
        for r in snap["finished"]:
            color = _state_color(r["state"])
            finished.add_row(r["project"], r["task"],
                             Text(r["state"], style=color),
                             str(r["docs"]), ops._format_elapsed(r["elapsed"]),
                             r["completed"] or "")
    else:
        finished.add_row(Text("(none)", style="dim"), "", "", "", "", "")

    # PROJECTS
    projects = Table(title=f"Projects in {org!r} ({len(snap['projects'])})",
                     show_lines=False, header_style="bold blue", expand=True)
    projects.add_column("Name", style="cyan", no_wrap=True)
    projects.add_column("Handle", justify="right", no_wrap=True, style="dim")
    projects.add_column("State", no_wrap=True)
    projects.add_column("Docs", justify="right")
    projects.add_column("Elapsed", justify="right", no_wrap=True)
    for p in snap["projects"]:
        color = _state_color(p["state"])
        projects.add_row(p["name"], p["handle"],
                         Text(p["state"], style=color),
                         str(p["doc_count"]), ops._format_elapsed(p["total_elapsed"]))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return Panel(
        Group(running, scheduled, finished, projects),
        title=f"[bold]dr-load dashboard[/]  ·  org [cyan]{org}[/]  ·  {timestamp}",
        subtitle="[dim]Ctrl-C to exit[/]",
        border_style="white",
    )


@app.command("dashboard")
def dashboard(
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION",
                            help="Org to inspect (e.g. 'training'). Required."),
    finished_limit: int = typer.Option(10, "--finished-limit",
                                       help="How many finished jobs to show (most recent first)"),
    rich_mode: bool = typer.Option(False, "--rich",
                                   help="Render a single snapshot using Rich (colors, boxes)."),
    watch: bool = typer.Option(False, "--watch",
                               help="Live-refresh the dashboard every --interval seconds. "
                                    "Implies --rich. Ctrl-C to exit."),
    interval: int = typer.Option(5, "--interval",
                                 help="Seconds between refreshes when --watch is set"),
    alt_screen: bool = typer.Option(False, "--alt-screen",
                                    help="Render --watch in the terminal's alternate screen "
                                         "(like vim/htop). Restores the prior view on exit."),
) -> None:
    """
    Snapshot dashboard: running jobs, scheduled deletes, finished jobs,
    and a project summary with doc counts and total compute time.

    Three render modes:
      (default)  plain text. Pipeable; scripts can grep this.
      --rich     one Rich-rendered snapshot. Same data, nicer table.
      --watch    Rich Live, auto-refresh every --interval seconds.

    Columns:
        DOCS      Documents in the corpus (corpus.documentCount, summed
                  across the project's corpora) or processed by the task
                  (task.numberResults).
        ELAPSED   Total compute time consumed by the project's tasks
                  (sum of task.secondsElapsed). Closest proxy to "job
                  size" without downloading the storage-usage CSV.
    """
    if not org:
        _fail("--org (or DR_ORG_ORGANIZATION) is required.")
        raise typer.Exit(1)
    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)

    if watch:
        # Quiet the api_client INFO logs so they don't smear the Live frame.
        # (login happened above; the loop only does post() calls which log
        #  at DEBUG.) Belt-and-suspenders: raise the logger level for the
        # duration of the watch.
        api_logger = logging.getLogger("helpers.api_client")
        old_level = api_logger.level
        api_logger.setLevel(logging.WARNING)

        from rich.console import Console
        from rich.live import Live
        console = Console()
        try:
            snap = ops.dashboard_snapshot(client, org)
            snap["finished"] = snap["finished"][:finished_limit]
            with Live(_render_dashboard_rich(snap, org),
                      console=console,
                      refresh_per_second=4,
                      screen=alt_screen) as live:
                while True:
                    try:
                        time.sleep(interval)
                    except KeyboardInterrupt:
                        break
                    try:
                        snap = ops.dashboard_snapshot(client, org)
                        snap["finished"] = snap["finished"][:finished_limit]
                        live.update(_render_dashboard_rich(snap, org))
                    except APIError as e:
                        # Don't crash the loop on transient errors; surface
                        # in-frame so the operator notices.
                        console.print(f"[red]APIError:[/] {e}")
                    except KeyboardInterrupt:
                        break
        finally:
            api_logger.setLevel(old_level)
            client.logout()
        return

    try:
        snap = ops.dashboard_snapshot(client, org)
        snap["finished"] = snap["finished"][:finished_limit]
    finally:
        client.logout()

    if rich_mode:
        from rich.console import Console
        Console().print(_render_dashboard_rich(snap, org))
        return

    # Plain text (default, pipeable)
    typer.echo(f"\n=== dr-load dashboard for org {org!r}"
               f"  @ {datetime.now():%Y-%m-%d %H:%M:%S} ===")

    typer.echo(f"\n--- RUNNING JOBS ({len(snap['running'])}) ---")
    if snap["running"]:
        typer.echo(f"{'PROJECT':<25} {'TASK':<40} {'STATE':<12} {'DOCS':>6} {'ELAPSED':>9}")
        for r in snap["running"]:
            typer.echo(f"{r['project']:<25} {r['task']:<40} {r['state']:<12} "
                       f"{r['docs']:>6} {ops._format_elapsed(r['elapsed']):>9}")
    else:
        typer.echo("  (none)")

    typer.echo(f"\n--- SCHEDULED JOBS ({len(snap['scheduled'])}) ---")
    if snap["scheduled"]:
        typer.echo(f"{'PROJECT':<25} {'AT-JOB':<8} {'FIRES AT':<32}")
        for s in snap["scheduled"]:
            typer.echo(f"{s['project']:<25} {s['at_job_id']:<8} {s['scheduled_at']:<32}")
    else:
        typer.echo("  (none)")

    typer.echo(f"\n--- FINISHED JOBS (last {finished_limit}) ---")
    if snap["finished"]:
        typer.echo(f"{'PROJECT':<25} {'TASK':<40} {'STATE':<10} {'DOCS':>6} {'ELAPSED':>9} {'COMPLETED'}")
        for r in snap["finished"]:
            typer.echo(f"{r['project']:<25} {r['task']:<40} {r['state']:<10} "
                       f"{r['docs']:>6} {ops._format_elapsed(r['elapsed']):>9} {r['completed']}")
    else:
        typer.echo("  (none)")

    typer.echo(f"\n--- PROJECTS in {org!r} ({len(snap['projects'])}) ---")
    if snap["projects"]:
        typer.echo(f"{'NAME':<35} {'HANDLE':<8} {'STATE':<22} {'DOCS':>6} {'ELAPSED':>9}")
        for p in snap["projects"]:
            typer.echo(f"{p['name']:<35} {p['handle']:<8} {p['state']:<22} "
                       f"{p['doc_count']:>6} {ops._format_elapsed(p['total_elapsed']):>9}")
    typer.echo("")


def _is_protected_description(desc: str) -> bool:
    """Case-insensitive substring match for 'do not delete' anywhere in `desc`."""
    return "do not delete" in (desc or "").lower()


def _bulk_delete(client: EDiscoveryClient, org: str, candidates: list[dict]) -> tuple[int, list[tuple[str, str]]]:
    """Delete every project in `candidates` (each must have 'name' + 'handle').
    Returns (success_count, [(name, error_string), ...]) for any failures."""
    ok = 0
    failures: list[tuple[str, str]] = []
    for p in candidates:
        name = p["name"]
        handle = str(p["handle"])
        _info(f"Deleting {name!r} (handle={handle})...")
        try:
            ops.switch_to_project(client, handle, org)
            if ops.delete_project(
                client,
                project_handle=handle,
                project_name=name,
                system_org=default_config.organization,
            ):
                ok += 1
                cancelled = ops.cancel_scheduled_delete(name)
                if cancelled:
                    _info(f"  also cancelled at-job(s): {', '.join(cancelled)}")
            else:
                failures.append((name, "delete approval did not land in time"))
        except APIError as e:
            failures.append((name, str(e)))
        except Exception as e:
            failures.append((name, f"{type(e).__name__}: {e}"))
    return ok, failures


@app.command("cleanall")
def cleanall(
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION",
                            help="Org whose projects to clean. Required."),
    yes: bool = typer.Option(False, "--yes", "-y",
                             help="Skip confirmation prompt."),
    dry_run: bool = typer.Option(False, "--dry-run",
                                 help="Show the plan; do not delete anything."),
) -> None:
    """
    Bulk-delete every project in `--org` EXCEPT:

        - projects that currently have an ACTIVE task
          (RUNNING / QUEUED / PENDING / PROCESSING)
        - projects whose description contains "do not delete"
          (case-insensitive substring match, anywhere in the text)

    Wraps `dr-load admin delete-project` per row, so each project's
    scheduled auto-delete at-job is cancelled as a side effect.
    """
    if not org:
        _fail("--org (or DR_ORG_ORGANIZATION) is required.")
        raise typer.Exit(1)

    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)

    try:
        _info(f"Snapshotting projects in {org!r}...")
        snap = ops.dashboard_snapshot(client, org)
        projects = snap["projects"]

        to_delete: list[dict] = []
        skipped: list[tuple[dict, str]] = []
        for p in projects:
            if p.get("running"):
                skipped.append((p, "running"))
            elif _is_protected_description(p.get("description", "")):
                skipped.append((p, "protected: \"do not delete\""))
            else:
                to_delete.append(p)

        typer.echo("")
        typer.echo(f"Plan for org {org!r}:")
        typer.echo(f"  {len(to_delete)} to delete · {len(skipped)} skipped "
                   f"· {len(projects)} total")
        if to_delete:
            typer.echo("\nWill DELETE:")
            for p in to_delete:
                desc = (p["description"] or "")[:40]
                typer.echo(f"  - {p['name']:<35} (handle={p['handle']}, desc={desc!r})")
        if skipped:
            typer.echo("\nWill SKIP:")
            for p, why in skipped:
                desc = (p["description"] or "")[:40]
                typer.echo(f"  - {p['name']:<35} ({why}; desc={desc!r})")

        if dry_run:
            typer.echo("\n[dry-run] No changes made.")
            return
        if not to_delete:
            _ok("Nothing to delete.")
            return

        if not yes:
            ok = typer.confirm(f"\nDelete {len(to_delete)} project(s) in {org!r}?",
                               default=False)
            if not ok:
                _info("Aborted.")
                raise typer.Exit(0)

        ok_count, failures = _bulk_delete(client, org, to_delete)
        typer.echo("")
        _ok(f"Deleted {ok_count}/{len(to_delete)} project(s).")
        if failures:
            _fail(f"{len(failures)} failure(s):")
            for name, err in failures:
                typer.echo(f"  - {name}: {err}", err=True)
            raise typer.Exit(2)
    finally:
        client.logout()


@app.command("purgeall")
def purgeall(
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION",
                            help="Org whose projects to purge. Required."),
    force: bool = typer.Option(False, "--force",
                               help="Skip the typed-confirmation guard "
                                    "(for scripted use; be sure)."),
) -> None:
    """
    Indiscriminately delete every project in `--org`. NO exclusions:
    running projects are interrupted, "do not delete"-protected projects
    are deleted anyway. Also cancels every dr-load-tagged at-job for the
    org so no scheduled deletes hang around pointing at gone projects.

    DANGEROUS. The default prompt requires typing the org name to confirm,
    so a typo doesn't blow away an org you didn't mean.
    """
    if not org:
        _fail("--org (or DR_ORG_ORGANIZATION) is required.")
        raise typer.Exit(1)

    try:
        client = _client()
    except APIError as e:
        _fail(f"Login failed: {e}")
        raise typer.Exit(1)

    try:
        ops.switch_to_org(client, org)
        projs = client.post("orgManager/listProjects",
                            extra_body={"contextHandle": org}).get("projects", [])
        if not projs:
            _ok(f"No projects in {org!r} to purge.")
            return

        typer.echo("")
        typer.secho(f"!!! PURGE PLAN for org {org!r} !!!", fg=typer.colors.RED, bold=True)
        typer.echo(f"  {len(projs)} project(s) — ALL will be deleted, including:")
        for p in projs:
            tag = ""
            if _is_protected_description(p.get("description", "")):
                tag = " [PROTECTED — will be deleted anyway]"
            typer.echo(f"  - {p.get('name', '#'+str(p.get('handle'))):<35} "
                       f"(handle={p.get('handle')}{tag})")

        if not force:
            typer.echo("")
            typed = typer.prompt(
                f"To confirm, type the org name exactly ({org!r})",
                default="",
                show_default=False,
            )
            if typed != org:
                _fail(f"Confirmation did not match {org!r}. Aborting.")
                raise typer.Exit(1)

        # Pull at-jobs first so we can flush them at the end (in case any
        # don't get caught by the per-project delete's name match)
        prior_atjobs = ops.list_scheduled_deletes()

        to_delete = [{"name": p.get("name") or f"#{p.get('handle')}",
                      "handle": str(p.get("handle"))} for p in projs]
        ok_count, failures = _bulk_delete(client, org, to_delete)

        # Belt-and-suspenders: any dr-load-tagged at-jobs for this org
        # that didn't get cancelled name-by-name (e.g. stale schedules
        # pointing at projects that no longer exist) get nuked here.
        flushed = 0
        for j in prior_atjobs:
            if j.get("org") == org:
                # cancel_scheduled_delete is by name; loop in case names overlap
                cancelled = ops.cancel_scheduled_delete(j.get("project_name", ""))
                flushed += len(cancelled)

        typer.echo("")
        _ok(f"Purged {ok_count}/{len(to_delete)} project(s) from {org!r}.")
        if flushed:
            _ok(f"Also flushed {flushed} extra at-job(s).")
        if failures:
            _fail(f"{len(failures)} failure(s):")
            for name, err in failures:
                typer.echo(f"  - {name}: {err}", err=True)
            raise typer.Exit(2)
    finally:
        client.logout()


@app.command("stage-testload")
def stage_testload(
    src: Path = typer.Option(None, "--src",
                             help="Source dir (default: tests/fixtures/testload/ in this repo)"),
    dest: Path = typer.Option(Path("/data/import/testload"), "--dest"),
    owner: str = typer.Option("auraria", "--owner",
                              help="chown the staged files to this user:user"),
) -> None:
    """Copy fixture files into `/data/import/testload/` (or `--dest`).
    Idempotent: existing files are overwritten with fresh fixture content.
    """
    try:
        n = ops.stage_testload_fixtures(src=src, dest=dest, owner=owner, require_chown=True)
    except FileNotFoundError as e:
        _fail(str(e))
        raise typer.Exit(1)
    except PermissionError as e:
        _fail(f"chown to {owner} failed: {e}. Run with sudo.")
        raise typer.Exit(1)
    for f in sorted(dest.iterdir()):
        _info(f"Staged {f}")
    _ok(f"Staged {n} fixture file(s) in {dest} (owner={owner}).")

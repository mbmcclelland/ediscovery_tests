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
                name = p.get("name", "?")
                state = (p.get("projectActivationState") or p.get("projectState")
                         or p.get("state") or "?")
                sched = pending.get(name, {}).get("scheduled_at", "—")
                typer.echo(f"{name:<35} {o:<22} {state:<22} {sched}")
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

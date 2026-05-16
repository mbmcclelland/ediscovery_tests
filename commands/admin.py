"""
`dr-load admin` subcommands — bootstrap orgs, projects, and import jobs
without a browser.

Thin Typer wrappers over `helpers.admin_ops`. The CLI handles arg
parsing, credentials, and human-friendly output; admin_ops does the API
work. The pytest e2e smoke test reuses the same helpers, so what QA
exercises here is what CI verifies.

Endpoints used (verified live against build at 192.168.58.128:8443,
session 2026-05-16):
  realmManager/createSession, createOrganization, listOrganizations,
  initializeOrganization
  orgManager/listConnectors, listTemplates, createDataArea,
    createCorpus, listProjects
  ecaManager/createCase
  projectManager/listCorpusSets
  corpusSetManager/addCorpus
  corpusManager/createRepresentation
"""

from __future__ import annotations

import logging
import shutil
import uuid
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


# ------------------------------------------------------------------ commands
@app.command("create-org")
def create_org(
    name: str = typer.Argument(..., help="Organization name (e.g. 'training')"),
    description: str = typer.Option("", "--description", "-d"),
) -> None:
    """
    Create a new organization via realmManager/createOrganization.

    NOTE: Express Provisioning's "create the org admin user" step is a
    separate API (not yet wired up here — admin users are bootstrapped
    today through the web UI or by the DRSysAdmin pool).
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
        _ok(f"Created '{name}' (handle={handle}). Verifying via listOrganizations...")

        if not any(o.get("name") == name for o in ops.list_organizations(client)):
            _fail(f"Org '{name}' not found after create.")
            raise typer.Exit(3)
        _ok(f"Verified '{name}' present in realm.")
    finally:
        client.logout()


@app.command("list-connectors")
def list_connectors(
    org: str = typer.Argument(..., help="Organization name to scope the listing to"),
    org_user: str = typer.Option(None, "--user", "-u", envvar="DR_ORG_USERNAME",
                                 help="Org user (e.g. admin). Required — DRSysAdmin sees 0 connectors."),
    org_pass: str = typer.Option(None, "--password", "-p", envvar="DR_ORG_PASSWORD",
                                 help="Org user password"),
) -> None:
    """
    List connectors in `org`. Must run as an org user — DRSysAdmin returns
    zero connectors on this build (BUG_LOG B14).
    """
    if not org_user or not org_pass:
        _fail("--user and --password (or DR_ORG_USERNAME / DR_ORG_PASSWORD) are required.")
        raise typer.Exit(1)

    client = EDiscoveryClient(Config())
    try:
        client.login(username=org_user, password=org_pass, organization=org)
    except APIError as e:
        _fail(f"Login as {org_user}@{org} failed: {e}")
        raise typer.Exit(1)

    try:
        connectors = ops.list_connectors(client, org)
        if not connectors:
            _info(f"No connectors visible to {org_user}@{org}.")
            return
        typer.echo(f"{'NAME':<40} {'TYPE':<15} HANDLE")
        for c in connectors:
            typer.echo(f"{c.get('name', ''):<40} "
                       f"{c.get('type', c.get('connectorType', '')):<15} "
                       f"{c.get('handle', '')}")
        _ok(f"{len(connectors)} connector(s) listed.")
    finally:
        client.logout()


@app.command("create-project")
def create_project(
    name: str = typer.Argument(None, help="Project name (auto-generated if omitted)"),
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION",
                            help="Target organization (e.g. 'training')"),
    description: str = typer.Option("", "--description", "-d"),
    role_handle: str = typer.Option(None, "--role-handle", envvar="DR_ADMIN_ROLE_HANDLE",
                                    help="Role handle to grant on creation"),
    member: str = typer.Option("drsysadmin", "--member",
                               help="Username to add as project member"),
) -> None:
    """
    Create a project (case) in `org` via ecaManager/createCase, with
    template attributes discovered live via orgManager/listTemplates.
    """
    if not org:
        _fail("--org (or DR_ORG_ORGANIZATION) is required.")
        raise typer.Exit(1)
    if not role_handle:
        _fail("--role-handle (or DR_ADMIN_ROLE_HANDLE) is required. "
              "Look up the org's Organization Administrator role in authorization_roles.")
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
                                    role_handle=role_handle, description=description,
                                    member=member)
        _ok(f"Created project '{proj_name}' (handle={handle}). Verifying via listProjects...")
        match = ops.find_project(client, org, proj_name)
        if not match:
            _fail(f"Project '{proj_name}' not in listProjects after create.")
            raise typer.Exit(3)
        state = match.get("projectState") or match.get("state") or "UNKNOWN"
        _ok(f"Verified project present (state={state}).")
        typer.echo(f"\nproject_handle={handle}")
    finally:
        client.logout()


@app.command("create-import-job")
def create_import_job(
    project_handle: str = typer.Argument(..., help="Project handle (caseHandle) returned by create-project"),
    connector_handle: str = typer.Option(..., "--connector-handle", "-c",
                                         help="Connector handle (from list-connectors)"),
    path: str = typer.Option(..., "--path", help="Source path within the connector (e.g. '/testload')"),
    name: str = typer.Option(None, "--name", help="Data-area / corpus name (default: derived from path)"),
    org: str = typer.Option(None, "--org", envvar="DR_ORG_ORGANIZATION"),
) -> None:
    """
    Chain createDataArea → createCorpus → addCorpus to default corpusSet →
    createRepresentation. Submits the indexing pipeline; does not wait
    for it to finish.
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
        _info("Switching to project context...")
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
        typer.echo(f"\ndata_area_handle={result['data_area_handle']}")
        typer.echo(f"corpus_handle={result['corpus_handle']}")
        typer.echo(f"corpus_set_handle={result['corpus_set_handle']}")
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
    """
    Copy fixture files into `/data/import/testload/` (or `--dest`).
    Idempotent: existing files are overwritten with fresh fixture content.
    """
    if src is None:
        src = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "testload"
    if not src.is_dir():
        _fail(f"Source fixtures dir not found: {src}")
        raise typer.Exit(1)
    fixtures = sorted(p for p in src.iterdir() if p.is_file())
    if not fixtures:
        _fail(f"No files in {src}")
        raise typer.Exit(1)

    dest.mkdir(parents=True, exist_ok=True)
    for f in fixtures:
        target = dest / f.name
        shutil.copy2(f, target)
        _info(f"Staged {target}")
    try:
        shutil.chown(dest, user=owner, group=owner)
        for f in dest.iterdir():
            shutil.chown(f, user=owner, group=owner)
    except (LookupError, PermissionError) as e:
        _fail(f"chown to {owner} failed: {e}. Run with sudo.")
        raise typer.Exit(1)
    _ok(f"Staged {len(fixtures)} fixture file(s) in {dest} (owner={owner}).")

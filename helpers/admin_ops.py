"""
Workflow primitives for org / project / import-job orchestration.

Both `commands/admin.py` (the `dr-load admin` CLI) and the e2e smoke
test consume these. Keep them pure (no Typer, no print) — return data,
raise APIError on failure.

Each helper does its own API readback assertion where cheap, so callers
get a server-side confirmation rather than just trusting the create
response.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Iterable

from helpers.api_client import APIError, EDiscoveryClient

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------- orgs
def create_organization(client: EDiscoveryClient, name: str, description: str = "") -> str:
    """Create org `name`. Idempotent — returns existing handle if already present.

    Returns the org's handle (a numeric string on this build).
    """
    existing = client.post("realmManager/listOrganizations").get("organizations", [])
    for o in existing:
        if o.get("name") == name:
            return str(o.get("handle"))

    data = client.post("realmManager/createOrganization", extra_body={
        "name": name,
        "description": description,
        "organizationName": name,
    })
    org = data.get("organization") or {}
    handle = org.get("handle") or data.get("handle")
    if not handle:
        raise APIError("UNKNOWN", None, "createOrganization returned no handle", data)
    return str(handle)


def list_organizations(client: EDiscoveryClient) -> list[dict]:
    return client.post("realmManager/listOrganizations").get("organizations", [])


# ------------------------------------------------------------ connectors
def list_connectors(client: EDiscoveryClient, org: str) -> list[dict]:
    """List connectors visible in `org`. Caller must be logged in as an
    org user — DRSysAdmin sees zero connectors per BUG_LOG B14.
    """
    return client.post("orgManager/listConnectors", extra_body={
        "contextHandle": org,
    }).get("connectors", [])


def find_connector(client: EDiscoveryClient, org: str, name: str) -> dict | None:
    for c in list_connectors(client, org):
        if c.get("name") == name:
            return c
    return None


# ------------------------------------------------------------------ users
def list_users(client: EDiscoveryClient, org: str) -> list[dict]:
    """List users in `org` with their roleHandles embedded.

    `orgManager/listUsers` is the only role-discovery surface that works
    on this build — `listOrgRoles`/`listRoles`/`listAuthorizationRoles`
    all 500 or return empty (BUG_LOG B33).
    """
    return client.post("orgManager/listUsers", extra_body={
        "contextHandle": org,
    }).get("users", [])


def find_role_handle(client: EDiscoveryClient, org: str, username: str) -> str | None:
    """Look up the role handle assigned to `username` in `org`.

    Use case: the operator doesn't know internal handles. When creating
    a project, we discover the logged-in user's org-admin role handle
    via their user record and pass that to createCase.
    """
    for u in list_users(client, org):
        if u.get("name") == username or u.get("userName") == username:
            handles = u.get("roleHandles") or []
            if handles:
                return str(handles[0])
    return None


# --------------------------------------------------------------- projects
def switch_to_org(client: EDiscoveryClient, org: str) -> None:
    client.post("realmManager/initializeOrganization", extra_body={
        "requestHandle": None,
        "contextHandle": org,
        "organizationName": org,
    })


def switch_to_project(client: EDiscoveryClient, project_handle: str, org: str) -> None:
    client.post("realmManager/initializeOrganization", extra_body={
        "requestHandle": None,
        "contextHandle": project_handle,
        "organizationName": org,
        "systemScope": False,
    })


def create_project(
    client: EDiscoveryClient,
    *,
    org: str,
    name: str,
    role_handle: str | None = None,
    description: str = "",
    member: str | None = None,
) -> str:
    """Create project via ecaManager/createCase. Returns caseHandle.

    If `role_handle` is None, auto-discovers it from the logged-in user's
    record in `org` via listUsers. `member` defaults to the client's
    configured username (typically `drsysadmin` for DRSysAdmin sessions).

    createCase 500s with an empty `members.users` list on this build —
    a role handle is required, hence the auto-discovery.
    """
    switch_to_org(client, org)
    if member is None:
        member = client.cfg.username.lower()  # server expects lowercase
    if role_handle is None:
        role_handle = find_role_handle(client, org, member)
        if not role_handle:
            raise APIError(
                "UNKNOWN", None,
                f"Could not auto-discover role handle for {member!r} in {org!r} — "
                f"pass --role-handle explicitly", {},
            )
    attrs = client.discover_template_attributes(org)
    data = client.post("ecaManager/createCase", extra_body={
        "requestHandle": None,
        "contextHandle": org,
        "addToCaseData": False,
        "custodians": [],
        "name": name,
        "description": description or f"Created by admin_ops.create_project",
        "attributes": attrs,
        "membersRequestMessage": {
            "groups": [],
            "users": [{"name": member, "roleHandles": [role_handle]}],
        },
        "projectLogoBytes": None,
        "logoFileName": "",
        "systemScope": False,
        "reviewSystem": None,
        "reviewProjectId": 0,
    })
    handle = data.get("caseHandle") or data.get("handle")
    if not handle:
        raise APIError("UNKNOWN", None, "createCase returned no caseHandle", data)
    return str(handle)


def find_project(client: EDiscoveryClient, org: str, name: str) -> dict | None:
    projs = client.post("orgManager/listProjects", extra_body={
        "contextHandle": org,
    }).get("projects", [])
    for p in projs:
        if p.get("name") == name:
            return p
    return None


# ----------------------------------------------------------- import jobs
def create_import_job(
    client: EDiscoveryClient,
    *,
    project_handle: str,
    org: str,
    connector_handle: str,
    path: str,
    name: str,
) -> dict:
    """
    Run the full import pipeline:
      createDataArea -> createCorpus -> addCorpus to default corpusSet
      -> createRepresentation.
    Caller must be in project context (switch_to_project) first.

    Returns dict with handle fields for downstream verification.
    """
    da_data = client.post("orgManager/createDataArea", extra_body={
        "requestHandle": None,
        "contextHandle": project_handle,
        "connectorHandle": connector_handle,
        "description": "",
        "mode": "IMPORT",
        "name": f"{name}_{name}",
        "path": path,
        "skippedDirectories": [],
    })
    da = da_data.get("dataArea") or {}
    da_handle = da.get("handle") if isinstance(da, dict) else da_data.get("handle")
    if not da_handle:
        raise APIError("UNKNOWN", None, "createDataArea returned no handle", da_data)

    corpus_data = client.post("orgManager/createCorpus", extra_body={
        "requestHandle": None,
        "contextHandle": project_handle,
        "attributes": [{"name": "projecthandle", "value": project_handle}],
        "brand": True,
        "dataAreaHandles": [da_handle],
        "description": "",
        "name": name,
        "loadFileName": "",
        "loadFileType": "EDRM_XML",
        "loadFileProfileId": -1,
    })
    corpus = corpus_data.get("corpus") or {}
    corpus_handle = (corpus.get("handle") if isinstance(corpus, dict)
                     else corpus_data.get("corpusHandle"))
    if not corpus_handle:
        raise APIError("UNKNOWN", None, "createCorpus returned no handle", corpus_data)

    cs_data = client.post("projectManager/listCorpusSets", extra_body={
        "requestHandle": None,
        "contextHandle": project_handle,
        "projectHandle": project_handle,
        "count": 1,
        "startIndex": 0,
    })
    sets = cs_data.get("corpusSets", [])
    if not sets:
        raise APIError("UNKNOWN", None, "no corpusSets for project", cs_data)
    cs_handle = sets[0].get("handle")

    client.post("corpusSetManager/addCorpus", extra_body={
        "requestHandle": None,
        "contextHandle": project_handle,
        "corpusHandle": corpus_handle,
        "corpusSetHandle": cs_handle,
    })

    rep_data = client.post("corpusManager/createRepresentation", extra_body={
        "requestHandle": None,
        "contextHandle": project_handle,
        "attributes": [{"name": "projecthandle", "value": project_handle}],
        "corpusHandle": corpus_handle,
        "scanAttributes": [
            {"name": "batchNumber", "value": name},
            {"name": "projecthandle", "value": project_handle},
        ],
        "taskDescription": f"Creating representation Analytic Index for {name}",
        "typeList": ["CONTENT_INDEX", "VECTOR_SET"],
        "enablePatternDetection": True,
    })
    return {
        "data_area_handle": da_handle,
        "corpus_handle": corpus_handle,
        "corpus_set_handle": cs_handle,
        "representation_response": rep_data,
    }


# -------------------------------------------------------------- waiters
ACTIVE_STATES: frozenset = frozenset({"RUNNING", "QUEUED", "PENDING", "PROCESSING"})


def list_project_tasks(client: EDiscoveryClient, project_handle: str) -> list[dict]:
    return client.post("projectManager/listTasks", extra_body={
        "requestHandle": None,
        "contextHandle": project_handle,
        "projectHandle": project_handle,
    }).get("tasks", [])


def wait_for_tasks(
    client: EDiscoveryClient,
    project_handle: str,
    *,
    timeout: int = 300,
    interval: int = 5,
    max_consecutive_errors: int = 5,
) -> list[dict]:
    """
    Block until no project tasks are in an active state, or `timeout`
    seconds elapse. Caller must be in project context.

    Caps consecutive errors at `max_consecutive_errors` and re-raises
    rather than silently busy-looping (BUG_LOG B14c). Returns the final
    task list so the caller can assert on `taskStatus` / `operationState`.
    """
    start = time.time()
    consecutive_errors = 0
    last_tasks: list[dict] = []
    while time.time() - start < timeout:
        try:
            tasks = list_project_tasks(client, project_handle)
            consecutive_errors = 0
            last_tasks = tasks
            active = [t for t in tasks if t.get("state") in ACTIVE_STATES
                      or t.get("operationState") in ACTIVE_STATES]
            if not active:
                return tasks
        except Exception as e:
            consecutive_errors += 1
            logger.warning(
                "listTasks failed (consec=%d/%d): %s",
                consecutive_errors, max_consecutive_errors, e,
            )
            if consecutive_errors >= max_consecutive_errors:
                raise
        time.sleep(interval)
    return last_tasks


def all_tasks_succeeded(tasks: Iterable[dict]) -> bool:
    """True iff every task reports operationState=SUCCESS or taskStatus=SUCCESS."""
    tasks = list(tasks)
    if not tasks:
        return False
    for t in tasks:
        if (t.get("operationState") or t.get("taskStatus")) != "SUCCESS":
            return False
    return True


# --------------------------------------------------------------- delete
def delete_project(
    client: EDiscoveryClient,
    *,
    project_handle: str,
    project_name: str,
    system_org: str,
    max_attempts: int = 30,
    interval: int = 3,
) -> bool:
    """
    Two-phase delete: requestProjectDelete in project scope, then poll
    listDeletePendingProjects in system scope and approveProjectDeleteRequest.

    Matches the pending request by exact `projectHandle` field (avoiding
    BUG_LOG B14b's substring-on-stringified-dict bug).

    Returns True if the approve call returned successfully; False on timeout.
    """
    # requestProjectDelete is non-idempotent — it 500s with
    # "Deletion of this project has already been requested" if a prior
    # request is still pending. Swallow that case so cleanup recovers
    # from a partial earlier run.
    try:
        client.post("adminOrgManager/requestProjectDelete", extra_body={
            "requestHandle": None,
            "contextHandle": project_handle,
            "projectHandle": project_handle,
            "taskDescription": f"Delete Project {project_name}",
            "systemScope": True,
        })
    except APIError as e:
        msg = (e.extended_status or "").lower()
        if "already been requested" not in msg:
            raise

    # Switch back to system scope for the approval step
    switch_to_org(client, system_org)

    # Live API response shape (verified 2026-05-16):
    #   { "requests": [{ "handle": "<adminReqHandle>",
    #                    "objectHandle": "<projectHandle>",
    #                    "objectName": "<projectName>",
    #                    "adminRequestObjectType": "PROJECT",
    #                    "requestStatus": "PENDING", ... }, ... ] }
    for _ in range(max_attempts):
        time.sleep(interval)
        data = client.post("adminOrgManager/listDeletePendingProjects", extra_body={
            "requestHandle": None,
            "systemScope": True,
            "contextHandle": system_org,
        })
        for req in data.get("requests", []):
            if req.get("adminRequestObjectType") != "PROJECT":
                continue
            if (str(req.get("objectHandle")) == str(project_handle)
                    or req.get("objectName") == project_name):
                client.post("adminOrgManager/approveProjectDeleteRequest", extra_body={
                    "requestHandle": None,
                    "contextHandle": project_handle,
                    "handle": req.get("handle"),
                    "systemScope": True,
                    "taskDescription": f"Approving delete for {project_name}",
                })
                return True
    return False


# ----------------------------------------------------------- scheduling
# Background scheduling uses the standard `at(1)` queue. atd is enabled
# and active on this RHEL build; no new daemon to maintain. The queued
# script holds DR_* credentials inline so it can call dr-load when it
# fires — acceptable for a single-tenant QA VM; not for shared hosts.

_DURATION_UNITS = {
    "s": 1, "sec": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
}


def parse_duration(s: str) -> int:
    """Parse '1h' / '30m' / '7d' / '90s' / '2w' into seconds.

    Whitespace tolerated; case-insensitive. Raises ValueError on garbage.
    """
    if not s:
        raise ValueError("empty duration")
    m = re.fullmatch(r"\s*(\d+)\s*([a-zA-Z]+)\s*", s)
    if not m:
        raise ValueError(f"could not parse duration {s!r} — try '1h', '30m', '7d', '90s'")
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit not in _DURATION_UNITS:
        raise ValueError(f"unknown unit {unit!r} in {s!r} — use s/m/h/d/w")
    return n * _DURATION_UNITS[unit]


_AT_TAG = "DR_LOAD_SCHEDULED"


def _env_export_block(env_vars: Iterable[str]) -> str:
    """Render `export FOO=value` lines for every var in `env_vars` that
    is set in the current process environment. Values are shell-escaped.
    """
    lines = []
    for name in env_vars:
        if name in os.environ:
            lines.append(f"export {name}={shlex.quote(os.environ[name])}")
    return "\n".join(lines)


# Env vars that the scheduled `dr-load admin delete-project` invocation
# will need at fire time. Keep this list explicit — anything outside it
# is not snapshotted into the at-spool.
_SCHEDULED_ENV_VARS = (
    "DR_BASE_URL", "DR_USERNAME", "DR_PASSWORD", "DR_ORGANIZATION",
    "DR_LDAP_DOMAIN", "DR_VERIFY_SSL", "DR_ORG_ORGANIZATION",
    "DR_REQUEST_TIMEOUT", "DR_LONG_REQUEST_TIMEOUT",
)


def schedule_delete(
    *,
    project_name: str,
    org: str,
    lifetime_seconds: int,
    dr_load_binary: str | None = None,
) -> str:
    """Queue an `at` job that runs `dr-load admin delete-project NAME`
    after `lifetime_seconds`. Returns the at-job ID (as a string).

    Captures the relevant DR_* env vars from the current process so the
    scheduled invocation can authenticate without the user re-exporting
    them. Stored in /var/spool/at/<id> (root-owned, mode 700) — fine for
    a single-tenant QA VM, not for prod.
    """
    if not shutil.which("at"):
        raise RuntimeError("at(1) is not installed — `dnf install at` and `systemctl enable --now atd`")

    bin_path = dr_load_binary or shutil.which("dr-load") or "dr-load"
    minutes = max(1, (lifetime_seconds + 59) // 60)  # at granularity is minutes
    env_block = _env_export_block(_SCHEDULED_ENV_VARS)
    # The leading "echo" line is a tag the listing code can grep for to
    # identify dr-load-scheduled jobs (vs. other things in the at queue).
    script = (
        f"#!/bin/sh\n"
        f"# {_AT_TAG} project={project_name} org={org} created={int(time.time())}\n"
        f"echo '{_AT_TAG}' >/dev/null\n"
        f"{env_block}\n"
        f"{shlex.quote(bin_path)} "
        f"admin delete-project {shlex.quote(project_name)} "
        f"--org {shlex.quote(org)}\n"
    )
    proc = subprocess.run(
        ["at", "now", "+", str(minutes), "minutes"],
        input=script, capture_output=True, text=True, check=True,
    )
    # at emits "job 42 at <when>" to stderr; capture the job id
    m = re.search(r"job\s+(\d+)\b", proc.stderr)
    if not m:
        raise RuntimeError(f"could not parse at output: {proc.stderr!r}")
    return m.group(1)


def list_scheduled_deletes() -> list[dict]:
    """Return the dr-load-tagged at jobs.

    Each entry: {at_job_id, project_name, org, scheduled_at (str), created_at}.
    Jobs not tagged with our sentinel are filtered out so we don't
    list user-created at entries unrelated to dr-load.
    """
    if not shutil.which("atq"):
        return []
    q = subprocess.run(["atq"], capture_output=True, text=True, check=False)
    out: list[dict] = []
    for line in q.stdout.splitlines():
        # Format: "<id>\t<datetime>\t<queue>\t<user>"
        parts = line.split("\t")
        if not parts:
            continue
        job_id = parts[0].strip()
        when = parts[1].strip() if len(parts) > 1 else ""
        try:
            body = subprocess.run(
                ["at", "-c", job_id], capture_output=True, text=True, check=True,
            ).stdout
        except subprocess.CalledProcessError:
            continue
        if _AT_TAG not in body:
            continue
        project_match = re.search(r"# " + _AT_TAG + r"\s+project=(\S+)\s+org=(\S+)\s+created=(\d+)", body)
        out.append({
            "at_job_id": job_id,
            "scheduled_at": when,
            "project_name": project_match.group(1) if project_match else None,
            "org": project_match.group(2) if project_match else None,
            "created_at": int(project_match.group(3)) if project_match else None,
        })
    return out


def cancel_scheduled_delete(project_name: str) -> list[str]:
    """Remove all at jobs targeting `project_name`. Returns the list of
    cancelled at-job IDs.
    """
    cancelled = []
    for j in list_scheduled_deletes():
        if j["project_name"] == project_name:
            subprocess.run(["atrm", j["at_job_id"]], check=False)
            cancelled.append(j["at_job_id"])
    return cancelled


# ---------------------------------------------------------- fixtures
_DEFAULT_FIXTURE_SRC = (Path(__file__).resolve().parent.parent
                        / "tests" / "fixtures" / "testload")


def stage_testload_fixtures(
    *,
    src: Path | None = None,
    dest: Path = Path("/data/import/testload"),
    owner: str = "auraria",
    require_chown: bool = True,
) -> int:
    """
    Copy fixture files from `src` into `dest`, chown to `owner`.
    Returns the count of files staged. Idempotent.

    Used by both `dr-load admin stage-testload` and the smoke-test
    fixture in `tests/test_e2e_bootstrap.py` so the import job never
    fails opaquely because `/data/import/testload/` is missing.

    `require_chown=False` lets callers (e.g. tests not running as root)
    skip the chown step gracefully when it would otherwise fail.
    """
    if src is None:
        src = _DEFAULT_FIXTURE_SRC
    if not src.is_dir():
        raise FileNotFoundError(f"fixtures dir not found: {src}")
    fixtures = sorted(p for p in src.iterdir() if p.is_file())
    if not fixtures:
        raise FileNotFoundError(f"no files in {src}")

    dest.mkdir(parents=True, exist_ok=True)
    for f in fixtures:
        shutil.copy2(f, dest / f.name)
    try:
        shutil.chown(dest, user=owner, group=owner)
        for f in dest.iterdir():
            shutil.chown(f, user=owner, group=owner)
    except (LookupError, PermissionError):
        if require_chown:
            raise
    return len(fixtures)


def is_testload_staged(dest: Path = Path("/data/import/testload")) -> bool:
    """True iff `dest` exists, is a directory, and contains at least one file."""
    if not dest.is_dir():
        return False
    return any(p.is_file() for p in dest.iterdir())

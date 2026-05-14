"""
Role-aware data fetchers for the dr-tui dashboard.

Sync EDiscoveryClient calls are invoked from Textual's worker threads
(@work(thread=True)), so these functions are deliberately sync.

The two user roles take different paths:
  - DRSysAdmin   → realm-wide via realmManager/listSystemUserProjectsByUserName,
                    needs realmManager/initializeOrganization to read org-scoped
                    resources (connectors).
  - admin@training → org-scoped via orgManager/listUserProjectsForAllOrgs;
                      adminOrgManager/listConnectors works directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from helpers.api_client import APIError, EDiscoveryClient


@dataclass
class Connector:
    name: str
    type: str
    mode: str
    status: str
    host: str
    path: str
    handle: str


@dataclass
class OrgInfo:
    """Lightweight org row for the Organizations tree."""
    name: str
    handle: str
    description: str = ""


@dataclass
class JobRow:
    project: str
    job: str
    task_handle: str
    state: str          # "RUNNING" | "COMPLETE"
    started: str        # human-readable
    completed: str      # human-readable or ""
    duration: str       # "0h:1m:42s" style from server, or ""
    org: str = ""           # extracted from the project's listing context
    user: str = ""          # who requested it
    # Snapshot of the full task payload — used by the Jobs Monitor modal
    # to render the per-job detail pane (currentStatus sections, attributes).
    raw: dict = None


@dataclass
class DeletedProject:
    """Historical project from `realmManager/listDeletedProjects`."""
    project_id: int
    project_name: str
    description: str
    org_name: str
    user_name: str
    date_created: str
    date_deleted: str


@dataclass
class MailServerConfig:
    """Realm mail server / SMTP config (`realmManager/getMailServerConfig`)."""
    configured: bool
    smtp_host: str
    smtp_port: int
    smtp_auth: bool


@dataclass
class SplashMessage:
    """Login-banner splash message (`realmManager/getSplashMessage`)."""
    enabled: bool
    message: str


@dataclass
class PasswordPolicy:
    """Realm password policy (`realmManager/getPasswordPolicy`)."""
    enforce_strong: bool
    min_length: int
    min_uppercase: int
    min_lowercase: int
    min_numbers: int
    min_symbols: int
    expiration_days: int


@dataclass
class InactivityTimeout:
    """Realm session inactivity timeout."""
    seconds: int


@dataclass
class LicenseField:
    """One row from `realmManager/getLicenseInfo` (`{label, value}`)."""
    label: str
    value: str


@dataclass
class NodeInfo:
    """One realm node from `realmManager/listNodes`."""
    handle: str
    name: str
    ip_address: str
    node_type: str               # "FULL" / "MGMT" / …
    monitor_status: str          # "AVAILABLE" / "UNAVAILABLE"
    ae_status: str
    connector_status: str
    storage_status: str
    cores: int
    threads_executing: int
    storage_export: str = ""
    storage_name: str = ""
    analytic_mode: str = ""


@dataclass
class NodeComponent:
    """One row of `componentStatusList` from `getNodeStatus`."""
    name: str
    status: str
    threads: int
    memory_bytes: int
    last_poll: str


@dataclass
class NodeStorageMount:
    name: str
    status: str
    mount_point: str
    kb_used: int
    kb_available: int
    kb_allocated: int


@dataclass
class NodeStatusDetail:
    """Combined result of `realmManager/getNodeStatus`."""
    node: NodeInfo
    components: list           # list[NodeComponent]
    storage: list              # list[NodeStorageMount]
    connectors: int            # count — names rarely interesting


@dataclass
class StorageDepot:
    name: str
    use_type: str               # "DOCUMENT_STORE" | "INDEX_STORE"
    fqdn: str
    export: str
    in_service: bool
    kb_used: int
    kb_available: int
    allocation: int
    handle: str = ""


@dataclass
class SystemDepot:
    """Realm-wide system storage depot (singleton)."""
    depot_id: str
    name: str
    description: str
    directory_path: str
    attributes: list[tuple[str, str]]   # list of (name, value)


@dataclass
class VirusDefs:
    enabled: bool
    frequency: str
    run_hour: int
    running: bool
    update_status: str
    updated_on: str      # human-readable
    version: str


@dataclass
class UserRow:
    handle: str
    display: str
    email: str
    enabled: bool
    locked: bool
    mfa: bool
    last_access: str     # human-readable
    roles: str           # comma-joined role names
    is_admin: bool       # True if "Organization Administrator" role assigned


@dataclass
class GroupRow:
    handle: str
    name: str
    description: str
    members: int
    # First role assigned to the group, used by the CRUD edit modal.
    # Empty strings when no role is set.
    role_handle: str = ""
    role_name: str = ""


@dataclass
class ProjectRow:
    name: str
    handle: str
    created: str
    state: str


@dataclass
class OrgStorageRow:
    depot_name: str
    use_type: str       # "DOCUMENT_STORE" / "INDEX_STORE" / "SYSTEM_STORE"
    kb_used: int
    kb_available: int


# ----------------------------------------------------------------------------- connectors
def list_connectors(client: EDiscoveryClient, org: str) -> list[Connector]:
    """List connectors visible in *org*. Caller picks the right client."""
    # Org-context call. For DRSysAdmin, initializeOrganization must have been
    # called first; for the org user it's just their org.
    resp = client.post(
        "adminOrgManager/listConnectors",
        extra_body={"contextHandle": org, "systemScope": False},
    )
    out: list[Connector] = []
    for c in resp.get("connectors", []) or []:
        out.append(Connector(
            name=c.get("name") or "<unnamed>",
            type=c.get("type") or "?",
            mode=c.get("mode") or "?",
            status=c.get("status") or "?",
            host=c.get("networkId") or c.get("remoteHost") or "",
            path=c.get("offset") or c.get("remotePath") or "",
            handle=c.get("handle") or "",
        ))
    return out


def deactivate_connectors(
    client: EDiscoveryClient, *, org: str, names: list[str],
) -> dict:
    """Soft-delete one or more connectors — sets status=DEACTIVATED.

    Maps to `adminOrgManager/deactivateConnectors` (returns 204; the
    D1 fix in `api_client.post()` yields `{}`). Note the body sends
    connector **names** in a `handles` list, not the actual handles —
    quirky API choice, but that's what the captured shape uses.

    The row stays visible in `listConnectors` afterwards with
    `status: "DEACTIVATED"` — use `delete_connector()` for true removal.
    """
    return client.post(
        "adminOrgManager/deactivateConnectors",
        extra_body={
            "contextHandle": org,
            "handles": list(names),
        },
    )


def delete_connector(
    client: EDiscoveryClient, *, org: str, handle: str, name: str,
) -> dict:
    """Hard-delete a connector — removes the row entirely (returns 204).

    Maps to `orgManager/deleteConnector`. `taskDescription` is just a
    human-readable label for the async-delete job that surfaces in
    `realmManager/listDeletePendingProjects`-style lists; the UI fills
    it with the connector's name.
    """
    return client.post(
        "orgManager/deleteConnector",
        extra_body={
            "contextHandle": org,
            "handle": handle,
            "taskDescription": name,
        },
    )


def list_organizations_sys(client: EDiscoveryClient) -> list[OrgInfo]:
    """DRSysAdmin: list every organization in the realm."""
    resp = client.post(
        "realmManager/listOrganizations",
        extra_body={
            "contextHandle": "super_system_customer",
            "count": 0, "startIndex": 0, "filters": [],
            "systemScope": True,
        },
    )
    out: list[OrgInfo] = []
    for o in resp.get("organizations", []) or []:
        out.append(OrgInfo(
            name=o.get("name") or "?",
            handle=o.get("handle") or "",
            description=o.get("description") or "",
        ))
    return out


def ensure_org_context(sys_client: EDiscoveryClient, org: str) -> None:
    """DRSysAdmin needs this before reading org-scoped resources."""
    sys_client.post(
        "realmManager/initializeOrganization",
        extra_body={"organizationName": org},
        check=False,  # initializeOrganization may have empty body / no status
    )


# ----------------------------------------------------------------------------- projects
def list_projects_sys(client: EDiscoveryClient, sys_username: str) -> list[tuple[str, dict]]:
    """Return [(org_name, project_dict), …] across all orgs the sys user sees."""
    resp = client.post(
        "realmManager/listSystemUserProjectsByUserName",
        extra_body={
            "userName": sys_username.lower(),
            "startIndex": 0, "count": 500, "filters": [],
        },
    )
    out = []
    for grp in resp.get("userOrgProjects", []) or []:
        org = grp.get("organizationName") or "?"
        for p in grp.get("projects", []) or []:
            out.append((org, p))
    return out


def list_projects_org(client: EDiscoveryClient) -> list[tuple[str, dict]]:
    """Same shape as list_projects_sys but for an org-scoped user."""
    resp = client.post(
        "orgManager/listUserProjectsForAllOrgs",
        extra_body={
            "contextHandle": client.cfg.organization,
            "startIndex": 0, "count": 500, "filters": [],
            "systemUser": False,
        },
    )
    out = []
    for grp in resp.get("userOrgProjects", []) or []:
        org = grp.get("organizationName") or "?"
        for p in grp.get("projects", []) or []:
            out.append((org, p))
    return out


# ----------------------------------------------------------------------------- tasks
def _attr(task: dict, name: str) -> str:
    for a in task.get("attributes", []) or []:
        if a.get("name") == name:
            return str(a.get("value", ""))
    return ""


def _status_field(task: dict, section: str, field: str) -> str:
    for s in task.get("currentStatus", []) or []:
        if s.get("name") == section:
            for kv in s.get("data", []) or []:
                if kv.get("name", "").strip() == field:
                    return str(kv.get("value", ""))
    return ""


def list_tasks_for_project(
    client: EDiscoveryClient,
    project_handle: str,
    project_name: str,
    *,
    org_name: str = "",
) -> list[JobRow]:
    """Pull the task list for one project; split into running/complete by dateCompleted."""
    try:
        resp = client.post(
            "projectManager/listTasks",
            extra_body={
                "contextHandle": project_handle,
                "projectHandle": project_handle,
                "selectedAttributes": ["includesavedsearches"],
                "filters": [], "startIndex": 0, "count": 200,
            },
        )
    except APIError:
        return []

    out: list[JobRow] = []
    for t in resp.get("tasks", []) or []:
        date_completed = t.get("dateCompleted")
        # currentStatus → "Execution Summary" → "Job Description" / "Execution time"
        job_desc = _status_field(t, "Execution Summary", "Job Description") or "Task"
        exec_time = _status_field(t, "Execution Summary", "Execution time")
        started = (_status_field(t, "General Information", "Date Created")
                   or _status_field(t, "General Information", "Started")
                   or "")
        user = (_status_field(t, "General Information", "User")
                or _status_field(t, "General Information", "User Name")
                or "")
        completed = ""
        if date_completed:
            from datetime import datetime, timezone
            try:
                completed = datetime.fromtimestamp(
                    int(date_completed) / 1000, tz=timezone.utc,
                ).strftime("%H:%M:%S")
            except Exception:
                completed = str(date_completed)
        state = "COMPLETE" if date_completed else "RUNNING"
        out.append(JobRow(
            project=project_name,
            job=job_desc,
            task_handle=t.get("handle", "")[:16],
            state=state,
            started=started,
            completed=completed,
            duration=exec_time,
            org=org_name,
            user=user,
            raw=t,
        ))
    return out


def collect_jobs(
    client: EDiscoveryClient,
    projects: Iterable[tuple[str, dict]],
) -> tuple[list[JobRow], list[JobRow]]:
    """Fan out listTasks across projects, return (running, completed).

    Org name is propagated into each `JobRow.org` so the Jobs Monitor
    modal can display + filter by org without extra round-trips.
    """
    running: list[JobRow] = []
    completed: list[JobRow] = []
    for org, p in projects:
        ph = str(p.get("handle") or "")
        pname = p.get("name") or "?"
        if not ph:
            continue
        for row in list_tasks_for_project(client, ph, pname, org_name=org):
            (running if row.state == "RUNNING" else completed).append(row)
    return running, completed


# ----------------------------------------------------------------------------- jobs monitor (v0.10)
def list_realm_jobs(client: EDiscoveryClient) -> tuple[list[dict], int]:
    """Realm-wide active jobs from `realmManager/listJobs`.

    Returns (raw-jobs-list, totalCores). On empty realm both jobs[] and
    totalCores are present (cores reports the configured AE pool size
    even when nothing is running).
    """
    try:
        resp = client.post(
            "realmManager/listJobs",
            extra_body={
                "contextHandle": "super_system_customer",
                "systemScope": True,
                "startIndex": 0,
                "count": 500,
                "filters": [],
            },
        )
    except APIError:
        return [], 0
    return (resp.get("jobs") or []), int(resp.get("totalCores") or 0)


# --- v0.11: realm-wide task list (replaces per-project fan-out) -------------
def list_realm_tasks(
    client: EDiscoveryClient,
    *,
    operation_type: str = "",
) -> tuple[list["JobRow"], int]:
    """Realm-wide task list from `realmManager/listRealmTasks`.

    Returns `(rows, total_count)`. Each row is a `JobRow` built directly
    from the endpoint's pre-flat fields — no per-project fan-out, no
    `currentStatus` walk to extract orgName/owner/duration. `RUNNING`
    vs everything-else is decided by the `operationState` enum
    (CREATED / RUNNING / SUCCESS / FAILURE / CANCELLED / …).

    The body always sends a `SYNTAXERROR EQUALS false` filter — mirrors
    the DR Web UI, which uses this sentinel to mean "give me everything".
    When `operation_type` is supplied, an additional
    `OPERATION_TYPE EQUALS <value>` filter is appended.
    """
    filters = [
        {"attribute": "SYNTAXERROR", "operator": "EQUALS", "value": "false"},
    ]
    if operation_type:
        filters.append({
            "attribute": "OPERATION_TYPE",
            "operator": "EQUALS",
            "value": operation_type,
        })
    try:
        resp = client.post(
            "realmManager/listRealmTasks",
            extra_body={
                "contextHandle": "super_system_customer",
                "startIndex": 0,
                "count": 500,
                "filters": filters,
            },
        )
    except APIError:
        return [], 0

    out: list[JobRow] = []
    for t in resp.get("tasks") or []:
        op_state = str(t.get("operationState") or "").upper()
        # RUNNING / PAUSED / CREATED-ish are "active"; everything else
        # is history. The Jobs Monitor filter buckets use this split.
        state = "RUNNING" if op_state in (
            "RUNNING", "PAUSED", "CREATED", "QUEUED", "PENDING",
        ) else (op_state or "COMPLETE")
        out.append(JobRow(
            project=str(t.get("projectName") or "?"),
            job=str(t.get("description") or "Task"),
            task_handle=str(t.get("handle") or "")[:16],
            state=state,
            started=str(t.get("dateStarted") or ""),
            completed=str(t.get("dateCompleted") or ""),
            duration=str(t.get("secondsElapsed") or ""),
            org=str(t.get("orgName") or ""),
            user=str(t.get("owner") or ""),
            raw=t,
        ))
    return out, int(resp.get("totalCount") or len(out))


def list_operation_types(client: EDiscoveryClient) -> list[str]:
    """Enum of task operation types from `realmManager/listOperationTypes`.

    Used to populate the Jobs Monitor "filter by type" dropdown.
    Sentinel values `INVALID` and `NONE` are filtered out — they exist
    in the enum for protocol completeness but never appear on real tasks.
    """
    try:
        resp = client.post(
            "realmManager/listOperationTypes",
            extra_body={
                "contextHandle": "super_system_customer",
                "startIndex": 0,
                "count": 0,         # 0 = all (server-side default)
                "filters": [],
            },
        )
    except APIError:
        return []
    raw = resp.get("workbasketTypes") or []
    skip = {"INVALID", "NONE", ""}
    return sorted(str(w) for w in raw if str(w) not in skip)


def get_task_sri(
    client: EDiscoveryClient, *, task_handle: str,
) -> Optional[str]:
    """Look up the per-task SRI ("Instance ID") needed by `getSRITaskLog`.

    The SRI is only exposed inside the task's `currentStatus → Service
    Node Debug State → Instance ID` field — it's not in `listRealmTasks`
    or `listJobs`. We have to fetch the full task via
    `taskManager/getTasks` with `includeDrDebug: true`.

    Returns the SRI string (e.g. "593"), or None if the task has already
    finished and the AE no longer has a debug section for it.
    """
    try:
        resp = client.post(
            "taskManager/getTasks",
            extra_body={
                "taskHandles": [task_handle],
                "includeDrDebug": True,
                "includeResourceStatistics": False,
            },
        )
    except APIError:
        return None
    for t in resp.get("tasks") or []:
        for sec in t.get("currentStatus") or []:
            if str(sec.get("name") or "") != "Service Node Debug State":
                continue
            for kv in sec.get("data") or []:
                if str(kv.get("name") or "") == "Instance ID":
                    v = str(kv.get("value") or "").strip()
                    if v:
                        return v
    return None


def get_sri_task_log(
    client: EDiscoveryClient, *, task_sri: str, num_lines: int = 1000,
) -> list[str]:
    """Tail the per-task AE log via `taskManager/getSRITaskLog`.

    Returns up to `num_lines` lines (server may return fewer for short
    logs). Empty list on any error — caller decides how to surface that
    to the user.
    """
    try:
        resp = client.post(
            "taskManager/getSRITaskLog",
            extra_body={
                "numLines": int(num_lines),
                "taskSri": str(task_sri),
            },
        )
    except APIError:
        return []
    lines = resp.get("logLines") or []
    return [str(line) for line in lines]


def list_deleted_projects(client: EDiscoveryClient) -> list[DeletedProject]:
    """Historical project deletions from `realmManager/listDeletedProjects`."""
    try:
        resp = client.post(
            "realmManager/listDeletedProjects",
            extra_body={
                "contextHandle": "super_system_customer",
                "systemScope": True,
                "startIndex": 0,
                "count": 500,
                "filters": [],
            },
        )
    except APIError:
        return []
    out: list[DeletedProject] = []
    for d in resp.get("deletedProjects") or []:
        out.append(DeletedProject(
            project_id=int(d.get("projectId") or 0),
            project_name=str(d.get("projectName") or ""),
            description=str(d.get("description") or ""),
            org_name=str(d.get("orgName") or ""),
            user_name=str(d.get("userName") or ""),
            date_created=str(d.get("dateCreated") or ""),
            date_deleted=str(d.get("dateDeleted") or ""),
        ))
    return out


def _bool_or_status(resp) -> bool:
    """Normalize task-action responses.

    `taskManager/pauseTask` / `resumeTask` return a bare JSON boolean —
    api_client.post()'s `_check_status` chokes on that, so we catch and
    fall back to `post_raw`. True = action accepted, False = task was
    in a state where the action didn't apply.
    """
    if isinstance(resp, dict):
        return resp.get("status") == "SUCCESS" or bool(resp)
    return bool(resp)


def pause_task(client: EDiscoveryClient, *, task_handle: str) -> bool:
    """Pause a running task. Maps to `taskManager/pauseTask`.

    Returns True if the action was accepted, False if the task wasn't
    in a state that can be paused (already paused, already complete, …).
    """
    import json
    resp = client.post_raw(
        "taskManager/pauseTask",
        {
            "requestHandle": None,
            "contextHandle": "super_system_customer",
            "taskHandle": task_handle,
            "systemScope": True,
        },
    )
    try:
        return _bool_or_status(json.loads(resp.text))
    except Exception:
        return resp.status_code < 300


def resume_task(client: EDiscoveryClient, *, task_handle: str) -> bool:
    """Resume a paused task. Maps to `taskManager/resumeTask`."""
    import json
    resp = client.post_raw(
        "taskManager/resumeTask",
        {
            "requestHandle": None,
            "contextHandle": "super_system_customer",
            "taskHandle": task_handle,
            "systemScope": True,
        },
    )
    try:
        return _bool_or_status(json.loads(resp.text))
    except Exception:
        return resp.status_code < 300


def cancel_task(client: EDiscoveryClient, *, task_handle: str) -> None:
    """Cancel a running task. Maps to `taskManager/cancelTask`.

    Returns nothing — the endpoint returns 200 with an empty body,
    handled by api_client.post()'s D1 empty-response path. The task's
    operationState flips to `CANCELLED` on the next
    `listRealmTasks` / `listTasks` poll.

    Important: `systemScope: true` is required. Without it the call
    returns HTTP 500 (NullPointerException server-side).
    """
    client.post(
        "taskManager/cancelTask",
        extra_body={
            "taskHandle": task_handle,
            "systemScope": True,
        },
    )


def set_job_priority(
    client: EDiscoveryClient, *, task_handle: str, priority: str,
) -> None:
    """Set a task's queue priority. Maps to `taskManager/updateJobPriority`.

    `priority` must be one of "HIGH", "NORMAL", "LOW". The body is
    minimal — no contextHandle or systemScope; just
    `requestHandle: null` + `priority` + `taskHandle`.

    Returns 204 No Content — api_client.post()'s D1 fix yields {}.
    """
    p = (priority or "").upper()
    if p not in ("HIGH", "NORMAL", "LOW"):
        raise ValueError(f"priority must be HIGH/NORMAL/LOW, got {priority!r}")
    client.post(
        "taskManager/updateJobPriority",
        extra_body={
            "priority": p,
            "taskHandle": task_handle,
        },
    )


def format_job_detail(row: "JobRow") -> str:
    """Render a JobRow's `raw` task dict as a Rich-markup detail string.

    Walks every `currentStatus` section and every attribute, so the
    Jobs Monitor detail pane gets the same data the DR Web UI shows.
    """
    if row is None:
        return "[dim]No selection.[/]"
    raw = row.raw or {}
    chunks: list[str] = [
        f"[b]Job:[/] {row.job}",
        f"[b]Project:[/] {row.project}    [b]Org:[/] {row.org or '—'}",
        f"[b]State:[/] {row.state}    [b]Handle:[/] {row.task_handle}",
        f"[b]Started:[/] {row.started or '—'}",
        f"[b]Completed:[/] {row.completed or '—'}",
        f"[b]Duration:[/] {row.duration or '—'}",
    ]
    if row.user:
        chunks.append(f"[b]User:[/] {row.user}")
    chunks.append("")
    # Every status section in full.
    for sec in raw.get("currentStatus") or []:
        name = str(sec.get("name") or "").strip()
        if name:
            chunks.append(f"[b cyan]{name}[/]")
        for kv in sec.get("data") or []:
            k = str(kv.get("name") or "").strip()
            v = str(kv.get("value") or "").strip()
            if k or v:
                chunks.append(f"  {k}: {v}")
        chunks.append("")
    # Attributes block (key=value list — usually short).
    attrs = raw.get("attributes") or []
    if attrs:
        chunks.append("[b cyan]Attributes[/]")
        for a in attrs:
            k = str(a.get("name") or "").strip()
            v = str(a.get("value") or "").strip()
            chunks.append(f"  {k}: {v}")
    return "\n".join(chunks).rstrip()


# ----------------------------------------------------------------------------- helpers
def _epoch_ms_to_str(epoch_ms) -> str:
    """epoch-ms (int or str) → 'YYYY-MM-DD HH:MM' UTC, '' on failure."""
    if not epoch_ms:
        return ""
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(epoch_ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(epoch_ms)


def _join_role_names(user: dict) -> tuple[str, bool]:
    """Return (comma-joined role names, is_org_admin) for a user dict."""
    names: list[str] = []
    is_admin = False
    for r in user.get("roles", []) or []:
        nm = r.get("name") or ""
        if nm:
            names.append(nm)
        if nm == "Organization Administrator":
            is_admin = True
    if user.get("admin") is True:
        is_admin = True
    return ", ".join(names), is_admin


# ============================================================ system settings
# ----------------------------------------------------------------------------- landing dashboard (L1, L2, L3)
def get_license_info(client: EDiscoveryClient) -> list[LicenseField]:
    """Realm license details (`realmManager/getLicenseInfo`)."""
    resp = client.post(
        "realmManager/getLicenseInfo",
        extra_body={"contextHandle": "super_system_customer", "systemScope": True},
    )
    out: list[LicenseField] = []
    for row in resp.get("info", []) or []:
        out.append(LicenseField(
            label=row.get("label") or "",
            value=str(row.get("value") or ""),
        ))
    return out


def _node_from_dict(n: dict) -> NodeInfo:
    return NodeInfo(
        handle=str(n.get("handle") or ""),
        name=n.get("name") or "?",
        ip_address=n.get("ipAddress") or "",
        node_type=n.get("nodeType") or "",
        monitor_status=n.get("monitorStatus") or "",
        ae_status=n.get("aeComponentMonitorStatus") or "",
        connector_status=n.get("connectorMonitorStatus") or "",
        storage_status=n.get("storageMonitorStatus") or "",
        cores=int(n.get("numberCores") or 0),
        threads_executing=int(n.get("numberThreadsExecuting") or 0),
        storage_export=n.get("storageExport") or "",
        storage_name=n.get("storageName") or "",
        analytic_mode=n.get("analyticNodeMode") or "",
    )


def list_nodes(client: EDiscoveryClient) -> list[NodeInfo]:
    """List realm nodes (`realmManager/listNodes`)."""
    resp = client.post(
        "realmManager/listNodes",
        extra_body={
            "contextHandle": "super_system_customer",
            "sortByFilter": "NAME",
            "descending": False,
            "systemScope": True,
        },
    )
    return [_node_from_dict(n) for n in (resp.get("nodes") or [])]


def get_node_status(client: EDiscoveryClient, *, handle: str) -> NodeStatusDetail:
    """Detailed per-node status used by Monitoring → Node Status.

    Returns the node summary plus the three sub-lists (components,
    connectors, storage mounts). Component memory is reported in bytes;
    storage in KB.
    """
    resp = client.post(
        "realmManager/getNodeStatus",
        extra_body={
            "contextHandle": "super_system_customer",
            "handle": handle,
            "systemScope": True,
        },
    )
    node_d = resp.get("node") or {}
    node = _node_from_dict(node_d) if node_d else NodeInfo(
        handle="", name="?", ip_address="", node_type="", monitor_status="",
        ae_status="", connector_status="", storage_status="",
        cores=0, threads_executing=0,
    )
    components = [
        NodeComponent(
            name=c.get("name") or "?",
            status=c.get("monitorStatus") or "",
            threads=int(c.get("numberThreadsExecuting") or 0),
            memory_bytes=int(c.get("memory") or 0),
            last_poll=c.get("lastPollTime") or "",
        )
        for c in (resp.get("componentStatusList") or [])
    ]
    storage = [
        NodeStorageMount(
            name=s.get("name") or "?",
            status=s.get("monitorStatus") or "",
            mount_point=s.get("mountPoint") or "",
            kb_used=int(s.get("kbUsed") or 0),
            kb_available=int(s.get("kbAvailable") or 0),
            kb_allocated=int(s.get("kbAllocated") or 0),
        )
        for s in (resp.get("storageStatusList") or [])
    ]
    connectors = len(resp.get("connectorStatusList") or [])
    return NodeStatusDetail(
        node=node, components=components, storage=storage, connectors=connectors,
    )


# ----------------------------------------------------------------------------- realm settings (v0.08 reads)
def get_mail_server_config(client: EDiscoveryClient) -> MailServerConfig:
    """Read SMTP / mail server config. Empty body → `configured=False`."""
    resp = client.post(
        "realmManager/getMailServerConfig",
        extra_body={"contextHandle": "super_system_customer", "systemScope": True},
    )
    cfg = resp.get("mailServerConfig") or {}
    return MailServerConfig(
        configured=bool(cfg),
        smtp_host=str(cfg.get("smtpHostId") or ""),
        smtp_port=int(cfg.get("smtpHostPort") or 0),
        smtp_auth=bool(cfg.get("mailSmtpAuth")),
    )


def get_splash_message(client: EDiscoveryClient) -> SplashMessage:
    """Read login splash message."""
    resp = client.post(
        "realmManager/getSplashMessage",
        extra_body={"contextHandle": "super_system_customer"},
    )
    return SplashMessage(
        enabled=bool(resp.get("enabled")),
        message=str(resp.get("splashMessage") or ""),
    )


def get_password_policy(client: EDiscoveryClient) -> PasswordPolicy:
    """Read realm password policy."""
    resp = client.post(
        "realmManager/getPasswordPolicy",
        extra_body={"contextHandle": "super_system_customer", "systemScope": True},
    )
    return PasswordPolicy(
        enforce_strong=bool(resp.get("enforceStrongPasswords")),
        min_length=int(resp.get("minimumPasswordLength") or 0),
        min_uppercase=int(resp.get("minimumUppercaseLetters") or 0),
        min_lowercase=int(resp.get("minimumLowercaseLetters") or 0),
        min_numbers=int(resp.get("minimumNumbers") or 0),
        min_symbols=int(resp.get("minimumSymbols") or 0),
        expiration_days=int(resp.get("passwordExpirationInDays") or 0),
    )


def get_inactivity_timeout(client: EDiscoveryClient) -> InactivityTimeout:
    """Read realm session inactivity timeout (seconds)."""
    resp = client.post(
        "realmManager/getInactivityTimeout",
        extra_body={"contextHandle": "super_system_customer", "systemScope": True},
    )
    # Captured response uses `inactivityTimeoutInSeconds`; falling back to
    # `inactivityTimeout` for older builds.
    secs = (resp.get("inactivityTimeoutInSeconds")
            or resp.get("inactivityTimeout") or 0)
    return InactivityTimeout(seconds=int(secs))


# --- v0.12: realm-settings writes -------------------------------------------
def set_mail_server_config(
    client: EDiscoveryClient, *, smtp_host: str, smtp_port: int,
) -> MailServerConfig:
    """Write SMTP / mail server config via `realmManager/createMailServerConfig`.

    Despite the "create" name, this is the upsert path — there's no
    separate update endpoint. Body shape per v0.08 capture: `smtpHostId`
    + `smtpHostPort` (both as strings server-side; we coerce).

    v0.14.7: the set-endpoint responses on this realm don't reliably
    echo the persisted state (QA-11 finding — `setPasswordPolicy` /
    `setSplashMessage` return zeros while the actual persisted state is
    correct). We do a follow-up `get` and return THAT, so the caller
    sees what was actually written.
    """
    client.post(
        "realmManager/createMailServerConfig",
        extra_body={
            "contextHandle": "super_system_customer",
            "smtpHostId": str(smtp_host),
            "smtpHostPort": str(smtp_port),
            "systemScope": True,
        },
    )
    # Re-read to get the canonical persisted state.
    return get_mail_server_config(client)


def set_splash_message(
    client: EDiscoveryClient, *, enabled: bool, message: str,
) -> SplashMessage:
    """Write login banner via `realmManager/setSplashMessage`.

    v0.14.7: the set-endpoint response doesn't reliably echo the
    persisted state (QA-11 finding — set returned `enabled: false`
    while the persisted value was `true`). We follow up with `get`
    and return that.

    To clear the banner, pass `enabled=False` — the message text can
    stay (DR persists it for the next time the banner is re-enabled).
    """
    client.post(
        "realmManager/setSplashMessage",
        extra_body={
            "contextHandle": "super_system_customer",
            "enabled": bool(enabled),
            "splashMessage": str(message or ""),
            "systemScope": True,
        },
    )
    return get_splash_message(client)


def set_password_policy(
    client: EDiscoveryClient, *, policy: PasswordPolicy,
) -> PasswordPolicy:
    """Write realm password policy via `realmManager/setPasswordPolicy`.

    All eight numeric fields are mandatory in the body — server treats
    a missing field as "leave unchanged" inconsistently, so we send the
    whole policy every time.

    v0.14.7: the set-endpoint response on this realm doesn't echo the
    persisted state — it returns all zeros and `enforceStrongPasswords:
    false` regardless of what was actually written (QA-11 finding,
    confirmed against `getPasswordPolicy` immediately afterwards).
    We do a follow-up `get_password_policy()` and return that.
    """
    client.post(
        "realmManager/setPasswordPolicy",
        extra_body={
            "contextHandle": "super_system_customer",
            "enforceStrongPasswords": bool(policy.enforce_strong),
            "minimumPasswordLength": int(policy.min_length),
            "minimumUppercaseLetters": int(policy.min_uppercase),
            "minimumLowercaseLetters": int(policy.min_lowercase),
            "minimumNumbers": int(policy.min_numbers),
            "minimumSymbols": int(policy.min_symbols),
            "passwordExpirationInDays": int(policy.expiration_days),
            "systemScope": True,
        },
    )
    # Re-read to get the canonical persisted state.
    return get_password_policy(client)


def set_inactivity_timeout(
    client: EDiscoveryClient, *, seconds: int,
) -> InactivityTimeout:
    """Write session inactivity timeout (seconds) via `realmManager/setInactivityTimeout`.

    Server returns 204 No Content on success — api_client.post()'s D1
    fix yields {}. The fetcher returns the value we just wrote (the
    server doesn't echo it).
    """
    client.post(
        "realmManager/setInactivityTimeout",
        extra_body={
            "contextHandle": "super_system_customer",
            "inactivityTimeoutInSeconds": int(seconds),
            "systemScope": True,
        },
    )
    return InactivityTimeout(seconds=int(seconds))


# ----------------------------------------------------------------------------- storage depots (F1, F2)
def list_storage_depots(client: EDiscoveryClient, use_type: str) -> list[StorageDepot]:
    """List NFS storage areas filtered by storageUseType.

    use_type: 'DOCUMENT_STORE' or 'INDEX_STORE'.
    """
    resp = client.post(
        "realmManager/listRemoteNFSStorageAreas",
        extra_body={"contextHandle": "super_system_customer", "systemScope": True},
    )
    out: list[StorageDepot] = []
    for s in resp.get("storageAreas", []) or []:
        if s.get("storageUseType") != use_type:
            continue
        out.append(StorageDepot(
            name=s.get("name") or "?",
            use_type=s.get("storageUseType") or "?",
            fqdn=s.get("fqdn") or "",
            export=s.get("export") or "",
            in_service=bool(s.get("inService")),
            kb_used=int(s.get("kbUsed") or 0),
            kb_available=int(s.get("kbAvailable") or 0),
            allocation=int(s.get("allocationSize") or 0),
            handle=s.get("handle") or "",
        ))
    return out


# ----------------------------------------------------------------------------- storage depot writes (D4)
def create_storage_depot(
    client: EDiscoveryClient,
    *,
    name: str,
    fqdn: str,
    export: str,
    use_type: str,                # "DOCUMENT_STORE" | "INDEX_STORE"
    allocation_size: int = 0,
    in_use: bool = True,
) -> dict:
    """Create a remote NFS storage area (Document or Index depot).

    Maps to `realmManager/createRemoteNFSStorageArea`. Both depot variants
    share `facilityType=NFS_NAS` + `storageAreaType=DOC_STORAGE`; only
    `storageUseType` distinguishes them.

    NFS probe + facility provisioning can run well past the default 30 s
    HTTP timeout (observed ~30-60 s on a fresh install). Bump the timeout
    so callers see the success / failure status rather than a misleading
    client-side ReadTimeout while the server keeps working.
    """
    return client.post(
        "realmManager/createRemoteNFSStorageArea",
        extra_body={
            "contextHandle": "super_system_customer",
            "name": name,
            "fqdn": fqdn,
            "export": export,
            "facilityType": "NFS_NAS",
            "storageAreaType": "DOC_STORAGE",
            "storageUseType": use_type,
            "allocationSize": int(allocation_size),
            "inUse": bool(in_use),
            "monitoringNode": None,
            "systemScope": True,
        },
        timeout=120,
    )


def update_storage_depot(
    client: EDiscoveryClient,
    *,
    handle: str,
    fqdn: str,
    export: str,
    use_type: str,
    allocation_size: int = 0,
) -> dict:
    """Edit a remote NFS storage area.

    Maps to `storageAreaManager/updateRemoteNFSStorageArea`. The captured
    body uses `requestHandle` to carry the depot handle (overrides the
    usual `None`); the rest mirrors create minus `name` (immutable).
    """
    return client.post(
        "storageAreaManager/updateRemoteNFSStorageArea",
        extra_body={
            "requestHandle": handle,
            "contextHandle": "super_system_customer",
            "fqdn": fqdn,
            "export": export,
            "facilityType": "NFS_NAS",
            "storageAreaType": "DOC_STORAGE",
            "storageUseType": use_type,
            "allocationSize": int(allocation_size),
            "systemScope": True,
        },
        timeout=120,
    )


def delete_storage_depot(client: EDiscoveryClient, *, handle: str) -> None:
    """Delete a remote NFS storage area. Returns 204 — D1 fix yields {}."""
    client.post(
        "realmManager/deleteStorageArea",
        extra_body={
            "handle": handle,
            "contextHandle": "super_system_customer",
            "systemScope": True,
        },
    )


# ----------------------------------------------------------------------------- system roles (D5 helper)
def list_system_roles(client: EDiscoveryClient) -> list[tuple[str, str]]:
    """Return [(role_name, role_handle), …] for system-scoped roles.

    Maps to `realmManager/listSystemRoles` with `objectType: "ALL"`,
    `systemScope: true`. Used to populate the role dropdown when
    creating/editing a system user.
    """
    resp = client.post(
        "realmManager/listSystemRoles",
        extra_body={
            "contextHandle": "super_system_customer",
            "objectType": "ALL",
            "systemScope": True,
        },
    )
    out: list[tuple[str, str]] = []
    for r in resp.get("roles", []) or []:
        name = r.get("name")
        handle = r.get("handle")
        if name and handle:
            out.append((name, handle))
    return out


# ----------------------------------------------------------------------------- system user writes (D5)
def create_system_user(
    client: EDiscoveryClient,
    *,
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    role_handle: str,
    domain_handle: str = "local",
    mfa: bool = False,
) -> dict:
    """Create a realm-scoped (system) user.

    Maps to `adminOrgManager/createUser` with `orgName: "super_system_customer"`
    + `systemScope: true`. The captured shape carries `contextHandle: "training"`
    (whichever org the admin is currently in); we use `super_system_customer`
    so the call is self-contained for the dr-tui session.
    """
    return client.post(
        "adminOrgManager/createUser",
        extra_body={
            "contextHandle": "super_system_customer",
            "domainHandle": domain_handle,
            "local": True,
            "roleHandles": [role_handle],
            "password": password,
            "userName": username,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "mfa": bool(mfa),
            "conditionalOnIPAddress": False,
            "allowedIPAddressRange": None,
            "systemScope": True,
            "orgName": "super_system_customer",
        },
    )


def update_system_user(
    client: EDiscoveryClient,
    *,
    user_handle: str,
    email: str,
    first_name: str,
    last_name: str,
    role_handle: str,
    mfa: bool = False,
) -> dict:
    """Edit a system user. Maps to `userManager/updateUser`.

    `user_handle` is the realm-qualified handle (e.g.
    `newsystemuser@super_system_customer`). Username + domain are
    immutable; this endpoint mutates only display + role fields.
    """
    return client.post(
        "userManager/updateUser",
        extra_body={
            "contextHandle": "super_system_customer",
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "userHandle": user_handle,
            "roleHandles": [role_handle],
            "mfa": bool(mfa),
            "conditionalOnIPAddress": False,
            "allowedIPAddressRange": None,
            "systemScope": True,
        },
    )


def delete_system_user(client: EDiscoveryClient, *, username: str) -> dict:
    """Delete a system user. Maps to `adminOrgManager/deleteUser`."""
    return client.post(
        "adminOrgManager/deleteUser",
        extra_body={
            "contextHandle": "super_system_customer",
            "organizationName": "super_system_customer",
            "userName": username,
            "systemScope": True,
        },
    )


def reset_user_password(
    client: EDiscoveryClient,
    *,
    username: str,
    new_password: str,
    org_name: str = "super_system_customer",
) -> dict:
    """Admin-side password reset. Maps to `userManager/resetPassword`.

    For system users keep `org_name="super_system_customer"` (the working
    shape captured 2026-05-11; earlier attempts with the user's own org
    returned HTTP 500). For org users pass the user's org as *org_name*.
    """
    return client.post(
        "userManager/resetPassword",
        extra_body={
            "contextHandle": "super_system_customer",
            "userName": username,
            "newPassword": new_password,
            "orgName": org_name,
            "systemScope": True,
        },
    )


# ----------------------------------------------------------------------------- system group writes (D6)
def create_system_group(
    client: EDiscoveryClient,
    *,
    name: str,
    description: str,
    role_handle: str,
) -> dict:
    """Create a realm-scoped (system) group.

    Maps to `adminOrgManager/createGroup` — captured 2026-05-12.
    Body shape is `name + description + roleHandles` plus the
    `organizationName: "super_system_customer"` + `systemScope: true`
    that flag it as a realm-wide group.
    """
    return client.post(
        "adminOrgManager/createGroup",
        extra_body={
            "contextHandle": "super_system_customer",
            "name": name,
            "description": description,
            "roleHandles": [role_handle],
            "systemScope": True,
            "organizationName": "super_system_customer",
        },
    )


def update_system_group(
    client: EDiscoveryClient,
    *,
    handle: str,
    name: str,
    description: str,
    role_handle: str,
    role_name: str,
) -> dict:
    """Edit a system group.

    Maps to `orgManager/updateGroup` with `systemScope: true` — the
    org-scope endpoint works for system groups via the scope flag (no
    separate `adminOrgManager/updateGroup` exists). Body carries a nested
    `group` object; both `roleHandles` and `roles` are sent (the latter
    holds the human-readable role name, used for display).
    """
    return client.post(
        "orgManager/updateGroup",
        extra_body={
            "contextHandle": "super_system_customer",
            "group": {
                "name": name,
                "description": description,
                "handle": handle,
                "roleHandles": [role_handle],
                "roles": [{"name": role_name, "handle": role_handle}],
            },
            "systemScope": True,
        },
    )


def delete_system_group(client: EDiscoveryClient, *, handle: str) -> dict:
    """Delete a system group.

    Maps to `orgManager/deleteGroup` with `systemScope: true`. Like the
    update path, the org-scope endpoint covers system groups via scope
    rather than via a separate admin variant.
    """
    return client.post(
        "orgManager/deleteGroup",
        extra_body={
            "contextHandle": "super_system_customer",
            "handle": handle,
            "taskDescription": f"Deleting Group {handle}",
            "systemScope": True,
        },
    )


# ----------------------------------------------------------------------------- system depot (F3)
def get_system_storage_depot(client: EDiscoveryClient) -> SystemDepot | None:
    """Read the realm's single system storage depot."""
    resp = client.post(
        "realmManager/getSystemStorageDepot",
        extra_body={"contextHandle": "super_system_customer", "systemScope": True},
    )
    dto = resp.get("systemStorageDepotDto") or {}
    if not dto:
        return None
    attrs = [
        (a.get("name") or "", str(a.get("value") or ""))
        for a in (dto.get("attributes") or [])
    ]
    return SystemDepot(
        depot_id=str(dto.get("depotId") or ""),
        name=dto.get("depotName") or "",
        description=dto.get("description") or "",
        directory_path=dto.get("directoryPath") or "",
        attributes=attrs,
    )


# ----------------------------------------------------------------------------- virus defs (F4)
def get_virus_definitions(client: EDiscoveryClient) -> VirusDefs | None:
    """Read virus-detection settings + last update info."""
    resp = client.post(
        "realmManager/getVirusDefinitions",
        extra_body={"contextHandle": "super_system_customer", "systemScope": True},
    )
    if not resp:
        return None
    return VirusDefs(
        enabled=bool(resp.get("enabled")),
        frequency=resp.get("frequency") or "",
        run_hour=int(resp.get("runHour") or 0),
        running=bool(resp.get("running")),
        update_status=resp.get("updateStatus") or "",
        updated_on=_epoch_ms_to_str(resp.get("updatedOn")),
        version=resp.get("version") or "",
    )


# ----------------------------------------------------------------------------- virus defs writes (D7)
def trigger_virus_update(
    client: EDiscoveryClient,
    *,
    enabled: bool = True,
    frequency: str = "DAILY",
) -> dict:
    """Trigger an immediate virus-definitions sync.

    Maps to `realmManager/updateVirusDefinitions` with
    `updateDefinitionFiles: true`. Returns immediately while the update
    runs in the background — subsequent calls return
    `errorCode=INVALID_STATE` with extendedStatus
    "A Virus Definitions update is already running."

    *enabled* and *frequency* persist the scheduled-update config; the
    UI normally re-uses whatever was just read via
    `get_virus_definitions()` so the schedule stays untouched.
    """
    return client.post(
        "realmManager/updateVirusDefinitions",
        extra_body={
            "contextHandle": "super_system_customer",
            "enabled": bool(enabled),
            "frequency": frequency,
            "updateDefinitionFiles": True,
            "systemScope": True,
        },
    )


# ----------------------------------------------------------------------------- system users / groups (F5, F6)
def _user_to_row(u: dict) -> UserRow:
    roles, is_admin = _join_role_names(u)
    return UserRow(
        handle=u.get("handle") or "",
        display=u.get("displayName") or u.get("handle") or "",
        email=u.get("email") or "",
        enabled=bool(u.get("enabled")),
        locked=bool(u.get("locked")),
        mfa=bool(u.get("mfa")),
        last_access=_epoch_ms_to_str(u.get("lastAccess")),
        roles=roles,
        is_admin=is_admin,
    )


def _group_to_row(g: dict) -> GroupRow:
    # Groups can carry multiple roles in theory; the UI binds a single
    # role per group, so take the first entry for the edit form.
    role_handle = ""
    role_name = ""
    for r in (g.get("roles") or []):
        h = r.get("handle") or ""
        n = r.get("name") or ""
        if h:
            role_handle, role_name = h, n
            break
    if not role_handle:
        handles = g.get("roleHandles") or []
        names = g.get("roleNames") or []
        if handles:
            role_handle = handles[0]
            role_name = names[0] if names else ""
    return GroupRow(
        handle=g.get("handle") or "",
        name=g.get("name") or g.get("displayName") or "?",
        description=g.get("description") or "",
        members=len(g.get("members") or g.get("userHandles") or []),
        role_handle=role_handle,
        role_name=role_name,
    )


def list_system_users_and_groups(
    client: EDiscoveryClient,
) -> tuple[list[UserRow], list[GroupRow]]:
    """Realm-wide system users + groups (DRSysAdmin)."""
    resp = client.post(
        "adminOrgManager/listUsersAndGroups",
        extra_body={
            "contextHandle": "super_system_customer",
            "organizationName": "super_system_customer",
            "onlyUsers": False, "onlyGroups": False,
            "systemScope": True,
        },
    )
    users = [_user_to_row(u) for u in (resp.get("users") or [])]
    groups = [_group_to_row(g) for g in (resp.get("groups") or [])]
    return users, groups


# ============================================================ org drill-down
# ----------------------------------------------------------------------------- org users / admins / groups (Org-2)
def list_org_users_and_groups(
    client: EDiscoveryClient,
    org: str,
) -> tuple[list[UserRow], list[GroupRow]]:
    """Per-org users + groups."""
    resp = client.post(
        "orgManager/listUsersAndGroups",
        extra_body={
            "contextHandle": org,
            "organizationName": org,
            "onlyUsers": False, "onlyGroups": False,
            "systemScope": False,
        },
    )
    users = [_user_to_row(u) for u in (resp.get("users") or [])]
    groups = [_group_to_row(g) for g in (resp.get("groups") or [])]
    return users, groups


# ----------------------------------------------------------------------------- projects table (Org-3)
def project_rows_for_org(
    projects: Iterable[tuple[str, dict]], org: str,
) -> list[ProjectRow]:
    """Filter (org, project) tuples to one org and shape for display."""
    out: list[ProjectRow] = []
    for o, p in projects:
        if o != org:
            continue
        out.append(ProjectRow(
            name=p.get("name") or "?",
            handle=str(p.get("handle") or "")[:16],
            created=_epoch_ms_to_str(p.get("dateCreated")),
            state=p.get("state") or p.get("projectState") or "",
        ))
    return out


# ----------------------------------------------------------------------------- org storage (Org-6)
def org_storage_rows(
    client: EDiscoveryClient, org: str,
) -> list[OrgStorageRow]:
    """Cross-reference org's storageUsages with depot names from listRemoteNFSStorageAreas."""
    orgs = client.post(
        "realmManager/listOrganizations",
        extra_body={
            "contextHandle": "super_system_customer",
            "count": 0, "startIndex": 0, "filters": [],
            "systemScope": True,
        },
    ).get("organizations", []) or []
    usages: list[dict] = []
    for o in orgs:
        if o.get("name") == org:
            usages = o.get("storageUsages") or []
            break

    depot_lookup: dict[str, dict] = {}
    try:
        areas = client.post(
            "realmManager/listRemoteNFSStorageAreas",
            extra_body={"contextHandle": "super_system_customer", "systemScope": True},
        ).get("storageAreas", []) or []
        for a in areas:
            if a.get("handle"):
                depot_lookup[a["handle"]] = a
    except APIError:
        pass

    out: list[OrgStorageRow] = []
    for u in usages:
        h = u.get("depotHandle") or u.get("handle") or ""
        depot = depot_lookup.get(h, {})
        out.append(OrgStorageRow(
            depot_name=u.get("depotName") or depot.get("name") or h or "?",
            use_type=u.get("storageUseType") or depot.get("storageUseType") or "?",
            kb_used=int(u.get("kbUsed") or 0),
            kb_available=int(u.get("kbAvailable") or depot.get("kbAvailable") or 0),
        ))
    return out


# === v0.13 Job Scheduler — connector browse + indexing-chain submitter === #

@dataclass
class PathEntry:
    """One row of `connectorManager/exploreConnector.paths[]`.

    `leaf=True` means a file (no children); `leaf=False` is a directory
    that we can recurse into by re-calling exploreConnector with
    `parentPath.name = this.name`.
    """
    name: str
    handle: str
    leaf: bool


def explore_connector(
    client: EDiscoveryClient,
    *,
    org_name: str,
    connector_name: str,
    connector_type: str,
    remote_host: str,
    remote_path: str,
    parent_path: str = "",
    project_handle: str = "",
) -> list[PathEntry]:
    """Browse one directory under a connector.

    `parent_path` is the directory you want to list, anchored relative
    to `remote_path` (the connector's root). Use "" for the connector
    root itself. The captured response uses `name` for the path
    component; the DR Web UI builds a breadcrumb by concatenating these.

    v0.15.2 update: works for **both** DRSysAdmin and org-admin users.
    The previous v0.14.8 claim that DRSysAdmin gets `PERMISSION_DENIED`
    was a symptom of the (now-removed) `systemScope: True` auto-inject
    in api_client.post — see `docs/API_PROGRAMMING_GUIDE.md` §5. The
    only DRSysAdmin-specific prerequisite is that the caller has
    already invoked `ensure_org_context(client, org_name)` so the
    session token carries the org context.

    We re-raise APIError unchanged so the UI can surface a specific
    message rather than rendering an empty tree silently. (Earlier
    versions swallowed all APIError → [], which made permission
    failures look like empty directories.)

    v0.16.0: `contextHandle` is the **org name**, not the project
    handle. Empirically (live test against DR 5.5.3.2 on 2026-05-14):
      - ctx=<org name>           → works for DRSysAdmin + admin@org
      - ctx=<project handle>     → DRSysAdmin gets
        `PROJECT_NOT_ACTIVATED Project 0 not activated` unless the
        Web UI had pre-activated that project on the same token
        (which the TUI cannot do — there's no usable
        `ecaManager/selectProject` REST endpoint; it 500s).
    The v0.14.9 docstring (which preferred the project handle) was
    written from a single Web-UI capture where the project happened
    to be active, and turned out not to generalise. We keep the
    `project_handle` parameter as a signal-only field for callers
    that want to record it in the audit trail / error message; it
    no longer drives the request.
    """
    pp_name = parent_path or remote_path
    # contextHandle MUST be the org name here — see v0.16.0 note above.
    ctx = org_name or project_handle
    resp = client.post(
        "connectorManager/exploreConnector",
        extra_body={
            "contextHandle": ctx,
            "connectorType": connector_type,
            "connectorName": connector_name,
            "remoteHost": remote_host,
            "remotePath": remote_path,
            "organizationName": org_name,
            "parentPath": {
                "name": pp_name,
                "handle": "",
                "leaf": False,
                "type": None,
            },
        },
    )
    out: list[PathEntry] = []
    for p in resp.get("paths") or []:
        # The server emits "." as a self-reference in some captures —
        # filter it out; clients never want to navigate into "."
        nm = str(p.get("name") or "")
        if nm in ("", "."):
            continue
        out.append(PathEntry(
            name=nm,
            handle=str(p.get("handle") or ""),
            leaf=bool(p.get("leaf")),
        ))
    return out


def count_files_recursively(
    client: EDiscoveryClient,
    *,
    org_name: str,
    connector_name: str,
    connector_type: str,
    remote_host: str,
    remote_path: str,
    root_path: str,
    project_handle: str = "",
    progress_cb=None,
    max_depth: int = 12,
) -> tuple[int, int]:
    """Walk a connector subtree client-side; return (files, dirs).

    DR's REST API exposes no "folder size" endpoint and exploreConnector
    response paths carry no size field — so we limit to counts. Walk is
    iterative (deque) to keep stack usage flat even on deep trees, and
    capped by `max_depth` (default 12) as a runaway-recursion guard.

    `progress_cb`, if provided, is called as `progress_cb(files, dirs,
    current_path)` every 100 path entries so the UI can show a live
    counter.

    `project_handle` is threaded through to `explore_connector` so each
    recursive call carries the right `contextHandle` (v0.14.9 fix —
    without it, the server raises `PROJECT_NOT_ACTIVATED`).
    """
    from collections import deque
    files = 0
    dirs = 0
    seen_paths = 0
    queue: deque[tuple[str, int]] = deque([(root_path, 0)])
    while queue:
        current, depth = queue.popleft()
        if depth > max_depth:
            continue
        entries = explore_connector(
            client,
            org_name=org_name,
            connector_name=connector_name,
            connector_type=connector_type,
            remote_host=remote_host,
            remote_path=remote_path,
            parent_path=current,
            project_handle=project_handle,
        )
        for e in entries:
            seen_paths += 1
            if e.leaf:
                files += 1
            else:
                dirs += 1
                # Anchor child paths relative to the current dir. The
                # server takes absolute-ish paths (rooted at remote_path),
                # so we concatenate with "/".
                child = current.rstrip("/") + "/" + e.name
                queue.append((child, depth + 1))
            if progress_cb is not None and seen_paths % 100 == 0:
                try:
                    progress_cb(files, dirs, current)
                except Exception:
                    pass
    if progress_cb is not None:
        try:
            progress_cb(files, dirs, root_path)
        except Exception:
            pass
    return files, dirs


# --- v0.13 indexing-chain submitter ----------------------------------------
def submit_indexing_job(
    client: EDiscoveryClient,
    *,
    project_handle: str,
    connector_handle: str,
    path: str,
    dataset_name: str,
) -> dict:
    """Run createDataArea → getCorpusSetByName → createCorpus →
    addCorpus → createRepresentation. Returns:

        {"task_handle": str, "corpus_handle": str, "data_area_handle": str}

    The caller is responsible for owning the failure mode — every
    APIError propagates with the call name in the error chain via
    `APIError.extended_status`.

    Body shapes are pinned from `locustfile_indexing.py` (the load-test
    workflow that exercises this chain at scale, so they're known good).
    """
    # 1) createDataArea
    da_resp = client.post(
        "orgManager/createDataArea",
        extra_body={
            "contextHandle": project_handle,
            "connectorHandle": connector_handle,
            "name": f"{dataset_name}_data",
            "description": "",
            "mode": "IMPORT",
            "path": path,
            "skippedDirectories": [],
        },
    )
    da = da_resp.get("dataArea") or {}
    data_area_handle = str(da.get("handle") or da_resp.get("handle") or "")
    if not data_area_handle:
        raise APIError(
            "FAILURE", "MISSING_HANDLE",
            "createDataArea returned no handle", da_resp,
        )

    # 2) Look up "AllCorpora" corpus set (default container).
    cs_handle = ""
    try:
        cs_resp = client.post(
            "corpusSetManager/getCorpusSetByName",
            extra_body={
                "contextHandle": project_handle,
                "projectHandle": project_handle,
                "corpusSetName": "AllCorpora",
            },
        )
        cs = cs_resp.get("corpusSet") or {}
        cs_handle = str(cs.get("handle") or "")
    except APIError:
        # Some realms ship without AllCorpora; falling through is fine
        # — the corpus is still created, just not added to a set.
        pass

    # 3) createCorpus
    corp_resp = client.post(
        "orgManager/createCorpus",
        extra_body={
            "contextHandle": project_handle,
            "name": dataset_name,
            "description": "",
            "brand": True,
            "dataAreaHandles": [data_area_handle],
            "loadFileName": "",
            "loadFileType": "EDRM_XML",
            "loadFileProfileId": -1,
            "attributes": [{"name": "projecthandle", "value": project_handle}],
        },
    )
    corp = corp_resp.get("corpus") or {}
    corpus_handle = str(corp.get("handle") or corp_resp.get("handle") or "")
    if not corpus_handle:
        raise APIError(
            "FAILURE", "MISSING_HANDLE",
            "createCorpus returned no handle", corp_resp,
        )

    # 4) addCorpus (best-effort — depends on step 2 succeeding)
    if cs_handle:
        try:
            client.post(
                "corpusSetManager/addCorpus",
                extra_body={
                    "contextHandle": project_handle,
                    "corpusHandle": corpus_handle,
                    "corpusSetHandle": cs_handle,
                },
            )
        except APIError:
            pass

    # 5) createRepresentation — starts the indexing task
    rep_resp = client.post(
        "corpusManager/createRepresentation",
        extra_body={
            "contextHandle": project_handle,
            "corpusHandle": corpus_handle,
            "attributes": [{"name": "projecthandle", "value": project_handle}],
            "scanAttributes": [
                {"name": "batchNumber", "value": dataset_name},
                {"name": "projecthandle", "value": project_handle},
            ],
            "taskDescription": (
                f"Creating representation Analytic Index for {dataset_name}"
            ),
            "typeList": ["CONTENT_INDEX", "VECTOR_SET"],
            "enablePatternDetection": True,
        },
    )
    task_handle = str(rep_resp.get("taskHandle") or "")

    return {
        "task_handle": task_handle,
        "corpus_handle": corpus_handle,
        "data_area_handle": data_area_handle,
    }


def delete_corpus(
    client: EDiscoveryClient, *, project_handle: str, corpus_handle: str,
) -> None:
    """Delete a corpus via `orgManager/deleteCorpus`. Returns nothing.

    Used by the retention-cleanup script — wipes the indexed data so
    it doesn't outlive its retention window.
    """
    client.post(
        "orgManager/deleteCorpus",
        extra_body={
            "contextHandle": project_handle,
            "corpusHandle": corpus_handle,
        },
    )


def delete_data_area(
    client: EDiscoveryClient, *, project_handle: str, data_area_handle: str,
) -> None:
    """Delete a data area via `orgManager/deleteDataArea`. Returns nothing."""
    client.post(
        "orgManager/deleteDataArea",
        extra_body={
            "contextHandle": project_handle,
            "dataAreaHandle": data_area_handle,
        },
    )

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
from typing import Iterable

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


def list_tasks_for_project(client: EDiscoveryClient, project_handle: str, project_name: str) -> list[JobRow]:
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
        started = _status_field(t, "General Information", "Date Created") or ""
        completed = ""
        if date_completed:
            from datetime import datetime, timezone
            try:
                completed = datetime.fromtimestamp(int(date_completed)/1000, tz=timezone.utc).strftime("%H:%M:%S")
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
        ))
    return out


def collect_jobs(
    client: EDiscoveryClient,
    projects: Iterable[tuple[str, dict]],
) -> tuple[list[JobRow], list[JobRow]]:
    """Fan out listTasks across projects, return (running, completed)."""
    running: list[JobRow] = []
    completed: list[JobRow] = []
    for _org, p in projects:
        ph = str(p.get("handle") or "")
        pname = p.get("name") or "?"
        if not ph:
            continue
        for row in list_tasks_for_project(client, ph, pname):
            (running if row.state == "RUNNING" else completed).append(row)
    return running, completed


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

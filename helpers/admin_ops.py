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
import time
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
    role_handle: str,
    description: str = "",
    member: str = "drsysadmin",
) -> str:
    """Create project via ecaManager/createCase. Returns caseHandle."""
    switch_to_org(client, org)
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

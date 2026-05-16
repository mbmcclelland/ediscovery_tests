"""
Locust load test: Indexing Workflow.

Simulates concurrent users running the full project lifecycle, matching the
browser flow observed from the Digital Reef UI:
  1.  Login as admin@training
  2.  initializeOrganization → training (org context)
  3.  ecaManager/createCase  (as admin@training — matches UI behaviour)
  4.  initializeOrganization → project (project context)
  5.  orgManager/createDataArea
  6.  orgManager/createCorpus
  7.  projectManager/listCorpusSets + corpusSetManager/addCorpus
  8.  corpusManager/createRepresentation  (kicks off async indexing)
  9.  Poll projectManager/getUpdateStatus (3×5s)
  10. Login as DRSysAdmin for deletion
  11. adminOrgManager/requestProjectDelete
  12. adminOrgManager/listDeletePendingProjects + approveProjectDeleteRequest


Usage:
    source .venv/bin/activate
    locust -f locustfile_indexing.py --host https://192.168.58.128:8443

    # Headless with 5 concurrent workflows:
    locust -f locustfile_indexing.py --host https://192.168.58.128:8443 \\
        --headless -u 5 -r 1 --run-time 300s --csv=indexing_results

Configure via .env:
    DR_USERNAME, DR_PASSWORD, DR_ORGANIZATION      (DRSysAdmin — deletion only)
    DR_ORG_USERNAME, DR_ORG_PASSWORD, DR_ORG_ORGANIZATION  (admin@training — all creation)
    DR_NFS_CONNECTOR_HANDLE, DR_NFS_IMPORT_PATH, DR_NFS_DATASET_NAME
    DR_ADMIN_ROLE_HANDLE
"""

import os
import time
import uuid
import datetime
import logging

import requests
from locust import HttpUser, task, between, tag, events
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

REST_PREFIX = "/ediscovery/rest"

# System admin (DRSysAdmin) — used for deletion only
SYS_USERNAME = os.getenv("DR_USERNAME", "DRSysAdmin")
SYS_PASSWORD = os.getenv("DR_PASSWORD", "")
SYS_ORG      = os.getenv("DR_ORGANIZATION", "super_system_customer")

# Org user (admin@training) — used for data area, corpus, indexing
ORG_USERNAME = os.getenv("DR_ORG_USERNAME", "admin")
ORG_PASSWORD = os.getenv("DR_ORG_PASSWORD", "")
ORG_NAME     = os.getenv("DR_ORG_ORGANIZATION", "training")

VERIFY_SSL = os.getenv("DR_VERIFY_SSL", "false").lower() == "true"

NFS_CONNECTOR_HANDLE = os.getenv("DR_NFS_CONNECTOR_HANDLE", "")
NFS_IMPORT_PATH      = os.getenv("DR_NFS_IMPORT_PATH", "/test_datasets/Small Sample")
NFS_DATASET_NAME     = os.getenv("DR_NFS_DATASET_NAME", "Small Sample")
ADMIN_ROLE_HANDLE    = os.getenv("DR_ADMIN_ROLE_HANDLE", "")

_safe_name = NFS_DATASET_NAME.replace(" ", "_")

# Template attribute IDs are per-org and change on every install.
# Discovered once via listTemplates when the load test starts (see the
# events.test_start hook below). Populated before any User spawns.
TEMPLATE_ATTRIBUTES: list[dict] = []


@events.test_start.add_listener
def _discover_templates_once(environment, **_kwargs):
    """Populate TEMPLATE_ATTRIBUTES from the live system before users spawn.
    Replaces hardcoded per-env IDs that drifted on every fresh install."""
    base = environment.host.rstrip("/") + REST_PREFIX
    sess = requests.Session(); sess.verify = VERIFY_SSL
    # Login as org user — DRSysAdmin can also list templates but org user
    # mirrors who creates the project, keeping permissions identical.
    body = {
        "drWsClientContext": {"username": ORG_USERNAME, "organizationName": ORG_NAME},
        "contextPath": "/ediscovery", "userDeviceID": str(uuid.uuid4()),
    }
    r = sess.post(f"{base}/realmManager/createSession", json=body,
                  auth=(ORG_USERNAME, ORG_PASSWORD), timeout=30)
    tok = r.json().get("sessionToken")
    if not tok:
        logger.error("template discovery: login failed — using empty attributes")
        return
    # Switch context to the target org so listTemplates returns org-scoped rows
    sess.headers.update({"Authorization": tok, "Content-Type": "application/json"})
    sess.post(f"{base}/realmManager/initializeOrganization", json={
        "requestHandle": None, "contextHandle": ORG_NAME, "organizationName": ORG_NAME,
    }, timeout=30)
    r = sess.post(f"{base}/orgManager/listTemplates", json={
        "contextHandle": ORG_NAME, "systemScope": True,
    }, timeout=30)
    discovered = []
    for t in (r.json().get("templates") or []):
        ttype = t.get("templateType"); handle = t.get("handle")
        if ttype and handle:
            discovered.append({"name": ttype, "value": str(handle)})
    # Insert IS_IMPORTED='false' after INDEX_SETTINGS (browser flow)
    insert_at = next((i + 1 for i, a in enumerate(discovered)
                      if a["name"] == "INDEX_SETTINGS"), len(discovered))
    discovered.insert(insert_at, {"name": "IS_IMPORTED", "value": "false"})
    TEMPLATE_ATTRIBUTES[:] = discovered
    logger.info("Discovered %d template attributes for org %r", len(discovered), ORG_NAME)


def _login(client, username, password, org):
    """Authenticate and return a session token, or None on failure."""
    body = {
        "drWsClientContext": {
            "username": username,
            "organizationName": org,
        },
        "contextPath": "/ediscovery",
        "userDeviceID": str(uuid.uuid4()),
    }
    with client.post(
        f"{REST_PREFIX}/realmManager/createSession",
        json=body,
        name="[auth] createSession",
        verify=VERIFY_SSL,
        auth=(username, password),
        catch_response=True,
    ) as resp:
        if resp.status_code != 200:
            resp.failure(f"Login failed: HTTP {resp.status_code}")
            return None
        data = resp.json()
        token = data.get("sessionToken")
        if not token:
            resp.failure("No sessionToken in login response")
            return None
        return token


def _api_post(client, path, token, body, name=None):
    """POST with Authorization token. Returns (data, updated_token)."""
    with client.post(
        f"{REST_PREFIX}/{path}",
        json=body,
        name=name or f"[api] {path}",
        verify=VERIFY_SSL,
        headers={"Authorization": token} if token else {},
        catch_response=True,
    ) as resp:
        if resp.status_code != 200:
            resp.failure(f"HTTP {resp.status_code}")
            return None, token
        data = resp.json()
        new_token = data.get("sessionToken", token)
        if data.get("status") == "FAILURE":
            resp.failure(f"{data.get('errorCode')}: {data.get('extendedStatus', '')}")
            return data, new_token
        return data, new_token


def _init_org(client, token, context_handle, org_name, name_tag, case_handle=None):
    """
    Call initializeOrganization to switch token to org or project scope.
    Pass case_handle when switching to project scope.
    """
    body = {
        "requestHandle": None,
        "contextHandle": context_handle,
        "organizationName": org_name,
    }
    if case_handle:
        body["caseHandle"] = case_handle
    _, new_token = _api_post(client, "realmManager/initializeOrganization", token, body, name=name_tag)
    return new_token


class IndexingWorkflowUser(HttpUser):
    """Full indexing lifecycle load test user."""

    wait_time = between(2, 5)

    @tag("indexing")
    @task
    def run_indexing_workflow(self):
        ts           = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        project_name = f"load-test-{ts}-{uuid.uuid4().hex[:6]}"

        # ── 1. Login as admin@training ────────────────────────────────────────
        org_token = _login(self.client, ORG_USERNAME, ORG_PASSWORD, ORG_NAME)
        if not org_token:
            return

        # ── 2. Org context: training ──────────────────────────────────────────
        org_token = _init_org(
            self.client, org_token, ORG_NAME, ORG_NAME,
            "[2] initOrg→training",
        )

        # ── 3. Create project ─────────────────────────────────────────────────
        data, org_token = _api_post(self.client, "ecaManager/createCase", org_token, {
            "requestHandle":   None,
            "contextHandle":   ORG_NAME,
            "addToCaseData":   False,
            "custodians":      [],
            "name":            project_name,
            "description":     f"Load test {project_name}",
            "attributes":      TEMPLATE_ATTRIBUTES,
            "projectLogoBytes": None,
            "logoFileName":    "",
            "systemScope":     False,
            "reviewSystem":    None,
            "reviewProjectId": 0,
            "membersRequestMessage": {
                "groups": [],
                "users": [
                    {"name": ORG_USERNAME.lower(),  "roleHandles": [ADMIN_ROLE_HANDLE]},
                    {"name": SYS_USERNAME.lower(),  "roleHandles": [ADMIN_ROLE_HANDLE]},
                ],
            },
        }, name="[3] createCase")

        if not data:
            return
        project_handle = data.get("caseHandle") or data.get("handle")
        if not project_handle:
            logger.error("No project handle in createCase response: %s", data)
            return
        project_handle = str(project_handle)

        # ── 4. Login as DRSysAdmin — admin@training lacks createDataArea permission
        sys_token = _login(self.client, SYS_USERNAME, SYS_PASSWORD, SYS_ORG)
        if not sys_token:
            logger.error("DRSysAdmin login failed; cannot continue for %s", project_name)
            return

        sys_token = _init_org(self.client, sys_token, ORG_NAME, ORG_NAME, "[4a] initOrg→training")
        sys_token = _init_org(
            self.client, sys_token, project_handle, ORG_NAME,
            "[4b] initOrg→project", case_handle=project_handle,
        )

        # ── 5. Create data area ───────────────────────────────────────────────
        data, sys_token = _api_post(self.client, "orgManager/createDataArea", sys_token, {
            "requestHandle":      None,
            "contextHandle":      project_handle,
            "connectorHandle":    NFS_CONNECTOR_HANDLE,
            "name":               f"{_safe_name}_{_safe_name}",
            "description":        "",
            "mode":               "IMPORT",
            "path":               NFS_IMPORT_PATH,
            "skippedDirectories": [],
        }, name="[5] createDataArea")

        if not data:
            return
        da_obj = data.get("dataArea", {})
        da_handle = (da_obj.get("handle") if isinstance(da_obj, dict) else None) or data.get("handle")
        if not da_handle:
            logger.error("No data area handle: %s", data)
            return

        # ── 6. Create corpus ──────────────────────────────────────────────────
        data, sys_token = _api_post(self.client, "orgManager/createCorpus", sys_token, {
            "requestHandle":     None,
            "contextHandle":     project_handle,
            "name":              f"{_safe_name}_corpus",
            "description":       "",
            "brand":             True,
            "dataAreaHandles":   [da_handle],
            "loadFileName":      "",
            "loadFileType":      "EDRM_XML",
            "loadFileProfileId": -1,
            "attributes":        [{"name": "projecthandle", "value": project_handle}],
        }, name="[6] createCorpus")

        if not data:
            return
        corpus_obj = data.get("corpus", {})
        corpus_handle = (corpus_obj.get("handle") if isinstance(corpus_obj, dict) else None) or data.get("handle")
        if not corpus_handle:
            logger.error("No corpus handle: %s", data)
            return

        # ── 7. listCorpusSets + addCorpus ─────────────────────────────────────
        sets_data, sys_token = _api_post(self.client, "projectManager/listCorpusSets", sys_token, {
            "requestHandle": None,
            "contextHandle": project_handle,
            "projectHandle": project_handle,
            "count":         1,
            "startIndex":    0,
        }, name="[7a] listCorpusSets")

        corpus_set_handle = ""
        if sets_data:
            sets = sets_data.get("corpusSets", [])
            if sets and isinstance(sets[0], dict):
                corpus_set_handle = sets[0].get("handle", "")

        _api_post(self.client, "corpusSetManager/addCorpus", sys_token, {
            "requestHandle":   None,
            "contextHandle":   project_handle,
            "corpusHandle":    corpus_handle,
            "corpusSetHandle": corpus_set_handle,
        }, name="[7b] addCorpus")

        # ── 8. Start indexing ─────────────────────────────────────────────────
        _api_post(self.client, "corpusManager/createRepresentation", sys_token, {
            "requestHandle":  None,
            "contextHandle":  project_handle,
            "corpusHandle":   corpus_handle,
            "attributes":     [{"name": "projecthandle", "value": project_handle}],
            "scanAttributes": [
                {"name": "batchNumber",   "value": NFS_DATASET_NAME},
                {"name": "projecthandle", "value": project_handle},
            ],
            "taskDescription":        f"Creating representation Analytic Index for {NFS_DATASET_NAME}",
            "typeList":               ["CONTENT_INDEX", "VECTOR_SET"],
            "enablePatternDetection": True,
        }, name="[8] createRepresentation")

        # ── 9. Brief status poll ──────────────────────────────────────────────
        for _ in range(3):
            time.sleep(5)
            _api_post(self.client, "projectManager/getUpdateStatus", sys_token, {
                "contextHandle":     project_handle,
                "projectHandle":     0,
                "timestamp":         str(int(time.time() * 1000)),
                "updateStatusTypes": ["CONNECTOR", "COMPONENT", "STORAGE"],
            }, name="[9] getUpdateStatus")

        # ── 10. Request project deletion (sys_token still valid from step 4) ────
        _api_post(self.client, "adminOrgManager/requestProjectDelete", sys_token, {
            "contextHandle":  project_handle,
            "projectHandle":  project_handle,
            "taskDescription": f"Delete {project_name}",
            "systemScope":    True,
        }, name="[10] requestProjectDelete")

        # ── 11. Find and approve deletion ─────────────────────────────────────
        time.sleep(2)
        data, sys_token = _api_post(
            self.client, "adminOrgManager/listDeletePendingProjects", sys_token,
            {"systemScope": True},
            name="[11a] listDeletePendingProjects",
        )

        if not data:
            return

        pending      = data.get("requests", data.get("adminRequests", data.get("projects", [])))
        delete_handle = None
        for req in pending:
            if project_name in str(req) or project_handle in str(req):
                delete_handle = req.get("handle")
                break

        if delete_handle:
            _api_post(self.client, "adminOrgManager/approveProjectDeleteRequest", sys_token, {
                "contextHandle":   project_handle,
                "handle":          delete_handle,
                "systemScope":     True,
                "taskDescription": f"Approve delete for {project_name}",
            }, name="[11b] approveProjectDeleteRequest")
        else:
            logger.warning("Delete request not found for %s — project may be orphaned", project_name)

"""
Locust load test: Indexing Workflow.

Simulates concurrent users running the full project lifecycle, matching the
browser flow captured from the Digital Reef UI on 2026-05-11
(/tmp/dr_api_capture.json, 211 calls):

  on_start (once per User):
      sys_login → org_login
      Resolve env-specific handles via API:
        - import NFS connector handle  (adminOrgManager/listConnectors)
        - Organization Administrator role handle  (orgManager/listRoles)
        - default template handles by templateType  (orgManager/listTemplates)

  task (per workflow):
      1.  initializeOrganization → training (org context)
      2.  ecaManager/createCase                  ← creates project, returns caseHandle
      3.  orgManager/createDataArea              (mode=IMPORT, ctx=projectHandle)
      4.  corpusSetManager/getCorpusSetByName    (AllCorpora)
      5.  orgManager/createCorpus
      6.  corpusSetManager/addCorpus
      7.  corpusManager/createRepresentation     ← returns taskHandle
      8.  Poll taskManager/getTasks until dateCompleted is set (or timeout)
      9.  orgManager/requestProjectDelete        (ctx=ORG_NAME, org_token)
      10. realmManager/listDeletePendingProjects (ctx=SYS_ORG,  sys_token)
      11. adminOrgManager/approveProjectDeleteRequest

Project-scoped operations (createDataArea/createCorpus/createRepresentation)
pass contextHandle=<projectHandle> directly — there is no separate
"initializeOrganization → project" call in the captured flow.

Usage:
    source .venv/bin/activate
    locust -f locustfile_indexing.py --host https://192.168.58.128:8443

    # Headless with 5 concurrent workflows:
    locust -f locustfile_indexing.py --host https://192.168.58.128:8443 \\
        --headless -u 5 -r 1 --run-time 300s --csv=indexing_results

Configure via .env:
    DR_USERNAME, DR_PASSWORD, DR_ORGANIZATION                      (DRSysAdmin)
    DR_ORG_USERNAME, DR_ORG_PASSWORD, DR_ORG_ORGANIZATION          (admin@training)
    DR_NFS_IMPORT_PATH, DR_NFS_DATASET_NAME                        (load data location)
    DR_INDEX_POLL_INTERVAL  (default 5)   seconds between getTasks polls
    DR_INDEX_POLL_TIMEOUT   (default 600) seconds before giving up on indexing
"""

import os
import time
import uuid
import datetime
import logging

from locust import HttpUser, task, between, tag
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

REST_PREFIX = "/ediscovery/rest"

# System admin (DRSysAdmin) — used for approving project deletion
SYS_USERNAME = os.getenv("DR_USERNAME", "DRSysAdmin")
SYS_PASSWORD = os.getenv("DR_PASSWORD", "")
SYS_ORG      = os.getenv("DR_ORGANIZATION", "super_system_customer")

# Org user (admin@training) — used for all project creation/indexing
ORG_USERNAME = os.getenv("DR_ORG_USERNAME", "admin")
ORG_PASSWORD = os.getenv("DR_ORG_PASSWORD", "")
ORG_NAME     = os.getenv("DR_ORG_ORGANIZATION", "training")

VERIFY_SSL = os.getenv("DR_VERIFY_SSL", "false").lower() == "true"

NFS_IMPORT_PATH  = os.getenv("DR_NFS_IMPORT_PATH", "/testload")
NFS_DATASET_NAME = os.getenv("DR_NFS_DATASET_NAME", "testload")

POLL_INTERVAL = int(os.getenv("DR_INDEX_POLL_INTERVAL", "5"))
POLL_TIMEOUT  = int(os.getenv("DR_INDEX_POLL_TIMEOUT", "600"))

ADMIN_ROLE_NAME = "Organization Administrator"   # canonical default role
IMPORT_CONNECTOR_MODE = "READ"                   # READ for IMPORT connectors


# ──────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ──────────────────────────────────────────────────────────────────────────────

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


def _init_org(client, token, context_handle, org_name, name_tag, system_scope=None):
    """
    Call initializeOrganization to set org context on the token.
    Project-scoped APIs take contextHandle=<projectHandle> directly — no
    separate "project init" call is needed.
    """
    body = {
        "requestHandle": None,
        "contextHandle": context_handle,
        "organizationName": org_name,
    }
    if system_scope is not None:
        body["systemScope"] = system_scope
    _, new_token = _api_post(client, "realmManager/initializeOrganization", token, body, name=name_tag)
    return new_token


# ──────────────────────────────────────────────────────────────────────────────
# Dynamic handle resolution (avoids drift after playwright_fresh_install runs)
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_connector_handle(client, token):
    """Find the import NFS connector handle (mode=READ, type=NFS)."""
    data, token = _api_post(client, "adminOrgManager/listConnectors", token, {
        "requestHandle":    None,
        "contextHandle":    ORG_NAME,
        "organizationName": ORG_NAME,
    }, name="[setup] listConnectors")
    if not data:
        return None, token
    for c in data.get("connectors", []):
        if c.get("type") == "NFS" and c.get("mode") == IMPORT_CONNECTOR_MODE:
            return c.get("handle"), token
    return None, token


def _resolve_admin_role(client, token):
    """Find the Organization Administrator role handle."""
    data, token = _api_post(client, "orgManager/listRoles", token, {
        "requestHandle": None,
        "contextHandle": ORG_NAME,
        "objectType":    "ALL",
        "systemScope":   False,
    }, name="[setup] listRoles")
    if not data:
        return None, token
    for r in data.get("roles", []):
        if r.get("name") == ADMIN_ROLE_NAME:
            return r.get("handle"), token
    return None, token


def _resolve_template_attributes(client, token):
    """
    Look up default template handles by templateType and return the
    ecaManager/createCase `attributes` list. Capture shows 17 template types
    are sent; we include every defaultTemplate that listTemplates returns.
    """
    data, token = _api_post(client, "orgManager/listTemplates", token, {
        "requestHandle":    None,
        "contextHandle":    ORG_NAME,
        "scope":            "ORG_LEVEL",
        "tempType":         None,
        "organizationName": ORG_NAME,
        "systemScope":      False,
    }, name="[setup] listTemplates")
    if not data:
        return [], token
    attrs = []
    for t in data.get("templates", []):
        if t.get("defaultTemplate") and t.get("templateType") and t.get("handle"):
            attrs.append({"name": t["templateType"], "value": str(t["handle"])})
    return attrs, token


# ──────────────────────────────────────────────────────────────────────────────
# Locust user
# ──────────────────────────────────────────────────────────────────────────────

class IndexingWorkflowUser(HttpUser):
    """Full indexing lifecycle load test user."""

    wait_time = between(2, 5)

    def on_start(self):
        """
        One-time per-user setup: log in (org + sys), resolve env-specific
        handles. Per-workflow `task` calls reuse these but always re-login
        on token expiry by reissuing createSession.
        """
        self.connector_handle = None
        self.admin_role_handle = None
        self.template_attributes = []
        self._setup_ok = False

        org_token = _login(self.client, ORG_USERNAME, ORG_PASSWORD, ORG_NAME)
        if not org_token:
            logger.error("on_start: org login failed")
            return
        org_token = _init_org(self.client, org_token, ORG_NAME, ORG_NAME, "[setup] initOrg→training")

        self.connector_handle,   org_token = _resolve_connector_handle(self.client, org_token)
        self.admin_role_handle,  org_token = _resolve_admin_role(self.client, org_token)
        self.template_attributes, org_token = _resolve_template_attributes(self.client, org_token)

        if not self.connector_handle:
            logger.error("on_start: no import NFS connector found (mode=%s)", IMPORT_CONNECTOR_MODE)
            return
        if not self.admin_role_handle:
            logger.error("on_start: %r role not found", ADMIN_ROLE_NAME)
            return
        if not self.template_attributes:
            logger.error("on_start: no default templates found")
            return

        logger.info(
            "on_start: connector=%s, role=%s, %d templates",
            self.connector_handle, self.admin_role_handle, len(self.template_attributes),
        )
        self._setup_ok = True

    @tag("indexing")
    @task
    def run_indexing_workflow(self):
        if not self._setup_ok:
            return

        ts           = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        project_name = f"load-test-{ts}-{uuid.uuid4().hex[:6]}"
        dataset_name = f"{NFS_DATASET_NAME}-{ts}-{uuid.uuid4().hex[:4]}"

        # ── Login as admin@training (per-task to keep tokens fresh) ──────────
        org_token = _login(self.client, ORG_USERNAME, ORG_PASSWORD, ORG_NAME)
        if not org_token:
            return

        # ── 1. Org context: training ─────────────────────────────────────────
        org_token = _init_org(self.client, org_token, ORG_NAME, ORG_NAME, "[1] initOrg→training")

        # ── 2. Create project ────────────────────────────────────────────────
        data, org_token = _api_post(self.client, "ecaManager/createCase", org_token, {
            "requestHandle":   None,
            "contextHandle":   ORG_NAME,
            "addToCaseData":   False,
            "custodians":      [],
            "name":            project_name,
            "description":     f"Load test {project_name}",
            "attributes":      self.template_attributes,
            "projectLogoBytes": None,
            "logoFileName":    "",
            "systemScope":     False,
            "reviewSystem":    None,
            "reviewProjectId": 0,
            "membersRequestMessage": {
                "groups": [],
                "users": [
                    {"name": ORG_USERNAME.lower(), "roleHandles": [self.admin_role_handle]},
                    {"name": SYS_USERNAME.lower(), "roleHandles": [self.admin_role_handle]},
                ],
            },
        }, name="[2] createCase")

        if not data:
            return
        project_handle = data.get("caseHandle") or data.get("handle")
        if not project_handle:
            logger.error("No project handle in createCase response: %s", data)
            return
        project_handle = str(project_handle)

        # ── 3. Create import data area ───────────────────────────────────────
        data, org_token = _api_post(self.client, "orgManager/createDataArea", org_token, {
            "requestHandle":      None,
            "contextHandle":      project_handle,
            "connectorHandle":    self.connector_handle,
            "name":               f"{dataset_name}_{NFS_DATASET_NAME}",
            "description":        "",
            "mode":               "IMPORT",
            "path":               NFS_IMPORT_PATH,
            "skippedDirectories": [],
        }, name="[3] createDataArea")
        if not data:
            return
        da_obj = data.get("dataArea", {})
        da_handle = (da_obj.get("handle") if isinstance(da_obj, dict) else None) or data.get("handle")
        if not da_handle:
            logger.error("No data area handle: %s", data)
            return

        # ── 4. Look up AllCorpora corpus set ─────────────────────────────────
        sets_data, org_token = _api_post(self.client, "corpusSetManager/getCorpusSetByName", org_token, {
            "requestHandle":  None,
            "contextHandle":  project_handle,
            "projectHandle":  project_handle,
            "corpusSetName":  "AllCorpora",
        }, name="[4] getCorpusSetByName")
        corpus_set_handle = ""
        if sets_data:
            cs = sets_data.get("corpusSet")
            if isinstance(cs, dict):
                corpus_set_handle = cs.get("handle", "")

        # ── 5. Create corpus ─────────────────────────────────────────────────
        data, org_token = _api_post(self.client, "orgManager/createCorpus", org_token, {
            "requestHandle":     None,
            "contextHandle":     project_handle,
            "name":              dataset_name,
            "description":       "",
            "brand":             True,
            "dataAreaHandles":   [da_handle],
            "loadFileName":      "",
            "loadFileType":      "EDRM_XML",
            "loadFileProfileId": -1,
            "attributes":        [{"name": "projecthandle", "value": project_handle}],
        }, name="[5] createCorpus")
        if not data:
            return
        corpus_obj = data.get("corpus", {})
        corpus_handle = (corpus_obj.get("handle") if isinstance(corpus_obj, dict) else None) or data.get("handle")
        if not corpus_handle:
            logger.error("No corpus handle: %s", data)
            return

        # ── 6. Add corpus to AllCorpora ──────────────────────────────────────
        if corpus_set_handle:
            _api_post(self.client, "corpusSetManager/addCorpus", org_token, {
                "requestHandle":   None,
                "contextHandle":   project_handle,
                "corpusHandle":    corpus_handle,
                "corpusSetHandle": corpus_set_handle,
            }, name="[6] addCorpus")

        # ── 7. Start indexing (returns taskHandle) ───────────────────────────
        data, org_token = _api_post(self.client, "corpusManager/createRepresentation", org_token, {
            "requestHandle":  None,
            "contextHandle":  project_handle,
            "corpusHandle":   corpus_handle,
            "attributes":     [{"name": "projecthandle", "value": project_handle}],
            "scanAttributes": [
                {"name": "batchNumber",   "value": dataset_name},
                {"name": "projecthandle", "value": project_handle},
            ],
            "taskDescription":        f"Creating representation Analytic Index for {dataset_name}",
            "typeList":               ["CONTENT_INDEX", "VECTOR_SET"],
            "enablePatternDetection": True,
        }, name="[7] createRepresentation")
        task_handle = data.get("taskHandle") if data else None

        # ── 8. Poll taskManager/getTasks until done ──────────────────────────
        if task_handle:
            start = time.time()
            completed = False
            while time.time() - start < POLL_TIMEOUT:
                time.sleep(POLL_INTERVAL)
                tdata, org_token = _api_post(self.client, "taskManager/getTasks", org_token, {
                    "requestHandle": None,
                    "contextHandle": project_handle,
                    "taskHandles":   [task_handle],
                }, name="[8] getTasks")
                if not tdata:
                    continue
                tasks = tdata.get("tasks", [])
                if tasks and tasks[0].get("dateCompleted"):
                    completed = True
                    break
            if not completed:
                logger.warning(
                    "Indexing for %s did not complete within %ds (task %s)",
                    project_name, POLL_TIMEOUT, task_handle,
                )

        # ── 9. Request project deletion (org user, ORG_NAME scope) ───────────
        _api_post(self.client, "orgManager/requestProjectDelete", org_token, {
            "requestHandle":   None,
            "contextHandle":   ORG_NAME,
            "projectHandle":   project_handle,
            "taskDescription": f"Delete Project {project_name}",
        }, name="[9] requestProjectDelete")

        # ── 10. Approve deletion as DRSysAdmin ───────────────────────────────
        sys_token = _login(self.client, SYS_USERNAME, SYS_PASSWORD, SYS_ORG)
        if not sys_token:
            logger.warning("Sys login failed; %s left in PENDING delete state", project_name)
            return
        sys_token = _init_org(self.client, sys_token, SYS_ORG, SYS_ORG,
                              "[10a] initOrg→sys", system_scope=True)

        # Brief wait so the delete request shows up
        time.sleep(2)
        data, sys_token = _api_post(
            self.client, "realmManager/listDeletePendingProjects", sys_token, {
                "requestHandle": None,
                "contextHandle": SYS_ORG,
                "count":         100,
                "startIndex":    0,
                "descending":    True,
                "systemScope":   True,
                "sortByFilter":  "DATE_CREATED",
            },
            name="[10b] listDeletePendingProjects",
        )
        if not data:
            return

        delete_handle = None
        for req in data.get("requests", []):
            if str(req.get("objectHandle")) == project_handle:
                delete_handle = req.get("handle")
                break

        if delete_handle:
            _api_post(self.client, "adminOrgManager/approveProjectDeleteRequest", sys_token, {
                "requestHandle":   None,
                "contextHandle":   SYS_ORG,
                "handle":          delete_handle,
                "systemScope":     True,
                "taskDescription": f"Approving delete for project {project_name}",
            }, name="[10c] approveProjectDeleteRequest")
        else:
            logger.warning("Delete request not found for %s — project may be orphaned", project_name)

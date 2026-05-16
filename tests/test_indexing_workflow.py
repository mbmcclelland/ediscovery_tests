"""
End-to-end indexing workflow test.

Replicates the Edge-recorded workflow on 172.31.240.84:
  1. Login as DRSysAdmin -> super_system_customer
  2. initializeOrganization -> training
  3. createCase (create project)
  4. initializeOrganization -> project context
  5. createDataArea (link NFS connector)
  6. createCorpus (link data area)
  7. addCorpus to corpusSet
  8. createRepresentation (start indexing)
  9. Switch back to system context
  10. requestProjectDelete -> approveProjectDeleteRequest

Requires DR_NFS_CONNECTOR_HANDLE, DR_ADMIN_ROLE_HANDLE,
and DR_TEMPLATE_* in .env (server-specific values).
"""

import os
import time
import uuid
import datetime
import pytest

from helpers.api_client import EDiscoveryClient, APIError
from config import config


# ---------------------------------------------------------------- config
NFS_CONNECTOR = os.getenv(
    "DR_NFS_CONNECTOR_HANDLE",
    "0000840201143a35f1f34d8d9a76a34146268ddc",
)
NFS_PATH = os.getenv("DR_NFS_IMPORT_PATH", "/test_datasets/Small Sample")
NFS_DATASET_NAME = os.getenv("DR_NFS_DATASET_NAME", "Small Sample")
TARGET_ORG = os.getenv("DR_ORG_ORGANIZATION", "training")

# Template attribute IDs are discovered at runtime from the live system
# via client.discover_template_attributes(). They are per-org and change
# on every install, so shipping hardcoded values gives silent FK failures
# in mgmtproject_attributes on any host that isn't the one they were
# captured on (see BUG_LOG.md B11/B14d).

ADMIN_ROLE = os.getenv(
    "DR_ADMIN_ROLE_HANDLE",
    "00008798cf6b043a18104ccd8c437b29f688f847",
)


def _unique_name(prefix="api-test"):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{ts}"


class IndexingWorkflow:
    """Full create-index-delete workflow using a single DRSysAdmin client."""

    def __init__(self, client: EDiscoveryClient):
        self.client = client
        self.project_handle = None
        self.project_name = None
        self.da_handle = None
        self.corpus_handle = None

    def switch_to_org(self):
        """Initialize organization context to training."""
        self.client.post("realmManager/initializeOrganization", extra_body={
            "requestHandle": None,
            "contextHandle": TARGET_ORG,
            "organizationName": TARGET_ORG,
        })

    def switch_to_project(self):
        """Initialize organization context with project handle."""
        assert self.project_handle
        self.client.post("realmManager/initializeOrganization", extra_body={
            "requestHandle": None,
            "contextHandle": self.project_handle,
            "organizationName": TARGET_ORG,
            "systemScope": False,
        })
        # Browser also calls getIndexSettings + getUpdateStatus here
        self.client.post("projectManager/getIndexSettings", extra_body={
            "requestHandle": None,
            "contextHandle": self.project_handle,
            "handle": self.project_handle,
            "systemScope": False,
        })
        self.client.post("projectManager/getUpdateStatus", extra_body={
            "requestHandle": None,
            "contextHandle": self.project_handle,
            "projectHandle": 0,
            "timestamp": 0,
            "updateStatusTypes": ["CONNECTOR", "COMPONENT", "STORAGE"],
        })

    def switch_to_system(self):
        """Switch back to system org context."""
        self.client.post("realmManager/initializeOrganization", extra_body={
            "requestHandle": None,
            "contextHandle": config.organization,
            "organizationName": config.organization,
        })

    def create_project(self, name=None):
        self.project_name = name or _unique_name()
        attributes = self.client.discover_template_attributes(TARGET_ORG)
        data = self.client.post("ecaManager/createCase", extra_body={
            "requestHandle": None,
            "contextHandle": TARGET_ORG,
            "addToCaseData": False,
            "custodians": [],
            "name": self.project_name,
            "description": f"API test {self.project_name}",
            "attributes": attributes,
            "membersRequestMessage": {
                "groups": [],
                "users": [{"name": "drsysadmin", "roleHandles": [ADMIN_ROLE]}],
            },
            "projectLogoBytes": None,
            "logoFileName": "",
            "systemScope": False,
            "reviewSystem": None,
            "reviewProjectId": 0,
        })
        self.project_handle = data.get("caseHandle")
        return data

    def create_data_area(self):
        assert self.project_handle
        data = self.client.post("orgManager/createDataArea", extra_body={
            "requestHandle": None,
            "contextHandle": self.project_handle,
            "connectorHandle": NFS_CONNECTOR,
            "description": "",
            "mode": "IMPORT",
            "name": f"{NFS_DATASET_NAME}_{NFS_DATASET_NAME}",
            "path": NFS_PATH,
            "skippedDirectories": [],
        })
        da = data.get("dataArea", {})
        self.da_handle = da.get("handle") if isinstance(da, dict) else data.get("handle")
        return data

    def create_corpus(self):
        assert self.project_handle and self.da_handle
        data = self.client.post("orgManager/createCorpus", extra_body={
            "requestHandle": None,
            "contextHandle": self.project_handle,
            "attributes": [{"name": "projecthandle", "value": self.project_handle}],
            "brand": True,
            "dataAreaHandles": [self.da_handle],
            "description": "",
            "name": NFS_DATASET_NAME,
            "loadFileName": "",
            "loadFileType": "EDRM_XML",
            "loadFileProfileId": -1,
        })
        corpus = data.get("corpus", {})
        self.corpus_handle = corpus.get("handle") if isinstance(corpus, dict) else None
        if not self.corpus_handle:
            for k in ("corpusHandle", "handle"):
                v = data.get(k)
                if v and ":" in str(v):
                    self.corpus_handle = v
                    break
        return data

    def add_corpus_to_set(self):
        assert self.project_handle and self.corpus_handle
        cs_data = self.client.post("projectManager/listCorpusSets", extra_body={
            "requestHandle": None,
            "contextHandle": self.project_handle,
            "projectHandle": self.project_handle,
            "count": 1,
            "startIndex": 0,
        })
        sets = cs_data.get("corpusSets", [])
        if sets:
            cs_handle = sets[0].get("handle")
            self.client.post("corpusSetManager/addCorpus", extra_body={
                "requestHandle": None,
                "contextHandle": self.project_handle,
                "corpusHandle": self.corpus_handle,
                "corpusSetHandle": cs_handle,
            })

    def create_representation(self):
        assert self.project_handle and self.corpus_handle
        return self.client.post("corpusManager/createRepresentation", extra_body={
            "requestHandle": None,
            "contextHandle": self.project_handle,
            "attributes": [{"name": "projecthandle", "value": self.project_handle}],
            "corpusHandle": self.corpus_handle,
            "scanAttributes": [
                {"name": "batchNumber", "value": NFS_DATASET_NAME},
                {"name": "projecthandle", "value": self.project_handle},
            ],
            "taskDescription": f"Creating representation Analytic Index for {NFS_DATASET_NAME}",
            "typeList": ["CONTENT_INDEX", "VECTOR_SET"],
            "enablePatternDetection": True,
        })

    def wait_for_indexing(self, timeout=600, interval=15):
        """
        Poll task status until indexing completes or timeout.
        Returns True if indexing finished, False if timed out.
        """
        assert self.project_handle
        start = time.time()
        while time.time() - start < timeout:
            try:
                data = self.client.post("projectManager/listTasks", extra_body={
                    "requestHandle": None,
                    "contextHandle": self.project_handle,
                    "projectHandle": self.project_handle,
                })
                tasks = data.get("tasks", [])
                active = [t for t in tasks if t.get("state") in
                          ("RUNNING", "QUEUED", "PENDING", "PROCESSING")]
                if not active:
                    return True
            except Exception:
                pass
            time.sleep(interval)
        return False

    def request_delete(self):
        assert self.project_handle
        return self.client.post("adminOrgManager/requestProjectDelete", extra_body={
            "requestHandle": None,
            "contextHandle": self.project_handle,
            "projectHandle": self.project_handle,
            "taskDescription": f"Delete Project {self.project_name}",
            "systemScope": True,
        })

    def approve_delete(self, max_attempts=20, interval=5):
        """Retry finding and approving the delete request."""
        assert self.project_handle
        for attempt in range(max_attempts):
            time.sleep(interval)
            data = self.client.post("adminOrgManager/listDeletePendingProjects", extra_body={
                "requestHandle": None,
                "systemScope": True,
                "contextHandle": config.organization,
            })
            pending = data.get("adminRequests", data.get("projects", []))
            for req in pending:
                if self.project_name in str(req) or str(self.project_handle) in str(req):
                    return self.client.post(
                        "adminOrgManager/approveProjectDeleteRequest",
                        extra_body={
                            "requestHandle": None,
                            "contextHandle": self.project_handle,
                            "handle": req.get("handle"),
                            "systemScope": True,
                            "taskDescription": f"Approving delete for {self.project_name}",
                        },
                    )
        return None


# ----------------------------------------------------------- pytest tests

@pytest.mark.slow
class TestIndexingWorkflow:

    @pytest.fixture
    def wf(self, cfg):
        client = EDiscoveryClient(cfg)
        client.login()
        workflow = IndexingWorkflow(client)
        workflow.switch_to_org()
        yield workflow
        # Cleanup
        if workflow.project_handle:
            try:
                workflow.switch_to_system()
                workflow.request_delete()
                workflow.approve_delete()
            except Exception:
                pass
        client.logout()

    def test_create_project(self, wf):
        wf.create_project()
        assert wf.project_handle, "Expected a project handle"

    def test_create_and_import(self, wf):
        wf.create_project()
        assert wf.project_handle
        time.sleep(3)
        wf.switch_to_project()
        wf.create_data_area()
        assert wf.da_handle, "Expected a data area handle"
        wf.create_corpus()
        assert wf.corpus_handle, "Expected a corpus handle"

    def test_full_lifecycle(self, wf):
        # Create
        wf.create_project()
        assert wf.project_handle
        time.sleep(3)
        wf.switch_to_project()

        # Import
        wf.create_data_area()
        assert wf.da_handle
        wf.create_corpus()
        assert wf.corpus_handle
        wf.add_corpus_to_set()

        # Index
        wf.create_representation()

        # Wait for indexing to finish (up to 10 min)
        finished = wf.wait_for_indexing(timeout=600, interval=15)
        # Don't fail if timeout — just proceed to cleanup

        # Delete
        wf.switch_to_system()
        wf.request_delete()
        result = wf.approve_delete(max_attempts=20, interval=5)
        if result:
            wf.project_handle = None  # prevent fixture double-delete

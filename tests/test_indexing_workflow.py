"""
End-to-end indexing workflow test.

Replicates the Edge-recorded workflow:
  1. Login as DRSysAdmin -> super_system_customer
  2. initializeOrganization -> training
  3. createCase (create project)
  4. initializeOrganization -> project context
  5. createDataArea + createCorpus + addCorpus to corpusSet
  6. createRepresentation (start indexing)
  7. requestProjectDelete -> approveProjectDeleteRequest

As of v0.04 this test delegates to `helpers.admin_ops`, which is the
single source of truth for the create/import/delete chain. Tests that
exercised the previous inline `approve_delete` (substring match against
stringified-dict — BUG_LOG B14b) and `wait_for_indexing` (swallowed all
exceptions — B14c) now use the corrected helpers. Newer coverage of the
same path lives in `tests/test_e2e_bootstrap.py` (smoke-tagged, 16s).

Required env:
  DR_NFS_CONNECTOR_HANDLE  — connector to import from (per-install)
  DR_NFS_IMPORT_PATH       — path within that connector (e.g. /testload)
  DR_NFS_DATASET_NAME      — name for the data-area/corpus (default 'testload')
  DR_ORG_ORGANIZATION      — target org name (default 'training')
  DR_ADMIN_ROLE_HANDLE     — org admin role handle (per-install)
"""

from __future__ import annotations

import os
import datetime

import pytest

from config import config
from helpers import admin_ops as ops
from helpers.api_client import EDiscoveryClient


# ---------------------------------------------------------------- config
NFS_CONNECTOR = os.getenv("DR_NFS_CONNECTOR_HANDLE", "")
NFS_PATH = os.getenv("DR_NFS_IMPORT_PATH", "/testload")
NFS_DATASET_NAME = os.getenv("DR_NFS_DATASET_NAME", "testload")
TARGET_ORG = os.getenv("DR_ORG_ORGANIZATION", "training")
ADMIN_ROLE = os.getenv("DR_ADMIN_ROLE_HANDLE", "")


def _unique_name(prefix="api-test"):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{ts}"


class IndexingWorkflow:
    """
    Thin orchestration wrapper around `helpers.admin_ops`. Keeps a small
    bit of state (project/data-area/corpus handles) so the test body
    reads sequentially. All API calls go through admin_ops; the buggy
    inline approve_delete and wait_for_indexing from earlier versions
    are gone.
    """

    def __init__(self, client: EDiscoveryClient):
        self.client = client
        self.project_handle: str | None = None
        self.project_name: str | None = None
        self.da_handle: str | None = None
        self.corpus_handle: str | None = None
        self.cs_handle: str | None = None

    # ---- context switches ------------------------------------------------
    def switch_to_org(self):
        ops.switch_to_org(self.client, TARGET_ORG)

    def switch_to_project(self):
        assert self.project_handle
        ops.switch_to_project(self.client, self.project_handle, TARGET_ORG)

    def switch_to_system(self):
        ops.switch_to_org(self.client, config.organization)

    # ---- create ----------------------------------------------------------
    def create_project(self, name: str | None = None):
        self.project_name = name or _unique_name()
        self.project_handle = ops.create_project(
            self.client,
            org=TARGET_ORG, name=self.project_name,
            role_handle=ADMIN_ROLE,
            description=f"API test {self.project_name}",
        )
        return self.project_handle

    def create_import_job(self):
        """One-shot replacement for the old four-method import chain."""
        assert self.project_handle, "create_project() must run first"
        result = ops.create_import_job(
            self.client,
            project_handle=self.project_handle, org=TARGET_ORG,
            connector_handle=NFS_CONNECTOR, path=NFS_PATH,
            name=NFS_DATASET_NAME,
        )
        self.da_handle = result["data_area_handle"]
        self.corpus_handle = result["corpus_handle"]
        self.cs_handle = result["corpus_set_handle"]
        return result

    def wait_for_indexing(self, timeout: int = 600, interval: int = 5) -> bool:
        """Returns True if all tasks reached SUCCESS, False on timeout."""
        assert self.project_handle
        tasks = ops.wait_for_tasks(
            self.client, self.project_handle,
            timeout=timeout, interval=interval,
        )
        return ops.all_tasks_succeeded(tasks)

    def delete(self) -> bool:
        """Two-phase delete using the corrected admin_ops helper."""
        assert self.project_handle and self.project_name
        self.switch_to_project()
        ok = ops.delete_project(
            self.client,
            project_handle=self.project_handle,
            project_name=self.project_name,
            system_org=config.organization,
        )
        if ok:
            self.project_handle = None  # prevent fixture double-delete
        return ok


# ----------------------------------------------------------- pytest tests

def _skip_if_unconfigured():
    missing = [n for n, v in [
        ("DR_NFS_CONNECTOR_HANDLE", NFS_CONNECTOR),
        ("DR_ADMIN_ROLE_HANDLE", ADMIN_ROLE),
    ] if not v]
    if missing:
        pytest.skip(f"Indexing workflow requires: {', '.join(missing)}")


@pytest.mark.slow
class TestIndexingWorkflow:

    @pytest.fixture
    def wf(self, cfg):
        _skip_if_unconfigured()
        client = EDiscoveryClient(cfg)
        client.login()
        workflow = IndexingWorkflow(client)
        workflow.switch_to_org()
        yield workflow
        # Cleanup — best-effort, never fails the test
        if workflow.project_handle:
            try:
                workflow.delete()
            except Exception as e:
                print(f"WARNING: cleanup of {workflow.project_name} failed: {e}")
        client.logout()

    def test_create_project(self, wf: IndexingWorkflow):
        wf.create_project()
        assert wf.project_handle, "Expected a project handle"

    def test_create_and_import(self, wf: IndexingWorkflow):
        wf.create_project()
        wf.switch_to_project()
        wf.create_import_job()
        assert wf.da_handle, "Expected a data area handle"
        assert wf.corpus_handle, "Expected a corpus handle"

    def test_full_lifecycle(self, wf: IndexingWorkflow):
        wf.create_project()
        wf.switch_to_project()
        wf.create_import_job()
        # Indexing typically completes in ~15s for the small testload fixture.
        finished = wf.wait_for_indexing(timeout=300, interval=5)
        assert finished, "Indexing did not reach SUCCESS within the timeout"
        # The fixture teardown will exercise delete; assert it works here too
        # so the test owns its own cleanup verification.
        assert wf.delete(), "Project delete did not get approved in time"

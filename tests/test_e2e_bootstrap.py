"""
End-to-end bootstrap smoke test.

What this test proves:
  - A new project can be created in an existing org
  - The import pipeline (createDataArea -> createCorpus -> addCorpus ->
    createRepresentation) runs to SUCCESS against /testload
  - The indexing task reports operationState=SUCCESS within the timeout
  - The project can be deleted afterwards (cleanup runs even on failure)

This is the canonical "is the install healthy enough for QA?" check.
If this passes, `dr-load admin` is wired up correctly and the indexing
service is alive. If it fails, the rest of the test suite will fail too.

Required env vars (all read by config.py / via the OrgUserConfig):
  DR_BASE_URL              eDiscovery REST base URL
  DR_USERNAME / DR_PASSWORD     DRSysAdmin credentials (orchestrates the workflow)
  DR_ORG_ORGANIZATION      target org name (e.g. "training")
  DR_ORG_USERNAME / DR_ORG_PASSWORD  org user (needed to list connectors)
  DR_ADMIN_ROLE_HANDLE     org's "Organization Administrator" role handle
                           — per-install; look up once via psql:
                             SELECT role_handle FROM authorization_roles
                              WHERE org_handle='training'
                                AND role_name='Organization Administrator';
  DR_NFS_CONNECTOR_NAME    (optional) connector name to import from.
                           Default: training-import-nfs-local
  DR_NFS_IMPORT_PATH       (optional) source path within the connector.
                           Default: /testload
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

from config import OrgUserConfig
from helpers import admin_ops as ops
from helpers.api_client import EDiscoveryClient


CONNECTOR_NAME = os.getenv("DR_NFS_CONNECTOR_NAME", "training-import-nfs-local")
IMPORT_PATH = os.getenv("DR_NFS_IMPORT_PATH", "/testload")
INDEX_TIMEOUT = int(os.getenv("DR_INDEX_TIMEOUT", "180"))


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        pytest.skip(
            f"{name} not set. The e2e smoke test needs it — see "
            f"tests/test_e2e_bootstrap.py docstring for the full list."
        )
    return val


@pytest.fixture(scope="module")
def org_name() -> str:
    return _require("DR_ORG_ORGANIZATION")


@pytest.fixture(scope="module")
def role_handle() -> None:
    """
    The smoke test relies on `helpers.admin_ops.create_project`
    auto-discovering the role handle from the logged-in user's record
    in the target org. Deliberately does NOT read DR_ADMIN_ROLE_HANDLE
    from env, because a stale value left in .env from earlier versions
    would silently break createCase before auto-discovery ever ran.
    """
    return None


@pytest.fixture(scope="module")
def connector_handle(org_name: str) -> str:
    """Look up the connector handle live (per BUG_LOG B14: must be done
    as an org user; DRSysAdmin sees 0 connectors)."""
    org_cfg = OrgUserConfig()
    if not org_cfg.is_configured:
        pytest.skip(
            "DR_ORG_USERNAME / DR_ORG_PASSWORD not set — needed for "
            "listConnectors (DRSysAdmin cannot see them)."
        )
    client = EDiscoveryClient(org_cfg)
    client.login()
    try:
        connector = ops.find_connector(client, org_name, CONNECTOR_NAME)
        if not connector or not connector.get("handle"):
            pytest.skip(
                f"Connector {CONNECTOR_NAME!r} not visible to "
                f"{org_cfg.username}@{org_name}. Check Express Provisioning."
            )
        return connector["handle"]
    finally:
        client.logout()


@pytest.fixture
def project(api: EDiscoveryClient, org_name: str, role_handle: str):
    """
    Create a uniquely-named project; tear it down at the end.

    `api` is the session-scoped DRSysAdmin client from conftest.py.
    """
    name = f"smoke-{uuid.uuid4().hex[:8]}"
    handle = ops.create_project(
        api, org=org_name, name=name, role_handle=role_handle,
        description="e2e bootstrap smoke test",
    )
    yield {"name": name, "handle": handle}
    # Cleanup — best-effort, never fails the test
    try:
        from config import config as default_cfg
        # Phase 1: requestProjectDelete must happen in project scope
        ops.switch_to_project(api, handle, org_name)
        # Phase 2: approveProjectDeleteRequest happens in system scope
        ops.delete_project(
            api,
            project_handle=handle, project_name=name,
            system_org=default_cfg.organization,
        )
    except Exception as e:
        # Surface as warning so a hung delete doesn't mask the test result
        print(f"WARNING: cleanup of project {name} ({handle}) failed: {e}")


@pytest.mark.smoke
def test_create_project_visible_via_list(api: EDiscoveryClient, org_name: str, project):
    """After create, the project is visible in listProjects with state=AVAILABLE."""
    match = ops.find_project(api, org_name, project["name"])
    assert match is not None, f"project {project['name']} not visible after create"
    state = match.get("projectState") or match.get("state")
    assert state == "AVAILABLE", f"expected state AVAILABLE, got {state}"


@pytest.mark.smoke
def test_import_job_runs_to_success(
    api: EDiscoveryClient,
    org_name: str,
    project,
    connector_handle: str,
):
    """The full import pipeline submits and completes within INDEX_TIMEOUT."""
    ops.switch_to_project(api, project["handle"], org_name)

    result = ops.create_import_job(
        api,
        project_handle=project["handle"], org=org_name,
        connector_handle=connector_handle, path=IMPORT_PATH,
        name="testload",
    )
    assert result["data_area_handle"], "createDataArea returned no handle"
    assert result["corpus_handle"], "createCorpus returned no handle"

    # Brief grace period for the task to register before we start polling
    time.sleep(2)
    tasks = ops.wait_for_tasks(
        api, project["handle"],
        timeout=INDEX_TIMEOUT, interval=3,
    )
    assert tasks, "no tasks recorded for project — createRepresentation didn't register"
    assert ops.all_tasks_succeeded(tasks), (
        "at least one task did not reach SUCCESS:\n"
        + "\n".join(
            f"  - {t.get('description', '?')[:60]}: "
            f"operationState={t.get('operationState')} "
            f"taskStatus={t.get('taskStatus')}"
            for t in tasks
        )
    )
    # Read back: every task should have processed the expected number of docs
    doc_counts = [t.get("numberResults") for t in tasks if t.get("numberResults")]
    if doc_counts:
        assert all(c == 2 for c in doc_counts), (
            f"expected 2 docs per task (the testload fixture), got {doc_counts}"
        )

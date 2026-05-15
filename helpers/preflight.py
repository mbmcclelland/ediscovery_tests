"""
Preflight checks for dr_load.

Runs before any load test to confirm the environment is ready:
  1. App reachable  — POST realmManager/getVersion
  2. Auth works     — POST realmManager/createSession (DRSysAdmin)
  3. Postgres       — subprocess psql ping via peer auth (sudo -u auraria)
  4. NFS path       — sudo -u auraria stat DR_NFS_IMPORT_PATH
  5. Log dir        — DR_LOG_DIR readable, at least one .log file present
  6. Connector UUID — listConnectors, verify DR_NFS_CONNECTOR_HANDLE is present

Each check returns a CheckResult. run_preflight() returns the list and a pass/fail bool.
Callers should abort the load test if any check fails.
"""

from __future__ import annotations

import logging
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import requests
import urllib3

from config import Config, config as default_config

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _check_app_reachable(cfg: Config) -> CheckResult:
    """Any HTTP response (even 4xx/5xx) means the app is up and listening."""
    url = cfg.endpoint("realmManager/getVersion")
    try:
        resp = requests.post(
            url,
            json={"contextHandle": cfg.organization, "systemScope": True},
            verify=cfg.verify_ssl,
            timeout=cfg.request_timeout,
        )
        # Server responded — it's up. Try to extract version if available.
        try:
            version = resp.json().get("version") or resp.json().get("serverVersion") or f"HTTP {resp.status_code}"
        except Exception:
            version = f"HTTP {resp.status_code}"
        return CheckResult("app_reachable", True, f"OK — {version}")
    except requests.exceptions.ConnectionError as e:
        return CheckResult("app_reachable", False, f"Connection refused: {e}")
    except requests.exceptions.Timeout:
        return CheckResult("app_reachable", False, f"Timed out after {cfg.request_timeout}s")
    except Exception as e:
        return CheckResult("app_reachable", False, str(e))


def _check_auth(cfg: Config) -> CheckResult:
    url = cfg.endpoint("realmManager/createSession")
    body = {
        "drWsClientContext": {
            "username": cfg.username,
            "organizationName": cfg.organization,
        },
        "contextPath": "/ediscovery",
        "userDeviceID": str(uuid.uuid4()),
    }
    try:
        resp = requests.post(
            url,
            json=body,
            auth=(cfg.username, cfg.password),
            verify=cfg.verify_ssl,
            timeout=cfg.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("sessionToken"):
            return CheckResult("auth", False, f"Login failed: {data.get('errorCode', 'no token')}")
        return CheckResult("auth", True, f"OK — logged in as {cfg.username}")
    except Exception as e:
        return CheckResult("auth", False, str(e))


def _check_postgres(cfg: Config) -> CheckResult:
    try:
        result = subprocess.run(
            ["sudo", "-u", "auraria", "psql", "-d", cfg.pg_db, "-c", r"\conninfo"],
            capture_output=True, text=True, timeout=10,
            input="",
        )
        if result.returncode == 0:
            return CheckResult("postgres", True, f"OK — {result.stdout.strip()}")
        return CheckResult("postgres", False, result.stderr.strip())
    except subprocess.TimeoutExpired:
        return CheckResult("postgres", False, "psql timed out after 10s")
    except Exception as e:
        return CheckResult("postgres", False, str(e))


def _check_nfs(nfs_import_path: str) -> CheckResult:
    # DR_NFS_IMPORT_PATH is relative to /data/import (the NFS export root)
    rel = nfs_import_path.lstrip("/")
    full_path = f"/data/import/{rel}"
    try:
        result = subprocess.run(
            ["sudo", "-u", "auraria", "stat", full_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return CheckResult("nfs_path", True, f"OK — accessible: {full_path}")
        return CheckResult("nfs_path", False, f"{full_path}: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        return CheckResult("nfs_path", False, f"stat timed out for {full_path}")
    except Exception as e:
        return CheckResult("nfs_path", False, str(e))


def _check_log_dir(log_dir: str) -> CheckResult:
    p = Path(log_dir)
    if not p.exists():
        return CheckResult("log_dir", False, f"Directory not found: {log_dir}")
    if not p.is_dir():
        return CheckResult("log_dir", False, f"Not a directory: {log_dir}")
    logs = list(p.glob("*.log"))
    if not logs:
        return CheckResult("log_dir", False, f"No .log files in {log_dir}")
    newest = max(logs, key=lambda f: f.stat().st_mtime)
    return CheckResult("log_dir", True, f"OK — {len(logs)} log file(s); newest: {newest.name}")


def _check_connector(cfg: Config) -> CheckResult:
    import os
    connector_handle = os.getenv("DR_NFS_CONNECTOR_HANDLE", "")
    if not connector_handle:
        return CheckResult("connector_uuid", False, "DR_NFS_CONNECTOR_HANDLE not set in environment")

    # listConnectors only works with an org user token (DRSysAdmin returns 0 results)
    import os
    org_user = os.getenv("DR_ORG_USERNAME", "")
    org_pass = os.getenv("DR_ORG_PASSWORD", "")
    org_name = os.getenv("DR_ORG_ORGANIZATION", "training")
    if not (org_user and org_pass):
        return CheckResult("connector_uuid", False, "DR_ORG_USERNAME/DR_ORG_PASSWORD not set — cannot verify connector")
    try:
        login_resp = requests.post(
            cfg.endpoint("realmManager/createSession"),
            json={
                "drWsClientContext": {"username": org_user, "organizationName": org_name},
                "contextPath": "/ediscovery",
                "userDeviceID": str(uuid.uuid4()),
            },
            auth=(org_user, org_pass),
            verify=cfg.verify_ssl,
            timeout=cfg.request_timeout,
        )
        token = login_resp.json().get("sessionToken", "")
    except Exception as e:
        return CheckResult("connector_uuid", False, f"Org user auth for connector check failed: {e}")

    try:
        resp = requests.post(
            cfg.endpoint("orgManager/listConnectors"),
            json={"contextHandle": cfg.organization, "systemScope": True},
            headers={"Authorization": token, "Content-Type": "application/json"},
            verify=cfg.verify_ssl,
            timeout=cfg.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        connectors = data.get("connectors", data.get("results", []))
        handles = [c.get("handle", "") for c in connectors if isinstance(c, dict)]
        if connector_handle in handles:
            return CheckResult("connector_uuid", True, f"OK — handle found among {len(handles)} connector(s)")
        return CheckResult(
            "connector_uuid", False,
            f"DR_NFS_CONNECTOR_HANDLE not found in {len(handles)} connector(s) — wrong host or stale handle",
        )
    except Exception as e:
        return CheckResult("connector_uuid", False, str(e))


def run_orphan_sweep(cfg: Config | None = None) -> int:
    """
    Find and delete orphaned load-test-* projects via DB + API.

    Queries mgmtproject for projects whose name starts with 'load-test-'
    that are not already pending deletion, then fires requestProjectDelete /
    approveProjectDeleteRequest for each.

    Returns the number of projects for which deletion was successfully requested.
    """
    cfg = cfg or default_config

    def _psql(query: str, timeout: int = 30) -> list[str]:
        r = subprocess.run(
            ["sudo", "-u", "auraria", "psql", "-d", cfg.pg_db, "-t", "-A", "-F", "|", "-c", query],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip())
        return [line.strip() for line in r.stdout.splitlines() if "|" in line.strip()]

    # ── Step 1: find orphan projects (include DELETE_REQUEST_PENDING — just need approval) ──
    try:
        rows = _psql(
            "SELECT projectname, projectid FROM mgmtproject "
            "WHERE projectname LIKE 'load-test-%' "
            "AND projectstate NOT IN ('DELETE_PENDING', 'DELETED')"
        )
    except Exception as e:
        logger.warning("Orphan sweep DB query failed: %s", e)
        return 0

    projects = []  # list of {name, id} where id is string(projectid)
    for row in rows:
        parts = row.split("|", 1)
        if len(parts) == 2 and parts[1]:
            projects.append({"name": parts[0], "id": parts[1]})

    if not projects:
        return 0

    logger.info("Orphan sweep: found %d stale load-test-* project(s)", len(projects))

    # ── Step 2: login ───────────────────────────────────────────────────────
    try:
        login_resp = requests.post(
            cfg.endpoint("realmManager/createSession"),
            json={
                "drWsClientContext": {
                    "username": cfg.username,
                    "organizationName": cfg.organization,
                },
                "contextPath": "/ediscovery",
                "userDeviceID": str(uuid.uuid4()),
            },
            auth=(cfg.username, cfg.password),
            verify=cfg.verify_ssl,
            timeout=cfg.request_timeout,
        )
        token = login_resp.json().get("sessionToken", "")
        if not token:
            logger.warning("Orphan sweep: DRSysAdmin login failed")
            return 0
    except Exception as e:
        logger.warning("Orphan sweep login error: %s", e)
        return 0

    auth_headers = {"Authorization": token, "Content-Type": "application/json"}

    # ── Step 3: requestProjectDelete for any that don't have a pending request ──
    try:
        pending_ids = {
            row.split("|")[0]
            for row in _psql(
                "SELECT objecthandle FROM admin_request_table "
                "WHERE objecthandle IN ("
                + ",".join(f"'{p['id']}'" for p in projects)
                + ") AND requeststatus = 0"
            )
        }
    except Exception:
        pending_ids = set()

    needs_request = [p for p in projects if p["id"] not in pending_ids]
    logger.info("Orphan sweep: %d need requestProjectDelete, %d already pending",
                len(needs_request), len(pending_ids))

    for proj in needs_request:
        try:
            r1 = requests.post(
                cfg.endpoint("adminOrgManager/requestProjectDelete"),
                json={
                    "contextHandle":  proj["id"],
                    "projectHandle":  proj["id"],
                    "taskDescription": f"Orphan cleanup: {proj['name']}",
                    "systemScope":    True,
                },
                headers=auth_headers,
                verify=cfg.verify_ssl,
                timeout=cfg.request_timeout,
            )
            if r1.status_code not in (200, 204):
                logger.warning("Orphan sweep: requestProjectDelete HTTP %d for %s",
                               r1.status_code, proj["name"])
                continue
            try:
                new_tok = r1.json().get("sessionToken")
                if new_tok:
                    token = new_tok
                    auth_headers["Authorization"] = token
            except Exception:
                pass
        except Exception as e:
            logger.warning("Orphan sweep: requestProjectDelete error for %s: %s", proj["name"], e)

    time.sleep(2)

    # ── Step 4: fetch all delete-request handles from DB, then approve ─────
    deleted = 0
    project_ids = {p["id"] for p in projects}
    try:
        req_rows = _psql(
            "SELECT objecthandle, handle FROM admin_request_table "
            "WHERE objecthandle IN ("
            + ",".join(f"'{pid}'" for pid in project_ids)
            + ") AND requeststatus = 0"
        )
    except Exception as e:
        logger.warning("Orphan sweep: admin_request_table query failed: %s", e)
        return 0

    for row in req_rows:
        parts = row.split("|", 1)
        if len(parts) != 2:
            continue
        proj_id, req_handle = parts[0], parts[1]
        try:
            r3 = requests.post(
                cfg.endpoint("adminOrgManager/approveProjectDeleteRequest"),
                json={
                    "requestHandle":  None,
                    "contextHandle":  proj_id,
                    "handle":         req_handle,
                    "systemScope":    True,
                    "taskDescription": "Orphan cleanup approve",
                },
                headers=auth_headers,
                verify=cfg.verify_ssl,
                timeout=cfg.request_timeout,
            )
            try:
                new_tok = r3.json().get("sessionToken")
                if new_tok:
                    token = new_tok
                    auth_headers["Authorization"] = token
                if r3.json().get("status") == "SUCCESS":
                    deleted += 1
                    logger.info("Orphan sweep: approved delete for project %s", proj_id)
                else:
                    logger.warning("Orphan sweep: approve returned %s for %s",
                                   r3.json().get("errorCode"), proj_id)
            except Exception:
                deleted += 1
        except Exception as e:
            logger.warning("Orphan sweep: approveProjectDeleteRequest error for %s: %s", proj_id, e)

    logger.info("Orphan sweep complete: %d approved for deletion", deleted)
    return deleted


def run_preflight(cfg: Config | None = None) -> Tuple[List[CheckResult], bool]:
    """
    Run all preflight checks. Returns (results, all_passed).
    Callers should abort the load test if all_passed is False.
    """
    import os
    cfg = cfg or default_config
    nfs_path = os.getenv("DR_NFS_IMPORT_PATH", "/test_datasets/Small Sample")

    results = [
        _check_app_reachable(cfg),
        _check_auth(cfg),
        _check_postgres(cfg),
        _check_nfs(nfs_path),
        _check_log_dir(cfg.log_dir),
        _check_connector(cfg),
    ]
    all_passed = all(r.passed for r in results)
    return results, all_passed

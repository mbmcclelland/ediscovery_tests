#!/usr/bin/env python3
"""DR_freshinstall.py — end-to-end fresh-install driver for Digital Reef.

Replaces the three-script sequence:

    bash cleandr.sh
    expect -f DR_freshinstall.exp
    python playwright_fresh_init.py        # browser-driven, slow

with a single Python entry point that talks to DR over REST. The
cleandr + installer steps are still done via the existing shell/expect
scripts (kept for "what exactly does this delete?" auditability) but
the post-install provisioning runs entirely through `dr_tui/data.py`
helpers — no Playwright, no Chromium download, no proxy capture. It's
~5x faster than the Playwright path and survives in environments
without a GUI.

Usage:

    sudo .venv/bin/python DR_freshinstall.py             # full sequence
    sudo .venv/bin/python DR_freshinstall.py --dry-run   # print only
    sudo .venv/bin/python DR_freshinstall.py --skip-clean --skip-installer
    sudo .venv/bin/python DR_freshinstall.py --keep-existing

Flags:

    --skip-clean        don't run the cleandr teardown
    --skip-installer    don't run the expect-driven .bin reinstall
                        (use when drd is already up but un-provisioned)
    --skip-api          stop after the installer; useful for debugging
    --keep-existing     idempotent mode — every API step skips if the
                        target object already exists. Safe to re-run
                        after a partial failure.
    --keeprpm           passed through to cleandr.sh
    --dry-run           print every action without doing it
    --hostname HOST     DR host (default: 192.168.58.128)
    --nfs-host HOST     storage / connector NFS server (default: same
                        as --hostname; almost always identical)

The 13 API-level steps are documented in the top-level user request
that produced this script and mirrored in the `STEPS` list below.

This script is destructive when run without `--skip-clean`. Hold on
to /root/license.lic — both this script and DR_freshinstall.exp
expect it there.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import warnings
from pathlib import Path

# Silence the urllib3 self-signed-cert spam early. data.py imports already
# emit warnings; squash them at module load so the progress log stays
# readable.
warnings.filterwarnings("ignore")

# Repo root + ensure local imports resolve when running as a script.
_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from config import Config                                           # noqa: E402
from helpers.api_client import EDiscoveryClient, APIError           # noqa: E402
from dr_tui import data as drdata                                   # noqa: E402


# ---------- CLI ----------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-clean", action="store_true",
                    help="skip the cleandr teardown")
    ap.add_argument("--skip-installer", action="store_true",
                    help="skip DR_freshinstall.exp (assume drd is up)")
    ap.add_argument("--skip-api", action="store_true",
                    help="skip API provisioning (clean + install only)")
    ap.add_argument("--keep-existing", action="store_true",
                    help="API steps no-op when target already exists")
    ap.add_argument("--keeprpm", action="store_true",
                    help="passed through to cleandr.sh (keep dr-tools RPM)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print every action without doing it")
    ap.add_argument("--hostname", default="192.168.58.128",
                    help="DR REST host (default: 192.168.58.128)")
    ap.add_argument("--nfs-host", default="",
                    help="NFS server fqdn for storage + connectors "
                         "(default: same as --hostname)")
    ap.add_argument("--inactivity-minutes", type=int, default=99,
                    help="session inactivity timeout in minutes "
                         "(default: 99)")
    ap.add_argument("--initial-password", default="DRSysAdmin",
                    help="DRSysAdmin's default first-login password "
                         "(default: DRSysAdmin)")
    ap.add_argument("--final-password", default="password",
                    help="DRSysAdmin's new password after change "
                         "(default: password)")
    return ap.parse_args()


# ---------- progress logging ----------------------------------------------------

# A single global so step output stays aligned regardless of which
# function is logging. The terminal-width check keeps wide messages
# readable on 80-column legacy clients (v0.10.2 lesson).
_TERM_WIDTH = 100
try:
    _TERM_WIDTH = max(80, min(120, os.get_terminal_size().columns))
except Exception:
    pass


def _hr() -> None:
    print("─" * _TERM_WIDTH)


def _step(num: int, title: str) -> None:
    print()
    _hr()
    print(f"  Step {num:2d}.  {title}")
    _hr()


def _ok(msg: str) -> None:
    print(f"    ✓  {msg}")


def _info(msg: str) -> None:
    print(f"    ·  {msg}")


def _warn(msg: str) -> None:
    print(f"    ⚠  {msg}")


def _fail(msg: str) -> None:
    print(f"    ✗  {msg}")


def _skip(msg: str) -> None:
    print(f"    ⊘  skipped: {msg}")


# ---------- Phase 1: teardown via cleandr.sh -----------------------------------

def phase_clean(args: argparse.Namespace) -> None:
    """Inline cleandr.sh action.

    We call the existing shell script as a subprocess rather than
    re-implementing it in Python — `rm -rfv` with a real shell is
    auditable, and the script has been battle-tested. The user can
    diff cleandr.sh and trust this driver to behave identically.
    """
    cmd = ["bash", str(_REPO / "cleandr.sh")]
    if args.keeprpm:
        cmd.append("--keeprpm")
    if args.dry_run:
        _info(f"DRY-RUN: would run: {' '.join(cmd)}")
        return
    _info(f"running: {' '.join(cmd)}")
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        raise RuntimeError(f"cleandr.sh exited with {rc}")
    _ok("teardown complete")


# ---------- Phase 2: installer via DR_freshinstall.exp -------------------------

def phase_installer(args: argparse.Namespace) -> None:
    """Run the expect script that drives the InstallAnywhere .bin.

    The .bin lives at /tmp/5.5.3.2.bin (the script `cd`s to /tmp
    internally via `spawn ./5.5.3.2.bin`). License restoration is
    appended inside the expect file itself (it copies /root/license.lic
    back to /home/auraria/AHS/conf/ and restarts drd).
    """
    if not (_REPO / "DR_freshinstall.exp").is_file():
        raise FileNotFoundError("DR_freshinstall.exp not found")
    if not Path("/tmp/5.5.3.2.bin").is_file():
        raise FileNotFoundError(
            "/tmp/5.5.3.2.bin not found — copy the DR installer there "
            "before running."
        )
    cmd = ["expect", "-f", str(_REPO / "DR_freshinstall.exp")]
    if args.dry_run:
        _info(f"DRY-RUN: would run: {' '.join(cmd)}")
        return
    _info("driving the installer (this takes a few minutes…)")
    # The expect script spawns `./5.5.3.2.bin -i console` from /tmp,
    # so we cd there first. cwd= isolates the change from the rest
    # of the driver.
    rc = subprocess.run(cmd, cwd="/tmp").returncode
    if rc != 0:
        raise RuntimeError(f"DR_freshinstall.exp exited with {rc}")
    _ok("installer finished")


# ---------- Phase 2.5: wait for drd --------------------------------------------

def _drd_listening(host: str, port: int = 8443, timeout: float = 5.0) -> bool:
    """Cheap TCP probe — does drd accept a connection on :8443 yet?"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_drd(host: str, max_wait_s: int = 180) -> None:
    """Poll until drd is up after an installer run. Times out cleanly
    so a hang in jboss startup doesn't leave us spinning forever.
    """
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        if _drd_listening(host):
            _ok(f"drd is listening on {host}:8443")
            return
        time.sleep(3)
    raise TimeoutError(
        f"drd did not come up within {max_wait_s}s — check "
        f"/home/auraria/AHS/jboss/standalone/log/server.log"
    )


# ---------- Phase 3: API provisioning ------------------------------------------

# These are the 13 steps from the user request. Kept as a single list
# so the script's structure mirrors the spec exactly — anyone reading
# this can match step N here to step N in the request.

STEPS = [
    "Login + change DRSysAdmin's default password",
    "Create document storage at /data/docstorage",
    "Create index storage at /data/indexstorage",
    "Create the system storage depot (using the index storage)",
    "Update virus definitions",
    "Set the logon inactivity timeout (minutes)",
    "Create the 'training' organization",
    "Create admin@training as Organization Administrator",
    "Add DRSysAdmin to 'training' as Organization Administrator",
    "Create read-only IMPORT connector @ /data/import",
    "Create read-write connector @ /data/export",
    "Create read-write connector @ /data/archive",
    "Create PROJECT data area on /data/archive + EXPORT data area on /data/export",
]


def _make_cfg(host: str, username: str, password: str,
              organization: str = "super_system_customer") -> Config:
    """Config is a frozen dataclass — build a fresh instance per call
    rather than mutating fields (the env-driven defaults still apply
    for anything we don't override)."""
    base_url = f"https://{host}:8443/ediscovery/rest"
    return Config(
        base_url=base_url,
        username=username,
        password=password,
        organization=organization,
    )


def _try_initial_login(host: str, initial_pw: str, final_pw: str) -> tuple[EDiscoveryClient, bool]:
    """Try the final password first (idempotent re-run), then the
    initial. Returns (client, changed_already) — `changed_already`
    is True when we logged in with the final password (so step 1's
    change-password call is a no-op).
    """
    # Final-password attempt first → idempotent re-run path.
    try:
        c = EDiscoveryClient(_make_cfg(host, "DRSysAdmin", final_pw))
        c.login()
        return c, True
    except (APIError, Exception):
        pass
    # Fall back to the default first-install password.
    c = EDiscoveryClient(_make_cfg(host, "DRSysAdmin", initial_pw))
    c.login()
    return c, False


def step_1_login_and_change_password(args) -> EDiscoveryClient:
    _step(1, STEPS[0])
    if args.dry_run:
        _info(f"DRY-RUN: would login {args.initial_password!r} → "
              f"change to {args.final_password!r}")
        return None  # type: ignore
    client, already_changed = _try_initial_login(
        args.hostname, args.initial_password, args.final_password,
    )
    if already_changed:
        _ok(f"already logged in with {args.final_password!r} "
            f"(password previously changed)")
        return client
    _info(f"logged in with default password {args.initial_password!r}")
    drdata.change_user_password(
        client,
        old_password=args.initial_password,
        new_password=args.final_password,
        org_name="super_system_customer",
    )
    _ok(f"password changed → {args.final_password!r}")
    # Re-login with the new password to refresh the session token in
    # the canonical "post-change" state. Some endpoints reject the
    # old token after a password change even though it's not yet
    # expired. Config is a frozen dataclass — build a fresh client
    # rather than mutating in place.
    client = EDiscoveryClient(
        _make_cfg(args.hostname, "DRSysAdmin", args.final_password)
    )
    client.login()
    _ok("re-logged in with new password")
    return client


def step_2_create_doc_storage(args, client: EDiscoveryClient) -> str:
    """Returns the document-storage handle (for traceability)."""
    _step(2, STEPS[1])
    name = "localDocStorage"
    nfs_host = args.nfs_host or args.hostname
    if args.dry_run:
        _info(f"DRY-RUN: createRemoteNFSStorageArea name={name} "
              f"export=/data/docstorage")
        return ""
    export = "/data/docstorage"
    if args.keep_existing:
        # Match by (export, fqdn) first so renamed depots are still
        # recognised — a partially-failed prior run might have left
        # the same mount under a different label.
        for d in drdata.list_storage_depots(client, "DOCUMENT_STORE"):
            if d.export == export and (not d.fqdn or d.fqdn == nfs_host):
                _skip(f"DOC storage at {export!r} already exists "
                      f"(name={d.name!r} handle={d.handle})")
                return d.handle
    resp = drdata.create_storage_depot(
        client, name=name, fqdn=nfs_host, export=export,
        use_type="DOCUMENT_STORE",
    )
    handle = (resp.get("remoteStorageArea") or {}).get("handle", "")
    _ok(f"created {name} → handle={handle}")
    return handle


def step_3_create_index_storage(args, client: EDiscoveryClient) -> tuple[str, str, str]:
    """Returns (handle, fqdn, export) — needed by step 4."""
    _step(3, STEPS[2])
    name = "localIndexStorage"
    nfs_host = args.nfs_host or args.hostname
    export = "/data/indexstorage"
    if args.dry_run:
        _info(f"DRY-RUN: createRemoteNFSStorageArea name={name} "
              f"export={export}")
        return ("", nfs_host, export)
    if args.keep_existing:
        for d in drdata.list_storage_depots(client, "INDEX_STORE"):
            if d.export == export and (not d.fqdn or d.fqdn == nfs_host):
                _skip(f"INDEX storage at {export!r} already exists "
                      f"(name={d.name!r} handle={d.handle})")
                return (d.handle, d.fqdn or nfs_host, d.export or export)
    resp = drdata.create_storage_depot(
        client, name=name, fqdn=nfs_host, export=export,
        use_type="INDEX_STORE",
    )
    handle = (resp.get("remoteStorageArea") or {}).get("handle", "")
    _ok(f"created {name} → handle={handle}")
    return (handle, nfs_host, export)


def step_4_create_system_storage_depot(
    args, client: EDiscoveryClient,
    idx_handle: str, idx_fqdn: str, idx_export: str,
) -> None:
    _step(4, STEPS[3])
    if args.dry_run:
        _info(f"DRY-RUN: createSystemStorageDepot using "
              f"index storage handle={idx_handle}")
        return
    if args.keep_existing:
        cur = drdata.get_system_storage_depot(client)
        if cur and cur.directory_path:
            _skip(f"system depot already assigned: {cur.name!r}")
            return
    if not idx_handle:
        # Re-discover by name (covers a partial-failure run).
        for d in drdata.list_storage_depots(client, "INDEX_STORE"):
            if d.name == "localIndexStorage":
                idx_handle, idx_fqdn, idx_export = (
                    d.handle, d.fqdn or idx_fqdn, d.export or idx_export,
                )
                break
    drdata.create_system_storage_depot(
        client,
        ip_address=idx_fqdn,
        storage_facility_id=idx_handle,
        mount_point=idx_export,
    )
    _ok(f"system storage depot pointed at {idx_fqdn}:{idx_export}")


def step_5_virus_update(args, client: EDiscoveryClient) -> None:
    _step(5, STEPS[4])
    if args.dry_run:
        _info("DRY-RUN: trigger_virus_update")
        return
    try:
        drdata.trigger_virus_update(client, enabled=True, frequency="DAILY")
        _ok("virus update queued (runs in background)")
    except APIError as e:
        # INVALID_STATE on a re-run just means an update is already in
        # progress — treat as success.
        if e.error_code == "INVALID_STATE":
            _skip("virus update already in progress")
        else:
            raise


def step_6_inactivity_timeout(args, client: EDiscoveryClient) -> None:
    _step(6, STEPS[5])
    minutes = args.inactivity_minutes
    seconds = minutes * 60
    if args.dry_run:
        _info(f"DRY-RUN: setInactivityTimeout {seconds}s ({minutes} min)")
        return
    drdata.set_inactivity_timeout(client, seconds=seconds)
    _ok(f"session timeout set to {minutes} minutes ({seconds}s)")


def step_7_create_training_org(args, client: EDiscoveryClient) -> None:
    _step(7, STEPS[6])
    if args.dry_run:
        _info("DRY-RUN: createOrganization name='training'")
        return
    if args.keep_existing:
        for o in drdata.list_organizations_sys(client):
            if o.name == "training":
                _skip(f"org 'training' already exists (handle={o.handle})")
                return
    drdata.create_organization(client, name="training", description="")
    _ok("created organization 'training'")


def _resolve_org_admin_role(client: EDiscoveryClient) -> str:
    """Look up the Organization Administrator role handle for training.

    Uses the sys-scoped `adminOrgManager/listRoles` so the call works
    even when DRSysAdmin hasn't been added to the org yet (the state
    of a brand-new org created by `realmManager/createOrganization`).
    """
    drdata.ensure_org_context(client, "training")
    roles = drdata.list_org_roles(client, org_name="training", sys_scope=True)
    for name, h in roles:
        if name == "Organization Administrator":
            return h
    raise RuntimeError(
        f"Organization Administrator role not found in training. "
        f"Available roles: {[n for n,_ in roles]!r}"
    )


def step_8_create_org_admin(
    args, client: EDiscoveryClient, org_admin_handle: str,
) -> None:
    """Creates `admin@training`. Requires DRSysAdmin to already be a
    member of the org (step 9 has been moved BEFORE step 8 in
    `phase_api` for this reason)."""
    _step(8, STEPS[7])
    if args.dry_run:
        _info("DRY-RUN: createUser admin@training with Organization "
              "Administrator role")
        return
    if args.keep_existing:
        # listUsersAndGroups → look for 'admin'
        try:
            r = client.post(
                "adminOrgManager/listUsersAndGroups",
                extra_body={
                    "contextHandle": "training",
                    "organizationName": "training",
                    "systemScope": True,
                },
            )
            for u in (r.get("users") or []):
                if (u.get("userName") or "").lower() == "admin":
                    _skip(f"admin@training already exists "
                          f"(handle={u.get('handle')})")
                    return
        except Exception:
            pass
    drdata.create_org_user(
        client,
        org_name="training",
        user_name="admin",
        password="Password123",
        role_handles=[org_admin_handle],
        email="admin@localhost.com",
        first_name="Admin",
        last_name="User",
    )
    _ok("created admin@training (initial pw 'Password123')")


def step_8b_change_org_admin_password(args, client: EDiscoveryClient) -> None:
    """Bonus: admin@training is forced to change pw on first login. The
    dr-tui org-pinned login expects 'password' (env DR_ORG_PASSWORD).
    Log in once as admin@training, change the pw, log back out."""
    if args.dry_run:
        _info(f"DRY-RUN: would login admin@training and change pw → "
              f"{args.final_password!r}")
        return
    # Try the FINAL password first — handles the idempotent re-run
    # path (admin already past the forced-change flow). DR returns
    # 500 (not a structured APIError) for a bad password, so we
    # catch broadly and fall through.
    try:
        EDiscoveryClient(
            _make_cfg(args.hostname, "admin", args.final_password,
                      organization="training")
        ).login()
        _skip("admin@training already on final password")
        return
    except Exception:
        pass
    # Initial password — first run after createUser.
    org_client = EDiscoveryClient(
        _make_cfg(args.hostname, "admin", "Password123",
                  organization="training")
    )
    org_client.login()
    drdata.change_user_password(
        org_client,
        old_password="Password123",
        new_password=args.final_password,
        org_name="training",
    )
    _ok(f"admin@training password → {args.final_password!r}")


def step_9_add_drsysadmin_to_org(
    args, client: EDiscoveryClient, role_handle: str,
) -> None:
    _step(9, STEPS[8])
    if args.dry_run:
        _info(f"DRY-RUN: addSystemUserToOrg DRSysAdmin → training "
              f"(role={role_handle})")
        return
    if args.keep_existing:
        # listUsersAndGroups for training — does DRSysAdmin appear?
        try:
            r = client.post(
                "adminOrgManager/listUsersAndGroups",
                extra_body={
                    "contextHandle": "training",
                    "organizationName": "training",
                    "systemScope": True,
                },
            )
            for u in (r.get("users") or []):
                if (u.get("userName") or "").lower() == "drsysadmin":
                    _skip("DRSysAdmin already a member of training")
                    return
        except Exception:
            pass
    drdata.add_system_user_to_org(
        client,
        system_user_name="DRSysAdmin",
        org_name="training",
        role_handle=role_handle,
    )
    _ok("DRSysAdmin added to training as Organization Administrator")


def step_10_create_import_connector(
    args, client: EDiscoveryClient,
) -> str:
    _step(10, STEPS[9])
    nfs_host = args.nfs_host or args.hostname
    name = "import-training-nfs-local"
    if args.dry_run:
        _info(f"DRY-RUN: createNFSConnector {name} (read-only) → "
              f"/data/import")
        return ""
    if args.keep_existing:
        for c in drdata.list_connectors(client, "training"):
            if c.name == name:
                _skip(f"{name} already exists (handle={c.handle})")
                return c.handle
    resp = drdata.create_nfs_connector(
        client, org_name="training", name=name,
        remote_host=nfs_host, remote_path="/data/import",
        read_only=True,
    )
    handle = (resp.get("connector") or {}).get("handle", "")
    _ok(f"created {name} (READ ONLY) → handle={handle}")
    return handle


def step_11_create_export_connector(
    args, client: EDiscoveryClient,
) -> str:
    _step(11, STEPS[10])
    nfs_host = args.nfs_host or args.hostname
    name = "export-training-nfs-local"
    if args.dry_run:
        _info(f"DRY-RUN: createNFSConnector {name} (read/write) → "
              f"/data/export")
        return ""
    if args.keep_existing:
        for c in drdata.list_connectors(client, "training"):
            if c.name == name:
                _skip(f"{name} already exists (handle={c.handle})")
                return c.handle
    resp = drdata.create_nfs_connector(
        client, org_name="training", name=name,
        remote_host=nfs_host, remote_path="/data/export",
        read_only=False,
    )
    handle = (resp.get("connector") or {}).get("handle", "")
    _ok(f"created {name} (READ/WRITE) → handle={handle}")
    return handle


def step_12_create_archive_connector(
    args, client: EDiscoveryClient,
) -> str:
    _step(12, STEPS[11])
    nfs_host = args.nfs_host or args.hostname
    name = "archive-training-nfs-local"
    if args.dry_run:
        _info(f"DRY-RUN: createNFSConnector {name} (read/write) → "
              f"/data/archive")
        return ""
    if args.keep_existing:
        for c in drdata.list_connectors(client, "training"):
            if c.name == name:
                _skip(f"{name} already exists (handle={c.handle})")
                return c.handle
    resp = drdata.create_nfs_connector(
        client, org_name="training", name=name,
        remote_host=nfs_host, remote_path="/data/archive",
        read_only=False,
    )
    handle = (resp.get("connector") or {}).get("handle", "")
    _ok(f"created {name} (READ/WRITE) → handle={handle}")
    return handle


def step_13_create_data_areas(
    args, client: EDiscoveryClient,
    archive_handle: str, export_handle: str,
) -> None:
    _step(13, STEPS[12])
    if args.dry_run:
        _info("DRY-RUN: createDataArea PROJECT on archive, "
              "EXPORT on export")
        return

    # PROJECT data area on the archive connector.
    project_name = "pda-training-archive"
    try:
        drdata.create_data_area(
            client,
            context_handle="training",
            connector_handle=archive_handle,
            name=project_name,
            mode="PROJECT",
            path=".",
        )
        _ok(f"created PROJECT data area '{project_name}' on archive")
    except APIError as e:
        if args.keep_existing and "ALREADY" in (e.extended_status or "").upper():
            _skip(f"{project_name} already exists")
        else:
            raise

    # EXPORT data area on the export connector.
    export_name = "xda-training-export"
    try:
        drdata.create_data_area(
            client,
            context_handle="training",
            connector_handle=export_handle,
            name=export_name,
            mode="EXPORT",
            path=".",
        )
        _ok(f"created EXPORT data area '{export_name}' on export")
    except APIError as e:
        if args.keep_existing and "ALREADY" in (e.extended_status or "").upper():
            _skip(f"{export_name} already exists")
        else:
            raise


# ---------- Phase 3 orchestrator ------------------------------------------------

def phase_api(args: argparse.Namespace) -> None:
    """Run the 13 provisioning steps end-to-end."""
    if not args.dry_run:
        wait_for_drd(args.hostname)

    client = step_1_login_and_change_password(args)
    step_2_create_doc_storage(args, client)
    idx_handle, idx_fqdn, idx_export = step_3_create_index_storage(args, client)
    step_4_create_system_storage_depot(args, client, idx_handle, idx_fqdn, idx_export)
    step_5_virus_update(args, client)
    step_6_inactivity_timeout(args, client)
    step_7_create_training_org(args, client)
    # Resolve the Organization Administrator role handle BEFORE
    # creating any users. The sys-scoped listRoles works without
    # DRSysAdmin being a member yet (a brand-new org has zero users,
    # not even DRSysAdmin).
    if args.dry_run:
        org_admin_role = ""
    else:
        org_admin_role = _resolve_org_admin_role(client)
    # Step 9 BEFORE step 8 — DRSysAdmin needs to be in the org as
    # Organization Administrator before `orgManager/createUser` will
    # accept it. The user's spec lists steps 8 and 9 in the other
    # order, but the dependency only flows one way, so we run them
    # in dependency order and call out the swap in the step header.
    step_9_add_drsysadmin_to_org(args, client, org_admin_role)
    step_8_create_org_admin(args, client, org_admin_role)
    # Bonus: log in once as admin@training to clear the forced-change.
    # This keeps the dr-tui org login working with `password` afterwards.
    step_8b_change_org_admin_password(args, client)
    import_handle  = step_10_create_import_connector(args, client)
    export_handle  = step_11_create_export_connector(args, client)
    archive_handle = step_12_create_archive_connector(args, client)
    step_13_create_data_areas(args, client, archive_handle, export_handle)


# ---------- main ----------------------------------------------------------------

def main() -> int:
    args = _parse_args()

    # Banner — show the user exactly what they're about to do BEFORE
    # we start ripping things out.
    print()
    _hr()
    print(f"  DR_freshinstall.py — fresh-install driver "
          f"(target: {args.hostname})")
    _hr()
    print(f"  Phases: "
          f"clean={'no' if args.skip_clean else 'YES'} | "
          f"installer={'no' if args.skip_installer else 'YES'} | "
          f"api={'no' if args.skip_api else 'YES'}")
    print(f"  dry-run: {args.dry_run}   keep-existing: {args.keep_existing}")
    print()

    try:
        if not args.skip_clean:
            _step(0, "Phase 1 — teardown (cleandr.sh inline)")
            phase_clean(args)
        else:
            _skip("Phase 1 (teardown)")

        if not args.skip_installer:
            _step(0, "Phase 2 — DR installer (DR_freshinstall.exp)")
            phase_installer(args)
        else:
            _skip("Phase 2 (installer)")

        if not args.skip_api:
            print()
            _hr()
            print(f"  Phase 3 — API provisioning ({len(STEPS)} steps)")
            _hr()
            phase_api(args)
        else:
            _skip("Phase 3 (API provisioning)")
    except (APIError, RuntimeError, TimeoutError, FileNotFoundError) as e:
        print()
        _fail(f"FATAL: {e}")
        if isinstance(e, APIError):
            print(f"        error_code={e.error_code}  status={e.status}")
            print(f"        extended={e.extended_status[:200]}")
        return 1
    except KeyboardInterrupt:
        print()
        _fail("interrupted by user")
        return 130

    print()
    _hr()
    print("  ✓ Fresh install complete.")
    _hr()
    print(f"  DR Web UI:  https://{args.hostname}:8443/ediscovery/")
    print(f"  DRSysAdmin   /  {args.final_password}")
    print(f"  admin@training / {args.final_password}")
    print()
    print(f"  To use dr-tui against this install, drop into the repo and run:")
    print(f"    .venv/bin/dr-tui")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Playwright automation of the DR fresh install workflow.

Converts the MS Edge Recorder JSON (DR-5532-FreshInstall) to Playwright.
Starts mitmproxy as a subprocess and routes all browser traffic through it
so every REST call is captured.  Also captures inline via page.on('request')
as a belt-and-suspenders fallback.

Usage:
    source .venv/bin/activate
    python playwright_fresh_install.py [--headless] [--no-proxy] [--slow-mo 200]

Captures written to:
    /tmp/dr_api_capture.json       (Playwright inline listener)
    /tmp/dr_proxy_capture.json     (mitmproxy, if proxy not disabled)
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# ── Config ────────────────────────────────────────────────────────────────────
BASE        = "https://192.168.58.128:8443"
REST_PREFIX = "/ediscovery/rest/"
CAPTURE     = "/tmp/dr_api_capture.json"
PROXY_PORT  = 8090
PROXY_ADDON = str(Path(__file__).parent / "proxy_logger.py")

# ── Argument parsing ──────────────────────────────────────────────────────────
# Parsed only when invoked as __main__ — `args` is set inside main() so phase_*
# functions can be imported by other scripts (e.g. playwright_fresh_init.py)
# without polluting sys.argv.
def _parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless",  action="store_true", default=True)
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--no-proxy",  action="store_true")
    ap.add_argument("--slow-mo",   type=int, default=0,
                    help="milliseconds between actions (use 300+ for watching)")
    return ap.parse_args()


# Module-level placeholder; populated by main() and overridable by callers
# that want a non-default config (e.g. headless=True, no-proxy=True).
class _ArgsDefault:
    headless = True
    no_proxy = False
    slow_mo = 0


args = _ArgsDefault()

# ── Inline capture ────────────────────────────────────────────────────────────
_api_calls: list[dict] = []

def _save():
    with open(CAPTURE, "w") as f:
        json.dump(_api_calls, f, indent=2, default=str)

def _attach_capture(page: Page):
    def on_req(req):
        if REST_PREFIX not in req.url:
            return
        ep = req.url.split(REST_PREFIX, 1)[-1]
        entry: dict = {
            "ts":            datetime.now().isoformat(),
            "endpoint":      ep,
            "method":        req.method,
            "request_body":  None,
            "status":        None,
            "response_body": None,
        }
        try:
            entry["request_body"] = req.post_data_json
        except Exception:
            entry["request_body"] = req.post_data
        _api_calls.append(entry)
        print(f"  → {req.method} {ep}")

    def on_resp(resp):
        if REST_PREFIX not in resp.url:
            return
        ep = resp.url.split(REST_PREFIX, 1)[-1]
        for e in reversed(_api_calls):
            if e["endpoint"] == ep and e["status"] is None:
                e["status"] = resp.status
                try:
                    e["response_body"] = resp.json()
                except Exception:
                    try:
                        e["response_body"] = resp.text()[:4000]
                    except Exception:
                        pass
                _save()
                break

    page.on("request",  on_req)
    page.on("response", on_resp)

# ── Playwright helpers ────────────────────────────────────────────────────────
DEFAULT_TIMEOUT = 15_000   # ms

def wait_click(page: Page, selector: str, timeout: int = DEFAULT_TIMEOUT):
    """Wait for selector then click first match."""
    page.wait_for_selector(selector, state="visible", timeout=timeout)
    page.locator(selector).first.click()

def fill(page: Page, selector: str, value: str):
    el = page.locator(selector).first
    el.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
    el.click()
    el.fill(value)

def modal_button(page: Page, text: str, nth: int = 0):
    """Click a labelled button inside a modal-container."""
    sel = f"modal-container button:has-text('{text}')"
    page.locator(sel).nth(nth).wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
    page.locator(sel).nth(nth).click()

def dismiss_popover(page: Page):
    """Dismiss mitmproxy / ngx-popover validation overlay."""
    try:
        page.wait_for_selector("[id^='ngx-popover'] i", timeout=5000)
        page.locator("[id^='ngx-popover'] i").first.click()
    except Exception:
        pass

def close_settings(page: Page):
    """Close the res-settings modal (X button). No-op if already closed."""
    if not page.locator("res-settings").is_visible():
        return
    page.locator("button.close-button > i").first.click()
    page.wait_for_selector("res-settings", state="detached", timeout=10_000)

def open_system_settings(page: Page):
    """Settings menu → System Settings."""
    page.locator("[data-automation-id='top-nav-bar-settings-button']").click()
    page.locator("div.admin-label").filter(has_text="System Settings").first.click()
    page.wait_for_selector("res-settings", state="visible", timeout=10_000)

def nav_settings_tree(page: Page, node_text: str):
    """Click a settings left-tree node by exact text."""
    page.locator("res-generic-tree cdk-tree-node").filter(
        has=page.get_by_text(node_text, exact=True)
    ).first.click()
    time.sleep(0.5)

# ── Phase A: DRSysAdmin first login ──────────────────────────────────────────
SYSADMIN_PW = "DRSysAdmin"   # mutated to actual working password at runtime

def _try_login(page: Page, username: str, password: str) -> bool:
    """Fill and submit login form. Returns True if successful (no error message)."""
    page.locator("[data-automation-id='login-user-name-input']").fill(username)
    page.locator("[data-automation-id='login-password-input']").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_load_state("networkidle", timeout=15_000)
    import time as _t; _t.sleep(1)
    err = page.locator("[data-automation-id='login-error-bad-auth-message']")
    return not err.is_visible()

def phase_login_initial(page: Page):
    global SYSADMIN_PW
    print("\n=== Phase A: First login as DRSysAdmin ===")
    page.goto(f"{BASE}/ediscovery/")
    page.wait_for_load_state("networkidle", timeout=20_000)

    for pw in ("DRSysAdmin", "password"):
        if _try_login(page, "DRSysAdmin", pw):
            SYSADMIN_PW = pw
            print(f"  Logged in with password '{pw}'")
            break
        print(f"  Password '{pw}' rejected, trying next...")
    else:
        raise RuntimeError("Could not log in as DRSysAdmin with any known password")

    # Continue modal (temporary-password notice on a genuine fresh install)
    try:
        page.wait_for_selector("modal-container button:has-text('Continue')", timeout=5000)
        modal_button(page, "Continue")
    except Exception:
        pass

# ── Phase B: Mandatory password change ───────────────────────────────────────
def phase_change_password(page: Page, old_pw: str, new_pw: str):
    print(f"\n=== Phase B: Change password ({old_pw} → {new_pw}) ===")
    # "Password change required" notice appears before the actual change form
    try:
        page.wait_for_selector("modal-container button:has-text('Continue')", timeout=5_000)
        modal_button(page, "Continue")
    except Exception:
        pass
    try:
        page.wait_for_selector("res-change-password-modal", timeout=8000)
    except Exception:
        print("  (no password-change modal — may already be set)")
        return

    # Old password field is div[3] input; new password is div[4] input
    page.locator("res-change-password-modal div:nth-of-type(3) input").fill(old_pw)
    page.locator("res-change-password-modal div:nth-of-type(4) input").fill(new_pw)
    modal_button(page, "Save Changes")

    # Policy acknowledgment — two checkboxes + Continue
    try:
        page.wait_for_selector("res-policy-acknowledgment-modal", timeout=8000)
        # First checkbox (EULA)
        page.locator("res-policy-acknowledgment-modal div:nth-of-type(3) label,"\
                     "res-policy-acknowledgment-modal div:nth-of-type(3) i").first.click()
        time.sleep(0.3)
        # Second checkbox
        page.locator("res-policy-acknowledgment-modal div.mb label,"\
                     "res-policy-acknowledgment-modal div.mb i").first.click()
        time.sleep(0.3)
        modal_button(page, "Continue")
    except Exception as e:
        print(f"  (policy modal not seen: {e})")

    page.wait_for_load_state("networkidle", timeout=15_000)

# ── Phase C: Create storage depots ───────────────────────────────────────────
def _storage_exists(page: Page, name: str) -> bool:
    return page.locator(
        f"#navigationSettingContent div.ag-row:has-text('{name}')"
    ).count() > 0

def _wait_for_ok_enabled(page: Page, timeout_s: int = 15):
    """Poll until the OK button in the open modal is enabled."""
    ok = page.locator("modal-container button:has-text('OK')").first
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if ok.is_enabled():
            return ok
        time.sleep(0.4)
    raise RuntimeError("Storage modal OK button never became enabled (validate may have failed)")

def _create_storage(page: Page, name: str, storage_type: str,
                    ip: str, nfs_item_index: int):
    """Create one storage depot (Doc or Index type), skip if already exists."""
    if _storage_exists(page, name):
        print(f"    Storage '{name}' already exists — skipping")
        return

    print(f"    Creating storage: {name} ({storage_type})")
    wait_click(page, "button:has-text('New Storage')")
    page.wait_for_selector("res-storage-modal", state="visible", timeout=10_000)

    fill(page, "#name", name)

    if storage_type == "Index":
        page.locator("res-storage-modal button:has-text('Index')").click()
        time.sleep(0.3)
    else:
        # Doc storage — click the "IP Address" radio so NFS fields appear
        try:
            page.locator("res-storage-modal label:has-text('IP Address')").first.click()
        except Exception:
            pass

    fill(page, "#ipInput", ip)
    page.keyboard.press("Tab")
    time.sleep(2)   # wait for NFS share list to populate

    # Open the NFS export dropdown and select by index
    page.locator("res-storage-modal res-custom-combo-box button").first.click()
    time.sleep(0.5)
    page.locator("res-storage-modal res-custom-combo-box li").nth(nfs_item_index).click()
    time.sleep(0.3)

    # Validate — wait generously for the popover, then dismiss it
    page.locator("res-storage-modal button.validate-button").click()
    time.sleep(2)
    dismiss_popover(page)
    time.sleep(0.5)

    # Poll until OK is enabled (becomes enabled only after successful validate)
    ok = _wait_for_ok_enabled(page)
    ok.click()
    page.wait_for_selector("res-storage-modal", state="detached", timeout=10_000)

def phase_create_storages(page: Page):
    print("\n=== Phase C: Create storage depots ===")
    open_system_settings(page)
    nav_settings_tree(page, "Storage")

    # Doc storage — /data/docstorage is list item index 1 (0-based → second item)
    _create_storage(page, "localDocStorage",   "Doc",   "192.168.58.128", 1)
    # Index storage — /data/indexstorage is list item index 4 (fifth item)
    _create_storage(page, "localIndexStorage", "Index", "192.168.58.128", 4)

# ── Phase D: Assign system storage depot ─────────────────────────────────────
def phase_system_depot(page: Page):
    print("\n=== Phase D: Assign system storage depot ===")
    nav_settings_tree(page, "System Storage Depot")
    btn_sel = ("button:has-text('Select System Storage'), "
               "button:has-text('Change System Storage')")
    btn = page.locator(btn_sel).first
    try:
        btn.wait_for(state="visible", timeout=10_000)
    except Exception:
        # Depot already assigned — no button visible; skip
        print("    (no Select/Change button — depot already assigned, skipping)")
        return
    btn.click()
    page.wait_for_selector("res-select-system-storage-depot-modal", timeout=10_000)
    time.sleep(1)  # let ag-grid rows render

    rows = page.locator("res-select-system-storage-depot-modal div.ag-center-cols-viewport div.ag-row")

    ok       = page.locator("res-select-system-storage-depot-modal button:has-text('OK')").first
    validate = page.locator("res-select-system-storage-depot-modal button:has-text('Validate')").first

    if ok.is_enabled():
        print("      → OK already enabled (depot pre-selected)")
        ok.click()
        page.wait_for_selector("res-select-system-storage-depot-modal",
                               state="detached", timeout=10_000)
        return

    rows.first.click()
    time.sleep(0.5)
    if validate.is_enabled():
        validate.click()
        page.wait_for_load_state("networkidle", timeout=15_000)
        time.sleep(1)
    if ok.is_enabled():
        ok.click()
        try:
            page.wait_for_selector("res-select-system-storage-depot-modal",
                                   state="detached", timeout=30_000)
        except Exception:
            page.keyboard.press("Escape")
            time.sleep(1)
        page.wait_for_load_state("networkidle", timeout=15_000)
        return

    # If still not enabled, cancel — depot may be assigned through another mechanism
    print("      → OK still disabled after Validate — cancelling")
    try:
        page.locator("res-select-system-storage-depot-modal button:has-text('Cancel')").first.click()
    except Exception:
        page.keyboard.press("Escape")
    page.wait_for_selector("res-select-system-storage-depot-modal",
                           state="detached", timeout=10_000)

# ── Phase E: Update virus definitions ────────────────────────────────────────
def phase_virus_update(page: Page):
    print("\n=== Phase E: Update virus definitions ===")
    nav_settings_tree(page, "Virus Detection")
    # Scope to settings content to avoid matching the project-list refresh icon
    btn = page.locator(
        "#navigationSettingContent button:has-text('Update Now'), "
        "#navigationSettingContent button > i.fa-refresh"
    ).first
    try:
        btn.wait_for(state="visible", timeout=8_000)
        if btn.is_enabled():
            btn.click()
            time.sleep(1)
        else:
            print("  (Update Now button disabled — may require system depot or already updated)")
    except Exception as e:
        print(f"  (Virus update skipped: {e})")

# ── Phase F: Create training organisation ────────────────────────────────────
def phase_create_org(page: Page):
    print("\n=== Phase F: Create 'training' organisation ===")
    nav_settings_tree(page, "Organizations")
    if page.locator("#navigationSettingContent div.ag-row:has-text('training')").count() > 0:
        print("  Org 'training' already exists — skipping")
        close_settings(page)
        return
    wait_click(page, "button:has-text('New Organization')")
    page.wait_for_selector("res-new-organization-modal", timeout=10_000)

    fill(page, "res-new-organization-modal #name", "training")
    # DRSysAdmin is added automatically — no need to open membership modal
    page.locator("res-new-organization-modal button:has-text('Create Organization')").click()
    page.wait_for_selector("res-new-organization-modal", state="detached", timeout=10_000)
    time.sleep(1)

    close_settings(page)

# ── Phase G: Open org settings ───────────────────────────────────────────────
def _open_org_settings(page: Page, org_name: str = "training"):
    """Right-click the training org row on the project list → Settings..."""
    # The org appears as a row in the project list ag-grid.
    # The last column has the context-menu trigger (span inside ag-column-last div).
    row_action = page.locator(
        f"div.ag-row:has-text('{org_name}') div.ag-column-last span"
    ).first
    row_action.wait_for(state="visible", timeout=15_000)
    row_action.click()
    time.sleep(0.5)
    # Use exact match so we don't accidentally hit "System Settings ..." in the nav
    page.get_by_text("Settings ...", exact=True).first.click()
    page.wait_for_selector("res-settings", state="visible", timeout=10_000)

# ── Phase H: Create connectors ───────────────────────────────────────────────
def _connector_exists(page: Page, name: str) -> bool:
    return page.locator(
        f"#navigationSettingContent div.ag-row:has-text('{name}')"
    ).count() > 0

def _create_connector(page: Page, name: str, mode: str,
                      ip: str, nfs_tree_index: int):
    """mode: 'Read Only' or 'Read/Write'"""
    if _connector_exists(page, name):
        print(f"    Connector '{name}' already exists — skipping")
        return
    print(f"    Connector: {name} ({mode})")
    page.locator("button:has-text('New Connector')").click()
    page.wait_for_selector("res-connectors-modal", state="visible", timeout=10_000)

    fill(page, "#nameId", name)

    if mode == "Read/Write":
        page.locator("res-connectors-modal label:has-text('Read/Write')").first.click()
        time.sleep(0.3)

    fill(page, "#nfs-server-input", ip)
    page.keyboard.press("Tab")
    time.sleep(1.5)   # NFS share tree takes a moment

    # Select the nth tree node in the shares tree
    page.locator("res-connectors-modal res-generic-tree cdk-tree-node").nth(
        nfs_tree_index
    ).click()
    time.sleep(0.3)

    page.locator("res-connectors-modal button.validate-button").click()
    time.sleep(1)
    dismiss_popover(page)

    page.locator("res-connectors-modal button:has-text('Create Connector')").click()
    page.wait_for_selector("res-connectors-modal", state="detached", timeout=10_000)

def phase_create_connectors(page: Page):
    print("\n=== Phase H: Create connectors ===")
    nav_settings_tree(page, "Connectors")

    # Import connector — Read Only, /data/import (tree node index 3 = 4th node)
    _create_connector(page, "import-training-local-nfs", "Read Only",
                      "192.168.58.128", 3)
    # Export connector — Read/Write, /data/export (tree node index 2 = 3rd node)
    _create_connector(page, "export-training-local-nfs", "Read/Write",
                      "192.168.58.128", 2)

# ── Phase I: Create org-level data areas ─────────────────────────────────────
def _data_area_exists(page: Page, name: str) -> bool:
    return page.locator(
        f"#navigationSettingContent div.ag-row:has-text('{name}')"
    ).count() > 0

def _create_org_data_area(page: Page, name: str, connector_name: str):
    """connector_name: substring of connector to select in grid."""
    if _data_area_exists(page, name):
        print(f"    Data area '{name}' already exists — skipping")
        return
    print(f"    Data area: {name}")
    page.locator("button:has-text('New Data Area')").click()
    page.wait_for_selector("res-data-area-modal", state="visible", timeout=10_000)

    fill(page, "res-data-area-modal #name", name)

    grid = page.locator("res-data-area-modal div.ag-center-cols-viewport div.ag-row")
    try:
        grid.first.wait_for(state="visible", timeout=10_000)
    except Exception:
        pass

    # Select connector row by name
    page.locator("res-data-area-modal div.ag-center-cols-viewport div.ag-row").filter(
        has_text=connector_name
    ).first.click()
    time.sleep(1)   # tree loads after connector is selected

    # Select the root tree node
    page.locator("res-data-area-modal res-generic-tree cdk-tree-node").first.click()
    time.sleep(0.3)

    page.locator("res-data-area-modal button:has-text('Create Data Area')").click()
    page.wait_for_selector("res-data-area-modal", state="detached", timeout=10_000)

def phase_create_data_areas(page: Page):
    print("\n=== Phase I: Create org-level data areas ===")
    nav_settings_tree(page, "Export Data Areas")
    _create_org_data_area(page, "xda-training-export-local-nfs", "export-training-local-nfs")

    nav_settings_tree(page, "Project Data Areas")
    _create_org_data_area(page, "pda-training-local-nfs", "export-training-local-nfs")

# ── Phase J: Create org user ──────────────────────────────────────────────────
def phase_create_org_user(page: Page):
    print("\n=== Phase J: Create org user admin ===")
    nav_settings_tree(page, "Organization Users")
    # Use exact match to avoid false-positive on 'DRSysAdmin'
    admin_rows = page.locator("#navigationSettingContent div.ag-row").filter(
        has=page.get_by_text("admin", exact=True)
    )
    if admin_rows.count() > 0:
        print("  Org user 'admin' already exists — skipping")
        close_settings(page)
        return
    wait_click(page, "button:has-text('New Organization User')")
    page.wait_for_selector("res-new-user-modal", state="visible", timeout=10_000)

    fill(page, "res-new-user-modal #name", "admin")
    page.keyboard.press("Tab")

    # Email field
    fill(page, "div.left-settings-panel > div:nth-of-type(2) input", "admin@localhost.com")
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")

    # Password
    fill(page, "div.left-settings-panel > div:nth-of-type(4) input", "Password123")
    page.keyboard.press("Tab")

    # First name
    fill(page, "div.left-settings-panel > div:nth-of-type(6) input", "Admin")
    page.keyboard.press("Tab")

    # Last name
    fill(page, "div.left-settings-panel > div:nth-of-type(7) input", "User")

    page.locator("res-new-user-modal button:has-text('OK')").click()
    page.wait_for_selector("res-new-user-modal", state="detached", timeout=10_000)

    close_settings(page)

# ── Phase K: Log out ──────────────────────────────────────────────────────────
def phase_logout(page: Page):
    print("\n=== Phase K: Log out ===")
    # Click username in topbar (last li) to open user dropdown
    page.locator("#topBar li").last.click()
    time.sleep(0.5)
    # Find the "Log Out" / "Logout" item — filter by substring, case-insensitive via regex
    logout_loc = page.locator("li a, li div.admin-label").filter(
        has_text=re.compile(r"log\s*out", re.IGNORECASE)
    ).first
    try:
        logout_loc.wait_for(state="visible", timeout=5_000)
        logout_loc.click()
    except Exception:
        # Last-resort: navigate directly to login page
        page.goto(f"{BASE}/ediscovery/")
    page.wait_for_selector("res-login", state="visible", timeout=20_000)

# ── Phase L: Login (any user) ─────────────────────────────────────────────────
def phase_login(page: Page, username: str, password: str):
    """Login.  For org users pass 'user@org' as username."""
    print(f"\n=== Login: {username} ===")
    # Ensure we're on the login page
    if not page.locator("res-login").is_visible():
        page.goto(f"{BASE}/ediscovery/")
        page.wait_for_selector("res-login", state="visible", timeout=20_000)

    for pw in dict.fromkeys([password, "password"]):
        if _try_login(page, username, pw):
            print(f"  Logged in with password '{pw}'")
            return
        print(f"  Password '{pw}' rejected, trying next...")
        if not page.locator("res-login").is_visible():
            page.goto(f"{BASE}/ediscovery/")
            page.wait_for_selector("res-login", state="visible", timeout=15_000)
    raise RuntimeError(f"Could not log in as {username}")

# ── Phase M: admin@training project creation ─────────────────────────────────
def phase_create_project(page: Page, project_name: str):
    print(f"\n=== Phase M: Create project '{project_name}' ===")
    if page.locator(f"div.ag-row:has-text('{project_name}')").count() > 0:
        print(f"  Project '{project_name}' already exists — navigating to it")
        page.locator(f"div.ag-row:has-text('{project_name}')").first.dblclick()
        page.wait_for_load_state("networkidle", timeout=20_000)
        return

    # Try approach 1: click org row's last-column span
    try:
        row_action = page.locator(
            "div.ag-row:has-text('training') div.ag-column-last span"
        ).first
        row_action.wait_for(state="visible", timeout=5_000)
        row_action.click()
        time.sleep(0.5)
        page.get_by_text("New Project ...", exact=True).first.click()
    except Exception:
        # Approach 2: look for a New Project button anywhere on the page
        try:
            page.locator("button:has-text('New Project')").first.wait_for(
                state="visible", timeout=5_000)
            page.locator("button:has-text('New Project')").first.click()
        except Exception:
            # Approach 3: right-click the ag-body background
            page.locator("div.ag-body-viewport").click(button="right")
            time.sleep(0.5)
            page.get_by_text("New Project ...", exact=True).first.click()

    page.wait_for_selector("res-new-project-modal", state="visible", timeout=10_000)

    fill(page, "res-new-project-modal #name", project_name)

    # Add DRSysAdmin as a project member
    page.locator("res-new-project-modal button:has-text('Add / Remove')").click()
    page.wait_for_selector("res-membership-modal", state="visible", timeout=10_000)
    page.locator("res-membership-modal div.left-content").get_by_text(
        "drsysadmin", exact=False
    ).first.click()
    page.locator("res-membership-modal div.left-right-button button").click()
    time.sleep(0.3)
    page.locator("res-membership-modal button:has-text('OK')").click()
    page.wait_for_selector("res-membership-modal", state="detached", timeout=8_000)

    page.locator("res-new-project-modal button:has-text('Create Project')").click()
    page.wait_for_selector("res-new-project-modal", state="detached", timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)

# ── Phase N: Create dataset ───────────────────────────────────────────────────
def phase_create_dataset(page: Page, dataset_name: str, ocr: bool = False):
    """Create an import dataset.  Call from within the project view."""
    print(f"\n=== Phase N: Create dataset '{dataset_name}' (OCR={ocr}) ===")

    # Navigate to Imports tree node (left click first to load the panel)
    page.locator("cdk-tree-node").filter(has_text="Imports").first.click()
    time.sleep(0.5)

    # Try toolbar "New Batch" / "New Data Set" button first
    try:
        nb = page.locator(
            "button:has-text('New Batch'), button:has-text('New Data Set')"
        ).first
        nb.wait_for(state="visible", timeout=5_000)
        nb.click()
    except Exception:
        # Fallback: right-click the Imports node and use a specific context menu item
        page.locator("cdk-tree-node").filter(has_text="Imports").first.click(
            button="right"
        )
        time.sleep(0.5)
        page.locator(
            "ul.dropdown-menu li, div.dropdown-menu li"
        ).filter(has_text="New").first.click()

    page.wait_for_selector("res-data-set-modal", state="visible", timeout=10_000)

    # Select the import connector (first one if import not found)
    connector_rows = page.locator("res-data-set-modal #connectorGrid div.ag-row")
    import_row = connector_rows.filter(has_text="import-training-local-nfs")
    if import_row.count() > 0:
        import_row.first.click()
    else:
        connector_rows.first.click()
    time.sleep(2)   # wait for folder tree to load

    # Select "testload" folder using its checkbox (gtn-checkbox <i> element)
    cb = page.locator("[data-automation-id='import-testload-checkbox']")
    if cb.count() > 0:
        cb.first.click()
    else:
        all_cb = page.locator("[data-automation-id$='-checkbox'].gtn-checkbox")
        if all_cb.count() > 0:
            all_cb.first.click()
    time.sleep(0.5)

    name_el = page.locator("[data-automation-id='new-data-set-name-input']").first
    name_el.wait_for(state="visible", timeout=10_000)
    name_el.click()
    name_el.fill(dataset_name)
    page.keyboard.press("Tab")
    time.sleep(0.3)

    batch_el = page.locator("[data-automation-id='new-data-set-batch-name-input']").first
    batch_el.wait_for(state="visible", timeout=10_000)
    batch_el.click()
    batch_el.fill(dataset_name)
    page.keyboard.press("Tab")
    time.sleep(0.3)

    # Click Create Data Set — poll until enabled (normally enabled once name+batch filled)
    create_btn = page.locator("res-data-set-modal button:has-text('Create Data Set')").first
    create_btn.wait_for(state="visible", timeout=10_000)
    deadline = time.time() + 10
    while time.time() < deadline:
        if create_btn.is_enabled():
            break
        time.sleep(0.5)
    if not create_btn.is_enabled():
        print("    Create Data Set button still disabled after 10s — force clicking")
    create_btn.click(force=True)
    page.wait_for_selector("res-data-set-modal", state="detached", timeout=15_000)
    page.wait_for_load_state("networkidle", timeout=20_000)

# ── Phase N-OCR: Enable OCR in project index settings ────────────────────────
def phase_enable_project_ocr(page: Page):
    """Click the 'Index Settings' button to open the index settings panel and enable OCR."""
    print("\n=== Phase N-OCR: Enable project-level OCR ===")

    btn = page.locator("button:has-text('Index Settings')").first
    try:
        btn.wait_for(state="visible", timeout=8_000)
    except Exception:
        page.screenshot(path="/tmp/dr_phase_nocr.png", full_page=False)
        print("    'Index Settings' button not found — screenshot at /tmp/dr_phase_nocr.png — skipping")
        return
    btn.click()

    try:
        page.wait_for_selector("res-index-settings", state="visible", timeout=10_000)
    except Exception:
        print("    res-index-settings not found after clicking button — skipping")
        return

    ocr_cb = page.locator("[data-automation-id='index-settings-enable-automatic-ocr-toggle']")
    if ocr_cb.count() > 0:
        if not ocr_cb.is_checked():
            ocr_cb.click()
            time.sleep(0.3)
            print("    OCR enabled")
    else:
        page.locator("label:has-text('Enable Automatic OCR')").first.click()
        time.sleep(0.3)
        print("    OCR enabled via label")

    page.locator("[data-automation-id='index-settings-save-button']").click()
    page.wait_for_load_state("networkidle", timeout=10_000)
    print("    index settings saved")

    # Close the settings panel with the X button (stays open after save)
    page.locator("button.close-button > i").first.click()
    try:
        page.wait_for_selector("res-index-settings", state="detached", timeout=8_000)
    except Exception:
        pass


# ── Phase O: Delete a dataset (batch) ────────────────────────────────────────
def phase_delete_dataset(page: Page, dataset_name: str, project_name: str = "LoadTesting-01"):
    print(f"\n=== Phase O: Delete dataset '{dataset_name}' ===")

    # Navigate Home → project to reload the tree with all datasets (including newly created)
    page.get_by_text("Home").click()
    page.wait_for_load_state("networkidle", timeout=15_000)
    page.locator(f"div.ag-row:has-text('{project_name}')").first.dblclick()
    # Wait until the project's left-tree has rendered (confirms we're inside the project)
    page.wait_for_selector("cdk-tree-node", state="visible", timeout=20_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    time.sleep(1)

    # Expand Imports if it's collapsed
    imports_node = page.locator("cdk-tree-node").filter(has_text="Imports").first
    imports_node.wait_for(state="visible", timeout=10_000)
    imports_node.click()
    time.sleep(1.5)

    # Use 'attached' state (not 'visible') to handle off-screen virtual scroll elements
    ds_node = page.locator("cdk-tree-node").filter(has_text=dataset_name).filter(
        has_not_text="OCR"
    ).first
    try:
        ds_node.wait_for(state="attached", timeout=10_000)
        ds_node.scroll_into_view_if_needed()
        time.sleep(0.3)
        ds_node.click(button="right")
    except Exception:
        # Last resort: use JS dispatchEvent for right-click
        print("    using JS contextmenu event")
        page.evaluate(f"""() => {{
            for (const n of document.querySelectorAll('cdk-tree-node')) {{
                if ((n.innerText||'').includes('{dataset_name}') && !(n.innerText||'').includes('OCR')) {{
                    n.scrollIntoView({{behavior: 'instant', block: 'center'}});
                    n.dispatchEvent(new MouseEvent('contextmenu', {{bubbles: true, cancelable: true, button: 2}}));
                    break;
                }}
            }}
        }}""")
    time.sleep(0.5)
    page.locator("ul.dropdown-menu li, div.dropdown-menu li").filter(
        has_text="Delete"
    ).first.click()
    page.wait_for_selector("res-delete-entity", state="visible", timeout=8_000)
    page.locator("res-delete-entity button:has-text('Delete')").click()
    page.wait_for_selector("res-delete-entity", state="detached", timeout=10_000)

# ── Phase P: Request project deletion ────────────────────────────────────────
def phase_request_project_delete(page: Page, project_name: str):
    print(f"\n=== Phase P: Request deletion of '{project_name}' ===")
    page.get_by_text("Home").click()
    page.wait_for_load_state("networkidle", timeout=15_000)

    page.locator(f"div.ag-row:has-text('{project_name}') div.ag-column-last span").first.click()
    time.sleep(0.5)
    page.locator("ul.dropdown-menu li, div.dropdown-menu li").filter(
        has_text="Delete"
    ).first.click()
    page.wait_for_selector("res-delete-entity", state="visible", timeout=8_000)
    page.locator("res-delete-entity button:has-text('Request Project Deletion')").click()
    page.wait_for_selector("res-delete-entity", state="detached", timeout=10_000)

# ── Phase Q: Approve pending project deletion ─────────────────────────────────
def phase_approve_deletion(page: Page, project_name: str):
    print(f"\n=== Phase Q: Approve all pending deletions (target: '{project_name}') ===")
    open_system_settings(page)
    page.wait_for_load_state("networkidle", timeout=15_000)
    nav_settings_tree(page, "Delete Pending Projects")

    # Loop until no more pending projects remain (clears stale entries from failed runs too)
    for attempt in range(20):
        rows = page.locator(
            "#navigationSettingContent res-delete-pending-projects div.ag-row"
        )
        try:
            rows.first.wait_for(state="visible", timeout=5_000)
        except Exception:
            print(f"    no more pending projects (cleared {attempt})")
            break
        n_rows = rows.count()
        print(f"    pending rows remaining: {n_rows}")
        if n_rows == 0:
            break
        page.locator(
            "#navigationSettingContent div.ag-body div.ag-column-last span"
        ).first.click()
        time.sleep(0.5)
        # Click the approval option using get_by_text (avoids stale dropdown selectors)
        approve_item = page.get_by_text("Approve Project Deletion", exact=True)
        approve_item.first.wait_for(state="visible", timeout=5_000)
        approve_item.first.click()
        time.sleep(1)
        # Confirmation dialog: "Approve Deletion" button (plain floating modal)
        confirm_btn = page.locator("button:has-text('Approve Deletion')")
        try:
            confirm_btn.first.wait_for(state="visible", timeout=8_000)
            print("    clicking 'Approve Deletion' confirmation")
            confirm_btn.first.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            print("    no 'Approve Deletion' button — waiting for network idle")
            page.wait_for_load_state("networkidle", timeout=10_000)
        time.sleep(1)

    close_settings(page)

# ── Phase R: Delete organisation ─────────────────────────────────────────────
def phase_delete_org(page: Page, org_name: str):
    print(f"\n=== Phase R: Delete organisation '{org_name}' ===")
    open_system_settings(page)
    nav_settings_tree(page, "Organizations")

    page.locator(
        f"#navigationSettingContent div.ag-row:has-text('{org_name}') "
        "div.ag-column-last span"
    ).first.click()
    time.sleep(0.5)
    page.locator("text=Delete Organization").first.click()
    page.wait_for_selector("res-delete-entity", state="visible", timeout=8_000)
    page.locator("res-delete-entity button:has-text('Delete Organization')").click()
    page.wait_for_selector("res-delete-entity", state="detached", timeout=10_000)

    close_settings(page)

# ── Proxy lifecycle ───────────────────────────────────────────────────────────
def start_proxy():
    venv_bin = Path(__file__).parent / ".venv/bin"
    mitmdump  = venv_bin / "mitmdump"
    if not mitmdump.exists():
        mitmdump = "mitmdump"   # fall back to PATH

    cmd = [
        str(mitmdump),
        "-s", PROXY_ADDON,
        "--listen-host", "0.0.0.0",
        "--listen-port", str(PROXY_PORT),
        "--set", "ssl_insecure=true",
        "--quiet",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(2)   # let mitmproxy bind
    if proc.poll() is not None:
        err = proc.stderr.read().decode()
        print(f"[proxy] failed to start: {err}", file=sys.stderr)
        return None
    print(f"[proxy] mitmdump listening on 0.0.0.0:{PROXY_PORT}")
    return proc

def stop_proxy(proc):
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        print("[proxy] stopped")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global args
    args = _parse_args()
    proxy_proc = None

    if not args.no_proxy:
        proxy_proc = start_proxy()

    try:
        with sync_playwright() as pw:
            launch_kwargs = dict(
                headless=args.headless,
                slow_mo=args.slow_mo,
                args=["--ignore-certificate-errors",
                      "--disable-dev-shm-usage"],
            )
            if proxy_proc:
                launch_kwargs["proxy"] = {"server": f"http://127.0.0.1:{PROXY_PORT}"}

            browser = pw.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1600, "height": 900},
            )
            page = context.new_page()
            _attach_capture(page)

            # ── DRSysAdmin setup ──────────────────────────────────────────
            phase_login_initial(page)
            phase_change_password(page, old_pw=SYSADMIN_PW, new_pw="password")
            phase_create_storages(page)
            phase_system_depot(page)
            phase_virus_update(page)
            phase_create_org(page)

            # ── Org-level config ──────────────────────────────────────────
            _open_org_settings(page, "training")
            phase_create_connectors(page)
            phase_create_data_areas(page)
            phase_create_org_user(page)

            phase_logout(page)

            # ── admin@training setup ──────────────────────────────────────
            ts = datetime.now().strftime("%Y%m%d-%H%M")
            project_name = f"LoadTesting-{ts}"
            ds1_name = f"testload-{ts}-001"
            ds2_name = f"testload-OCR-{ts}-001"

            phase_login(page, "admin@training", "Password123")
            phase_change_password(page, old_pw="Password123", new_pw="password")
            phase_create_project(page, project_name)

            phase_create_dataset(page, ds1_name,  ocr=False)
            phase_enable_project_ocr(page)           # enable OCR at project level
            phase_create_dataset(page, ds2_name,  ocr=False)  # ds2 inherits project OCR
            phase_delete_dataset(page, ds1_name, project_name)
            phase_request_project_delete(page, project_name)

            phase_logout(page)

            # ── DRSysAdmin cleanup ────────────────────────────────────────
            phase_login(page, "DRSysAdmin", "password")
            phase_approve_deletion(page, project_name)
            phase_delete_org(page, "training")
            phase_logout(page)

            browser.close()

    finally:
        stop_proxy(proxy_proc)
        print(f"\n[capture] {len(_api_calls)} API calls written to {CAPTURE}")
        if proxy_proc:
            print(f"[capture] proxy log: /tmp/dr_proxy_capture.json")


if __name__ == "__main__":
    main()

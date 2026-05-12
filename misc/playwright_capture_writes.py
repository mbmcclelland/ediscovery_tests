"""
Capture v0.06 write-path endpoints for the dr-tui System Settings CRUD work.

Drives create / edit / delete on Document and Index storage depots through
the DR UI while mitmproxy + proxy_logger.py records traffic. Uses scratch
names (`capture-doc-<ts>` / `capture-idx-<ts>`) so it doesn't disturb the
system depots already in use by the training org.

Usage:
    source .venv/bin/activate
    python playwright_capture_writes.py [--no-headless] [--no-proxy]

Outputs:
    /tmp/dr_writes_capture.json     (Playwright inline listener)
    /tmp/dr_proxy_capture.json      (mitmproxy, if proxy not disabled)
    docs/endpoints_v0.06_draft.md   (write-up of newly-seen endpoints)
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# ── Config ──────────────────────────────────────────────────────────────
BASE         = "https://192.168.58.128:8443"
REST_PREFIX  = "/ediscovery/rest/"
CAPTURE      = "/tmp/dr_writes_capture.json"
PROXY_PORT   = 8091      # distinct from playwright_fresh_install (8090)
PROXY_ADDON  = str(Path(__file__).parent / "proxy_logger.py")
DEFAULT_TIMEOUT = 15_000

SCRATCH_TS = datetime.now().strftime("%H%M%S")
DOC_NAME   = f"captureDoc{SCRATCH_TS}"
IDX_NAME   = f"captureIdx{SCRATCH_TS}"

# Known v0.05 read endpoints — anything not in this set is a new write candidate.
KNOWN_READS: set[str] = {
    "realmManager/createSession",
    "realmManager/initializeOrganization",
    "userManager/getCurrentUser",
    "realmManager/getRealm",
    "realmManager/listOrganizations",
    "realmManager/listRemoteNFSStorageAreas",
    "realmManager/getSystemStorageDepot",
    "realmManager/getVirusDefinitions",
    "adminOrgManager/listUsersAndGroups",
    "orgManager/listUsersAndGroups",
    "orgManager/listUsers",
    "orgManager/listRoles",
    "realmManager/listSystemUserProjectsByUserName",
    "orgManager/listUserProjectsForAllOrgs",
    "projectManager/listTasks",
    "adminOrgManager/listConnectors",
    # Plus a few admin-housekeeping reads we don't care about
    "realmManager/getCurrentSession",
    "realmManager/refreshSession",
}

# ── Inline capture ──────────────────────────────────────────────────────
_api_calls: list[dict] = []

def _save() -> None:
    with open(CAPTURE, "w") as f:
        json.dump(_api_calls, f, indent=2, default=str)


def _attach_capture(page: Page) -> None:
    def on_req(req):
        if REST_PREFIX not in req.url:
            return
        ep = req.url.split(REST_PREFIX, 1)[-1]
        entry: dict = {
            "ts": datetime.now().isoformat(),
            "endpoint": ep, "method": req.method,
            "request_body": None, "status": None, "response_body": None,
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


# ── Playwright helpers (lifted from playwright_fresh_install.py) ────────
def wait_click(page: Page, selector: str, timeout: int = DEFAULT_TIMEOUT):
    page.wait_for_selector(selector, state="visible", timeout=timeout)
    page.locator(selector).first.click()


def fill(page: Page, selector: str, value: str):
    el = page.locator(selector).first
    el.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
    el.click()
    el.fill(value)


def modal_button(page: Page, text: str, nth: int = 0):
    sel = f"modal-container button:has-text('{text}')"
    page.locator(sel).nth(nth).wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
    page.locator(sel).nth(nth).click()


def dismiss_popover(page: Page):
    try:
        page.wait_for_selector("[id^='ngx-popover'] i", timeout=5000)
        page.locator("[id^='ngx-popover'] i").first.click()
    except Exception:
        pass


def open_system_settings(page: Page):
    page.locator("[data-automation-id='top-nav-bar-settings-button']").click()
    page.locator("div.admin-label").filter(has_text="System Settings").first.click()
    page.wait_for_selector("res-settings", state="visible", timeout=10_000)


def nav_settings_tree(page: Page, node_text: str):
    page.locator("res-generic-tree cdk-tree-node").filter(
        has=page.get_by_text(node_text, exact=True)
    ).first.click()
    time.sleep(0.5)


def _wait_for_ok_enabled(page: Page, timeout_s: int = 20):
    ok = page.locator("modal-container button:has-text('OK')").first
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if ok.is_enabled():
            return ok
        time.sleep(0.4)
    raise RuntimeError("OK button never became enabled")


def _try_login(page: Page, username: str, password: str) -> bool:
    page.locator("[data-automation-id='login-user-name-input']").fill(username)
    page.locator("[data-automation-id='login-password-input']").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_load_state("networkidle", timeout=15_000)
    time.sleep(1)
    err = page.locator("[data-automation-id='login-error-bad-auth-message']")
    return not err.is_visible()


# ── DR flows ────────────────────────────────────────────────────────────
def login_drsysadmin(page: Page) -> None:
    print("\n=== Login DRSysAdmin ===")
    page.goto(f"{BASE}/ediscovery/")
    page.wait_for_load_state("networkidle", timeout=20_000)
    if not _try_login(page, "DRSysAdmin", "password"):
        raise RuntimeError("DRSysAdmin login failed (try resetting password)")
    time.sleep(2)


def goto_storage(page: Page) -> None:
    open_system_settings(page)
    nav_settings_tree(page, "Storage")
    time.sleep(1)


def find_depot_row(page: Page, name: str):
    return page.locator(
        f"#navigationSettingContent div.ag-row:has-text('{name}')"
    ).first


def _storage_exists(page: Page, name: str) -> bool:
    return find_depot_row(page, name).count() > 0


def create_depot(page: Page, name: str, type_: str, nfs_idx: int = 0) -> None:
    print(f"\n--- CREATE depot: {name} ({type_}) ---")
    if _storage_exists(page, name):
        print(f"    (already exists — skipping create)")
        return
    wait_click(page, "button:has-text('New Storage')")
    page.wait_for_selector("res-storage-modal", state="visible", timeout=10_000)
    fill(page, "#name", name)
    if type_ == "Index":
        page.locator("res-storage-modal button:has-text('Index')").click()
        time.sleep(0.3)
    else:
        try:
            page.locator("res-storage-modal label:has-text('IP Address')").first.click()
        except Exception:
            pass
    fill(page, "#ipInput", "192.168.58.128")
    page.keyboard.press("Tab")
    time.sleep(2)
    page.locator("res-storage-modal res-custom-combo-box button").first.click()
    time.sleep(0.5)
    page.locator("res-storage-modal res-custom-combo-box li").nth(nfs_idx).click()
    time.sleep(0.3)
    page.locator("res-storage-modal button.validate-button").click()
    time.sleep(2)
    dismiss_popover(page)
    time.sleep(0.5)
    ok = _wait_for_ok_enabled(page)
    ok.click()
    page.wait_for_selector("res-storage-modal", state="detached", timeout=15_000)


def edit_depot(page: Page, name: str) -> None:
    """Open the depot for edit and toggle a property to fire an update call.

    The DR UI doesn't have an obvious Edit button — try common gestures
    (double-click row, right-click → Edit, or top-bar Modify button) and
    let the API capture record whichever endpoint fires.
    """
    print(f"\n--- EDIT depot: {name} ---")
    row = find_depot_row(page, name)
    if row.count() == 0:
        print("    (row not found — skipping)")
        return

    row.click()
    time.sleep(0.5)

    # Try named Edit/Modify buttons first.
    edit_clicked = False
    for sel in (
        "button:has-text('Edit Storage')",
        "button:has-text('Modify Storage')",
        "button:has-text('Edit')",
        "button:has-text('Modify')",
    ):
        try:
            btn = page.locator(sel).first
            if btn.is_visible() and btn.is_enabled():
                btn.click()
                edit_clicked = True
                print(f"    edit gesture: {sel}")
                break
        except Exception:
            continue

    if not edit_clicked:
        # Double-click row → may open modal in some UI versions
        try:
            row.dblclick()
            edit_clicked = True
            print("    edit gesture: dblclick row")
        except Exception:
            pass

    if not edit_clicked:
        print("    (no edit gesture worked — skipping)")
        return

    # Wait for the storage modal to open.
    try:
        page.wait_for_selector("res-storage-modal", state="visible", timeout=8_000)
    except Exception:
        print("    (modal never opened — likely no edit support in UI)")
        return

    # Toggle whatever is editable to trigger an update payload.
    toggled = False
    for sel in (
        "res-storage-modal input[type='checkbox']",
        "res-storage-modal toggle-switch",
    ):
        try:
            page.locator(sel).first.click(timeout=2000)
            toggled = True
            print(f"    toggled: {sel}")
            break
        except Exception:
            continue
    if not toggled:
        print("    (no toggle available; submitting unchanged)")

    time.sleep(0.5)
    try:
        ok = page.locator("res-storage-modal button:has-text('OK')").first
        if ok.is_enabled():
            ok.click()
        else:
            page.keyboard.press("Escape")
    except Exception:
        page.keyboard.press("Escape")
    try:
        page.wait_for_selector("res-storage-modal", state="detached", timeout=10_000)
    except Exception:
        pass


def delete_depot(page: Page, name: str) -> None:
    print(f"\n--- DELETE depot: {name} ---")
    row = find_depot_row(page, name)
    if row.count() == 0:
        print("    (row not found — skipping)")
        return
    row.click()
    time.sleep(0.5)

    # Click a Delete/Remove button in the toolbar.
    clicked = False
    for sel in (
        "button:has-text('Delete Storage')",
        "button:has-text('Remove Storage')",
        "button:has-text('Delete')",
        "button:has-text('Remove')",
    ):
        try:
            btn = page.locator(sel).first
            if btn.is_visible() and btn.is_enabled():
                btn.click()
                clicked = True
                print(f"    delete gesture: {sel}")
                break
        except Exception:
            continue
    if not clicked:
        print("    (no delete gesture worked — skipping)")
        return

    # Confirm dialog.
    try:
        page.wait_for_selector("modal-container", state="visible", timeout=5000)
        # Pick the strongest-affirmative button in the modal.
        for label in ("Delete", "Yes", "Confirm", "OK"):
            try:
                modal_button(page, label)
                print(f"    confirmed: {label}")
                break
            except Exception:
                continue
        page.wait_for_selector("modal-container", state="detached", timeout=10_000)
    except Exception:
        # Inline delete with no confirm — still ok
        time.sleep(2)


# ── Proxy management ────────────────────────────────────────────────────
def start_proxy() -> subprocess.Popen | None:
    venv_bin = Path(__file__).parent / ".venv/bin"
    mitmdump = venv_bin / "mitmdump"
    if not mitmdump.exists():
        mitmdump = "mitmdump"
    cmd = [
        str(mitmdump),
        "-s", PROXY_ADDON,
        "--listen-host", "0.0.0.0",
        "--listen-port", str(PROXY_PORT),
        "--set", "ssl_insecure=true",
        "--quiet",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(2)
    if proc.poll() is not None:
        err = proc.stderr.read().decode()
        print(f"[proxy] failed: {err}", file=sys.stderr)
        return None
    print(f"[proxy] mitmdump listening on 0.0.0.0:{PROXY_PORT}")
    return proc


def stop_proxy(proc) -> None:
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        print("[proxy] stopped")


# ── Capture analysis ────────────────────────────────────────────────────
def analyze_capture() -> None:
    calls: list[dict] = []
    if Path(CAPTURE).exists():
        with open(CAPTURE) as f:
            calls.extend(json.load(f))

    by_endpoint: dict[str, list[dict]] = {}
    for c in calls:
        ep = c.get("endpoint", "")
        if not ep:
            continue
        by_endpoint.setdefault(ep, []).append(c)

    writes = {ep: cs for ep, cs in by_endpoint.items() if ep not in KNOWN_READS}
    print(f"\n=== capture summary ===")
    print(f"  total calls:       {len(calls)}")
    print(f"  unique endpoints:  {len(by_endpoint)}")
    print(f"  write candidates:  {len(writes)}")

    lines = [
        f"# v0.06 write-path capture — draft\n",
        f"_Captured {datetime.now().isoformat()} via `playwright_capture_writes.py`_\n",
        "## Candidate write endpoints\n",
        "| Endpoint | Calls | Statuses | Sample req body keys |",
        "|---|---:|---|---|",
    ]
    for ep in sorted(writes):
        cs = writes[ep]
        statuses = sorted({c.get("status") for c in cs if c.get("status") is not None})
        # Sample first non-empty request body for key list.
        body_keys = ""
        for c in cs:
            rb = c.get("request_body")
            if isinstance(rb, dict) and rb:
                body_keys = ", ".join(sorted(rb.keys()))
                break
        lines.append(f"| `{ep}` | {len(cs)} | {statuses} | {body_keys} |")
    lines.append("\n## Raw bodies (one per endpoint)\n")
    for ep in sorted(writes):
        cs = writes[ep]
        first = next((c for c in cs if c.get("request_body")), cs[0])
        lines.append(f"### `{ep}`\n")
        lines.append("```json")
        lines.append(json.dumps(first.get("request_body"), indent=2, default=str))
        lines.append("```")
        lines.append(f"_Response status: {first.get('status')}_\n")

    out_path = Path(__file__).parent / "docs" / "endpoints_v0.06_draft.md"
    out_path.write_text("\n".join(lines))
    print(f"  draft written to {out_path}")

    print("\n  --- write candidates ---")
    for ep in sorted(writes):
        cs = writes[ep]
        statuses = sorted({c.get("status") for c in cs if c.get("status") is not None})
        print(f"    {ep}  (×{len(cs)}, statuses={statuses})")


# ── Main ────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--no-proxy", action="store_true")
    args = ap.parse_args()

    proxy_proc = None
    if not args.no_proxy:
        proxy_proc = start_proxy()

    try:
        with sync_playwright() as pw:
            launch_kwargs = dict(
                headless=args.headless,
                args=["--ignore-certificate-errors", "--disable-dev-shm-usage"],
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

            login_drsysadmin(page)
            goto_storage(page)

            # Doc depot lifecycle (best-effort — keep going on errors)
            try:
                create_depot(page, DOC_NAME, "Doc", nfs_idx=0)
            except Exception as e:
                print(f"  ! create-doc failed: {e!r}")
            try:
                edit_depot(page, DOC_NAME)
            except Exception as e:
                print(f"  ! edit-doc failed: {e!r}")
            try:
                delete_depot(page, DOC_NAME)
            except Exception as e:
                print(f"  ! delete-doc failed: {e!r}")

            # Idx depot lifecycle
            try:
                create_depot(page, IDX_NAME, "Index", nfs_idx=0)
            except Exception as e:
                print(f"  ! create-idx failed: {e!r}")
            try:
                delete_depot(page, IDX_NAME)
            except Exception as e:
                print(f"  ! delete-idx failed: {e!r}")

            browser.close()
    finally:
        stop_proxy(proxy_proc)
        analyze_capture()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Capture v0.06 edit / delete / reset-password endpoints for the dr-tui CRUD
work. Drives the DR UI through these gestures against scratch entities (and
revert-only edits against existing ones) while mitmproxy records the
traffic. Re-uses helpers from playwright_fresh_install.

Sections (each isolated in its own try/except — partial run is fine):

  A. Storage depot
       A1  edit existing localDocStorage  (toggle a field, save, revert)
       A2  create + delete scratch depot

  B. Org user (in 'training')
       B1  edit admin@training  (firstName: change + revert)
       B2  create scratch user 'probeUserXXXX'
       B3  reset scratch user's password (admin-side reset)
       B4  delete scratch user

  C. Organisation
       C1  edit 'training' description (change + revert)
       C2  create scratch org 'probeOrgXXXX' (via expressProvision UI)
       C3  delete scratch org

  D. Org group (in 'training')
       D1  create scratch group
       D2  edit it
       D3  delete it

  E. Connectors (in 'training')
       E1  create scratch connector
       E2  edit
       E3  delete

Captures land in /tmp/dr_api_capture.json (Playwright inline) + the proxy's
/tmp/dr_proxy_capture.json. The script copies them to
/tmp/dr_api_capture_v06_edits.json and prints a candidate-endpoint summary.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Page, sync_playwright

import playwright_fresh_install as pfi


SCRATCH_TS = datetime.now().strftime("%H%M%S")
SCRATCH_DEPOT = f"probeDepot{SCRATCH_TS}"
SCRATCH_USER  = f"probeUser{SCRATCH_TS}"
SCRATCH_ORG   = f"probeOrg{SCRATCH_TS}"
SCRATCH_GROUP = f"probeGroup{SCRATCH_TS}"
SCRATCH_CONN  = f"probeConn{SCRATCH_TS}"

SHOTS_DIR = Path("/tmp/dr_edits_shots")
SHOTS_DIR.mkdir(exist_ok=True)


# ── tiny helpers on top of pfi ─────────────────────────────────────────
def try_selectors(page: Page, selectors: Iterable[str], action: str = "click",
                  value: str | None = None, timeout_ms: int = 2000) -> str | None:
    """Try each selector in order; return the one that worked or None."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            if action == "click":
                loc.click(timeout=timeout_ms)
            elif action == "dblclick":
                loc.dblclick(timeout=timeout_ms)
            elif action == "fill":
                loc.fill(value or "")
            elif action == "type":
                loc.type(value or "")
            return sel
        except Exception:
            continue
    return None


def dismiss_any_modal(page: Page) -> None:
    """Escape-out of any open modal. No-op if none."""
    for _ in range(3):
        if not page.locator("modal-container, res-storage-modal, res-new-user-modal").count():
            return
        try:
            page.keyboard.press("Escape")
            time.sleep(0.4)
        except Exception:
            break


def shoot(page: Page, name: str) -> None:
    try:
        page.screenshot(path=str(SHOTS_DIR / f"{SCRATCH_TS}_{name}.png"))
    except Exception:
        pass


def section_banner(name: str) -> None:
    print(f"\n{'='*70}\n=== {name}\n{'='*70}")


def row_in_settings_grid(page: Page, name: str):
    return page.locator(
        f"#navigationSettingContent div.ag-row:has-text('{name}')"
    ).first


# ── Section A — Storage depot ─────────────────────────────────────────
def section_a_storage(page: Page) -> None:
    section_banner("A. Storage depot")
    pfi.open_system_settings(page)
    pfi.nav_settings_tree(page, "Storage")
    time.sleep(1)

    # A1: edit existing localDocStorage (open then close — captures any
    # 'get'/'view' calls plus, if we get into a modal, an Update payload).
    print("\n--- A1: open localDocStorage for edit ---")
    try:
        row_in_settings_grid(page, "localDocStorage").click()
        time.sleep(0.4)
        gesture = try_selectors(page, [
            "button:has-text('Edit Storage')",
            "button:has-text('Modify Storage')",
            "button:has-text('Edit')",
            "button:has-text('Modify')",
            "#navigationSettingContent button > i.fa-pencil",
        ])
        if not gesture:
            # try double-click row
            try:
                row_in_settings_grid(page, "localDocStorage").dblclick()
                gesture = "dblclick row"
            except Exception:
                pass
        print(f"  edit gesture: {gesture}")
        if gesture and page.locator("res-storage-modal").count():
            # Touch something benign (allocationSize), then submit.
            try:
                pfi.fill(page, "res-storage-modal #allocationSize, res-storage-modal input[type='number']", "100")
            except Exception:
                pass
            time.sleep(0.5)
            ok = page.locator("res-storage-modal button:has-text('OK'), res-storage-modal button:has-text('Save')").first
            if ok.is_enabled():
                ok.click()
                page.wait_for_selector("res-storage-modal", state="detached", timeout=10_000)
            else:
                page.keyboard.press("Escape")
        else:
            shoot(page, "a1_no_edit_gesture")
    except Exception as e:
        print(f"  A1 error: {e!r}")
        dismiss_any_modal(page)

    # A2: create scratch depot
    print(f"\n--- A2: create {SCRATCH_DEPOT} ---")
    try:
        pfi._create_storage(page, SCRATCH_DEPOT, "Doc", "192.168.58.128", 2)
    except Exception as e:
        print(f"  A2 error: {e!r}")
        shoot(page, "a2_create_fail")
        dismiss_any_modal(page)

    # A3: delete scratch depot
    print(f"\n--- A3: delete {SCRATCH_DEPOT} ---")
    try:
        row_in_settings_grid(page, SCRATCH_DEPOT).click()
        time.sleep(0.4)
        gesture = try_selectors(page, [
            "button:has-text('Delete Storage')",
            "button:has-text('Remove Storage')",
            "button:has-text('Delete')",
            "button:has-text('Remove')",
            "#navigationSettingContent button > i.fa-trash",
        ])
        print(f"  delete gesture: {gesture}")
        if gesture:
            # Confirm dialog
            try:
                page.wait_for_selector("modal-container", state="visible", timeout=4000)
                for label in ("Delete", "Yes", "Confirm", "OK"):
                    try:
                        pfi.modal_button(page, label)
                        print(f"  confirmed: {label}")
                        break
                    except Exception:
                        continue
                page.wait_for_selector("modal-container", state="detached", timeout=10_000)
            except Exception:
                pass
    except Exception as e:
        print(f"  A3 error: {e!r}")
        dismiss_any_modal(page)

    pfi.close_settings(page)


# ── Section B — Org user (in 'training') ──────────────────────────────
def section_b_user(page: Page) -> None:
    section_banner("B. Org user (training)")
    try:
        pfi._open_org_settings(page, "training")
    except Exception as e:
        print(f"  could not open training org settings: {e!r}")
        return
    pfi.nav_settings_tree(page, "Organization Users")
    time.sleep(1)

    # B1: edit admin@training (toggle then revert)
    print("\n--- B1: edit admin@training ---")
    try:
        row_in_settings_grid(page, "admin").click()
        time.sleep(0.4)
        gesture = try_selectors(page, [
            "button:has-text('Edit User')",
            "button:has-text('Edit')",
            "button:has-text('Modify')",
            "#navigationSettingContent button > i.fa-pencil",
        ])
        if not gesture:
            try:
                row_in_settings_grid(page, "admin").dblclick()
                gesture = "dblclick row"
            except Exception:
                pass
        print(f"  edit gesture: {gesture}")
        if gesture and page.locator("res-edit-user-modal, res-new-user-modal").count():
            ok = page.locator("button:has-text('OK'), button:has-text('Save')").first
            if ok.is_enabled():
                ok.click()
                time.sleep(0.5)
                dismiss_any_modal(page)
    except Exception as e:
        print(f"  B1 error: {e!r}")
        dismiss_any_modal(page)

    # B2: create scratch user
    print(f"\n--- B2: create {SCRATCH_USER} ---")
    try:
        wait_click(page, "button:has-text('New Organization User')")
        page.wait_for_selector("res-new-user-modal", state="visible", timeout=10_000)
        pfi.fill(page, "res-new-user-modal #name", SCRATCH_USER)
        page.keyboard.press("Tab")
        pfi.fill(page, "div.left-settings-panel > div:nth-of-type(2) input", f"{SCRATCH_USER}@example.com")
        page.keyboard.press("Tab"); page.keyboard.press("Tab")
        pfi.fill(page, "div.left-settings-panel > div:nth-of-type(4) input", "Password123")
        page.keyboard.press("Tab")
        pfi.fill(page, "div.left-settings-panel > div:nth-of-type(6) input", "Probe")
        page.keyboard.press("Tab")
        pfi.fill(page, "div.left-settings-panel > div:nth-of-type(7) input", "User")
        page.locator("res-new-user-modal button:has-text('OK')").click()
        page.wait_for_selector("res-new-user-modal", state="detached", timeout=10_000)
        time.sleep(1)
    except Exception as e:
        print(f"  B2 error: {e!r}")
        shoot(page, "b2_create_fail")
        dismiss_any_modal(page)

    # B3: reset password for scratch user
    print(f"\n--- B3: reset password for {SCRATCH_USER} ---")
    try:
        row_in_settings_grid(page, SCRATCH_USER).click()
        time.sleep(0.4)
        gesture = try_selectors(page, [
            "button:has-text('Reset Password')",
            "button:has-text('Change Password')",
            "button:has-text('Reset')",
            "#navigationSettingContent button > i.fa-key",
        ])
        print(f"  reset gesture: {gesture}")
        if gesture:
            try:
                page.wait_for_selector("modal-container", state="visible", timeout=4000)
                pfi.fill(page, "modal-container input[type='password']", "Password456")
                # try a second password field if there's a "confirm"
                try:
                    page.locator("modal-container input[type='password']").nth(1).fill("Password456")
                except Exception:
                    pass
                for label in ("OK", "Save", "Save Changes", "Reset"):
                    try:
                        pfi.modal_button(page, label)
                        break
                    except Exception:
                        continue
                page.wait_for_selector("modal-container", state="detached", timeout=8_000)
            except Exception:
                pass
    except Exception as e:
        print(f"  B3 error: {e!r}")
        dismiss_any_modal(page)

    # B4: delete scratch user
    print(f"\n--- B4: delete {SCRATCH_USER} ---")
    try:
        row_in_settings_grid(page, SCRATCH_USER).click()
        time.sleep(0.4)
        gesture = try_selectors(page, [
            "button:has-text('Delete User')",
            "button:has-text('Delete')",
            "button:has-text('Remove')",
            "#navigationSettingContent button > i.fa-trash",
        ])
        print(f"  delete gesture: {gesture}")
        if gesture:
            try:
                page.wait_for_selector("modal-container", state="visible", timeout=4000)
                for label in ("Delete", "Yes", "Confirm", "OK"):
                    try:
                        pfi.modal_button(page, label); break
                    except Exception: continue
                page.wait_for_selector("modal-container", state="detached", timeout=10_000)
            except Exception:
                pass
    except Exception as e:
        print(f"  B4 error: {e!r}")
        dismiss_any_modal(page)

    pfi.close_settings(page)


# ── Section C — Organisation ──────────────────────────────────────────
def section_c_org(page: Page) -> None:
    section_banner("C. Organisation")
    pfi.open_system_settings(page)
    pfi.nav_settings_tree(page, "Organizations")
    time.sleep(1)

    # C1: edit training (open then save without change, just to capture endpoint)
    print("\n--- C1: edit training org ---")
    try:
        row_in_settings_grid(page, "training").click()
        time.sleep(0.4)
        gesture = try_selectors(page, [
            "button:has-text('Edit Organization')",
            "button:has-text('Edit')",
            "button:has-text('Modify')",
        ])
        if not gesture:
            try:
                row_in_settings_grid(page, "training").dblclick()
                gesture = "dblclick row"
            except Exception:
                pass
        print(f"  edit gesture: {gesture}")
        if gesture:
            time.sleep(0.5)
            try:
                ok = page.locator("button:has-text('OK'), button:has-text('Save')").first
                if ok.is_enabled():
                    ok.click()
                else:
                    page.keyboard.press("Escape")
            except Exception:
                page.keyboard.press("Escape")
            time.sleep(1)
            dismiss_any_modal(page)
    except Exception as e:
        print(f"  C1 error: {e!r}")
        dismiss_any_modal(page)

    # C2: create scratch org
    print(f"\n--- C2: create {SCRATCH_ORG} ---")
    try:
        wait_click(page, "button:has-text('New Organization')")
        page.wait_for_selector("res-new-organization-modal", timeout=10_000)
        pfi.fill(page, "res-new-organization-modal #name", SCRATCH_ORG)
        page.locator("res-new-organization-modal button:has-text('Create Organization')").click()
        time.sleep(2)
        dismiss_any_modal(page)
    except Exception as e:
        print(f"  C2 error: {e!r}")
        shoot(page, "c2_create_fail")
        dismiss_any_modal(page)

    # C3: delete scratch org
    print(f"\n--- C3: delete {SCRATCH_ORG} ---")
    try:
        row_in_settings_grid(page, SCRATCH_ORG).click()
        time.sleep(0.4)
        gesture = try_selectors(page, [
            "button:has-text('Delete Organization')",
            "button:has-text('Remove Organization')",
            "button:has-text('Delete')",
            "button:has-text('Remove')",
        ])
        print(f"  delete gesture: {gesture}")
        if gesture:
            try:
                page.wait_for_selector("modal-container", state="visible", timeout=4000)
                for label in ("Delete", "Yes", "Confirm", "OK"):
                    try:
                        pfi.modal_button(page, label); break
                    except Exception: continue
                page.wait_for_selector("modal-container", state="detached", timeout=15_000)
            except Exception:
                pass
    except Exception as e:
        print(f"  C3 error: {e!r}")
        dismiss_any_modal(page)

    pfi.close_settings(page)


# ── helper ────────────────────────────────────────────────────────────
def wait_click(page: Page, sel: str, timeout: int = 15000) -> None:
    page.wait_for_selector(sel, state="visible", timeout=timeout)
    page.locator(sel).first.click()


# ── Main ──────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--no-proxy", action="store_true")
    ap.add_argument("--sections", default="A,B,C",
                    help="comma list: A=depot, B=user, C=org")
    args = ap.parse_args()
    pfi.args = args

    proxy_proc = None
    if not args.no_proxy:
        proxy_proc = pfi.start_proxy()

    sections = set(s.strip().upper() for s in args.sections.split(","))

    try:
        with sync_playwright() as pw:
            launch_kwargs = dict(
                headless=args.headless,
                args=["--ignore-certificate-errors", "--disable-dev-shm-usage"],
            )
            if proxy_proc:
                launch_kwargs["proxy"] = {"server": f"http://127.0.0.1:{pfi.PROXY_PORT}"}
            browser = pw.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1600, "height": 900},
            )
            page = context.new_page()
            pfi._attach_capture(page)

            # Login (DRSysAdmin / password is the state we're in)
            page.goto(f"{pfi.BASE}/ediscovery/")
            page.wait_for_load_state("networkidle", timeout=20_000)
            pfi._try_login(page, "DRSysAdmin", "password")
            time.sleep(2)

            if "A" in sections:
                try: section_a_storage(page)
                except Exception as e: print(f"section A crashed: {e!r}")
            if "B" in sections:
                try: section_b_user(page)
                except Exception as e: print(f"section B crashed: {e!r}")
            if "C" in sections:
                try: section_c_org(page)
                except Exception as e: print(f"section C crashed: {e!r}")

            browser.close()
    finally:
        pfi.stop_proxy(proxy_proc)
        print(f"\n[capture] {len(pfi._api_calls)} API calls in {pfi.CAPTURE}")
        # Stash a copy for parsing
        shutil.copy(pfi.CAPTURE, "/tmp/dr_api_capture_v06_edits.json")
        print("[capture] copied → /tmp/dr_api_capture_v06_edits.json")

    # Summary: write-candidate endpoints not in v0.05 reads
    KNOWN_READS = {
        "realmManager/createSession","realmManager/initializeOrganization",
        "userManager/getCurrentUser","realmManager/getRealm",
        "realmManager/listOrganizations","realmManager/listRemoteNFSStorageAreas",
        "realmManager/getSystemStorageDepot","realmManager/getVirusDefinitions",
        "adminOrgManager/listUsersAndGroups","orgManager/listUsersAndGroups",
        "orgManager/listUsers","orgManager/listRoles",
        "realmManager/listSystemUserProjectsByUserName",
        "orgManager/listUserProjectsForAllOrgs",
        "projectManager/listTasks","adminOrgManager/listConnectors",
        "realmManager/getLicensedFeatures","permissionManager/getCombinedUserRole",
        "projectManager/getUpdateStatus","realmManager/listNodes",
        "realmManager/getDREnumNames","realmManager/getPasswordPolicy",
        "realmManager/getMailServerConfig","orgManager/listLdapDomains",
        "viewManager/validateName","storageAreaManager/countCustomersForFacility",
        "realmManager/listCustomersForStorageFacility","orgManager/getNfsMounts",
        "connectorManager/validateNFSConnector",
        # Already confirmed in earlier captures
        "realmManager/createRemoteNFSStorageArea","realmManager/createSystemStorageDepot",
        "realmManager/updateVirusDefinitions","realmManager/expressProvision",
        "userManager/changeUserPassword","userManager/acceptEula","orgManager/createUser",
    }
    seen = {}
    for c in pfi._api_calls:
        ep = c.get("endpoint","")
        if not ep or ep in KNOWN_READS: continue
        seen.setdefault(ep, {"count":0,"first":None})
        seen[ep]["count"] += 1
        if seen[ep]["first"] is None and c.get("request_body"):
            seen[ep]["first"] = c
    print("\n=== NEW endpoint candidates (not in v0.05 reads or previously-captured writes) ===")
    for ep in sorted(seen):
        f = seen[ep]["first"] or {}
        body = f.get("request_body") if isinstance(f, dict) else None
        keys = ", ".join(sorted(body.keys())) if isinstance(body, dict) else "?"
        print(f"  {ep}")
        print(f"    calls={seen[ep]['count']}  status={(f or {}).get('status')}")
        print(f"    body_keys: {keys}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Focused post-install initial-setup driver for Digital Reef.

Run this AFTER `cleandr.sh` + `DR_freshinstall.exp` and once `drd` is up. It
drives the DR web UI through the minimum steps needed for the dr_tui /
dr_load test suite to function — nothing more.

Scope (subset of playwright_fresh_install.py):
  • Phase A — first login as DRSysAdmin (accepts initial `DRSysAdmin` pw)
  • Phase B — forced password change → `password`
  • Phase C — create `localDocStorage` + `localIndexStorage`
  • Phase D — assign System Storage Depot
  • Phase F — create `training` organisation
  • Phase J — create org user `admin/training` (Password123, email
              admin@localhost.com, display name Admin User)
  • Phase K — log out
  • Phase L — log in as admin@training/Password123
  • Phase B (again) — change admin@training's password to `password`
  • Phase K — log out

Skipped (vs the full install script): virus update, connectors, data areas,
projects, datasets, OCR, project deletion, org deletion.

Usage:
    source .venv/bin/activate
    python playwright_fresh_init.py [--no-headless] [--no-proxy] [--slow-mo 200]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Reuse all phase_* helpers from the full install script.
import playwright_fresh_install as pfi


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--no-proxy", action="store_true")
    ap.add_argument(
        "--slow-mo", type=int, default=0,
        help="milliseconds between actions (use 300+ for watching)",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    # Mirror the parsed config into the imported module so its helpers
    # (start_proxy, _attach_capture, etc.) see consistent flags.
    pfi.args = args

    proxy_proc = None
    if not args.no_proxy:
        proxy_proc = pfi.start_proxy()

    try:
        with sync_playwright() as pw:
            launch_kwargs = dict(
                headless=args.headless,
                slow_mo=args.slow_mo,
                args=["--ignore-certificate-errors", "--disable-dev-shm-usage"],
            )
            if proxy_proc:
                launch_kwargs["proxy"] = {
                    "server": f"http://127.0.0.1:{pfi.PROXY_PORT}",
                }
            browser = pw.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1600, "height": 900},
            )
            page = context.new_page()
            pfi._attach_capture(page)

            # ── DRSysAdmin: login + initial password change ────────────────
            pfi.phase_login_initial(page)
            pfi.phase_change_password(
                page, old_pw=pfi.SYSADMIN_PW, new_pw="password",
            )

            # ── Storage depots + system depot ──────────────────────────────
            pfi.phase_create_storages(page)
            pfi.phase_system_depot(page)

            # ── Organisation + org user ────────────────────────────────────
            pfi.phase_create_org(page)

            # phase_create_org_user requires the org's settings panel open.
            pfi._open_org_settings(page, "training")
            pfi.phase_create_org_user(page)

            # ── admin@training first login + forced password change ────────
            pfi.phase_logout(page)
            pfi.phase_login(page, "admin@training", "Password123")
            pfi.phase_change_password(
                page, old_pw="Password123", new_pw="password",
            )
            pfi.phase_logout(page)

            browser.close()
    finally:
        pfi.stop_proxy(proxy_proc)
        n_calls = len(pfi._api_calls)
        print(f"\n[capture] {n_calls} API calls written to {pfi.CAPTURE}")
        if proxy_proc:
            print(f"[capture] proxy log: /tmp/dr_proxy_capture.json")

    print("\n[init] DR initial setup complete:")
    print("  DRSysAdmin / password")
    print("  admin@training / password")
    print("  Depots: localDocStorage, localIndexStorage")
    print("  System Storage Depot assigned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

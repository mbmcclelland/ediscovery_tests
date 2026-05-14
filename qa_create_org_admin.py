"""qa_create_org_admin.py — one-shot bypass for playwright_fresh_init.py.

Skips the storage / org / system-depot phases (which fail when
already done) and only runs the org-user-create phase.

Use this when the training org exists but admin@training is missing —
which happens after a `cleandr.sh` + reinstall cycle if
`playwright_fresh_init.py` crashed mid-run, or after the user got
manually deleted.

Idempotent: if admin already exists, the org-settings page won't
offer to create another and the script will exit cleanly with a note.
"""
from __future__ import annotations
import sys
from playwright.sync_api import sync_playwright

import playwright_fresh_install as pfi
import argparse


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-headless", dest="headless",
                    action="store_false", default=True)
    ap.add_argument("--slow-mo", type=int, default=0)
    ap.add_argument("--no-proxy", action="store_true")
    args = ap.parse_args()
    pfi.args = args

    proxy = None if args.no_proxy else pfi.start_proxy()
    try:
        with sync_playwright() as pw:
            launch_kwargs = dict(
                headless=args.headless, slow_mo=args.slow_mo,
                args=["--ignore-certificate-errors",
                      "--disable-dev-shm-usage"],
            )
            if proxy:
                launch_kwargs["proxy"] = {
                    "server": f"http://127.0.0.1:{pfi.PROXY_PORT}",
                }
            browser = pw.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1600, "height": 900},
            )
            page = ctx.new_page()
            pfi._attach_capture(page)

            # Log in as DRSysAdmin (already has "password" set).
            pfi.phase_login(page, "DRSysAdmin", "password")
            print("[qa] logged in as DRSysAdmin")

            # Open the training org settings panel.
            pfi._open_org_settings(page, "training")
            print("[qa] opened training settings")

            # Create admin org user.
            pfi.phase_create_org_user(page)
            print("[qa] admin user creation phase done")

            # Logout from sysadmin, log in as the new admin, force PW change.
            pfi.phase_logout(page)
            pfi.phase_login(page, "admin@training", "Password123")
            pfi.phase_change_password(
                page, old_pw="Password123", new_pw="password",
            )
            pfi.phase_logout(page)
            print("[qa] admin@training password change → 'password' done")

            browser.close()
    finally:
        if proxy:
            pfi.stop_proxy(proxy)
        n = len(pfi._api_calls)
        print(f"[capture] {n} API calls")
    print("\n[OK] admin@training now exists with password 'password'")
    return 0


if __name__ == "__main__":
    sys.exit(main())

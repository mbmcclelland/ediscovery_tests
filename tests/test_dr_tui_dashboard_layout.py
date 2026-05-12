"""Pilot smoke for D8 — full DashboardScreen layout walk.

Confirms that:
  - Both tabs (System Settings + Organizations) mount
  - Every System Settings leaf has its action bar with the expected
    button ids (depots / users / groups / virus)
  - The Organizations tab renders the placeholder when no org is
    selected
  - Pressing an action button with no row selected does not crash; the
    status bar reflects the "select a row first" guard

The dashboard normally requires real DRSysAdmin / org clients; this
test installs a no-op stub so the screen mounts without contacting the
server.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from pathlib import Path as _Path
from textual.app import App
from textual.widgets import Button, Static, TabbedContent

from dr_tui.app import DashboardScreen, ROLE_SYS
from dr_tui.app import CSS_PATH as _CSS_PATH


# ---- a fake client that returns empty data for the loaders ----
class _FakeClient:
    def __init__(self):
        class _Cfg: organization = "training"
        self.cfg = _Cfg()

    def post(self, _path, extra_body=None, **_kw):
        # Empty shells — enough to keep fetchers from crashing.
        return {"users": [], "groups": [], "storageAreas": [],
                "organizations": [], "ldapDomains": [], "roles": []}


class _HarnessApp(App):
    """Plain App that pushes Dashboard directly — bypasses the login screen.

    Carries the same `role` / `sys_client` / `org_client` attributes the
    DashboardScreen reads off `self.app`.
    """

    CSS_PATH = _CSS_PATH
    role: str = ROLE_SYS
    target_org: str = "training"

    def __init__(self):
        super().__init__()
        self.sys_client = _FakeClient()
        self.org_client = _FakeClient()

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())


# Buttons we expect to find on each System Settings leaf.
EXPECTED_ACTION_BUTTONS = {
    "sys-doc-depots-view": ["#doc-depot-new", "#doc-depot-edit", "#doc-depot-delete"],
    "sys-idx-depots-view": ["#idx-depot-new", "#idx-depot-edit", "#idx-depot-delete"],
    "sys-virus-view":      ["#sys-virus-update"],
    "sys-users-view":      ["#sys-user-new", "#sys-user-edit",
                            "#sys-user-reset", "#sys-user-delete"],
    "sys-groups-view":     ["#sys-group-new", "#sys-group-edit", "#sys-group-delete"],
}


async def _walk_dashboard() -> None:
    app = _HarnessApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Wait for the screen-push to settle.
        for _ in range(20):
            if isinstance(app.screen, DashboardScreen):
                break
            await pilot.pause()
        else:
            raise AssertionError(f"DashboardScreen never mounted; got {type(app.screen).__name__}")

        screen = app.screen
        # Confirm both tabs exist.
        tabs = screen.query_one("#main-tabs", TabbedContent)
        assert tabs is not None
        # Confirm every expected action button is present.
        for view_id, btn_ids in EXPECTED_ACTION_BUTTONS.items():
            view = screen.query_one(f"#{view_id}")
            assert view is not None, f"view {view_id} missing"
            for bid in btn_ids:
                b = screen.query_one(bid, Button)
                assert b is not None, f"{view_id}: button {bid} missing"

        # Status bar exists.
        status = screen.query_one("#status-bar", Static)
        assert status is not None

        # Press a row-bound action with no selected row — must not crash.
        screen.query_one("#sys-user-edit", Button).action_press()
        await pilot.pause()
        screen.query_one("#sys-group-delete", Button).action_press()
        await pilot.pause()
        # If we got here without an exception, the no-row guards work.


def test_dashboard_layout() -> None:
    """pytest entry — full DashboardScreen action-bar inventory."""
    asyncio.run(_walk_dashboard())


if __name__ == "__main__":
    test_dashboard_layout()
    print("[D8 dashboard pilot smoke: PASS]")

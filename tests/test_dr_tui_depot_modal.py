"""Pilot smoke for the dr-tui Phase D CRUD modals.

Doesn't talk to the API. Mounts each modal in a dummy App and walks
the success / cancel / validation paths with a fresh modal per scenario.

Covers:
  - D4 depots:  DepotFormModal (create + edit) + ConfirmModal
  - D5 users:   UserFormModal (create + edit) + ResetPasswordModal

Run via:

    pytest tests/test_dr_tui_depot_modal.py
    # or, standalone:
    python tests/test_dr_tui_depot_modal.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow `python tests/test_dr_tui_depot_modal.py` from anywhere.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Static

from dr_tui.app import (
    ConfirmModal, DepotFormModal, GroupFormModal,
    InactivityTimeoutFormModal, MailServerFormModal,
    PasswordPolicyFormModal, PriorityModal,
    ResetPasswordModal, SplashMessageFormModal, UserFormModal,
)
from dr_tui.data import (
    GroupRow, InactivityTimeout, MailServerConfig, PasswordPolicy,
    SplashMessage, StorageDepot, UserRow,
)


class _Harness(App):
    def compose(self) -> ComposeResult:
        yield Static("harness")


async def _push_and_get(app: App, pilot, modal):
    """Push *modal* on *app*, wait for it to mount, return callback holder."""
    holder: list = []
    app.push_screen(modal, lambda r: holder.append(r))
    await pilot.pause()
    return holder


async def _walk_all_scenarios() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        # ---- empty-name validation blocks save ----
        holder = await _push_and_get(app, pilot, DepotFormModal(use_type="DOCUMENT_STORE"))
        for sel in ("#depot-name", "#depot-fqdn", "#depot-export", "#depot-allocation"):
            assert app.screen.query_one(sel, Input) is not None, f"missing {sel}"
        assert app.screen.query_one("#depot-name", Input).disabled is False
        app.screen.query_one("#depot-save", Button).action_press()
        await pilot.pause()
        assert not holder, f"empty-name save should not dismiss, got: {holder!r}"
        app.screen.query_one("#depot-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- valid create returns correct dict ----
        holder = await _push_and_get(app, pilot, DepotFormModal(use_type="DOCUMENT_STORE"))
        app.screen.query_one("#depot-name",       Input).value = "smokeDoc"
        app.screen.query_one("#depot-fqdn",       Input).value = "10.0.0.5"
        app.screen.query_one("#depot-export",     Input).value = "/srv/d1"
        app.screen.query_one("#depot-allocation", Input).value = "12"
        await pilot.pause()
        app.screen.query_one("#depot-save", Button).action_press()
        await pilot.pause()
        assert holder, "callback never fired on valid save"
        r = holder[0]
        assert r is not None
        assert r["name"] == "smokeDoc"
        assert r["fqdn"] == "10.0.0.5"
        assert r["export"] == "/srv/d1"
        assert r["allocation"] == 12
        assert r["handle"] is None
        assert r["use_type"] == "DOCUMENT_STORE"

        # ---- edit pre-fills + name disabled ----
        existing = StorageDepot(
            name="existingIdx", use_type="INDEX_STORE",
            fqdn="10.0.0.6", export="/srv/idx",
            in_service=True, kb_used=0, kb_available=0, allocation=42,
            handle="291",
        )
        holder = await _push_and_get(
            app, pilot,
            DepotFormModal(use_type="INDEX_STORE", existing=existing),
        )
        name_input = app.screen.query_one("#depot-name", Input)
        assert name_input.disabled is True
        assert name_input.value == "existingIdx"
        assert app.screen.query_one("#depot-fqdn", Input).value == "10.0.0.6"
        assert app.screen.query_one("#depot-allocation", Input).value == "42"
        app.screen.query_one("#depot-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- ConfirmModal yes / no ----
        holder = await _push_and_get(
            app, pilot,
            ConfirmModal("Delete depot?", "Are you sure?", confirm_label="Yes"),
        )
        app.screen.query_one("#confirm-yes", Button).action_press()
        await pilot.pause()
        assert holder == [True]

        holder = await _push_and_get(
            app, pilot,
            ConfirmModal("Delete depot?", "Are you sure?", confirm_label="Yes"),
        )
        app.screen.query_one("#confirm-no", Button).action_press()
        await pilot.pause()
        assert holder == [False]


async def _walk_user_scenarios() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        roles = [("System Administrator", "00sysadmin-handle"),
                 ("IT Administrator",     "00it-handle")]

        # ---- create: empty fields block save ----
        holder = await _push_and_get(app, pilot, UserFormModal(roles=roles))
        for sel in ("#user-username", "#user-email", "#user-first",
                    "#user-last", "#user-password", "#user-role"):
            assert app.screen.query_one(sel) is not None, f"missing {sel}"
        # Username editable on create.
        assert app.screen.query_one("#user-username", Input).disabled is False
        app.screen.query_one("#user-save", Button).action_press()
        await pilot.pause()
        assert not holder, "empty save should not dismiss"
        app.screen.query_one("#user-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- create: valid submit returns expected dict ----
        holder = await _push_and_get(app, pilot, UserFormModal(roles=roles))
        app.screen.query_one("#user-username", Input).value = "smokeuser"
        app.screen.query_one("#user-email",    Input).value = "smoke@example.com"
        app.screen.query_one("#user-first",    Input).value = "Smoke"
        app.screen.query_one("#user-last",     Input).value = "User"
        app.screen.query_one("#user-password", Input).value = "Password123"
        # Programmatically set the Select.
        from textual.widgets import Select as _Select
        app.screen.query_one("#user-role", _Select).value = "00sysadmin-handle"
        await pilot.pause()
        app.screen.query_one("#user-save", Button).action_press()
        await pilot.pause()
        assert holder, "valid save never dismissed"
        r = holder[0]
        assert r["username"]    == "smokeuser"
        assert r["email"]       == "smoke@example.com"
        assert r["first_name"]  == "Smoke"
        assert r["last_name"]   == "User"
        assert r["password"]    == "Password123"
        assert r["role_handle"] == "00sysadmin-handle"
        assert r["user_handle"] is None

        # ---- edit: pre-fills, username disabled, no password field ----
        existing = UserRow(
            handle="systemadmin@super_system_customer",
            display="System Admin",
            email="sa@example.com",
            enabled=True, locked=False, mfa=False,
            last_access="", roles="System Administrator", is_admin=False,
        )
        holder = await _push_and_get(
            app, pilot,
            UserFormModal(roles=roles, existing=existing,
                          existing_role_handle="00sysadmin-handle"),
        )
        u = app.screen.query_one("#user-username", Input)
        assert u.disabled is True
        assert u.value == "systemadmin"
        # No password field on edit.
        try:
            app.screen.query_one("#user-password", Input)
            raise AssertionError("password field should not appear on edit")
        except Exception as e:
            # Textual raises NoMatches; we just want the absence.
            if "NoMatches" not in type(e).__name__ and not isinstance(e, AssertionError):
                pass
            elif isinstance(e, AssertionError):
                raise
        app.screen.query_one("#user-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- ResetPasswordModal: mismatch blocks (fresh modal) ----
        holder = await _push_and_get(
            app, pilot, ResetPasswordModal(username="smokeuser"),
        )
        app.screen.query_one("#reset-new",     Input).value = "NewPass1"
        app.screen.query_one("#reset-confirm", Input).value = "Different!"
        await pilot.pause()
        app.screen.query_one("#reset-ok", Button).action_press()
        await pilot.pause()
        assert not holder, "mismatch should not dismiss"
        app.screen.query_one("#reset-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- ResetPasswordModal: matching passwords dismiss (fresh modal) ----
        holder = await _push_and_get(
            app, pilot, ResetPasswordModal(username="smokeuser"),
        )
        app.screen.query_one("#reset-new",     Input).value = "NewPass1"
        app.screen.query_one("#reset-confirm", Input).value = "NewPass1"
        await pilot.pause()
        app.screen.query_one("#reset-ok", Button).action_press()
        await pilot.pause()
        assert holder == [{"new_password": "NewPass1"}], f"got: {holder!r}"


async def _walk_group_scenarios() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        roles = [("System Administrator", "00sysadmin-handle"),
                 ("IT Administrator",     "00it-handle")]

        # ---- empty name blocks save ----
        holder = await _push_and_get(app, pilot, GroupFormModal(roles=roles))
        from textual.widgets import Select as _Select
        app.screen.query_one("#group-role", _Select).value = "00sysadmin-handle"
        await pilot.pause()
        app.screen.query_one("#group-save", Button).action_press()
        await pilot.pause()
        assert not holder, "empty-name save should not dismiss"
        app.screen.query_one("#group-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- valid create ----
        holder = await _push_and_get(app, pilot, GroupFormModal(roles=roles))
        app.screen.query_one("#group-name", Input).value = "smokeGroup"
        app.screen.query_one("#group-desc", Input).value = "smoke description"
        app.screen.query_one("#group-role", _Select).value = "00sysadmin-handle"
        await pilot.pause()
        app.screen.query_one("#group-save", Button).action_press()
        await pilot.pause()
        assert holder, "valid save never dismissed"
        r = holder[0]
        assert r["name"]        == "smokeGroup"
        assert r["description"] == "smoke description"
        assert r["role_handle"] == "00sysadmin-handle"
        assert r["role_name"]   == "System Administrator"
        assert r["handle"]      is None

        # ---- edit pre-fill ----
        existing = GroupRow(
            handle="00grouphandle", name="existing",
            description="old desc", members=3,
            role_handle="00sysadmin-handle",
            role_name="System Administrator",
        )
        holder = await _push_and_get(
            app, pilot, GroupFormModal(roles=roles, existing=existing),
        )
        assert app.screen.query_one("#group-name", Input).value == "existing"
        assert app.screen.query_one("#group-desc", Input).value == "old desc"
        assert app.screen.query_one("#group-role", _Select).value == "00sysadmin-handle"
        app.screen.query_one("#group-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]


async def _walk_priority_scenarios() -> None:
    """PriorityModal: each button returns the matching enum; cancel returns None."""
    app = _Harness()
    async with app.run_test() as pilot:
        holder = await _push_and_get(
            app, pilot,
            PriorityModal(job_label="some-task", current="NORMAL"),
        )
        app.screen.query_one("#pri-high", Button).action_press()
        await pilot.pause()
        assert holder == ["HIGH"], f"got: {holder!r}"

        holder = await _push_and_get(
            app, pilot, PriorityModal(job_label="x", current="HIGH"),
        )
        app.screen.query_one("#pri-normal", Button).action_press()
        await pilot.pause()
        assert holder == ["NORMAL"]

        holder = await _push_and_get(
            app, pilot, PriorityModal(job_label="x", current="HIGH"),
        )
        app.screen.query_one("#pri-low", Button).action_press()
        await pilot.pause()
        assert holder == ["LOW"]

        holder = await _push_and_get(
            app, pilot, PriorityModal(job_label="x", current=""),
        )
        app.screen.query_one("#pri-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]


async def _walk_settings_scenarios() -> None:
    """v0.12 Realm Settings modals: save returns the right payload; cancel = None."""
    app = _Harness()
    async with app.run_test() as pilot:
        # ---- MailServerFormModal ----
        existing = MailServerConfig(
            configured=True, smtp_host="smtp.old.com", smtp_port=2525,
            smtp_auth=False,
        )
        holder = await _push_and_get(
            app, pilot, MailServerFormModal(existing=existing),
        )
        # Pre-populate fields, edit host, save.
        app.screen.query_one("#mail-host", Input).value = "smtp.new.com"
        app.screen.query_one("#mail-port", Input).value = "587"
        app.screen.query_one("#settings-save", Button).action_press()
        await pilot.pause()
        assert holder == [{"smtp_host": "smtp.new.com", "smtp_port": 587}], \
            f"mail save: {holder!r}"

        # Bad port → error + no dismiss.
        holder = await _push_and_get(app, pilot, MailServerFormModal())
        app.screen.query_one("#mail-host", Input).value = "smtp.x"
        app.screen.query_one("#mail-port", Input).value = "no"
        app.screen.query_one("#settings-save", Button).action_press()
        await pilot.pause()
        assert holder == [], "bad port should not dismiss"
        # Cancel out of this one.
        app.screen.query_one("#settings-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- SplashMessageFormModal ----
        sp = SplashMessage(enabled=False, message="hello")
        holder = await _push_and_get(
            app, pilot, SplashMessageFormModal(existing=sp),
        )
        app.screen.query_one("#settings-save", Button).action_press()
        await pilot.pause()
        # enabled=False + non-empty message → saves fine.
        assert holder == [{"enabled": False, "message": "hello"}], \
            f"splash save: {holder!r}"

        # ---- PasswordPolicyFormModal ----
        pp = PasswordPolicy(
            enforce_strong=False, min_length=6, min_uppercase=0,
            min_lowercase=0, min_numbers=0, min_symbols=0,
            expiration_days=90,
        )
        holder = await _push_and_get(
            app, pilot, PasswordPolicyFormModal(existing=pp),
        )
        app.screen.query_one("#pwp-length", Input).value = "8"
        app.screen.query_one("#pwp-upper", Input).value = "1"
        app.screen.query_one("#settings-save", Button).action_press()
        await pilot.pause()
        assert len(holder) == 1
        out: PasswordPolicy = holder[0]
        assert out.min_length == 8 and out.min_uppercase == 1, \
            f"pwpolicy save: {out!r}"

        # Composition > length → blocked.
        holder = await _push_and_get(app, pilot, PasswordPolicyFormModal())
        app.screen.query_one("#pwp-length", Input).value = "4"
        app.screen.query_one("#pwp-upper", Input).value = "3"
        app.screen.query_one("#pwp-numbers", Input).value = "3"
        app.screen.query_one("#settings-save", Button).action_press()
        await pilot.pause()
        assert holder == [], "composition overflow should not dismiss"
        app.screen.query_one("#settings-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- InactivityTimeoutFormModal ----
        existing = InactivityTimeout(seconds=300)
        holder = await _push_and_get(
            app, pilot, InactivityTimeoutFormModal(existing=existing),
        )
        app.screen.query_one("#inact-seconds", Input).value = "1800"
        app.screen.query_one("#settings-save", Button).action_press()
        await pilot.pause()
        assert holder == [{"seconds": 1800}], f"inactivity save: {holder!r}"


def test_depot_modal_paths() -> None:
    """pytest entry point — wraps the async pilot walk."""
    asyncio.run(_walk_all_scenarios())


def test_settings_modal_paths() -> None:
    """pytest entry point — v0.12 Realm Settings edit modals."""
    asyncio.run(_walk_settings_scenarios())


def test_user_modal_paths() -> None:
    """pytest entry point — UserFormModal + ResetPasswordModal scenarios."""
    asyncio.run(_walk_user_scenarios())


def test_group_modal_paths() -> None:
    """pytest entry point — GroupFormModal scenarios."""
    asyncio.run(_walk_group_scenarios())


def test_priority_modal_paths() -> None:
    """pytest entry point — PriorityModal returns correct enum per button."""
    asyncio.run(_walk_priority_scenarios())


if __name__ == "__main__":
    test_depot_modal_paths()
    print("[D4 pilot smoke: PASS]")
    test_user_modal_paths()
    print("[D5 pilot smoke: PASS]")
    test_group_modal_paths()
    print("[D6 pilot smoke: PASS]")
    test_priority_modal_paths()
    print("[priority pilot smoke: PASS]")

"""
dr-tui — Textual TUI for the Digital Reef eDiscovery REST API.

Run:
    dr-tui                 # console_scripts entry from setup.cfg
    python -m dr_tui       # equivalent

v0.05 layout: TabbedContent with two tabs:
  - "System Settings"  (DRSysAdmin only) — Storage / Virus / Users / Groups
  - "Organizations"   (both roles)       — drill-down per org → Users / Admins /
    Groups / Projects / Running / Completed / Connectors / Storage.

Each tree leaf maps to a view inside a ContentSwitcher on the right. Phase B
wired the layout + routing; Phase C fills in per-leaf read-only data via the
`_load_view(kind, org)` dispatcher (each leaf has its own fetcher in data.py
and applier in DashboardScreen).
"""
from __future__ import annotations

import urllib3
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button, Checkbox, ContentSwitcher, DataTable, Footer, Header, Input, Label,
    Markdown, RadioButton, RadioSet, RichLog, Select, Sparkline, Static,
    TabbedContent, TabPane, TextArea, Tree,
)
from textual.worker import get_current_worker

from config import Config, OrgUserConfig
from helpers.api_client import APIError, EDiscoveryClient

from dr_tui import data as drdata
from dr_tui import help as drhelp
from dr_tui import metrics as drmetrics
from dr_tui import scheduler as drsch

urllib3.disable_warnings()

ROLE_SYS = "sys"
ROLE_ORG = "org"

CSS_PATH = Path(__file__).with_name("app.tcss")

# kind → ContentSwitcher view id
SYS_VIEW_MAP = {
    "sys-doc-depots": "sys-doc-depots-view",
    "sys-idx-depots": "sys-idx-depots-view",
    "sys-sysdepot":   "sys-sysdepot-view",
    "sys-virus":      "sys-virus-view",
    "sys-users":      "sys-users-view",
    "sys-groups":     "sys-groups-view",
    # v0.08 Realm Settings sub-tree
    "sys-mail":       "sys-mail-view",
    "sys-splash":     "sys-splash-view",
    "sys-pwpolicy":   "sys-pwpolicy-view",
    "sys-inactivity": "sys-inactivity-view",
}
ORG_VIEW_MAP = {
    "org-users":       "org-users-view",
    "org-admins":      "org-admins-view",
    "org-groups":      "org-groups-view",
    "org-projects":    "org-projects-view",
    "org-running":     "org-running-view",
    "org-completed":   "org-completed-view",
    "org-connectors":  "org-connectors-view",
    "org-storage":     "org-storage-view",
}
# v0.13 Job Scheduler tab — same idiom as SYS/ORG view maps.
SCH_VIEW_MAP = {
    "sch-running": "sch-running-view",
    "sch-saved":   "sch-saved-view",
    "sch-timers":  "sch-timers-view",
    "sch-runs":    "sch-runs-view",
}


def _fmt_kb(kb: int) -> str:
    """Render KB int as a human-readable size."""
    if kb <= 0:
        return "—"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    if gb < 1024:
        return f"{gb:.1f} GB"
    return f"{gb / 1024:.1f} TB"


def _yn(b: bool) -> str:
    return "yes" if b else "no"


def _fmt_retention(seconds: int) -> str:
    """Render a retention duration in the largest unit that divides cleanly."""
    if seconds <= 0:
        return "forever"
    for label, mult in (("w", 604800), ("d", 86400),
                        ("h", 3600), ("m", 60)):
        if seconds % mult == 0:
            return f"{seconds // mult}{label}"
    return f"{seconds}s"


def _fmt_rate(bytes_per_sec: float) -> str:
    """Render a byte/sec rate compactly: 1.2 MB/s, 800 KB/s, …"""
    if bytes_per_sec >= 1024 ** 3:
        return f"{bytes_per_sec / (1024 ** 3):5.2f} GB/s"
    if bytes_per_sec >= 1024 ** 2:
        return f"{bytes_per_sec / (1024 ** 2):5.2f} MB/s"
    if bytes_per_sec >= 1024:
        return f"{bytes_per_sec / 1024:5.1f} KB/s"
    return f"{bytes_per_sec:5.0f} B/s"


def _color_status(s: str) -> str:
    """Wrap a monitorStatus string with a Rich colour."""
    if not s:
        return "[dim]?[/]"
    if s == "AVAILABLE":
        return f"[green]{s}[/]"
    if s == "UNAVAILABLE":
        return f"[red]{s}[/]"
    return f"[yellow]{s}[/]"


# ============================================================ Login screen
class LoginScreen(Screen):
    """User-type selector + password field."""

    BINDINGS = [Binding("escape", "app.quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="login-card"):
            yield Static("DR eDiscovery TUI", id="login-title")
            yield Label("Sign in as:")
            with RadioSet(id="role"):
                yield RadioButton("DRSysAdmin (super_system_customer)", value=True, id="role-sys")
                yield RadioButton("admin@training (organization administrator)", id="role-org")
            yield Label("Password:")
            yield Input(value="password", password=True, id="password")
            yield Button.success("Sign in", id="signin")
            yield Static("", id="login-error")
            yield Static("Enter to submit · Esc to quit", id="login-hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#password", Input).focus()

    def on_input_submitted(self, _evt: Input.Submitted) -> None:
        self._signin()

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        if evt.button.id == "signin":
            self._signin()

    def _signin(self) -> None:
        pwd = self.query_one("#password", Input).value
        role = ROLE_SYS if self.query_one("#role-sys", RadioButton).value else ROLE_ORG
        self.query_one("#login-error", Static).update("Signing in…")
        self.app.do_login(role, pwd)


# ============================================================ Modal screens
class ConfirmModal(ModalScreen[bool]):
    """Generic yes/no confirmation. dismiss(True) on confirm, False on cancel."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm", show=False),
    ]

    def __init__(self, title: str, message: str, confirm_label: str = "Delete") -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Container(id="confirm-card"):
            yield Static(self._title, id="confirm-title")
            yield Static(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button(self._confirm_label, id="confirm-yes", variant="error")
                yield Button("Cancel", id="confirm-no")

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        self.dismiss(evt.button.id == "confirm-yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class DepotFormModal(ModalScreen[Optional[dict]]):
    """Create / edit form for an NFS storage depot.

    Returns a dict like:
        {"name": str, "fqdn": str, "export": str,
         "allocation": int, "handle": str | None}
    or None on cancel. `name` is empty / unchanged for edits (depot names
    are immutable server-side — the field is shown disabled).
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        *,
        use_type: str,                         # DOCUMENT_STORE | INDEX_STORE
        existing: Optional[drdata.StorageDepot] = None,
    ) -> None:
        super().__init__()
        self._use_type = use_type
        self._existing = existing
        self._mode = "Edit" if existing else "New"

    def compose(self) -> ComposeResult:
        label = "Index Depot" if self._use_type == "INDEX_STORE" else "Document Depot"
        with Container(id="depot-card"):
            yield Static(f"{self._mode} {label}", id="depot-title")
            yield Label("Name (immutable):" if self._existing else "Name:")
            yield Input(
                value=(self._existing.name if self._existing else ""),
                placeholder="e.g. localDocStorage",
                id="depot-name",
                disabled=bool(self._existing),
            )
            yield Label("FQDN / IP:")
            yield Input(
                value=(self._existing.fqdn if self._existing else ""),
                placeholder="192.168.58.128",
                id="depot-fqdn",
            )
            yield Label("Export path:")
            yield Input(
                value=(self._existing.export if self._existing else ""),
                placeholder="/data/archive",
                id="depot-export",
            )
            yield Label("Allocation (0 = no quota):")
            yield Input(
                value=str(self._existing.allocation if self._existing else 0),
                id="depot-allocation",
            )
            yield Static("", id="depot-error")
            with Horizontal(id="depot-buttons"):
                yield Button.success("Save", id="depot-save")
                yield Button("Cancel", id="depot-cancel")
            yield Static("[dim][Enter] save · [Esc] cancel · [Tab] next field[/]",
                         classes="modal-hint")

    def on_mount(self) -> None:
        # Focus first editable field — name for new, fqdn for edit.
        target = "#depot-fqdn" if self._existing else "#depot-name"
        self.query_one(target, Input).focus()

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        if evt.button.id == "depot-cancel":
            self.dismiss(None)
        elif evt.button.id == "depot-save":
            self._save()

    def on_input_submitted(self, _evt: Input.Submitted) -> None:
        """Enter inside any Input field triggers save."""
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        name = self.query_one("#depot-name", Input).value.strip()
        fqdn = self.query_one("#depot-fqdn", Input).value.strip()
        export = self.query_one("#depot-export", Input).value.strip()
        alloc_raw = self.query_one("#depot-allocation", Input).value.strip() or "0"

        # ---- validate ----
        err = self.query_one("#depot-error", Static)
        if not self._existing and not name:
            err.update("[red]Name is required.[/]")
            return
        if not fqdn:
            err.update("[red]FQDN / IP is required.[/]")
            return
        if not export:
            err.update("[red]Export path is required.[/]")
            return
        try:
            allocation = int(alloc_raw)
            if allocation < 0:
                raise ValueError
        except ValueError:
            err.update("[red]Allocation must be a non-negative integer.[/]")
            return

        self.dismiss({
            "name": name,
            "fqdn": fqdn,
            "export": export,
            "allocation": allocation,
            "handle": self._existing.handle if self._existing else None,
            "use_type": self._use_type,
        })


class UserFormModal(ModalScreen[Optional[dict]]):
    """Create / edit form for a system user.

    On submit returns:
        {"username": str, "email": str, "first_name": str, "last_name": str,
         "password": str | None,          # only when creating
         "role_handle": str,
         "user_handle": str | None}       # set only when editing

    The role dropdown is populated from `realmManager/listSystemRoles`;
    the caller must pass *roles* as `[(name, handle), …]`. `existing` is
    a `UserRow` from `data.list_system_users_and_groups()` plus the role
    handle resolved by the caller (because `UserRow` only carries the
    comma-joined role names, not handles).
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        *,
        roles: list,                              # list[(name, handle)]
        existing: Optional[drdata.UserRow] = None,
        existing_role_handle: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._roles = roles
        self._existing = existing
        self._existing_role_handle = existing_role_handle
        self._mode = "Edit" if existing else "New"

    def compose(self) -> ComposeResult:
        ex = self._existing
        with Container(id="user-card"):
            yield Static(f"{self._mode} System User", id="user-title")
            yield Label("Username (immutable):" if ex else "Username:")
            yield Input(
                value=(ex.handle.split("@")[0] if ex else ""),
                placeholder="e.g. systemadmin",
                id="user-username",
                disabled=bool(ex),
            )
            yield Label("Email:")
            yield Input(
                value=(ex.email if ex else ""),
                placeholder="user@example.com",
                id="user-email",
            )
            yield Label("First name:")
            yield Input(
                value=(ex.display.split(" ", 1)[0] if ex and ex.display else ""),
                id="user-first",
            )
            yield Label("Last name:")
            yield Input(
                value=(ex.display.split(" ", 1)[1] if ex and " " in (ex.display or "") else ""),
                id="user-last",
            )
            if not ex:
                yield Label("Initial password:")
                yield Input(
                    value="",
                    placeholder="set a strong password",
                    password=True,
                    id="user-password",
                )
            yield Label("Role:")
            # Textual 8.2.5: blank sentinel is `Select.NULL` (not `BLANK`,
            # which is just bool False in this version).
            yield Select(
                options=[(name, handle) for (name, handle) in self._roles],
                value=(self._existing_role_handle if self._existing_role_handle else Select.NULL),
                id="user-role",
                prompt="Select a role…",
            )
            yield Static("", id="user-error")
            with Horizontal(id="user-buttons"):
                yield Button.success("Save", id="user-save")
                yield Button("Cancel", id="user-cancel")
            yield Static("[dim][Enter] save · [Esc] cancel · [Tab] next field[/]",
                         classes="modal-hint")

    def on_mount(self) -> None:
        target = "#user-email" if self._existing else "#user-username"
        self.query_one(target, Input).focus()

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        if evt.button.id == "user-cancel":
            self.dismiss(None)
        elif evt.button.id == "user-save":
            self._save()

    def on_input_submitted(self, _evt: Input.Submitted) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        ex = self._existing
        username = self.query_one("#user-username", Input).value.strip()
        email = self.query_one("#user-email", Input).value.strip()
        first = self.query_one("#user-first", Input).value.strip()
        last = self.query_one("#user-last", Input).value.strip()
        role_handle = self.query_one("#user-role", Select).value
        password = ""
        if not ex:
            password = self.query_one("#user-password", Input).value

        err = self.query_one("#user-error", Static)
        if not ex and not username:
            err.update("[red]Username is required.[/]")
            return
        if not email or "@" not in email:
            err.update("[red]A valid email is required.[/]")
            return
        if not first or not last:
            err.update("[red]First and last name are required.[/]")
            return
        if not ex and not password:
            err.update("[red]Initial password is required for new users.[/]")
            return
        if role_handle is Select.NULL or not role_handle:
            err.update("[red]Pick a role.[/]")
            return

        self.dismiss({
            "username": username or (ex.handle.split("@")[0] if ex else ""),
            "email": email,
            "first_name": first,
            "last_name": last,
            "password": password or None,
            "role_handle": role_handle,
            "user_handle": ex.handle if ex else None,
        })


class ResetPasswordModal(ModalScreen[Optional[dict]]):
    """Admin password-reset dialog.

    Returns `{"new_password": str}` on save or `None` on cancel.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, *, username: str) -> None:
        super().__init__()
        self._username = username

    def compose(self) -> ComposeResult:
        with Container(id="reset-card"):
            yield Static(f"Reset password — {self._username}", id="reset-title")
            yield Label("New password:")
            yield Input(value="", password=True, id="reset-new")
            yield Label("Confirm:")
            yield Input(value="", password=True, id="reset-confirm")
            yield Static("", id="reset-error")
            with Horizontal(id="reset-buttons"):
                yield Button.success("Reset", id="reset-ok")
                yield Button("Cancel", id="reset-cancel")
            yield Static("[dim][Enter] reset · [Esc] cancel · [Tab] next field[/]",
                         classes="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#reset-new", Input).focus()

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        if evt.button.id == "reset-cancel":
            self.dismiss(None)
        elif evt.button.id == "reset-ok":
            self._submit()

    def on_input_submitted(self, _evt: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        new = self.query_one("#reset-new", Input).value
        conf = self.query_one("#reset-confirm", Input).value
        err = self.query_one("#reset-error", Static)
        if not new:
            err.update("[red]Password is required.[/]")
            return
        if new != conf:
            err.update("[red]Passwords do not match.[/]")
            return
        self.dismiss({"new_password": new})

    def action_cancel(self) -> None:
        self.dismiss(None)


class GroupFormModal(ModalScreen[Optional[dict]]):
    """Create / edit form for a system group.

    On submit returns:
        {"name": str, "description": str, "role_handle": str,
         "role_name": str, "handle": str | None}
    or None on cancel. `handle` is set only when editing; `role_name`
    accompanies `role_handle` because `orgManager/updateGroup` carries
    a nested `roles` array that needs both.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        *,
        roles: list,                                  # list[(name, handle)]
        existing: Optional[drdata.GroupRow] = None,
    ) -> None:
        super().__init__()
        self._roles = roles
        self._existing = existing
        self._mode = "Edit" if existing else "New"

    def compose(self) -> ComposeResult:
        ex = self._existing
        with Container(id="group-card"):
            yield Static(f"{self._mode} System Group", id="group-title")
            yield Label("Name:")
            yield Input(
                value=(ex.name if ex else ""),
                placeholder="e.g. dataMgmtTeam",
                id="group-name",
            )
            yield Label("Description:")
            yield Input(
                value=(ex.description if ex else ""),
                placeholder="optional description",
                id="group-desc",
            )
            yield Label("Role:")
            yield Select(
                options=[(name, handle) for (name, handle) in self._roles],
                value=(ex.role_handle if ex and ex.role_handle else Select.NULL),
                id="group-role",
                prompt="Select a role…",
            )
            yield Static("", id="group-error")
            with Horizontal(id="group-buttons"):
                yield Button.success("Save", id="group-save")
                yield Button("Cancel", id="group-cancel")
            yield Static("[dim][Enter] save · [Esc] cancel · [Tab] next field[/]",
                         classes="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#group-name", Input).focus()

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        if evt.button.id == "group-cancel":
            self.dismiss(None)
        elif evt.button.id == "group-save":
            self._save()

    def on_input_submitted(self, _evt: Input.Submitted) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        name = self.query_one("#group-name", Input).value.strip()
        desc = self.query_one("#group-desc", Input).value.strip()
        role_handle = self.query_one("#group-role", Select).value

        err = self.query_one("#group-error", Static)
        if not name:
            err.update("[red]Name is required.[/]")
            return
        if role_handle is Select.NULL or not role_handle:
            err.update("[red]Pick a role.[/]")
            return

        # Resolve role name from the catalogue so the edit-body can ship it.
        role_name = next(
            (n for (n, h) in self._roles if h == role_handle), "",
        )

        self.dismiss({
            "name": name,
            "description": desc,
            "role_handle": role_handle,
            "role_name": role_name,
            "handle": self._existing.handle if self._existing else None,
        })


class JobsMonitorModal(ModalScreen[None]):
    """F3 — full-screen realm-wide jobs monitor.

    Three panels stacked vertically:
      - Header strip: counts + filter row (state radio + search input)
      - Master DataTable: every running + completed job, all orgs
      - Detail Static: full currentStatus + attributes for the selected row

    Refresh on `r`, auto-refresh every 5 s while open. Esc closes.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("r",      "refresh", "Refresh"),
        Binding("a",      "filter_all",       "All",       show=False),
        Binding("u",      "filter_running",   "Running",   show=False),
        Binding("c",      "filter_complete",  "Complete",  show=False),
        Binding("d",      "filter_deleted",   "Deleted",   show=False),
        Binding("slash",  "focus_search",     "Search",    show=False),
        Binding("l",      "view_log",         "Log",       show=False),
    ]

    # Filter state — "all" / "running" / "complete" / "deleted".
    _state_filter: str
    # Last fetched data.
    _running: list           # list[JobRow]
    _completed: list         # list[JobRow]
    _deleted: list           # list[DeletedProject]
    _total_cores: int
    # Snapshot of currently-displayed rows for cursor → detail.
    _displayed: list         # list[JobRow | DeletedProject]

    def __init__(self) -> None:
        super().__init__()
        self._state_filter = "all"
        self._running = []
        self._completed = []
        self._deleted = []
        self._total_cores = 0
        self._displayed = []
        self._search = ""
        # v0.11 — operation-type filter. Empty string = "any type".
        # _op_types is populated on first fetch (listOperationTypes);
        # _op_types_populated flips True once set_options() has run.
        self._type_filter: str = ""
        self._op_types: list[str] = []
        self._op_types_populated: bool = False

    def compose(self) -> ComposeResult:
        with Container(id="jobs-card"):
            yield Static("Jobs Monitor", id="jobs-title")
            yield Static(id="jobs-summary")
            with Horizontal(id="jobs-filter-row"):
                yield Button("All",       id="jobs-flt-all",      variant="primary")
                yield Button("Running",   id="jobs-flt-running",  variant="success")
                yield Button("Complete",  id="jobs-flt-complete", variant="default")
                yield Button("Deleted",   id="jobs-flt-deleted",  variant="warning")
                # Operation-type dropdown. Populated lazily on first
                # fetch; "" sentinel means "any type".
                yield Select(
                    [("Any type", "")], id="jobs-type-select",
                    prompt="Any type", allow_blank=False, value="",
                )
                yield Input(placeholder="search (org / project / job)…",
                            id="jobs-search")
            with Horizontal(id="jobs-action-row"):
                yield Button("Pause",    id="jobs-act-pause")
                yield Button("Resume",   id="jobs-act-resume",  variant="success")
                yield Button("Cancel",   id="jobs-act-cancel",  variant="error")
                yield Button("Priority", id="jobs-act-priority", variant="warning")
                yield Button("Log",      id="jobs-act-log",     variant="primary")
            with Horizontal(id="jobs-body"):
                yield DataTable(id="jobs-table", zebra_stripes=True, cursor_type="row")
                yield Static("[dim]Select a row to see full job detail.[/]",
                             id="jobs-detail", classes="detail-body")
            yield Static(
                "[dim][r] refresh · [a/u/c/d] filter · [/] search · "
                "[l] log · [Esc] close[/]",
                id="jobs-hint",
            )

    def on_mount(self) -> None:
        t = self.query_one("#jobs-table", DataTable)
        t.add_columns("Org", "Project", "Job", "State", "Started", "Completed", "Duration", "User")
        # Initial fetch + 5 s auto-refresh while open.
        self.action_refresh()
        self.set_interval(5.0, self.action_refresh)

    # ---- actions ----
    def action_dismiss(self, _result=None) -> None:
        self.dismiss(None)

    def action_refresh(self) -> None:
        self.run_worker(self._fetch_blocking, thread=True,
                        exclusive=True, group="jobs-mon-fetch")

    def action_filter_all(self) -> None:      self._set_filter("all")
    def action_filter_running(self) -> None:  self._set_filter("running")
    def action_filter_complete(self) -> None: self._set_filter("complete")
    def action_filter_deleted(self) -> None:  self._set_filter("deleted")

    def action_focus_search(self) -> None:
        try:
            self.query_one("#jobs-search", Input).focus()
        except Exception:
            pass

    def _set_filter(self, mode: str) -> None:
        self._state_filter = mode
        bmap = {"all": "jobs-flt-all", "running": "jobs-flt-running",
                "complete": "jobs-flt-complete", "deleted": "jobs-flt-deleted"}
        variants = {"all": "primary", "running": "success",
                    "complete": "primary", "deleted": "warning"}
        for m, bid in bmap.items():
            try:
                b = self.query_one(f"#{bid}", Button)
                b.variant = variants[m] if m == mode else "default"
            except Exception:
                pass
        self._render_rows()

    # ---- event handlers ----
    def on_button_pressed(self, evt: Button.Pressed) -> None:
        bid = evt.button.id or ""
        if bid == "jobs-flt-all":      self._set_filter("all")
        elif bid == "jobs-flt-running": self._set_filter("running")
        elif bid == "jobs-flt-complete": self._set_filter("complete")
        elif bid == "jobs-flt-deleted": self._set_filter("deleted")
        elif bid == "jobs-act-pause":   self._action_on_selected("pause")
        elif bid == "jobs-act-resume":  self._action_on_selected("resume")
        elif bid == "jobs-act-cancel":  self._action_on_selected("cancel")
        elif bid == "jobs-act-priority": self._action_on_selected("priority")
        elif bid == "jobs-act-log":     self._action_on_selected("log")

    def on_select_changed(self, evt) -> None:
        if getattr(evt, "select", None) is None or evt.select.id != "jobs-type-select":
            return
        self._type_filter = "" if evt.value in ("", Select.BLANK) else str(evt.value)
        # Re-fetch with the new server-side filter (listRealmTasks takes
        # an OPERATION_TYPE filter directly — cheaper than client-side).
        self.action_refresh()

    def action_view_log(self) -> None:
        self._action_on_selected("log")

    def _selected_job(self):
        try:
            idx = self.query_one("#jobs-table", DataTable).cursor_row
        except Exception:
            return None
        if idx is None or idx < 0 or idx >= len(self._displayed):
            return None
        item = self._displayed[idx]
        # Only JobRow entries are actionable — deleted projects are read-only.
        if isinstance(item, drdata.DeletedProject):
            return None
        return item

    def _action_on_selected(self, action: str) -> None:
        """Dispatch a pause/resume/cancel/priority action on the selected row."""
        job = self._selected_job()
        if job is None:
            # No action target — silently fail. Detail pane gives a hint.
            return
        if action == "pause":
            self.run_worker(
                lambda: self._job_action_blocking(job, "pause"),
                thread=True, exclusive=False, group="job-action",
            )
        elif action == "resume":
            self.run_worker(
                lambda: self._job_action_blocking(job, "resume"),
                thread=True, exclusive=False, group="job-action",
            )
        elif action == "cancel":
            # Cancel is destructive — confirm first.
            self.app.push_screen(
                ConfirmModal(
                    title="Cancel job?",
                    message=(
                        f"Cancel running job [b]{job.job}[/] in "
                        f"project [b]{job.project}[/]?\n\n"
                        "The task transitions to state CANCELLED. "
                        "This cannot be undone."
                    ),
                    confirm_label="Cancel Job",
                ),
                lambda ok: self._after_cancel_confirm(ok, job),
            )
        elif action == "priority":
            # Pop the priority picker; on dismiss with a value, fire the
            # updateJobPriority call.
            current = ""
            raw = job.raw or {}
            for sec in raw.get("currentStatus") or []:
                for kv in sec.get("data") or []:
                    if (kv.get("name") or "").strip().lower() == "priority":
                        current = str(kv.get("value") or "")
                        break
            self.app.push_screen(
                PriorityModal(job_label=job.job, current=current),
                lambda new_pri: self._after_priority_pick(new_pri, job),
            )
        elif action == "log":
            # v0.11 — tail the per-task AE log. Only viable for running
            # tasks (AE retains the Service Node Debug State only while
            # the worker is alive). For finished tasks we show a hint
            # rather than fire a doomed lookup.
            if job.state != "RUNNING":
                self.query_one("#jobs-detail", Static).update(
                    f"[yellow]Live log only available for RUNNING tasks "
                    f"(this one is {job.state}).[/]"
                )
                return
            full_handle = (job.raw or {}).get("handle", job.task_handle)
            self.app.push_screen(
                TaskLogModal(job_label=job.job, task_handle=full_handle),
            )

    def _after_cancel_confirm(self, ok: bool, job) -> None:
        if not ok:
            return
        self.run_worker(
            lambda: self._job_action_blocking(job, "cancel"),
            thread=True, exclusive=False, group="job-action",
        )

    def _after_priority_pick(self, priority, job) -> None:
        if not priority:
            return
        self.run_worker(
            lambda: self._job_priority_blocking(job, priority),
            thread=True, exclusive=False, group="job-action",
        )

    def _job_priority_blocking(self, job, priority: str) -> None:
        client = self._client()
        if client is None:
            return
        full_handle = (job.raw or {}).get("handle", job.task_handle)
        try:
            drdata.set_job_priority(
                client, task_handle=full_handle, priority=priority,
            )
            msg = f"priority {priority}: {job.job}"
            colored = f"[green]{msg}[/]"
        except APIError as e:
            colored = (f"[yellow]priority {priority}: "
                       f"{e.error_code or e.status} {e.extended_status[:60]}[/]")
        except Exception as e:
            colored = f"[yellow]priority error: {e!r}[/]"
        self.app.call_from_thread(
            self.query_one("#jobs-detail", Static).update, colored,
        )
        self.app.call_from_thread(self.action_refresh)

    def _job_action_blocking(self, job, action: str) -> None:
        """Worker: pause / resume / cancel the selected job, then refresh."""
        client = self._client()
        if client is None:
            return
        # Need the full task handle, not the 16-char truncated form shown
        # in the table. The raw task carries the canonical `handle`.
        full_handle = (job.raw or {}).get("handle", job.task_handle)
        try:
            if action == "pause":
                ok = drdata.pause_task(client, task_handle=full_handle)
                msg = (f"paused: {job.job}" if ok
                       else f"could not pause {job.job} (state={job.state})")
            elif action == "resume":
                ok = drdata.resume_task(client, task_handle=full_handle)
                msg = (f"resumed: {job.job}" if ok
                       else f"could not resume {job.job} (state={job.state})")
            elif action == "cancel":
                drdata.cancel_task(client, task_handle=full_handle)
                msg = f"cancelled: {job.job}"
            else:
                msg = f"unknown action: {action}"
        except APIError as e:
            msg = (f"{action}: {e.error_code or e.status} "
                   f"{e.extended_status[:60]}")
        except Exception as e:
            msg = f"{action} error: {e!r}"
        bad = ("could not" in msg) or ("error" in msg) or (":" in msg and action in msg.split(":")[0])
        colored = f"[green]{msg}[/]" if not bad else f"[yellow]{msg}[/]"
        self.app.call_from_thread(
            self.query_one("#jobs-detail", Static).update, colored,
        )
        self.app.call_from_thread(self.action_refresh)

    def on_input_changed(self, evt: Input.Changed) -> None:
        if evt.input.id == "jobs-search":
            self._search = evt.value.lower()
            self._render_rows()

    def on_data_table_row_highlighted(self, evt) -> None:
        # Update detail pane on cursor move.
        try:
            idx = evt.cursor_row
        except Exception:
            return
        self._update_detail(idx)

    # ---- worker (fetches data) ----
    def _fetch_blocking(self) -> None:
        client = self._client()
        if client is None:
            return
        # v0.11: single `realmManager/listRealmTasks` call gives us
        # every task in the realm with pre-flat fields — no more
        # per-project listTasks fan-out. listJobs is still useful for
        # totalCores; we keep it as a cheap secondary call.
        try:
            _, total_cores = drdata.list_realm_jobs(client)
        except Exception:
            total_cores = 0
        try:
            rows, _ = drdata.list_realm_tasks(
                client, operation_type=self._type_filter,
            )
        except Exception:
            rows = []
        running = [r for r in rows if r.state == "RUNNING"]
        completed = [r for r in rows if r.state != "RUNNING"]
        try:
            deleted = drdata.list_deleted_projects(client)
        except Exception:
            deleted = []
        # Populate the operation-type dropdown lazily on first fetch —
        # one call per session is plenty (the enum doesn't change).
        if not self._op_types:
            try:
                self._op_types = drdata.list_operation_types(client)
            except Exception:
                self._op_types = []
        self.app.call_from_thread(
            self._apply, running, completed, deleted, total_cores,
        )

    def _client(self):
        app = self.app
        return app.sys_client or app.org_client

    def _apply(
        self, running, completed, deleted, total_cores,
    ) -> None:
        self._running = running
        self._completed = completed
        self._deleted = deleted
        self._total_cores = total_cores
        # Populate the operation-type dropdown once we have the enum.
        # `_op_types_populated` guards against repopulating on every
        # 5 s refresh tick (Textual's Select has no public options-len
        # accessor, so we track state ourselves).
        if self._op_types and not self._op_types_populated:
            try:
                sel = self.query_one("#jobs-type-select", Select)
                options = [("Any type", "")] + [(t, t) for t in self._op_types]
                sel.set_options(options)
                sel.value = self._type_filter or ""
                self._op_types_populated = True
            except Exception:
                pass
        self._render_rows()

    def _render_rows(self) -> None:
        t = self.query_one("#jobs-table", DataTable)
        t.clear()

        # Build the candidate set per filter mode.
        rows_view: list = []
        if self._state_filter == "deleted":
            for d in self._deleted:
                rows_view.append(("deleted", d))
        else:
            if self._state_filter in ("all", "running"):
                rows_view.extend(("running", r) for r in self._running)
            if self._state_filter in ("all", "complete"):
                rows_view.extend(("complete", r) for r in self._completed)

        # Search filter.
        q = (self._search or "").strip()
        def _match(kind: str, row) -> bool:
            if not q:
                return True
            if kind == "deleted":
                hay = f"{row.org_name} {row.project_name} {row.description}".lower()
            else:
                hay = f"{row.org} {row.project} {row.job} {row.user}".lower()
            return q in hay

        rows_view = [(k, r) for (k, r) in rows_view if _match(k, r)]

        # Render rows.
        self._displayed = []
        for kind, row in rows_view:
            self._displayed.append(row)
            if kind == "deleted":
                t.add_row(
                    row.org_name, row.project_name,
                    "[dim](project deleted)[/]",
                    "DELETED",
                    row.date_created or "—",
                    row.date_deleted or "—",
                    "—",
                    row.user_name,
                )
            else:
                state_disp = (f"[green]{row.state}[/]" if row.state == "RUNNING"
                              else f"[dim]{row.state}[/]")
                t.add_row(
                    row.org or "—", row.project, row.job, state_disp,
                    row.started or "—", row.completed or "—",
                    row.duration or "—", row.user or "—",
                )

        # Summary.
        self.query_one("#jobs-summary", Static).update(
            f"running=[green]{len(self._running)}[/]  "
            f"complete=[dim]{len(self._completed)}[/]  "
            f"deleted=[yellow]{len(self._deleted)}[/]  "
            f"showing=[b]{len(rows_view)}[/]  "
            f"cores=[cyan]{self._total_cores}[/]"
        )
        # Refresh detail to track first row.
        self._update_detail(0)

    def _update_detail(self, idx: int) -> None:
        body = self.query_one("#jobs-detail", Static)
        if idx is None or idx < 0 or idx >= len(self._displayed):
            body.update("[dim]Select a row to see full job detail.[/]")
            return
        item = self._displayed[idx]
        if isinstance(item, drdata.DeletedProject):
            body.update("\n".join([
                f"[b]Deleted Project[/]",
                f"[b]Project:[/] {item.project_name}  (id {item.project_id})",
                f"[b]Org:[/] {item.org_name}",
                f"[b]Description:[/] {item.description or '—'}",
                f"[b]Created:[/] {item.date_created or '—'}",
                f"[b]Deleted:[/] {item.date_deleted or '—'}  "
                f"[b]By:[/] {item.user_name or '—'}",
            ]))
        else:
            body.update(drdata.format_job_detail(item))


class PriorityModal(ModalScreen[Optional[str]]):
    """Pick HIGH / NORMAL / LOW for a job. Returns the chosen value or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("h", "pick('HIGH')",   "High",   show=False),
        Binding("n", "pick('NORMAL')", "Normal", show=False),
        Binding("l", "pick('LOW')",    "Low",    show=False),
    ]

    def __init__(self, *, job_label: str, current: str = "") -> None:
        super().__init__()
        self._job_label = job_label
        self._current = (current or "").upper()

    def compose(self) -> ComposeResult:
        with Container(id="priority-card"):
            yield Static(f"Set Priority — {self._job_label}", id="priority-title")
            current_line = (f"[dim]Current: {self._current}[/]"
                            if self._current else
                            "[dim]Pick the new priority below.[/]")
            yield Static(current_line, id="priority-current")
            with Horizontal(id="priority-buttons"):
                yield Button("High",   id="pri-high",   variant="error")
                yield Button("Normal", id="pri-normal", variant="primary")
                yield Button("Low",    id="pri-low",    variant="default")
                yield Button("Cancel", id="pri-cancel")
            yield Static(
                "[dim][h] High · [n] Normal · [l] Low · [Esc] cancel[/]",
                classes="modal-hint",
            )

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        bid = evt.button.id
        mapping = {"pri-high": "HIGH", "pri-normal": "NORMAL", "pri-low": "LOW"}
        if bid in mapping:
            self.dismiss(mapping[bid])
        elif bid == "pri-cancel":
            self.dismiss(None)

    def action_pick(self, priority: str) -> None:
        self.dismiss(priority)

    def action_cancel(self) -> None:
        self.dismiss(None)


class TaskLogModal(ModalScreen[None]):
    """v0.11 — live per-task AE log tail via `taskManager/getSRITaskLog`.

    Lookup chain on open:
      1. `taskManager/getTasks(includeDrDebug=true)` → find "Instance ID"
         under the "Service Node Debug State" status section.
      2. `taskManager/getSRITaskLog(taskSri, numLines=1000)` → render.

    Esc closes. `r` re-fetches. `n` cycles 1000 / 2000 / 3000 lines —
    same step the DR Web UI's "View More" button uses.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("r",      "refresh", "Refresh"),
        Binding("n",      "more",    "More lines", show=False),
    ]

    def __init__(self, *, job_label: str, task_handle: str) -> None:
        super().__init__()
        self._job_label = job_label
        self._task_handle = task_handle
        self._task_sri: Optional[str] = None
        self._num_lines = 1000

    def compose(self) -> ComposeResult:
        with Container(id="tasklog-card"):
            yield Static(
                f"Task Log — {self._job_label}",
                id="tasklog-title",
            )
            yield Static("[dim]Looking up taskSri…[/]", id="tasklog-status")
            yield RichLog(id="tasklog-body",
                          wrap=False, highlight=False, markup=False,
                          max_lines=5000)
            yield Static(
                "[dim][r] refresh · [n] +1000 lines · [Esc] close[/]",
                classes="modal-hint",
            )

    def on_mount(self) -> None:
        self.action_refresh()

    def action_dismiss(self, _result=None) -> None:
        self.dismiss(None)

    def action_refresh(self) -> None:
        self.run_worker(self._fetch_blocking, thread=True,
                        exclusive=True, group="tasklog-fetch")

    def action_more(self) -> None:
        # 1000 → 2000 → 3000 → wrap back to 1000. Matches DR UI behaviour.
        self._num_lines = 1000 if self._num_lines >= 3000 else self._num_lines + 1000
        self.action_refresh()

    def _client(self):
        app = self.app
        return getattr(app, "sys_client", None) or getattr(app, "org_client", None)

    def _fetch_blocking(self) -> None:
        client = self._client()
        if client is None:
            self.app.call_from_thread(
                self.query_one("#tasklog-status", Static).update,
                "[red]No active API client.[/]",
            )
            return
        # First call: discover the SRI if we don't have it yet.
        if not self._task_sri:
            try:
                sri = drdata.get_task_sri(client, task_handle=self._task_handle)
            except Exception as e:
                sri = None
                err = str(e)[:80]
            else:
                err = ""
            if not sri:
                self.app.call_from_thread(
                    self.query_one("#tasklog-status", Static).update,
                    f"[yellow]No taskSri found — task may have finished. "
                    f"{err}[/]",
                )
                return
            self._task_sri = sri
        # Second call: pull log lines.
        try:
            lines = drdata.get_sri_task_log(
                client, task_sri=self._task_sri, num_lines=self._num_lines,
            )
        except Exception as e:
            self.app.call_from_thread(
                self.query_one("#tasklog-status", Static).update,
                f"[red]Log fetch failed: {e!r}[/]",
            )
            return
        self.app.call_from_thread(self._apply_lines, lines)

    def _apply_lines(self, lines: list[str]) -> None:
        body = self.query_one("#tasklog-body", RichLog)
        body.clear()
        for line in lines:
            body.write(line)
        self.query_one("#tasklog-status", Static).update(
            f"[dim]taskSri={self._task_sri}  "
            f"lines={len(lines)}  buffer={self._num_lines}[/]"
        )


# === v0.12 Realm Settings edit modals ====================================== #

class MailServerFormModal(ModalScreen[Optional[dict]]):
    """v0.12 — edit SMTP host + port for `realmManager/createMailServerConfig`.

    Returns `{"smtp_host": str, "smtp_port": int}` on save, None on cancel.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, *, existing: Optional[drdata.MailServerConfig] = None) -> None:
        super().__init__()
        self._existing = existing

    def compose(self) -> ComposeResult:
        with Container(id="settings-card"):
            yield Static("Mail Server Configuration", id="settings-title")
            yield Label("SMTP host (FQDN / IP):")
            yield Input(
                value=(self._existing.smtp_host if self._existing else ""),
                placeholder="smtp.example.com",
                id="mail-host",
            )
            yield Label("SMTP port:")
            yield Input(
                value=str(self._existing.smtp_port if self._existing else 25),
                placeholder="25",
                id="mail-port",
            )
            yield Static("", id="settings-error")
            with Horizontal(classes="settings-buttons"):
                yield Button.success("Save", id="settings-save")
                yield Button("Cancel", id="settings-cancel")
            yield Static("[dim][Enter] save · [Esc] cancel · [Tab] next field[/]",
                         classes="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#mail-host", Input).focus()

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        if evt.button.id == "settings-cancel":
            self.dismiss(None)
        elif evt.button.id == "settings-save":
            self._save()

    def on_input_submitted(self, _evt: Input.Submitted) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        host = self.query_one("#mail-host", Input).value.strip()
        port_raw = self.query_one("#mail-port", Input).value.strip() or "0"
        err = self.query_one("#settings-error", Static)
        if not host:
            err.update("[red]SMTP host is required.[/]")
            return
        try:
            port = int(port_raw)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            err.update("[red]Port must be an integer in 1–65535.[/]")
            return
        self.dismiss({"smtp_host": host, "smtp_port": port})


class SplashMessageFormModal(ModalScreen[Optional[dict]]):
    """v0.12 — edit login-banner splash message via `setSplashMessage`.

    Returns `{"enabled": bool, "message": str}` on save, None on cancel.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, *, existing: Optional[drdata.SplashMessage] = None) -> None:
        super().__init__()
        self._existing = existing

    def compose(self) -> ComposeResult:
        with Container(id="settings-card"):
            yield Static("Splash Message (login banner)", id="settings-title")
            yield Checkbox(
                "Enabled (shown to users at login)",
                value=bool(self._existing and self._existing.enabled),
                id="splash-enabled",
            )
            yield Label("Message text:")
            yield TextArea(
                (self._existing.message if self._existing else ""),
                id="splash-message",
            )
            yield Static("", id="settings-error")
            with Horizontal(classes="settings-buttons"):
                yield Button.success("Save", id="settings-save")
                yield Button("Cancel", id="settings-cancel")
            yield Static("[dim][Esc] cancel · message can be multi-line[/]",
                         classes="modal-hint")

    def on_mount(self) -> None:
        # Focus the TextArea so users can start typing immediately.
        self.query_one("#splash-message", TextArea).focus()

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        if evt.button.id == "settings-cancel":
            self.dismiss(None)
        elif evt.button.id == "settings-save":
            self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        enabled = bool(self.query_one("#splash-enabled", Checkbox).value)
        message = self.query_one("#splash-message", TextArea).text
        # If enabling, require some text — empty enabled banner is a UX trap.
        if enabled and not message.strip():
            self.query_one("#settings-error", Static).update(
                "[red]Message text required when enabled.[/]"
            )
            return
        self.dismiss({"enabled": enabled, "message": message})


class PasswordPolicyFormModal(ModalScreen[Optional[dict]]):
    """v0.12 — edit realm password policy via `setPasswordPolicy`.

    Returns a `PasswordPolicy` instance on save, None on cancel.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, *, existing: Optional[drdata.PasswordPolicy] = None) -> None:
        super().__init__()
        # Default policy mirrors DR's out-of-box values (min_length=6,
        # everything else zero, 90-day expiration).
        self._existing = existing or drdata.PasswordPolicy(
            enforce_strong=False, min_length=6,
            min_uppercase=0, min_lowercase=0, min_numbers=0, min_symbols=0,
            expiration_days=90,
        )

    def compose(self) -> ComposeResult:
        e = self._existing
        with Container(id="settings-card"):
            yield Static("Password Policy", id="settings-title")
            yield Checkbox(
                "Enforce strong passwords",
                value=bool(e.enforce_strong),
                id="pwp-strong",
            )
            for field_id, label, value in (
                ("pwp-length",     "Minimum length:",            e.min_length),
                ("pwp-upper",      "Minimum uppercase letters:", e.min_uppercase),
                ("pwp-lower",      "Minimum lowercase letters:", e.min_lowercase),
                ("pwp-numbers",    "Minimum numbers:",           e.min_numbers),
                ("pwp-symbols",    "Minimum symbols:",           e.min_symbols),
                ("pwp-expiration", "Expiration (days, 0 = never):", e.expiration_days),
            ):
                yield Label(label)
                yield Input(value=str(value), id=field_id)
            yield Static("", id="settings-error")
            with Horizontal(classes="settings-buttons"):
                yield Button.success("Save", id="settings-save")
                yield Button("Cancel", id="settings-cancel")
            yield Static("[dim][Enter] save · [Esc] cancel · [Tab] next field[/]",
                         classes="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#pwp-length", Input).focus()

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        if evt.button.id == "settings-cancel":
            self.dismiss(None)
        elif evt.button.id == "settings-save":
            self._save()

    def on_input_submitted(self, _evt: Input.Submitted) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        err = self.query_one("#settings-error", Static)
        try:
            vals = {
                "min_length":      int(self.query_one("#pwp-length", Input).value or "0"),
                "min_uppercase":   int(self.query_one("#pwp-upper", Input).value or "0"),
                "min_lowercase":   int(self.query_one("#pwp-lower", Input).value or "0"),
                "min_numbers":     int(self.query_one("#pwp-numbers", Input).value or "0"),
                "min_symbols":     int(self.query_one("#pwp-symbols", Input).value or "0"),
                "expiration_days": int(self.query_one("#pwp-expiration", Input).value or "0"),
            }
        except ValueError:
            err.update("[red]All numeric fields must be integers.[/]")
            return
        if vals["min_length"] < 1:
            err.update("[red]Minimum length must be at least 1.[/]")
            return
        if any(v < 0 for v in vals.values()):
            err.update("[red]No field may be negative.[/]")
            return
        composition = (vals["min_uppercase"] + vals["min_lowercase"]
                       + vals["min_numbers"] + vals["min_symbols"])
        if composition > vals["min_length"]:
            err.update(
                f"[red]Composition requirements ({composition}) exceed "
                f"min length ({vals['min_length']}).[/]"
            )
            return
        self.dismiss(drdata.PasswordPolicy(
            enforce_strong=bool(self.query_one("#pwp-strong", Checkbox).value),
            **vals,
        ))


class InactivityTimeoutFormModal(ModalScreen[Optional[dict]]):
    """v0.12 — edit session inactivity timeout (seconds).

    Returns `{"seconds": int}` on save, None on cancel.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, *, existing: Optional[drdata.InactivityTimeout] = None) -> None:
        super().__init__()
        self._existing = existing

    def compose(self) -> ComposeResult:
        with Container(id="settings-card"):
            yield Static("Inactivity Timeout", id="settings-title")
            yield Label("Session timeout (seconds):")
            yield Input(
                value=str(self._existing.seconds if self._existing else 5940),
                placeholder="5940",
                id="inact-seconds",
            )
            yield Static(
                "[dim]Tip: 1800=30 min, 3600=1 h, 5940=99 min (DR default), "
                "0=disable timeout.[/]",
                classes="modal-hint",
            )
            yield Static("", id="settings-error")
            with Horizontal(classes="settings-buttons"):
                yield Button.success("Save", id="settings-save")
                yield Button("Cancel", id="settings-cancel")
            yield Static("[dim][Enter] save · [Esc] cancel[/]",
                         classes="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#inact-seconds", Input).focus()

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        if evt.button.id == "settings-cancel":
            self.dismiss(None)
        elif evt.button.id == "settings-save":
            self._save()

    def on_input_submitted(self, _evt: Input.Submitted) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        raw = self.query_one("#inact-seconds", Input).value.strip() or "0"
        err = self.query_one("#settings-error", Static)
        try:
            seconds = int(raw)
            if seconds < 0:
                raise ValueError
        except ValueError:
            err.update("[red]Seconds must be a non-negative integer.[/]")
            return
        self.dismiss({"seconds": seconds})


# === v0.13 New Job wizard ================================================== #

# Retention unit choices for the NewJobModal Select widget. Stored as a
# tuple (display, seconds-multiplier) so we can convert in one place.
_RETENTION_UNITS = [
    ("seconds", 1),
    ("minutes", 60),
    ("hours",   3600),
    ("days",    86400),
    ("weeks",   604800),
]


class NewJobModal(ModalScreen[Optional[dict]]):
    """v0.13 — New / Edit dialog for the Job Scheduler.

    Returns a dict shaped like JobDefinition (minus `created_at` /
    `slug`) on save, None on cancel. The DashboardScreen unpacks the
    dict into a JobDefinition and persists it via `drsch.save_job`.

    Org / Project / Connector are populated by the parent before the
    modal is pushed (passed in as ctor args) to keep the modal itself
    side-effect-free aside from the file-tree lazy loads.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        *,
        orgs: list[str],
        connectors_by_org: dict[str, list[drdata.Connector]],
        projects_by_org: dict[str, list[dict]],
        api_client,
        existing: Optional["drsch.JobDefinition"] = None,
    ) -> None:
        super().__init__()
        self._orgs = orgs or []
        self._connectors_by_org = connectors_by_org or {}
        self._projects_by_org = projects_by_org or {}
        self._client = api_client
        self._existing = existing
        # Track the currently-selected connector + path so the Tree
        # lazy-loader and Count-Files button have a stable target.
        self._cur_org: str = (existing.org if existing else
                              (orgs[0] if orgs else ""))
        self._cur_conn_handle: str = (existing.connector_handle if existing else "")
        self._cur_path: str = (existing.path if existing else "")

    # ---- compose -----------------------------------------------------
    def compose(self) -> ComposeResult:
        # Seed values for edit mode.
        e = self._existing
        with Container(id="newjob-card"):
            yield Static(
                ("Edit Job" if e else "New Indexing Job"),
                id="newjob-title",
            )
            with Horizontal(id="newjob-row1"):
                with Vertical(id="newjob-pickers"):
                    yield Label("Org:")
                    yield Select(
                        [(o, o) for o in self._orgs] or [("(none)", "")],
                        id="newjob-org",
                        value=(self._cur_org or (self._orgs[0] if self._orgs else "")),
                        allow_blank=False,
                    )
                    yield Label("Project:")
                    proj_opts = self._project_options(self._cur_org)
                    proj_select = Select(
                        proj_opts,
                        id="newjob-project",
                        allow_blank=False,
                    )
                    if e and any(v == e.project_handle for _, v in proj_opts):
                        proj_select.value = e.project_handle
                    yield proj_select
                    yield Label("Connector:")
                    conn_opts = self._connector_options(self._cur_org)
                    conn_select = Select(
                        conn_opts,
                        id="newjob-connector",
                        allow_blank=False,
                    )
                    if e and any(v == e.connector_handle for _, v in conn_opts):
                        conn_select.value = e.connector_handle
                    yield conn_select
                with Vertical(id="newjob-tree-wrap"):
                    yield Label("Filesystem (click a folder to expand):")
                    yield Tree("(pick a connector)", id="newjob-tree")
                    yield Static(
                        "[dim]Selected: —[/]",
                        id="newjob-selected",
                    )
                    with Horizontal(id="newjob-tree-actions"):
                        yield Button("Browse", id="newjob-browse",
                                     variant="primary")
                        yield Button("Count files (recursive)",
                                     id="newjob-count")
                    yield Static("", id="newjob-count-status")
            with Horizontal(id="newjob-meta"):
                with Vertical(classes="newjob-meta-col"):
                    yield Label("Job name:")
                    yield Input(
                        value=(e.name if e else ""),
                        placeholder="e.g. nightly-payroll-longterm",
                        id="newjob-name",
                    )
                    yield Label("Description (optional):")
                    yield Input(
                        value=(e.description if e else ""),
                        id="newjob-desc",
                    )
                with Vertical(classes="newjob-meta-col"):
                    yield Label("Retention period:")
                    with Horizontal():
                        yield Input(
                            value=str(self._initial_retention_value()),
                            id="newjob-retention",
                        )
                        yield Select(
                            [(u, str(m)) for u, m in _RETENTION_UNITS],
                            id="newjob-retention-unit",
                            value=str(self._initial_retention_mult()),
                            allow_blank=False,
                        )
                    yield Static(
                        "[dim]Indexed data + corpus auto-deleted after this "
                        "period. 0 = keep forever.[/]",
                        classes="modal-hint",
                    )
            yield Static("", id="newjob-error")
            with Horizontal(classes="settings-buttons"):
                yield Button.success("Save", id="newjob-save")
                yield Button("Cancel", id="newjob-cancel")
            yield Static("[dim][Esc] cancel · selecting a folder opens it[/]",
                         classes="modal-hint")

    def _project_options(self, org: str) -> list[tuple[str, str]]:
        projs = self._projects_by_org.get(org, [])
        out = []
        for p in projs:
            name = p.get("name") or "?"
            handle = str(p.get("handle") or "")
            if handle:
                out.append((name, handle))
        return out or [("(no projects)", "")]

    def _connector_options(self, org: str) -> list[tuple[str, str]]:
        conns = self._connectors_by_org.get(org, [])
        return [(f"{c.name}  ({c.type})", c.handle) for c in conns] \
            or [("(no connectors)", "")]

    def _initial_retention_value(self) -> int:
        if not self._existing:
            return 1                 # default: 1 week
        # Pick the largest unit that divides exactly.
        s = self._existing.retention_seconds
        for _, mult in reversed(_RETENTION_UNITS):
            if s % mult == 0 and s // mult >= 1:
                return s // mult
        return s

    def _initial_retention_mult(self) -> int:
        if not self._existing:
            return 604800              # weeks (default)
        s = self._existing.retention_seconds
        for _, mult in reversed(_RETENTION_UNITS):
            if s % mult == 0 and s // mult >= 1:
                return mult
        return 1

    # ---- mount -------------------------------------------------------
    def on_mount(self) -> None:
        # Build the root if we're in edit mode (so the user sees the
        # tree they previously navigated).
        if self._existing and self._cur_conn_handle:
            self._action_browse()
        self.query_one("#newjob-name", Input).focus()

    # ---- events ------------------------------------------------------
    def on_button_pressed(self, evt: Button.Pressed) -> None:
        bid = evt.button.id
        if bid == "newjob-cancel":
            self.dismiss(None)
        elif bid == "newjob-save":
            self._save()
        elif bid == "newjob-browse":
            self._action_browse()
        elif bid == "newjob-count":
            self._action_count()

    def on_select_changed(self, evt) -> None:
        sid = getattr(evt.select, "id", "")
        if sid == "newjob-org":
            org = evt.value if evt.value != Select.BLANK else ""
            self._cur_org = str(org)
            # Re-populate project + connector dropdowns from the new org.
            try:
                self.query_one("#newjob-project", Select).set_options(
                    self._project_options(self._cur_org)
                )
                self.query_one("#newjob-connector", Select).set_options(
                    self._connector_options(self._cur_org)
                )
            except Exception:
                pass
        elif sid == "newjob-connector":
            self._cur_conn_handle = (str(evt.value)
                                     if evt.value != Select.BLANK else "")

    def action_cancel(self) -> None:
        self.dismiss(None)

    # ---- file tree ---------------------------------------------------
    def _selected_connector(self) -> Optional[drdata.Connector]:
        conns = self._connectors_by_org.get(self._cur_org, [])
        for c in conns:
            if c.handle == self._cur_conn_handle:
                return c
        return None

    def _action_browse(self) -> None:
        """Repopulate the tree with the connector root listing."""
        conn = self._selected_connector()
        if conn is None:
            self.query_one("#newjob-error", Static).update(
                "[red]Pick an org + connector first.[/]"
            )
            return
        self.query_one("#newjob-error", Static).update("")
        tree = self.query_one("#newjob-tree", Tree)
        tree.reset(conn.path or conn.host or conn.name,
                   data={"path": conn.path or "", "leaf": False,
                         "loaded": False, "host": conn.host,
                         "ctype": conn.type, "cname": conn.name})
        # Fire the lazy-loader on the root.
        self.run_worker(
            lambda: self._load_children_blocking(tree.root),
            thread=True, exclusive=False, group="newjob-tree",
        )

    def on_tree_node_selected(self, evt) -> None:
        node = evt.node
        data = node.data or {}
        # Remember the current path for "Count Files" / "Save".
        self._cur_path = str(data.get("path") or "")
        self.query_one("#newjob-selected", Static).update(
            f"[dim]Selected: {self._cur_path or '(connector root)'}[/]"
        )
        # Lazy-load children if this is a directory we haven't expanded yet.
        if data.get("leaf"):
            return
        if data.get("loaded"):
            return
        self.run_worker(
            lambda: self._load_children_blocking(node),
            thread=True, exclusive=False, group="newjob-tree",
        )

    def _load_children_blocking(self, node) -> None:
        data = node.data or {}
        conn = self._selected_connector()
        if conn is None or self._client is None:
            return
        try:
            entries = drdata.explore_connector(
                self._client,
                org_name=self._cur_org,
                connector_name=conn.name,
                connector_type=conn.type,
                remote_host=conn.host,
                remote_path=conn.path or "",
                parent_path=data.get("path") or conn.path or "",
            )
        except Exception:
            entries = []
        self.app.call_from_thread(self._apply_children, node, entries)

    def _apply_children(self, node, entries: list[drdata.PathEntry]) -> None:
        node.remove_children()
        parent_path = (node.data or {}).get("path") or ""
        for e in entries:
            child_path = (parent_path.rstrip("/") + "/" + e.name).lstrip("/")
            label = (f"[dim]🗎[/] {e.name}" if e.leaf
                     else f"[b]🗀[/] {e.name}")
            child_data = {
                "path": child_path,
                "leaf": e.leaf,
                "loaded": False,
            }
            if e.leaf:
                node.add_leaf(label, data=child_data)
            else:
                node.add(label, data=child_data)
        if node.data is not None:
            node.data["loaded"] = True
        node.expand()

    # ---- count files -------------------------------------------------
    def _action_count(self) -> None:
        conn = self._selected_connector()
        if conn is None:
            self.query_one("#newjob-error", Static).update(
                "[red]Pick a connector first.[/]"
            )
            return
        if not self._cur_path:
            self.query_one("#newjob-error", Static).update(
                "[red]Select a directory in the tree first.[/]"
            )
            return
        self.query_one("#newjob-count-status", Static).update(
            "[yellow]counting…[/]"
        )
        self.run_worker(
            self._count_blocking, thread=True, exclusive=True,
            group="newjob-count",
        )

    def _count_blocking(self) -> None:
        conn = self._selected_connector()
        if conn is None: return

        def _cb(files, dirs, current):
            try:
                self.app.call_from_thread(
                    self.query_one("#newjob-count-status", Static).update,
                    f"[yellow]counting… {files} files / {dirs} dirs  "
                    f"current={current[:40]}[/]",
                )
            except Exception:
                pass

        try:
            files, dirs = drdata.count_files_recursively(
                self._client,
                org_name=self._cur_org,
                connector_name=conn.name,
                connector_type=conn.type,
                remote_host=conn.host,
                remote_path=conn.path or "",
                root_path=self._cur_path,
                progress_cb=_cb,
            )
        except Exception as e:
            self.app.call_from_thread(
                self.query_one("#newjob-count-status", Static).update,
                f"[red]count error: {e!r}[/]",
            )
            return
        self.app.call_from_thread(
            self.query_one("#newjob-count-status", Static).update,
            f"[green]{files} files, {dirs} dirs under "
            f"{self._cur_path}[/]  "
            f"[dim](no byte total — DR API exposes no size)[/]",
        )

    # ---- save --------------------------------------------------------
    def _save(self) -> None:
        err = self.query_one("#newjob-error", Static)
        name = self.query_one("#newjob-name", Input).value.strip()
        if not name:
            err.update("[red]Job name is required.[/]")
            return
        try:
            project = str(self.query_one("#newjob-project", Select).value or "")
            connector_handle = str(
                self.query_one("#newjob-connector", Select).value or ""
            )
        except Exception:
            project = connector_handle = ""
        if not project or not connector_handle:
            err.update("[red]Pick a project + connector first.[/]")
            return
        if not self._cur_path:
            err.update("[red]Pick a directory in the tree before saving.[/]")
            return
        try:
            ret_raw = self.query_one("#newjob-retention", Input).value.strip() or "0"
            ret_n = int(ret_raw)
            ret_mult = int(self.query_one(
                "#newjob-retention-unit", Select,
            ).value or "1")
            ret_seconds = ret_n * ret_mult
            if ret_seconds < 0:
                raise ValueError
        except ValueError:
            err.update("[red]Retention must be a non-negative integer.[/]")
            return

        conn = self._selected_connector()
        payload = {
            "name": name,
            "org": self._cur_org,
            "project_handle": project,
            "connector_name": (conn.name if conn else ""),
            "connector_handle": connector_handle,
            "connector_type": (conn.type if conn else "NFS"),
            "remote_host": (conn.host if conn else ""),
            "remote_path": (conn.path if conn else ""),
            "path": self._cur_path,
            "retention_seconds": ret_seconds,
            "description": self.query_one("#newjob-desc", Input).value.strip(),
        }
        self.dismiss(payload)


class HelpModal(ModalScreen[None]):
    """F1 — keyboard reference. Dismiss with any key."""

    BINDINGS = [
        Binding("escape,f1,q,enter,space", "dismiss", "Close", show=False),
    ]

    HELP_TEXT = (
        "[b]dr-tui — Keyboard reference[/]\n\n"
        "[b cyan]Global[/]\n"
        "  F1            this help screen\n"
        "  F2            toggle DR documentation side-pane\n"
        "  F3            realm-wide Jobs Monitor modal\n"
        "  F5            refresh current view\n"
        "  F10  /  q     quit\n"
        "  Tab           cycle focus (tree ↔ table)\n"
        "  1  /  2       jump to System Settings / Organizations\n"
        "  l             logout (back to login)\n\n"
        "[b cyan]Within a view (System Settings)[/]\n"
        "  F7            New entity (depot, user, group)\n"
        "  F4            Edit selected row\n"
        "  F8            Delete selected row\n"
        "  F6            Reset password (on Users) / Update Now (on Virus)\n\n"
        "[b cyan]In tree[/]\n"
        "  ↑ / ↓         move cursor\n"
        "  Enter / Space expand / collapse / select leaf\n\n"
        "[b cyan]In table[/]\n"
        "  ↑ / ↓         move row cursor\n"
        "  PgUp / PgDn   page-scroll\n"
        "  Home / End    first / last row\n\n"
        "[b cyan]In a form modal[/]\n"
        "  Tab           next field / button\n"
        "  Enter         save (when in an Input field)\n"
        "  Esc           cancel and close\n\n"
        "[dim]Press any key to close.[/]"
    )

    def compose(self) -> ComposeResult:
        with Container(id="help-card"):
            yield Static(self.HELP_TEXT, id="help-body")

    def on_key(self, evt) -> None:
        # Any key dismisses (the BINDINGS catch common ones; this is a
        # safety net for keys not in the bindings list).
        self.dismiss(None)


# ============================================================ Dashboard screen
class DashboardScreen(Screen):
    # Midnight Commander-style F-key action bar. Actions dispatch on the
    # currently-selected leaf (`selected_kind`) so the same F-key drives
    # depots, users, groups depending on context. Legacy single-letter
    # aliases (`q`/`r`/`l`) stay as hidden bindings so old muscle memory
    # still works.
    BINDINGS = [
        Binding("f1",  "show_help",   "Help"),
        Binding("f2",  "toggle_doc",  "Docs"),
        Binding("f3",  "jobs_monitor","Jobs"),
        Binding("f4",  "ctx_edit",    "Edit"),
        Binding("f5",  "refresh_now", "Refresh"),
        Binding("f6",  "ctx_reset",   "Reset PW"),
        Binding("f7",  "ctx_new",     "New"),
        Binding("f8",  "ctx_delete",  "Delete"),
        Binding("f10", "app.quit",    "Quit"),
        Binding("tab", "focus_next",  "Cycle pane"),
        Binding("1",   "switch_tab('tab-sys')",  "Sys", show=False),
        Binding("2",   "switch_tab('tab-orgs')", "Orgs", show=False),
        # Legacy aliases — kept for muscle memory but hidden from footer.
        Binding("q", "app.quit",     "Quit",    show=False),
        Binding("r", "refresh_now",  "Refresh", show=False),
        Binding("l", "logout",       "Logout",  show=False),
    ]

    last_status: reactive[str] = reactive("")
    selected_kind: reactive[str] = reactive("")     # e.g. "org-connectors"
    selected_org: reactive[str] = reactive("")
    # F2 help side-pane visibility (per-tab, but a single shared flag —
    # the active tab's pane is the one that responds to F2).
    help_visible: reactive[bool] = reactive(False)

    # cursor-row → StorageDepot, keyed by table id. Refreshed on every
    # _apply_storage_depots() so CRUD actions can resolve the selected row.
    _depots_by_table: dict[str, list]
    # Row cache + role catalogue for the system-users CRUD layer.
    _sys_users_rows: list
    _sys_groups_rows: list
    _system_roles: list
    # Connector row cache (Org panel → cursor → Connector).
    _connectors_rows: list
    # Last-read virus defs — used by the "Update Now" handler to preserve
    # enabled/frequency on the trigger call.
    _virus_last: Optional["drdata.VirusDefs"]
    # v0.12 — last-read Realm Settings, used to pre-populate edit modals.
    _mail_last:       Optional["drdata.MailServerConfig"]
    _splash_last:     Optional["drdata.SplashMessage"]
    _pwpolicy_last:   Optional["drdata.PasswordPolicy"]
    _inactivity_last: Optional["drdata.InactivityTimeout"]

    # ---- Landing dashboard state ----
    _metrics_prev: Optional["drmetrics.MetricsSample"]
    _metrics_history: "drmetrics.MetricsHistory"
    _log_tailer: Optional["drmetrics.LogTailer"]
    _log_filter: set        # subset of {"INFO","WARN","ERROR"}; "" always shown

    # ---------------------------------------------------------- compose
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="status-bar")
        with TabbedContent(id="main-tabs", initial="tab-dashboard"):
            # ----------------------- Dashboard (DRSysAdmin only) -----------
            with TabPane("Dashboard", id="tab-dashboard"):
                with Vertical(id="dash-root"):
                    # Top row: License + Realm Node summary, side by side.
                    with Horizontal(id="dash-top"):
                        with Vertical(id="dash-license-card", classes="dash-card"):
                            yield Static("License", classes="dash-title")
                            yield Static("Loading…", id="dash-license-body",
                                         classes="dash-body")
                        with Vertical(id="dash-node-card", classes="dash-card"):
                            yield Static("Realm Node — Status Details",
                                         classes="dash-title")
                            yield Static("Loading…", id="dash-node-body",
                                         classes="dash-body")
                    # Metrics strip.
                    with Vertical(id="dash-metrics-card", classes="dash-card"):
                        yield Static("System Metrics", classes="dash-title")
                        with Horizontal(id="dash-metrics-row"):
                            with Vertical(classes="dash-metric-col"):
                                yield Static("CPU —", id="dash-cpu-text")
                                yield Sparkline([0], id="dash-cpu-spark",
                                                summary_function=max)
                            with Vertical(classes="dash-metric-col"):
                                yield Static("Memory —", id="dash-mem-text")
                                yield Sparkline([0], id="dash-mem-spark",
                                                summary_function=max)
                            with Vertical(classes="dash-metric-col"):
                                yield Static("Net / IOPS —", id="dash-net-text")
                    # Logs + processes — side by side if room.
                    with Horizontal(id="dash-bottom"):
                        with Vertical(id="dash-logs-card", classes="dash-card"):
                            with Horizontal(id="dash-log-header"):
                                yield Static("Logs (tail -f AHS/output/*.log)",
                                             classes="dash-title")
                                yield Button("INFO",  id="dash-flt-info",  variant="primary")
                                yield Button("WARN",  id="dash-flt-warn",  variant="warning")
                                yield Button("ERROR", id="dash-flt-error", variant="error")
                            yield RichLog(id="dash-log",
                                          highlight=False, markup=True,
                                          wrap=False, max_lines=2000)
                        with Vertical(id="dash-procs-card", classes="dash-card"):
                            yield Static("Top processes (ps aux)",
                                         classes="dash-title")
                            yield DataTable(id="dash-procs-table",
                                            zebra_stripes=True, cursor_type="row")

            # ----------------------- System Settings (DRSysAdmin only) -----
            with TabPane("System Settings", id="tab-sys"):
                with Horizontal(id="sys-h"):
                    yield Tree("System", id="sys-tree")
                    with ContentSwitcher(id="sys-switcher", initial="sys-placeholder"):
                        yield Static(
                            "Select an item from the tree.\n\n"
                            "v0.05 read-only views are wired below; "
                            "create / edit / delete arrive in v0.06.",
                            id="sys-placeholder",
                        )
                        with Vertical(id="sys-doc-depots-view"):
                            yield Static("Document Storage Depots", classes="panel-title")
                            with Horizontal(classes="action-bar"):
                                yield Button("New", id="doc-depot-new", variant="success")
                                yield Button("Edit", id="doc-depot-edit")
                                yield Button("Delete", id="doc-depot-delete", variant="error")
                            yield DataTable(id="sys-doc-depots-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="sys-idx-depots-view"):
                            yield Static("Index Storage Depots", classes="panel-title")
                            with Horizontal(classes="action-bar"):
                                yield Button("New", id="idx-depot-new", variant="success")
                                yield Button("Edit", id="idx-depot-edit")
                                yield Button("Delete", id="idx-depot-delete", variant="error")
                            yield DataTable(id="sys-idx-depots-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="sys-sysdepot-view"):
                            yield Static("System Storage Depot", classes="panel-title")
                            yield Static("Loading…", id="sys-sysdepot-body",
                                         classes="detail-body")
                        with Vertical(id="sys-virus-view"):
                            yield Static("Virus Detection", classes="panel-title")
                            with Horizontal(classes="action-bar"):
                                yield Button("Update Now", id="sys-virus-update",
                                             variant="primary")
                            yield Static("Loading…", id="sys-virus-body",
                                         classes="detail-body")
                        with Vertical(id="sys-users-view"):
                            yield Static("System Users", classes="panel-title")
                            with Horizontal(classes="action-bar"):
                                yield Button("New", id="sys-user-new", variant="success")
                                yield Button("Edit", id="sys-user-edit")
                                yield Button("Reset PW", id="sys-user-reset")
                                yield Button("Delete", id="sys-user-delete", variant="error")
                            yield DataTable(id="sys-users-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="sys-groups-view"):
                            yield Static("System Groups", classes="panel-title")
                            with Horizontal(classes="action-bar"):
                                yield Button("New", id="sys-group-new", variant="success")
                                yield Button("Edit", id="sys-group-edit")
                                yield Button("Delete", id="sys-group-delete", variant="error")
                            yield DataTable(id="sys-groups-table",
                                            zebra_stripes=True, cursor_type="row")
                        # ---- Realm Settings sub-tree (v0.08) ----
                        with Vertical(id="sys-mail-view"):
                            yield Static("Mail Server", classes="panel-title")
                            with Horizontal(classes="settings-actions"):
                                yield Button("Edit", id="sys-mail-edit",
                                             variant="primary")
                            yield Static("Loading…", id="sys-mail-body",
                                         classes="detail-body")
                        with Vertical(id="sys-splash-view"):
                            yield Static("Splash Message", classes="panel-title")
                            with Horizontal(classes="settings-actions"):
                                yield Button("Edit", id="sys-splash-edit",
                                             variant="primary")
                            yield Static("Loading…", id="sys-splash-body",
                                         classes="detail-body")
                        with Vertical(id="sys-pwpolicy-view"):
                            yield Static("Password Policy", classes="panel-title")
                            with Horizontal(classes="settings-actions"):
                                yield Button("Edit", id="sys-pwpolicy-edit",
                                             variant="primary")
                            yield Static("Loading…", id="sys-pwpolicy-body",
                                         classes="detail-body")
                        with Vertical(id="sys-inactivity-view"):
                            yield Static("Inactivity Timeout", classes="panel-title")
                            with Horizontal(classes="settings-actions"):
                                yield Button("Edit", id="sys-inactivity-edit",
                                             variant="primary")
                            yield Static("Loading…", id="sys-inactivity-body",
                                         classes="detail-body")
                    # F2 help side-pane — hidden by default; populated by
                    # `_help_apply` when toggled on.
                    yield Markdown("", id="sys-help-pane", classes="help-pane")

            # ----------------------- Organizations (both roles) ------------
            with TabPane("Organizations", id="tab-orgs"):
                with Horizontal(id="orgs-h"):
                    yield Tree("Organizations", id="orgs-tree")
                    with ContentSwitcher(id="orgs-switcher", initial="orgs-placeholder"):
                        yield Static(
                            "Select an organization from the tree on the left.",
                            id="orgs-placeholder",
                        )
                        with Vertical(id="org-users-view"):
                            yield Static("Users", classes="panel-title")
                            yield DataTable(id="org-users-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="org-admins-view"):
                            yield Static("Admins", classes="panel-title")
                            yield DataTable(id="org-admins-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="org-groups-view"):
                            yield Static("Groups", classes="panel-title")
                            yield DataTable(id="org-groups-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="org-projects-view"):
                            yield Static("Projects", classes="panel-title")
                            yield DataTable(id="org-projects-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="org-running-view"):
                            yield Static("Running Jobs", classes="panel-title")
                            yield DataTable(id="running-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="org-completed-view"):
                            yield Static("Completed Jobs", classes="panel-title")
                            yield DataTable(id="completed-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="org-connectors-view"):
                            yield Static("Connectors", classes="panel-title")
                            with Horizontal(classes="action-bar"):
                                yield Button("Deactivate", id="conn-deactivate",
                                             variant="warning")
                            yield DataTable(id="connectors-table",
                                            zebra_stripes=True, cursor_type="row")
                        with Vertical(id="org-storage-view"):
                            yield Static("Storage", classes="panel-title")
                            yield DataTable(id="org-storage-table",
                                            zebra_stripes=True, cursor_type="row")
                    # F2 help side-pane — same pattern as the System Settings tab.
                    yield Markdown("", id="orgs-help-pane", classes="help-pane")

            # ----------------------- Job Scheduler (v0.13) -----------------
            with TabPane("Job Scheduler", id="tab-scheduler"):
                with Vertical():
                    with Horizontal(id="scheduler-actions"):
                        yield Button("New Job", id="sch-new",
                                     variant="success")
                        yield Button("Run", id="sch-run", variant="primary")
                        yield Button("Edit", id="sch-edit")
                        yield Button("Delete", id="sch-delete",
                                     variant="error")
                        yield Button("Refresh", id="sch-refresh")
                    with Horizontal():
                        yield Tree("Scheduler", id="scheduler-tree")
                        with ContentSwitcher(id="scheduler-switcher",
                                             initial="sch-running-view"):
                            with Vertical(id="sch-running-view"):
                                yield Static("Running Jobs",
                                             classes="panel-title")
                                yield DataTable(id="sch-running-table",
                                                zebra_stripes=True,
                                                cursor_type="row")
                            with Vertical(id="sch-saved-view"):
                                yield Static("Saved Job Templates",
                                             classes="panel-title")
                                yield DataTable(id="sch-saved-table",
                                                zebra_stripes=True,
                                                cursor_type="row")
                            with Vertical(id="sch-timers-view"):
                                yield Static("Scheduled Retention Timers",
                                             classes="panel-title")
                                yield DataTable(id="sch-timers-table",
                                                zebra_stripes=True,
                                                cursor_type="row")
                            with Vertical(id="sch-runs-view"):
                                yield Static("Run History",
                                             classes="panel-title")
                                yield DataTable(id="sch-runs-table",
                                                zebra_stripes=True,
                                                cursor_type="row")
        yield Footer()

    # ---------------------------------------------------------- mount
    def on_mount(self) -> None:
        self._depots_by_table = {"sys-doc-depots-table": [], "sys-idx-depots-table": []}
        self._sys_users_rows = []
        self._sys_groups_rows = []
        self._system_roles = []
        self._connectors_rows = []
        self._virus_last = None
        self._mail_last = None
        self._splash_last = None
        self._pwpolicy_last = None
        self._inactivity_last = None
        self._metrics_prev = None
        self._metrics_history = drmetrics.MetricsHistory(max_points=60)
        self._log_filter = {"INFO", "WARN", "ERROR"}
        # AHS log location is a known constant for the lab/install — overridable.
        self._log_tailer = drmetrics.LogTailer(
            ["/home/auraria/AHS/output/*.log"], start_from_end=True,
        )
        drmetrics.prime_cpu_percent()
        # Initialize DataTable columns once.
        self.query_one("#sys-doc-depots-table", DataTable).add_columns(
            "Name", "FQDN", "Export", "In-Service", "Used", "Available", "Allocation",
        )
        self.query_one("#sys-idx-depots-table", DataTable).add_columns(
            "Name", "FQDN", "Export", "In-Service", "Used", "Available", "Allocation",
        )
        self.query_one("#sys-users-table", DataTable).add_columns(
            "User", "Display", "Email", "Enabled", "Locked", "MFA", "Last Access", "Roles",
        )
        self.query_one("#sys-groups-table", DataTable).add_columns(
            "Group", "Description", "Members",
        )
        self.query_one("#org-users-table", DataTable).add_columns(
            "User", "Display", "Email", "Enabled", "Locked", "MFA", "Last Access", "Roles",
        )
        self.query_one("#org-admins-table", DataTable).add_columns(
            "User", "Display", "Email", "Enabled", "Locked", "MFA", "Last Access", "Roles",
        )
        self.query_one("#org-groups-table", DataTable).add_columns(
            "Group", "Description", "Members",
        )
        self.query_one("#org-projects-table", DataTable).add_columns(
            "Project", "Handle", "Created", "State",
        )
        self.query_one("#connectors-table", DataTable).add_columns(
            "Name", "Type", "Mode", "Host", "Path", "Status",
        )
        self.query_one("#running-table", DataTable).add_columns(
            "Project", "Job", "Task", "Elapsed",
        )
        self.query_one("#completed-table", DataTable).add_columns(
            "Project", "Job", "Task", "Completed", "Took",
        )
        self.query_one("#org-storage-table", DataTable).add_columns(
            "Depot", "Use", "Used", "Available",
        )
        # v0.13 Job Scheduler tables.
        self.query_one("#sch-running-table", DataTable).add_columns(
            "Org", "Project", "Job", "State", "Started", "Duration", "User",
        )
        self.query_one("#sch-saved-table", DataTable).add_columns(
            "Job Name", "Org", "Path", "Retention", "Description",
        )
        self.query_one("#sch-timers-table", DataTable).add_columns(
            "Unit", "Next fire", "Time left", "Activates",
        )
        self.query_one("#sch-runs-table", DataTable).add_columns(
            "Run ID", "Started", "Status", "Task Handle", "Finished",
        )

        self._populate_sys_tree()
        self._populate_scheduler_tree()

        # F2 help panes — both default to hidden. F2 toggles whichever tab
        # the user is currently on.
        for pane_id in ("#sys-help-pane", "#orgs-help-pane"):
            try:
                self.query_one(pane_id, Markdown).display = False
            except Exception:
                pass

        # Role-gate: hide System Settings tab for admin@training.
        if self.app.role == ROLE_ORG:
            tabs = self.query_one("#main-tabs", TabbedContent)
            for hidden in ("tab-sys", "tab-dashboard"):
                try:
                    tabs.hide_tab(hidden)
                except Exception:
                    pass
            tabs.active = "tab-orgs"

        # Async populate Organizations tree.
        self.run_worker(self._load_orgs_tree, thread=True, group="orgs-tree")

        # Auto-refresh ticks the currently-visible view's loader.
        self.set_interval(5.0, self.action_refresh_now)

        # ---- Dashboard timers (DRSysAdmin only — needs the realm client) ----
        if self.app.role == ROLE_SYS:
            # Initialize the processes DataTable columns.
            pt = self.query_one("#dash-procs-table", DataTable)
            pt.add_columns("PID", "USER", "CPU%", "MEM%", "CMD")
            # Fast (metrics) and slow (license + node + processes) cycles.
            self.set_interval(2.0, self._dash_tick_metrics)
            self.set_interval(1.0, self._dash_tick_logs)
            self.set_interval(3.0, self._dash_tick_procs)
            self.set_interval(30.0, self._dash_tick_realm)
            # Initial paint.
            self.call_after_refresh(self._dash_tick_realm)
            self.call_after_refresh(self._dash_tick_procs)
            self.call_after_refresh(self._dash_tick_metrics)
            self.call_after_refresh(self._dash_tick_logs)

    # ---------------------------------------------------------- tree builders
    def _populate_sys_tree(self) -> None:
        t = self.query_one("#sys-tree", Tree)
        t.show_root = False
        t.root.expand()
        storage = t.root.add("Storage", data={"kind": "sys-storage-cat"}, expand=True)
        storage.add_leaf("Document Storage Depots", data={"kind": "sys-doc-depots"})
        storage.add_leaf("Index Storage Depots", data={"kind": "sys-idx-depots"})
        t.root.add_leaf("System Storage Depot", data={"kind": "sys-sysdepot"})
        t.root.add_leaf("Virus Detection", data={"kind": "sys-virus"})
        t.root.add_leaf("System Users", data={"kind": "sys-users"})
        t.root.add_leaf("System Groups", data={"kind": "sys-groups"})
        # v0.08 Realm Settings sub-tree.
        realm = t.root.add("Realm Settings",
                            data={"kind": "sys-realm-cat"}, expand=False)
        realm.add_leaf("Mail Server",        data={"kind": "sys-mail"})
        realm.add_leaf("Splash Message",     data={"kind": "sys-splash"})
        realm.add_leaf("Password Policy",    data={"kind": "sys-pwpolicy"})
        realm.add_leaf("Inactivity Timeout", data={"kind": "sys-inactivity"})

    def _populate_scheduler_tree(self) -> None:
        """v0.13 — tree on the Job Scheduler tab: four leaf views."""
        t = self.query_one("#scheduler-tree", Tree)
        t.show_root = False
        t.root.expand()
        t.root.add_leaf("Running Jobs",         data={"kind": "sch-running"})
        t.root.add_leaf("Saved Templates",      data={"kind": "sch-saved"})
        t.root.add_leaf("Retention Timers",     data={"kind": "sch-timers"})
        t.root.add_leaf("Run History",          data={"kind": "sch-runs"})
        # Default landing: Saved Templates (matches what most users open
        # the tab to do — pick a job and run it).
        self.query_one("#scheduler-switcher", ContentSwitcher).current = \
            "sch-saved-view"

    def _load_orgs_tree(self) -> None:
        orgs: list[drdata.OrgInfo] = []
        try:
            if self.app.role == ROLE_SYS and self.app.sys_client is not None:
                orgs = drdata.list_organizations_sys(self.app.sys_client)
            elif self.app.org_client is not None:
                orgs = [drdata.OrgInfo(
                    name=self.app.org_client.cfg.organization,
                    handle="",
                )]
        except APIError as e:
            self.app.call_from_thread(self._post_status, f"orgs: {e.error_code or e.status}")
        except Exception as e:
            self.app.call_from_thread(self._post_status, f"orgs error: {e!r}")
        self.app.call_from_thread(self._apply_orgs_tree, orgs)

    def _apply_orgs_tree(self, orgs: list[drdata.OrgInfo]) -> None:
        t = self.query_one("#orgs-tree", Tree)
        t.show_root = False
        t.root.expand()
        for child in list(t.root.children):
            child.remove()
        for o in orgs:
            org_node = t.root.add(o.name, data={"kind": "org-root", "org": o.name})
            org_node.add_leaf("Users",          data={"kind": "org-users",      "org": o.name})
            org_node.add_leaf("Admins",         data={"kind": "org-admins",     "org": o.name})
            org_node.add_leaf("Groups",         data={"kind": "org-groups",     "org": o.name})
            org_node.add_leaf("Projects",       data={"kind": "org-projects",   "org": o.name})
            org_node.add_leaf("Running Jobs",   data={"kind": "org-running",    "org": o.name})
            org_node.add_leaf("Completed Jobs", data={"kind": "org-completed",  "org": o.name})
            org_node.add_leaf("Connectors",     data={"kind": "org-connectors", "org": o.name})
            org_node.add_leaf("Storage",        data={"kind": "org-storage",    "org": o.name})

    # ---------------------------------------------------------- routing
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data or {}
        kind = data.get("kind", "")
        org = data.get("org", "")

        if kind in SYS_VIEW_MAP:
            self.query_one("#sys-switcher", ContentSwitcher).current = SYS_VIEW_MAP[kind]
            self.selected_kind = kind
            self.selected_org = ""
            self._load_view(kind, "")
            if self.help_visible:
                self._refresh_help_pane()
            return

        if kind in ORG_VIEW_MAP:
            self.query_one("#orgs-switcher", ContentSwitcher).current = ORG_VIEW_MAP[kind]
            self.selected_kind = kind
            self.selected_org = org or self.app.target_org
            if org:
                self.app.target_org = org
            self._load_view(kind, self.selected_org)
            if self.help_visible:
                self._refresh_help_pane()
            return

        if kind in SCH_VIEW_MAP:
            self.query_one("#scheduler-switcher", ContentSwitcher).current = \
                SCH_VIEW_MAP[kind]
            self.selected_kind = kind
            self.selected_org = ""
            self._load_view(kind, "")
            return

        # Non-leaf clicks (category headings, org root) — keep current pane.

    # ---------------------------------------------------------- view loader
    def _load_view(self, kind: str, org: str) -> None:
        """Fetch data for *kind* on a worker thread, apply on UI thread."""
        self.run_worker(
            lambda: self._fetch_view(kind, org),
            thread=True, exclusive=True, group="view",
        )

    def _client_for_org(self, org: str) -> EDiscoveryClient | None:
        """Pick the right client + ensure org context if needed."""
        role = self.app.role
        if role == ROLE_SYS:
            c = self.app.sys_client
            if c is None or not org:
                return c
            try:
                drdata.ensure_org_context(c, org)
            except Exception:
                pass
            return c
        return self.app.org_client

    def _fetch_view(self, kind: str, org: str) -> None:
        worker = get_current_worker()
        try:
            # ----- system settings (sys client required) -----
            sys_c = self.app.sys_client
            if kind in SYS_VIEW_MAP and sys_c is None:
                self._post_status("system settings unavailable for this role")
                return

            if kind == "sys-doc-depots":
                rows = drdata.list_storage_depots(sys_c, "DOCUMENT_STORE")
                self._cb(worker, self._apply_storage_depots, "sys-doc-depots-table", rows)
            elif kind == "sys-idx-depots":
                rows = drdata.list_storage_depots(sys_c, "INDEX_STORE")
                self._cb(worker, self._apply_storage_depots, "sys-idx-depots-table", rows)
            elif kind == "sys-sysdepot":
                depot = drdata.get_system_storage_depot(sys_c)
                self._cb(worker, self._apply_sysdepot, depot)
            elif kind == "sys-virus":
                v = drdata.get_virus_definitions(sys_c)
                self._cb(worker, self._apply_virus, v)
            elif kind in ("sys-users", "sys-groups"):
                users, groups = drdata.list_system_users_and_groups(sys_c)
                self._cb(worker, self._apply_sys_users_groups, users, groups)

            # ----- realm settings (v0.08) -----
            elif kind == "sys-mail":
                cfg = drdata.get_mail_server_config(sys_c)
                self._cb(worker, self._apply_mail, cfg)
            elif kind == "sys-splash":
                sp = drdata.get_splash_message(sys_c)
                self._cb(worker, self._apply_splash, sp)
            elif kind == "sys-pwpolicy":
                pp = drdata.get_password_policy(sys_c)
                self._cb(worker, self._apply_pwpolicy, pp)
            elif kind == "sys-inactivity":
                it = drdata.get_inactivity_timeout(sys_c)
                self._cb(worker, self._apply_inactivity, it)

            # ----- org drill-down -----
            elif kind in ("org-users", "org-admins", "org-groups"):
                c = self._client_for_org(org)
                if c is None:
                    return
                users, groups = drdata.list_org_users_and_groups(c, org)
                self._cb(worker, self._apply_org_users_admins_groups, users, groups)
            elif kind == "org-projects":
                projs = self._list_projects()
                rows = drdata.project_rows_for_org(projs, org)
                self._cb(worker, self._apply_org_projects, rows)
            elif kind in ("org-running", "org-completed"):
                c = self._client_for_org(org)
                if c is None:
                    return
                projs = self._list_projects()
                projs = [(o, p) for (o, p) in projs if o == org]
                running, completed = drdata.collect_jobs(c, projs)
                self._cb(worker, self._apply_jobs, running, completed, len(projs))
            elif kind == "org-connectors":
                c = self._client_for_org(org)
                if c is None:
                    return
                connectors = drdata.list_connectors(c, org)
                self._cb(worker, self._apply_connectors, connectors)
            elif kind == "org-storage":
                if sys_c is None:
                    self._post_status("org storage requires DRSysAdmin")
                    return
                rows = drdata.org_storage_rows(sys_c, org)
                self._cb(worker, self._apply_org_storage, rows)

            # ----- v0.13 Job Scheduler -----
            elif kind == "sch-running":
                c = self.app.sys_client or self.app.org_client
                if c is None:
                    return
                rows, _ = drdata.list_realm_tasks(c)
                running = [r for r in rows if r.state == "RUNNING"]
                self._cb(worker, self._apply_sch_running, running)
            elif kind == "sch-saved":
                jobs = drsch.load_saved_jobs()
                self._cb(worker, self._apply_sch_saved, jobs)
            elif kind == "sch-timers":
                timers = drsch.list_dr_timers()
                self._cb(worker, self._apply_sch_timers, timers)
            elif kind == "sch-runs":
                # All runs across all saved jobs, newest first.
                all_runs: list[tuple[str, drsch.RunRecord]] = []
                for j in drsch.load_saved_jobs():
                    for r in drsch.list_runs(j.slug()):
                        all_runs.append((j.name, r))
                all_runs.sort(key=lambda kv: kv[1].started_at, reverse=True)
                self._cb(worker, self._apply_sch_runs, all_runs)

        except APIError as e:
            self._post_status(f"{kind}: {e.error_code or e.status}")
        except Exception as e:
            self._post_status(f"{kind} error: {e!r}")

    def _list_projects(self) -> list[tuple[str, dict]]:
        if self.app.role == ROLE_SYS and self.app.sys_client is not None:
            return drdata.list_projects_sys(self.app.sys_client, "drsysadmin")
        if self.app.org_client is not None:
            return drdata.list_projects_org(self.app.org_client)
        return []

    def _cb(self, worker, fn, *args) -> None:
        """Bounce a UI update to the main thread unless the worker was cancelled."""
        if worker.is_cancelled:
            return
        self.app.call_from_thread(fn, *args)

    def _post_status(self, msg: str) -> None:
        """Update the status bar (red). Safe from both worker + UI threads."""
        import threading
        bar = self.query_one("#status-bar", Static)
        text = f"[red]{msg}[/]"
        # On Textual 8.x the main-thread event loop is the asyncio loop;
        # workers spawned via run_worker(thread=True) run elsewhere. Only
        # bounce through call_from_thread when we're actually off-thread.
        if threading.current_thread() is threading.main_thread():
            bar.update(text)
        else:
            self.app.call_from_thread(bar.update, text)

    # ---------------------------------------------------------- appliers
    def _apply_storage_depots(self, table_id: str, rows: list[drdata.StorageDepot]) -> None:
        t = self.query_one(f"#{table_id}", DataTable)
        t.clear()
        for r in rows:
            t.add_row(
                r.name, r.fqdn, r.export, _yn(r.in_service),
                _fmt_kb(r.kb_used), _fmt_kb(r.kb_available), _fmt_kb(r.allocation),
            )
        # Cache row order for cursor→handle lookup in CRUD actions.
        self._depots_by_table[table_id] = list(rows)
        self._update_status_bar(extra=f"depots=[yellow]{len(rows)}[/]")

    def _apply_sysdepot(self, depot: drdata.SystemDepot | None) -> None:
        body = self.query_one("#sys-sysdepot-body", Static)
        if depot is None:
            body.update("[dim]No system storage depot found.[/]")
            return
        lines = [
            f"[b]Name:[/] {depot.name}",
            f"[b]ID:[/] {depot.depot_id}",
            f"[b]Description:[/] {depot.description or '—'}",
            f"[b]Directory:[/] {depot.directory_path}",
        ]
        if depot.attributes:
            lines.append("")
            lines.append("[b]Attributes[/]")
            for k, v in depot.attributes:
                lines.append(f"  {k}: {v}")
        body.update("\n".join(lines))
        self._update_status_bar()

    def _apply_virus(self, v: Optional["drdata.VirusDefs"]) -> None:
        body = self.query_one("#sys-virus-body", Static)
        if v is None:
            body.update("[dim]Virus definitions not configured.[/]")
            self._virus_last = None
            return
        body.update("\n".join([
            f"[b]Enabled:[/] {_yn(v.enabled)}",
            f"[b]Frequency:[/] {v.frequency or '—'}  [b]Hour:[/] {v.run_hour}",
            f"[b]Running:[/] {_yn(v.running)}",
            f"[b]Update status:[/] {v.update_status or '—'}",
            f"[b]Last updated:[/] {v.updated_on or '—'}",
            f"[b]Version:[/] {v.version or '—'}",
        ]))
        self._virus_last = v
        self._update_status_bar()

    # ---- Realm Settings appliers (v0.08) ----
    def _apply_mail(self, cfg: "drdata.MailServerConfig") -> None:
        body = self.query_one("#sys-mail-body", Static)
        if not cfg.configured:
            body.update("[dim]No mail server configured.[/]")
        else:
            body.update("\n".join([
                f"[b]SMTP host:[/] {cfg.smtp_host or '—'}",
                f"[b]SMTP port:[/] {cfg.smtp_port}",
                f"[b]SMTP auth:[/] {_yn(cfg.smtp_auth)}",
            ]))
        self._mail_last = cfg
        self._update_status_bar()

    def _apply_splash(self, sp: "drdata.SplashMessage") -> None:
        body = self.query_one("#sys-splash-body", Static)
        body.update("\n".join([
            f"[b]Enabled:[/] {_yn(sp.enabled)}",
            f"[b]Message:[/]",
            f"  {sp.message or '[dim]—[/]'}",
        ]))
        self._splash_last = sp
        self._update_status_bar()

    def _apply_pwpolicy(self, pp: "drdata.PasswordPolicy") -> None:
        body = self.query_one("#sys-pwpolicy-body", Static)
        body.update("\n".join([
            f"[b]Enforce strong passwords:[/] {_yn(pp.enforce_strong)}",
            f"[b]Minimum length:[/] {pp.min_length}",
            f"[b]Minimum uppercase:[/] {pp.min_uppercase}",
            f"[b]Minimum lowercase:[/] {pp.min_lowercase}",
            f"[b]Minimum numbers:[/] {pp.min_numbers}",
            f"[b]Minimum symbols:[/] {pp.min_symbols}",
            f"[b]Password expiration:[/] {pp.expiration_days} days",
        ]))
        self._pwpolicy_last = pp
        self._update_status_bar()

    def _apply_inactivity(self, it: "drdata.InactivityTimeout") -> None:
        body = self.query_one("#sys-inactivity-body", Static)
        # Render seconds + a friendlier h:m:s for context.
        secs = it.seconds
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        pretty = f"{h}h:{m}m:{s}s" if secs else "—"
        body.update("\n".join([
            f"[b]Session inactivity timeout:[/] {secs} seconds  [dim]({pretty})[/]",
            "",
            "[dim]Idle sessions are automatically logged out after this[/]",
            "[dim]duration. Set to 0 to disable.[/]",
        ]))
        self._inactivity_last = it
        self._update_status_bar()

    def _apply_sys_users_groups(
        self, users: list[drdata.UserRow], groups: list[drdata.GroupRow],
    ) -> None:
        ut = self.query_one("#sys-users-table", DataTable)
        ut.clear()
        for u in users:
            ut.add_row(
                u.handle, u.display, u.email,
                _yn(u.enabled), _yn(u.locked), _yn(u.mfa),
                u.last_access, u.roles,
            )
        gt = self.query_one("#sys-groups-table", DataTable)
        gt.clear()
        for g in groups:
            gt.add_row(g.name, g.description, str(g.members))
        # Cache rows so CRUD actions can resolve cursor → entity.
        self._sys_users_rows = list(users)
        self._sys_groups_rows = list(groups)
        self._update_status_bar(extra=f"users=[yellow]{len(users)}[/] groups=[yellow]{len(groups)}[/]")

    def _apply_org_users_admins_groups(
        self, users: list[drdata.UserRow], groups: list[drdata.GroupRow],
    ) -> None:
        ut = self.query_one("#org-users-table", DataTable)
        at = self.query_one("#org-admins-table", DataTable)
        ut.clear(); at.clear()
        n_users = n_admins = 0
        for u in users:
            row = (
                u.handle, u.display, u.email,
                _yn(u.enabled), _yn(u.locked), _yn(u.mfa),
                u.last_access, u.roles,
            )
            if u.is_admin:
                at.add_row(*row); n_admins += 1
            else:
                ut.add_row(*row); n_users += 1
        gt = self.query_one("#org-groups-table", DataTable)
        gt.clear()
        for g in groups:
            gt.add_row(g.name, g.description, str(g.members))
        self._update_status_bar(
            extra=f"users=[yellow]{n_users}[/] admins=[yellow]{n_admins}[/] groups=[yellow]{len(groups)}[/]",
        )

    def _apply_org_projects(self, rows: list[drdata.ProjectRow]) -> None:
        t = self.query_one("#org-projects-table", DataTable)
        t.clear()
        for r in rows:
            t.add_row(r.name, r.handle, r.created, r.state)
        self._update_status_bar(extra=f"projects=[yellow]{len(rows)}[/]")

    def _apply_jobs(
        self, running: list[drdata.JobRow], completed: list[drdata.JobRow], n_projects: int,
    ) -> None:
        rt = self.query_one("#running-table", DataTable)
        rt.clear()
        for j in running:
            rt.add_row(j.project, j.job, j.task_handle, j.duration)

        kt = self.query_one("#completed-table", DataTable)
        kt.clear()
        for j in reversed(completed):     # newest first
            kt.add_row(j.project, j.job, j.task_handle, j.completed, j.duration)
        self._update_status_bar(
            extra=(
                f"projects=[yellow]{n_projects}[/] "
                f"running=[green]{len(running)}[/] "
                f"completed=[dim]{len(completed)}[/]"
            ),
        )

    def _apply_connectors(self, connectors: list[drdata.Connector]) -> None:
        t = self.query_one("#connectors-table", DataTable)
        t.clear()
        for c in connectors:
            t.add_row(c.name, c.type, c.mode, c.host, c.path, c.status)
        # Cache row order so the Deactivate action can resolve cursor → connector.
        self._connectors_rows = list(connectors)
        self._update_status_bar(extra=f"connectors=[yellow]{len(connectors)}[/]")

    def _apply_org_storage(self, rows: list[drdata.OrgStorageRow]) -> None:
        t = self.query_one("#org-storage-table", DataTable)
        t.clear()
        for r in rows:
            t.add_row(r.depot_name, r.use_type, _fmt_kb(r.kb_used), _fmt_kb(r.kb_available))
        self._update_status_bar(extra=f"depots=[yellow]{len(rows)}[/]")

    # ---- v0.13 Job Scheduler appliers ----
    def _apply_sch_running(self, running: list["drdata.JobRow"]) -> None:
        t = self.query_one("#sch-running-table", DataTable)
        t.clear()
        for r in running:
            state_disp = (f"[green]{r.state}[/]" if r.state == "RUNNING"
                          else f"[dim]{r.state}[/]")
            t.add_row(
                r.org or "—", r.project, r.job, state_disp,
                r.started or "—", r.duration or "—", r.user or "—",
            )
        self._update_status_bar(extra=f"running=[green]{len(running)}[/]")

    def _apply_sch_saved(self, jobs: list[drsch.JobDefinition]) -> None:
        t = self.query_one("#sch-saved-table", DataTable)
        t.clear()
        self._sch_saved_rows = jobs
        for j in jobs:
            # "longterm" anywhere in the name → yellow-bold highlight,
            # per the user's request: visually flag long-retention jobs.
            name_disp = (f"[yellow b]{j.name}[/]"
                         if "longterm" in j.name.lower()
                         else j.name)
            t.add_row(
                name_disp, j.org, j.path,
                _fmt_retention(j.retention_seconds),
                j.description or "",
            )
        self._update_status_bar(extra=f"saved=[cyan]{len(jobs)}[/]")

    def _apply_sch_timers(self, timers: list[drsch.TimerInfo]) -> None:
        t = self.query_one("#sch-timers-table", DataTable)
        t.clear()
        for ti in timers:
            t.add_row(ti.unit, ti.next_fire, ti.left, ti.activates or "—")
        self._update_status_bar(extra=f"timers=[yellow]{len(timers)}[/]")

    def _apply_sch_runs(
        self, all_runs: list[tuple[str, "drsch.RunRecord"]],
    ) -> None:
        t = self.query_one("#sch-runs-table", DataTable)
        t.clear()
        for job_name, r in all_runs:
            colour = {
                "RUNNING": "yellow", "SUCCESS": "green",
                "FAILURE": "red", "DELETED": "dim",
                "DELETE_FAILED": "red",
            }.get(r.status, "")
            status_disp = f"[{colour}]{r.status}[/]" if colour else r.status
            t.add_row(
                f"{job_name}:{r.run_id}", r.started_at, status_disp,
                r.task_handle[:16], r.finished_at or "—",
            )
        self._update_status_bar(extra=f"runs=[cyan]{len(all_runs)}[/]")

    def _sch_saved_selected(self) -> Optional["drsch.JobDefinition"]:
        rows = getattr(self, "_sch_saved_rows", None) or []
        try:
            idx = self.query_one("#sch-saved-table", DataTable).cursor_row
        except Exception:
            return None
        if idx is None or idx < 0 or idx >= len(rows):
            return None
        return rows[idx]

    # ---------------------------------------------------------- CRUD: depots
    # Button id → (action, use_type). Action is "new" / "edit" / "delete".
    _DEPOT_BTN_MAP = {
        "doc-depot-new":    ("new",    "DOCUMENT_STORE", "sys-doc-depots-table"),
        "doc-depot-edit":   ("edit",   "DOCUMENT_STORE", "sys-doc-depots-table"),
        "doc-depot-delete": ("delete", "DOCUMENT_STORE", "sys-doc-depots-table"),
        "idx-depot-new":    ("new",    "INDEX_STORE",    "sys-idx-depots-table"),
        "idx-depot-edit":   ("edit",   "INDEX_STORE",    "sys-idx-depots-table"),
        "idx-depot-delete": ("delete", "INDEX_STORE",    "sys-idx-depots-table"),
    }

    def on_button_pressed(self, evt: Button.Pressed) -> None:
        bid = evt.button.id or ""

        # ----- depots -----
        info = self._DEPOT_BTN_MAP.get(bid)
        if info:
            action, use_type, table_id = info
            if action == "new":
                self._depot_open_new(use_type)
            else:
                depot = self._depot_selected(table_id)
                if depot is None:
                    self._post_status("select a depot row first")
                    return
                if action == "edit":
                    self._depot_open_edit(use_type, depot)
                elif action == "delete":
                    self._depot_confirm_delete(depot)
            return

        # ----- system users -----
        if bid == "sys-user-new":
            self._sys_user_open_new()
        elif bid in ("sys-user-edit", "sys-user-reset", "sys-user-delete"):
            user = self._sys_user_selected()
            if user is None:
                self._post_status("select a user row first")
                return
            if bid == "sys-user-edit":
                self._sys_user_open_edit(user)
            elif bid == "sys-user-reset":
                self._sys_user_open_reset(user)
            elif bid == "sys-user-delete":
                self._sys_user_confirm_delete(user)
            return

        # ----- system groups -----
        if bid == "sys-group-new":
            self._sys_group_open_new()
            return
        elif bid in ("sys-group-edit", "sys-group-delete"):
            group = self._sys_group_selected()
            if group is None:
                self._post_status("select a group row first")
                return
            if bid == "sys-group-edit":
                self._sys_group_open_edit(group)
            elif bid == "sys-group-delete":
                self._sys_group_confirm_delete(group)
            return

        # ----- virus update -----
        if bid == "sys-virus-update":
            self._virus_trigger_update()
            return

        # ----- v0.12 realm settings edit buttons -----
        if bid == "sys-mail-edit":
            self._settings_mail_open_edit(); return
        if bid == "sys-splash-edit":
            self._settings_splash_open_edit(); return
        if bid == "sys-pwpolicy-edit":
            self._settings_pwpolicy_open_edit(); return
        if bid == "sys-inactivity-edit":
            self._settings_inactivity_open_edit(); return

        # ----- v0.13 Job Scheduler -----
        if bid == "sch-new":
            self._sch_open_new(); return
        if bid == "sch-edit":
            j = self._sch_saved_selected()
            if j is None:
                self._post_status("select a saved job first")
                return
            self._sch_open_edit(j); return
        if bid == "sch-delete":
            j = self._sch_saved_selected()
            if j is None:
                self._post_status("select a saved job first")
                return
            self._sch_confirm_delete(j); return
        if bid == "sch-run":
            j = self._sch_saved_selected()
            if j is None:
                self._post_status("select a saved job first")
                return
            self._sch_run_now(j); return
        if bid == "sch-refresh":
            self._load_view(self.selected_kind or "sch-saved", ""); return

        # ----- dashboard log filters -----
        if bid == "dash-flt-info":
            self._toggle_log_filter("INFO")
        elif bid == "dash-flt-warn":
            self._toggle_log_filter("WARN")
        elif bid == "dash-flt-error":
            self._toggle_log_filter("ERROR")
        elif bid == "conn-deactivate":
            self._conn_confirm_deactivate()

    def _depot_selected(self, table_id: str) -> Optional[drdata.StorageDepot]:
        rows = self._depots_by_table.get(table_id, [])
        if not rows:
            return None
        try:
            t = self.query_one(f"#{table_id}", DataTable)
            idx = t.cursor_row
        except Exception:
            return None
        if idx is None or idx < 0 or idx >= len(rows):
            return None
        return rows[idx]

    def _depot_open_new(self, use_type: str) -> None:
        self.app.push_screen(
            DepotFormModal(use_type=use_type),
            self._depot_after_form,
        )

    def _depot_open_edit(self, use_type: str, depot: drdata.StorageDepot) -> None:
        self.app.push_screen(
            DepotFormModal(use_type=use_type, existing=depot),
            self._depot_after_form,
        )

    def _depot_after_form(self, result: Optional[dict]) -> None:
        if not result:
            return
        is_edit = bool(result.get("handle"))
        verb = "edit" if is_edit else "create"
        self._post_status(f"depot: {verb}…")
        self.run_worker(
            lambda: self._depot_write_blocking(result, is_edit),
            thread=True, exclusive=False, group="depot-write",
        )

    def _depot_confirm_delete(self, depot: drdata.StorageDepot) -> None:
        self.app.push_screen(
            ConfirmModal(
                title="Delete storage depot?",
                message=(
                    f"Permanently delete depot [b]{depot.name}[/]\n"
                    f"({depot.use_type})?\n\nThis cannot be undone."
                ),
                confirm_label="Delete",
            ),
            lambda ok: self._depot_after_confirm(ok, depot),
        )

    def _depot_after_confirm(self, ok: bool, depot: drdata.StorageDepot) -> None:
        if not ok:
            return
        self._post_status(f"depot: deleting {depot.name}…")
        self.run_worker(
            lambda: self._depot_delete_blocking(depot),
            thread=True, exclusive=False, group="depot-write",
        )

    def _depot_write_blocking(self, form: dict, is_edit: bool) -> None:
        """Worker thread: create or update a depot, then refresh the table."""
        sys_c = self.app.sys_client
        if sys_c is None:
            self._post_status("depot write: no DRSysAdmin session")
            return
        try:
            if is_edit:
                drdata.update_storage_depot(
                    sys_c,
                    handle=form["handle"],
                    fqdn=form["fqdn"],
                    export=form["export"],
                    use_type=form["use_type"],
                    allocation_size=form["allocation"],
                )
                msg = f"depot updated: {form['fqdn']}:{form['export']}"
            else:
                drdata.create_storage_depot(
                    sys_c,
                    name=form["name"],
                    fqdn=form["fqdn"],
                    export=form["export"],
                    use_type=form["use_type"],
                    allocation_size=form["allocation"],
                )
                msg = f"depot created: {form['name']}"
            self.app.call_from_thread(self._post_status_ok, msg)
        except APIError as e:
            self._post_status(f"depot write: {e.error_code or e.status}")
            return
        except Exception as e:
            self._post_status(f"depot write error: {e!r}")
            return
        # Refresh whichever leaf is currently visible.
        if self.selected_kind in SYS_VIEW_MAP:
            self.app.call_from_thread(self._load_view, self.selected_kind, "")

    def _depot_delete_blocking(self, depot: drdata.StorageDepot) -> None:
        sys_c = self.app.sys_client
        if sys_c is None:
            self._post_status("depot delete: no DRSysAdmin session")
            return
        try:
            drdata.delete_storage_depot(sys_c, handle=depot.handle)
            self.app.call_from_thread(self._post_status_ok, f"depot deleted: {depot.name}")
        except APIError as e:
            self._post_status(f"depot delete: {e.error_code or e.status}")
            return
        except Exception as e:
            self._post_status(f"depot delete error: {e!r}")
            return
        if self.selected_kind in SYS_VIEW_MAP:
            self.app.call_from_thread(self._load_view, self.selected_kind, "")

    def _post_status_ok(self, msg: str) -> None:
        """Like _post_status but green — call from UI thread."""
        self.query_one("#status-bar", Static).update(f"[green]{msg}[/]")

    # ---------------------------------------------------------- CRUD: system users
    def _sys_user_selected(self) -> Optional[drdata.UserRow]:
        if not self._sys_users_rows:
            return None
        try:
            t = self.query_one("#sys-users-table", DataTable)
            idx = t.cursor_row
        except Exception:
            return None
        if idx is None or idx < 0 or idx >= len(self._sys_users_rows):
            return None
        return self._sys_users_rows[idx]

    # ---- v0.12 Realm Settings edit dispatch ----
    def _settings_mail_open_edit(self) -> None:
        self.app.push_screen(
            MailServerFormModal(existing=self._mail_last),
            self._settings_mail_after,
        )

    def _settings_splash_open_edit(self) -> None:
        self.app.push_screen(
            SplashMessageFormModal(existing=self._splash_last),
            self._settings_splash_after,
        )

    def _settings_pwpolicy_open_edit(self) -> None:
        self.app.push_screen(
            PasswordPolicyFormModal(existing=self._pwpolicy_last),
            self._settings_pwpolicy_after,
        )

    def _settings_inactivity_open_edit(self) -> None:
        self.app.push_screen(
            InactivityTimeoutFormModal(existing=self._inactivity_last),
            self._settings_inactivity_after,
        )

    def _settings_mail_after(self, result: Optional[dict]) -> None:
        if not result: return
        self._post_status("mail: saving…")
        self.run_worker(
            lambda: self._settings_write_blocking(
                "mail", lambda c: drdata.set_mail_server_config(
                    c, smtp_host=result["smtp_host"],
                    smtp_port=result["smtp_port"],
                ),
            ),
            thread=True, exclusive=False, group="settings-write",
        )

    def _settings_splash_after(self, result: Optional[dict]) -> None:
        if not result: return
        self._post_status("splash: saving…")
        self.run_worker(
            lambda: self._settings_write_blocking(
                "splash", lambda c: drdata.set_splash_message(
                    c, enabled=result["enabled"], message=result["message"],
                ),
            ),
            thread=True, exclusive=False, group="settings-write",
        )

    def _settings_pwpolicy_after(self, result) -> None:
        # PasswordPolicyFormModal returns a PasswordPolicy directly.
        if not result: return
        self._post_status("password policy: saving…")
        self.run_worker(
            lambda: self._settings_write_blocking(
                "pwpolicy",
                lambda c: drdata.set_password_policy(c, policy=result),
            ),
            thread=True, exclusive=False, group="settings-write",
        )

    def _settings_inactivity_after(self, result: Optional[dict]) -> None:
        if not result: return
        self._post_status("inactivity: saving…")
        self.run_worker(
            lambda: self._settings_write_blocking(
                "inactivity",
                lambda c: drdata.set_inactivity_timeout(
                    c, seconds=result["seconds"],
                ),
            ),
            thread=True, exclusive=False, group="settings-write",
        )

    def _settings_write_blocking(self, kind: str, op) -> None:
        """Worker thread: run a Realm Settings write + refresh the view.

        `op` is a 1-arg callable taking the API client; it returns the
        new dataclass (Mail / Splash / PasswordPolicy / Inactivity).
        Any APIError lands in the status bar; other exceptions are
        surfaced verbatim for the user to copy/paste.
        """
        client = self.app.sys_client or self.app.org_client
        if client is None:
            self._post_status(f"{kind}: no API session")
            return
        try:
            op(client)
        except APIError as e:
            self._post_status(
                f"{kind}: {e.error_code or e.status} {e.extended_status[:60]}"
            )
            return
        except Exception as e:
            self._post_status(f"{kind} error: {e!r}")
            return
        # Refresh the matching sub-view so the body reflects the new state.
        kind_to_leaf = {
            "mail":       "sys-mail",
            "splash":     "sys-splash",
            "pwpolicy":   "sys-pwpolicy",
            "inactivity": "sys-inactivity",
        }
        leaf = kind_to_leaf.get(kind)
        if leaf:
            self.app.call_from_thread(self._post_status_ok, f"{kind}: saved")
            self.app.call_from_thread(self._load_view, leaf, "")

    # ---- v0.13 Job Scheduler open/run helpers ----
    def _sch_open_new(self) -> None:
        """Open NewJobModal — fetch orgs/connectors/projects in a worker first."""
        self._post_status("loading orgs + connectors…")
        self.run_worker(
            lambda: self._sch_collect_then_open(existing=None),
            thread=True, exclusive=True, group="sch-open",
        )

    def _sch_open_edit(self, job: "drsch.JobDefinition") -> None:
        self._post_status(f"loading wizard for {job.name}…")
        self.run_worker(
            lambda: self._sch_collect_then_open(existing=job),
            thread=True, exclusive=True, group="sch-open",
        )

    def _sch_collect_then_open(
        self, *, existing: Optional["drsch.JobDefinition"],
    ) -> None:
        """Gather org/connector/project data, then push NewJobModal."""
        client = self.app.sys_client or self.app.org_client
        if client is None:
            self._post_status("scheduler: no API session")
            return
        try:
            if self.app.role == ROLE_SYS and self.app.sys_client is not None:
                orgs_full = drdata.list_organizations_sys(self.app.sys_client)
                org_names = [o.name for o in orgs_full]
            else:
                # admin@<org> only sees their own org.
                org_names = [self.app.org_client.cfg.organization] \
                    if self.app.org_client is not None else []
        except Exception:
            org_names = []

        connectors_by_org: dict[str, list[drdata.Connector]] = {}
        projects_by_org: dict[str, list[dict]] = {}
        for org in org_names:
            try:
                connectors_by_org[org] = drdata.list_connectors(client, org)
            except Exception:
                connectors_by_org[org] = []
        try:
            for org, p in self._list_projects():
                projects_by_org.setdefault(org, []).append(p)
        except Exception:
            pass

        self.app.call_from_thread(
            self._sch_push_modal,
            org_names, connectors_by_org, projects_by_org, client, existing,
        )

    def _sch_push_modal(
        self, orgs, connectors_by_org, projects_by_org, client, existing,
    ) -> None:
        self.app.push_screen(
            NewJobModal(
                orgs=orgs,
                connectors_by_org=connectors_by_org,
                projects_by_org=projects_by_org,
                api_client=client,
                existing=existing,
            ),
            self._sch_after_modal,
        )

    def _sch_after_modal(self, payload: Optional[dict]) -> None:
        if not payload:
            return
        # Save (or overwrite) the JobDefinition.
        job = drsch.JobDefinition(**payload)
        drsch.save_job(job)
        self._post_status_ok(f"job saved: {job.name}")
        # Refresh the Saved Templates view if we're on it.
        if self.selected_kind == "sch-saved":
            self._load_view("sch-saved", "")

    def _sch_confirm_delete(self, job: "drsch.JobDefinition") -> None:
        self.app.push_screen(
            ConfirmModal(
                title="Delete saved job?",
                message=(
                    f"Permanently delete the saved job template "
                    f"[b]{job.name}[/]?\n\n"
                    "Scheduled retention timers for past runs are not "
                    "cancelled by this action — manage those from the "
                    "Retention Timers view."
                ),
                confirm_label="Delete",
            ),
            lambda ok: self._sch_delete_after_confirm(ok, job),
        )

    def _sch_delete_after_confirm(
        self, ok: bool, job: "drsch.JobDefinition",
    ) -> None:
        if not ok:
            return
        if drsch.delete_saved_job(job.name):
            self._post_status_ok(f"deleted: {job.name}")
        else:
            self._post_status(f"delete: file missing for {job.name}")
        if self.selected_kind == "sch-saved":
            self._load_view("sch-saved", "")

    def _sch_run_now(self, job: "drsch.JobDefinition") -> None:
        """Shell out to dr-job-run in a background thread.

        Same code path as cron / systemd would use — we deliberately
        don't replicate the submit-chain inline so there's exactly one
        place where things can go wrong.
        """
        import shutil, subprocess
        bin_path = shutil.which("dr-job-run") or "/opt/dr-tools/venv/bin/dr-job-run"
        self._post_status(f"running: {job.name} via {bin_path}")
        def _run():
            try:
                r = subprocess.run(
                    [bin_path, job.slug()],
                    capture_output=True, text=True, timeout=120,
                )
                msg = (f"run {job.name}: rc={r.returncode}"
                       + (f"  {r.stderr.strip()[:80]}" if r.stderr else ""))
                self.app.call_from_thread(self._post_status, msg)
            except FileNotFoundError:
                self.app.call_from_thread(
                    self._post_status,
                    f"dr-job-run not found at {bin_path}",
                )
            except Exception as e:
                self.app.call_from_thread(
                    self._post_status, f"run error: {e!r}",
                )
            # Refresh run history if visible.
            if self.selected_kind in ("sch-runs", "sch-saved"):
                self.app.call_from_thread(
                    self._load_view, self.selected_kind, "",
                )
        self.run_worker(_run, thread=True, exclusive=False, group="sch-run")

    def _sys_user_open_new(self) -> None:
        # Need roles loaded before the modal renders.
        self.run_worker(
            lambda: self._sys_user_load_roles_then(self._sys_user_show_new),
            thread=True, exclusive=False, group="user-write",
        )

    def _sys_user_open_edit(self, user: drdata.UserRow) -> None:
        self.run_worker(
            lambda: self._sys_user_load_roles_then(
                lambda: self._sys_user_show_edit(user)
            ),
            thread=True, exclusive=False, group="user-write",
        )

    def _sys_user_load_roles_then(self, ui_fn) -> None:
        """Worker: fetch system roles (if not cached) then dispatch *ui_fn*."""
        sys_c = self.app.sys_client
        if sys_c is None:
            self._post_status("user form: no DRSysAdmin session")
            return
        if not self._system_roles:
            try:
                self._system_roles = drdata.list_system_roles(sys_c)
            except APIError as e:
                self._post_status(f"roles: {e.error_code or e.status}")
                return
            except Exception as e:
                self._post_status(f"roles error: {e!r}")
                return
        self.app.call_from_thread(ui_fn)

    def _sys_user_show_new(self) -> None:
        self.app.push_screen(
            UserFormModal(roles=self._system_roles),
            self._sys_user_after_form,
        )

    def _sys_user_show_edit(self, user: drdata.UserRow) -> None:
        # Map the row's role-name string to a handle via the role catalogue.
        # `user.roles` is comma-joined; for system users they typically have
        # exactly one realm role. Match by first non-empty token.
        first_role = (user.roles.split(",")[0] if user.roles else "").strip()
        role_handle = next((h for (n, h) in self._system_roles if n == first_role), None)
        self.app.push_screen(
            UserFormModal(
                roles=self._system_roles,
                existing=user,
                existing_role_handle=role_handle,
            ),
            self._sys_user_after_form,
        )

    def _sys_user_after_form(self, result: Optional[dict]) -> None:
        if not result:
            return
        is_edit = bool(result.get("user_handle"))
        self._post_status(f"user: {'edit' if is_edit else 'create'}…")
        self.run_worker(
            lambda: self._sys_user_write_blocking(result, is_edit),
            thread=True, exclusive=False, group="user-write",
        )

    def _sys_user_write_blocking(self, form: dict, is_edit: bool) -> None:
        sys_c = self.app.sys_client
        if sys_c is None:
            self._post_status("user write: no DRSysAdmin session")
            return
        try:
            if is_edit:
                drdata.update_system_user(
                    sys_c,
                    user_handle=form["user_handle"],
                    email=form["email"],
                    first_name=form["first_name"],
                    last_name=form["last_name"],
                    role_handle=form["role_handle"],
                )
                msg = f"user updated: {form['username']}"
            else:
                drdata.create_system_user(
                    sys_c,
                    username=form["username"],
                    email=form["email"],
                    first_name=form["first_name"],
                    last_name=form["last_name"],
                    password=form["password"] or "",
                    role_handle=form["role_handle"],
                )
                msg = f"user created: {form['username']}"
            self.app.call_from_thread(self._post_status_ok, msg)
        except APIError as e:
            self._post_status(f"user write: {e.error_code or e.status}")
            return
        except Exception as e:
            self._post_status(f"user write error: {e!r}")
            return
        if self.selected_kind in SYS_VIEW_MAP:
            self.app.call_from_thread(self._load_view, self.selected_kind, "")

    def _sys_user_open_reset(self, user: drdata.UserRow) -> None:
        username = user.handle.split("@")[0]
        self.app.push_screen(
            ResetPasswordModal(username=username),
            lambda r: self._sys_user_after_reset(r, user),
        )

    def _sys_user_after_reset(self, result: Optional[dict], user: drdata.UserRow) -> None:
        if not result:
            return
        self._post_status(f"user: resetting password for {user.handle}…")
        self.run_worker(
            lambda: self._sys_user_reset_blocking(user, result["new_password"]),
            thread=True, exclusive=False, group="user-write",
        )

    def _sys_user_reset_blocking(self, user: drdata.UserRow, new_password: str) -> None:
        sys_c = self.app.sys_client
        if sys_c is None:
            self._post_status("reset: no DRSysAdmin session")
            return
        username = user.handle.split("@")[0]
        try:
            drdata.reset_user_password(
                sys_c, username=username, new_password=new_password,
            )
            self.app.call_from_thread(
                self._post_status_ok, f"password reset: {username}",
            )
        except APIError as e:
            self._post_status(f"reset: {e.error_code or e.status}")
        except Exception as e:
            self._post_status(f"reset error: {e!r}")

    def _sys_user_confirm_delete(self, user: drdata.UserRow) -> None:
        username = user.handle.split("@")[0]
        self.app.push_screen(
            ConfirmModal(
                title="Delete system user?",
                message=(
                    f"Permanently delete user [b]{username}[/]\n"
                    f"({user.email or 'no email'})?\n\nThis cannot be undone."
                ),
                confirm_label="Delete",
            ),
            lambda ok: self._sys_user_after_confirm(ok, user),
        )

    def _sys_user_after_confirm(self, ok: bool, user: drdata.UserRow) -> None:
        if not ok:
            return
        username = user.handle.split("@")[0]
        self._post_status(f"user: deleting {username}…")
        self.run_worker(
            lambda: self._sys_user_delete_blocking(user),
            thread=True, exclusive=False, group="user-write",
        )

    def _sys_user_delete_blocking(self, user: drdata.UserRow) -> None:
        sys_c = self.app.sys_client
        if sys_c is None:
            self._post_status("delete: no DRSysAdmin session")
            return
        username = user.handle.split("@")[0]
        try:
            drdata.delete_system_user(sys_c, username=username)
            self.app.call_from_thread(self._post_status_ok, f"user deleted: {username}")
        except APIError as e:
            self._post_status(f"delete: {e.error_code or e.status}")
            return
        except Exception as e:
            self._post_status(f"delete error: {e!r}")
            return
        if self.selected_kind in SYS_VIEW_MAP:
            self.app.call_from_thread(self._load_view, self.selected_kind, "")

    # ---------------------------------------------------------- CRUD: system groups
    def _sys_group_selected(self) -> Optional[drdata.GroupRow]:
        if not self._sys_groups_rows:
            return None
        try:
            t = self.query_one("#sys-groups-table", DataTable)
            idx = t.cursor_row
        except Exception:
            return None
        if idx is None or idx < 0 or idx >= len(self._sys_groups_rows):
            return None
        return self._sys_groups_rows[idx]

    def _sys_group_open_new(self) -> None:
        self.run_worker(
            lambda: self._sys_user_load_roles_then(self._sys_group_show_new),
            thread=True, exclusive=False, group="group-write",
        )

    def _sys_group_open_edit(self, group: drdata.GroupRow) -> None:
        self.run_worker(
            lambda: self._sys_user_load_roles_then(
                lambda: self._sys_group_show_edit(group)
            ),
            thread=True, exclusive=False, group="group-write",
        )

    def _sys_group_show_new(self) -> None:
        self.app.push_screen(
            GroupFormModal(roles=self._system_roles),
            self._sys_group_after_form,
        )

    def _sys_group_show_edit(self, group: drdata.GroupRow) -> None:
        self.app.push_screen(
            GroupFormModal(roles=self._system_roles, existing=group),
            self._sys_group_after_form,
        )

    def _sys_group_after_form(self, result: Optional[dict]) -> None:
        if not result:
            return
        is_edit = bool(result.get("handle"))
        self._post_status(f"group: {'edit' if is_edit else 'create'}…")
        self.run_worker(
            lambda: self._sys_group_write_blocking(result, is_edit),
            thread=True, exclusive=False, group="group-write",
        )

    def _sys_group_write_blocking(self, form: dict, is_edit: bool) -> None:
        sys_c = self.app.sys_client
        if sys_c is None:
            self._post_status("group write: no DRSysAdmin session")
            return
        try:
            if is_edit:
                drdata.update_system_group(
                    sys_c,
                    handle=form["handle"],
                    name=form["name"],
                    description=form["description"],
                    role_handle=form["role_handle"],
                    role_name=form["role_name"],
                )
                msg = f"group updated: {form['name']}"
            else:
                drdata.create_system_group(
                    sys_c,
                    name=form["name"],
                    description=form["description"],
                    role_handle=form["role_handle"],
                )
                msg = f"group created: {form['name']}"
            self.app.call_from_thread(self._post_status_ok, msg)
        except APIError as e:
            self._post_status(f"group write: {e.error_code or e.status}")
            return
        except Exception as e:
            self._post_status(f"group write error: {e!r}")
            return
        if self.selected_kind in SYS_VIEW_MAP:
            self.app.call_from_thread(self._load_view, self.selected_kind, "")

    def _sys_group_confirm_delete(self, group: drdata.GroupRow) -> None:
        self.app.push_screen(
            ConfirmModal(
                title="Delete system group?",
                message=(
                    f"Permanently delete group [b]{group.name}[/]?\n\n"
                    f"Members ({group.members}) lose this role; "
                    f"the operation cannot be undone."
                ),
                confirm_label="Delete",
            ),
            lambda ok: self._sys_group_after_confirm(ok, group),
        )

    def _sys_group_after_confirm(self, ok: bool, group: drdata.GroupRow) -> None:
        if not ok:
            return
        self._post_status(f"group: deleting {group.name}…")
        self.run_worker(
            lambda: self._sys_group_delete_blocking(group),
            thread=True, exclusive=False, group="group-write",
        )

    def _sys_group_delete_blocking(self, group: drdata.GroupRow) -> None:
        sys_c = self.app.sys_client
        if sys_c is None:
            self._post_status("group delete: no DRSysAdmin session")
            return
        try:
            drdata.delete_system_group(sys_c, handle=group.handle)
            self.app.call_from_thread(self._post_status_ok, f"group deleted: {group.name}")
        except APIError as e:
            self._post_status(f"group delete: {e.error_code or e.status}")
            return
        except Exception as e:
            self._post_status(f"group delete error: {e!r}")
            return
        if self.selected_kind in SYS_VIEW_MAP:
            self.app.call_from_thread(self._load_view, self.selected_kind, "")

    # ---------------------------------------------------------- ACTION: virus update
    def _virus_trigger_update(self) -> None:
        """Kick off a virus-definitions sync. Fire-and-forget; the call
        returns immediately and the panel auto-refreshes to show progress."""
        self._post_status("virus: triggering update…")
        self.run_worker(
            self._virus_update_blocking,
            thread=True, exclusive=False, group="virus-write",
        )

    def _virus_update_blocking(self) -> None:
        sys_c = self.app.sys_client
        if sys_c is None:
            self._post_status("virus: no DRSysAdmin session")
            return
        # Preserve the most recently-read schedule fields (or sensible
        # defaults if we never read them).
        v = self._virus_last
        enabled = v.enabled if v else True
        frequency = v.frequency if v else "DAILY"
        try:
            drdata.trigger_virus_update(
                sys_c, enabled=enabled, frequency=frequency,
            )
            self.app.call_from_thread(
                self._post_status_ok, "virus: update started",
            )
        except APIError as e:
            # INVALID_STATE = already running. Friendlier message.
            if (e.error_code or "") == "INVALID_STATE":
                self._post_status("virus: update already running")
            else:
                self._post_status(
                    f"virus: {e.error_code or e.status}: {e.extended_status[:80]}"
                )
            return
        except Exception as e:
            self._post_status(f"virus error: {e!r}")
            return
        if self.selected_kind == "sys-virus":
            self.app.call_from_thread(self._load_view, "sys-virus", "")

    # ---------------------------------------------------------- ACTION: connector deactivate
    def _conn_selected(self) -> Optional[drdata.Connector]:
        if not self._connectors_rows:
            return None
        try:
            t = self.query_one("#connectors-table", DataTable)
            idx = t.cursor_row
        except Exception:
            return None
        if idx is None or idx < 0 or idx >= len(self._connectors_rows):
            return None
        return self._connectors_rows[idx]

    def _conn_confirm_deactivate(self) -> None:
        """Confirmation modal for the soft-delete (deactivate) path.

        Deactivate is reversible-feeling (the row stays, status flips to
        DEACTIVATED), so a single-line modal is enough — no full red
        warning UX.
        """
        conn = self._conn_selected()
        if conn is None:
            self._post_status("select a connector row first")
            return
        if (conn.status or "").upper() == "DEACTIVATED":
            self._post_status(f"connector {conn.name} is already DEACTIVATED")
            return
        self.app.push_screen(
            ConfirmModal(
                title="Deactivate connector?",
                message=(
                    f"Mark connector [b]{conn.name}[/] ({conn.type}) as "
                    f"[yellow]DEACTIVATED[/]?\n\n"
                    "The row stays visible but the connector stops "
                    "responding to new requests. Use Delete in the UI "
                    "for true removal."
                ),
                confirm_label="Deactivate",
            ),
            lambda ok: self._conn_after_confirm(ok, conn),
        )

    def _conn_after_confirm(self, ok: bool, conn: drdata.Connector) -> None:
        if not ok:
            return
        self._post_status(f"connector: deactivating {conn.name}…")
        self.run_worker(
            lambda: self._conn_deactivate_blocking(conn),
            thread=True, exclusive=False, group="conn-write",
        )

    def _conn_deactivate_blocking(self, conn: drdata.Connector) -> None:
        """Worker: call deactivateConnectors, then refresh."""
        org = self.selected_org or self.app.target_org
        client = self._client_for_org(org)
        if client is None:
            self._post_status("deactivate: no session")
            return
        try:
            drdata.deactivate_connectors(client, org=org, names=[conn.name])
            self.app.call_from_thread(
                self._post_status_ok,
                f"connector deactivated: {conn.name}",
            )
        except APIError as e:
            self._post_status(
                f"deactivate: {e.error_code or e.status}: {e.extended_status[:60]}"
            )
            return
        except Exception as e:
            self._post_status(f"deactivate error: {e!r}")
            return
        # Refresh the connectors view so the status flips.
        if self.selected_kind == "org-connectors":
            self.app.call_from_thread(self._load_view, "org-connectors", org)

    # ---------------------------------------------------------- status bar
    def _update_status_bar(self, extra: str = "") -> None:
        role_label = "DRSysAdmin" if self.app.role == ROLE_SYS else "admin@training"
        org = self.selected_org or self.app.target_org
        view = self.selected_kind or "—"
        parts = [
            f"[b]{role_label}[/]",
            f"org=[cyan]{org}[/]" if org else "",
            f"view=[magenta]{view}[/]",
            extra,
        ]
        bar = " · ".join(p for p in parts if p)
        self.query_one("#status-bar", Static).update(bar)

    # ---------------------------------------------------------- actions
    def action_logout(self) -> None:
        self.app.do_logout()

    def action_refresh_now(self) -> None:
        # Only refresh when a leaf is selected — avoid hammering the API.
        if self.selected_kind:
            self._load_view(self.selected_kind, self.selected_org)

    def action_switch_tab(self, tab_id: str) -> None:
        """Jump to a named tab (TabPane id)."""
        try:
            self.query_one("#main-tabs", TabbedContent).active = tab_id
        except Exception:
            pass

    # ---------------------------------------------------------- F-key dispatch
    # Each F-key resolves the currently-selected leaf and forwards to the
    # matching CRUD entry point. Unrelated leaves get a status hint rather
    # than failing silently.

    def action_ctx_new(self) -> None:
        kind = self.selected_kind
        if kind == "sys-doc-depots":
            self._depot_open_new("DOCUMENT_STORE")
        elif kind == "sys-idx-depots":
            self._depot_open_new("INDEX_STORE")
        elif kind == "sys-users":
            self._sys_user_open_new()
        elif kind == "sys-groups":
            self._sys_group_open_new()
        else:
            self._post_status("[F7] New — not available on this view")

    def action_ctx_edit(self) -> None:
        kind = self.selected_kind
        if kind == "sys-doc-depots":
            d = self._depot_selected("sys-doc-depots-table")
            if d is None:
                self._post_status("select a depot row first"); return
            self._depot_open_edit("DOCUMENT_STORE", d)
        elif kind == "sys-idx-depots":
            d = self._depot_selected("sys-idx-depots-table")
            if d is None:
                self._post_status("select a depot row first"); return
            self._depot_open_edit("INDEX_STORE", d)
        elif kind == "sys-users":
            u = self._sys_user_selected()
            if u is None:
                self._post_status("select a user row first"); return
            self._sys_user_open_edit(u)
        elif kind == "sys-groups":
            g = self._sys_group_selected()
            if g is None:
                self._post_status("select a group row first"); return
            self._sys_group_open_edit(g)
        elif kind == "sys-mail":
            self._settings_mail_open_edit()
        elif kind == "sys-splash":
            self._settings_splash_open_edit()
        elif kind == "sys-pwpolicy":
            self._settings_pwpolicy_open_edit()
        elif kind == "sys-inactivity":
            self._settings_inactivity_open_edit()
        else:
            self._post_status("[F4] Edit — not available on this view")

    def action_ctx_delete(self) -> None:
        kind = self.selected_kind
        if kind == "sys-doc-depots":
            d = self._depot_selected("sys-doc-depots-table")
            if d is None:
                self._post_status("select a depot row first"); return
            self._depot_confirm_delete(d)
        elif kind == "sys-idx-depots":
            d = self._depot_selected("sys-idx-depots-table")
            if d is None:
                self._post_status("select a depot row first"); return
            self._depot_confirm_delete(d)
        elif kind == "sys-users":
            u = self._sys_user_selected()
            if u is None:
                self._post_status("select a user row first"); return
            self._sys_user_confirm_delete(u)
        elif kind == "sys-groups":
            g = self._sys_group_selected()
            if g is None:
                self._post_status("select a group row first"); return
            self._sys_group_confirm_delete(g)
        else:
            self._post_status("[F8] Delete — not available on this view")

    def action_ctx_reset(self) -> None:
        """F6 — repurposed as Reset Password on the users panel; on the
        Virus Detection panel it triggers an update-now (the only other
        leaf with a meaningful 'refresh-ish' action)."""
        kind = self.selected_kind
        if kind == "sys-users":
            u = self._sys_user_selected()
            if u is None:
                self._post_status("select a user row first"); return
            self._sys_user_open_reset(u)
        elif kind == "sys-virus":
            self._virus_trigger_update()
        else:
            self._post_status("[F6] Reset PW — not available on this view")

    def action_show_help(self) -> None:
        """F1 — pop the help modal showing keybindings."""
        self.app.push_screen(HelpModal())

    def action_jobs_monitor(self) -> None:
        """F3 — pop the realm-wide Jobs Monitor modal."""
        self.app.push_screen(JobsMonitorModal())

    # ---------------------------------------------------------- F2: docs side-pane
    def action_toggle_doc(self) -> None:
        """Toggle the DR-documentation side-pane on the active tab."""
        self.help_visible = not self.help_visible
        for pane_id in ("#sys-help-pane", "#orgs-help-pane"):
            try:
                p = self.query_one(pane_id, Markdown)
                p.display = self.help_visible
            except Exception:
                pass
        if self.help_visible:
            self._refresh_help_pane()

    def _refresh_help_pane(self) -> None:
        """Populate both help panes with the current view's documentation."""
        kind = self.selected_kind
        entry = drhelp.get_help(kind) if kind else None
        if entry is None:
            md = (
                f"# Documentation\n\n"
                f"_No help topic mapped for view `{kind or '<none>'}`._\n\n"
                f"Use the tree on the left to pick a leaf, then press "
                f"**F2** again to refresh this pane."
            )
        else:
            md = (
                f"# {entry.label}\n\n"
                f"_Source: {entry.source_pdf}_\n\n"
                f"---\n\n"
                f"{entry.body_markdown}"
            )
        for pane_id in ("#sys-help-pane", "#orgs-help-pane"):
            try:
                p = self.query_one(pane_id, Markdown)
                p.update(md)
            except Exception:
                pass

    # ============================================================ Dashboard tab
    # Four independent tick cycles. Metrics + logs + procs are local-host
    # reads (psutil + tail) so they're cheap; realm (license + node)
    # touches the DR REST API and runs at a slower cadence.

    def _dash_tick_metrics(self) -> None:
        """Sample CPU/mem/net/disk and update the metrics strip."""
        try:
            sample = drmetrics.sample_metrics(self._metrics_prev)
        except Exception:
            return
        self._metrics_prev = sample
        self._metrics_history.add(sample)
        h = self._metrics_history
        cpu_text = (
            f"CPU [b]{sample.cpu_pct:5.1f}%[/]  "
            f"peak [yellow]{h.cpu_peak():5.1f}%[/]  "
            f"avg [dim]{h.cpu_avg():5.1f}%[/]"
        )
        mem_text = (
            f"Memory [b]{sample.mem_pct:5.1f}%[/]  "
            f"({sample.mem_used_gb:.1f} / {sample.mem_total_gb:.1f} GB)  "
            f"peak [yellow]{h.mem_peak():5.1f}%[/]  "
            f"avg [dim]{h.mem_avg():5.1f}%[/]"
        )
        net_text = (
            f"Net  rx [green]{_fmt_rate(sample.net_rx_per_sec)}[/]  "
            f"tx [magenta]{_fmt_rate(sample.net_tx_per_sec)}[/]\n"
            f"IOPS r {sample.disk_read_iops:6.0f}  "
            f"w {sample.disk_write_iops:6.0f}  "
            f"total {sample.disk_read_iops + sample.disk_write_iops:6.0f}"
        )
        self.query_one("#dash-cpu-text", Static).update(cpu_text)
        self.query_one("#dash-mem-text", Static).update(mem_text)
        self.query_one("#dash-net-text", Static).update(net_text)
        # Sparklines need at least one positive sample to render meaningfully.
        cpu_series = h.cpu_series() or [0]
        mem_series = h.mem_series() or [0]
        self.query_one("#dash-cpu-spark", Sparkline).data = cpu_series
        self.query_one("#dash-mem-spark", Sparkline).data = mem_series

    def _dash_tick_logs(self) -> None:
        """Pull new lines from the AHS tailer and append to the RichLog."""
        if self._log_tailer is None:
            return
        try:
            new_lines = self._log_tailer.poll()
        except Exception:
            return
        if not new_lines:
            return
        log = self.query_one("#dash-log", RichLog)
        for ll in new_lines:
            # Always render unleveled lines (often stack traces) — the
            # filter only excludes explicit non-matching levels.
            if ll.level and ll.level not in self._log_filter:
                continue
            color = {
                "ERROR": "red",
                "WARN":  "yellow",
                "INFO":  "green",
            }.get(ll.level, "dim")
            tag = f"[{color}]{ll.level or '   '}[/]"
            log.write(f"[cyan]{ll.file:>12s}[/] {tag} {ll.text}")

    def _dash_tick_procs(self) -> None:
        """Refresh the top-5 processes table."""
        try:
            rows = drmetrics.top_processes(n=5)
        except Exception:
            return
        t = self.query_one("#dash-procs-table", DataTable)
        t.clear()
        for r in rows:
            t.add_row(
                str(r.pid), r.user,
                f"{r.cpu_pct:5.1f}", f"{r.mem_pct:5.1f}",
                r.cmd,
            )

    def _dash_tick_realm(self) -> None:
        """Pull license + realm node data from the REST API."""
        if self.app.sys_client is None:
            return
        self.run_worker(self._dash_realm_blocking,
                        thread=True, exclusive=False, group="dash-realm")

    def _dash_realm_blocking(self) -> None:
        sys_c = self.app.sys_client
        if sys_c is None:
            return
        try:
            license_info = drdata.get_license_info(sys_c)
        except Exception:
            license_info = None
        nodes_detail: list = []
        try:
            for n in drdata.list_nodes(sys_c):
                try:
                    nd = drdata.get_node_status(sys_c, handle=n.handle)
                except Exception:
                    nd = drdata.NodeStatusDetail(
                        node=n, components=[], storage=[], connectors=0,
                    )
                nodes_detail.append(nd)
        except Exception:
            pass
        self.app.call_from_thread(self._dash_apply_realm, license_info, nodes_detail)

    def _dash_apply_realm(
        self, license_info, nodes_detail: list,
    ) -> None:
        # License panel: render as a label/value table.
        body = self.query_one("#dash-license-body", Static)
        if not license_info:
            body.update("[red]license info unavailable[/]")
        else:
            lines = []
            for f in license_info:
                # Highlight expiry + permanence.
                v = f.value
                if f.label == "Mode":
                    v = f"[green]{v}[/]" if v == "PERMANENT" else f"[yellow]{v}[/]"
                elif f.label == "Valid until":
                    v = f"[green]{v}[/]"
                lines.append(f"[b]{f.label}:[/] {v}")
            body.update("\n".join(lines))

        # Node panel: walk every node and render its component + storage info.
        nbody = self.query_one("#dash-node-body", Static)
        if not nodes_detail:
            nbody.update("[red]no nodes returned[/]")
            return
        chunks = []
        for nd in nodes_detail:
            n = nd.node
            chunks.append(
                f"[b]{n.name}[/] [dim]({n.node_type}, {n.cores} cores)[/]"
            )
            chunks.append(
                f"  Status: {_color_status(n.monitor_status)}  "
                f"AE: {_color_status(n.ae_status)}  "
                f"Connector: {_color_status(n.connector_status)}  "
                f"Storage: {_color_status(n.storage_status)}"
            )
            chunks.append(
                f"  Threads executing: [b]{n.threads_executing}[/]   "
                f"Mode: {n.analytic_mode}"
            )
            if nd.components:
                chunks.append("  [b]Components:[/]")
                for c in nd.components:
                    mem_gb = c.memory_bytes / (1024 ** 3)
                    chunks.append(
                        f"    {c.name:<22s}  {_color_status(c.status):<26s}  "
                        f"threads={c.threads}  mem={mem_gb:.1f} GB"
                    )
            if nd.storage:
                chunks.append("  [b]Storage mounts:[/]")
                for s in nd.storage:
                    used_gb = s.kb_used / (1024 ** 2)
                    avail_gb = s.kb_available / (1024 ** 2)
                    chunks.append(
                        f"    {s.name:<24s}  "
                        f"used {used_gb:>6.1f} GB / avail {avail_gb:>6.1f} GB  "
                        f"{_color_status(s.status)}"
                    )
            chunks.append(
                f"  [dim]Connectors registered: {nd.connectors}[/]"
            )
            chunks.append("")
        nbody.update("\n".join(chunks).rstrip())

    # ---- log filter buttons ----
    def _toggle_log_filter(self, level: str) -> None:
        if level in self._log_filter:
            self._log_filter.discard(level)
        else:
            self._log_filter.add(level)
        # Visually mark which filters are on by toggling the button variant.
        bmap = {"INFO": "dash-flt-info", "WARN": "dash-flt-warn", "ERROR": "dash-flt-error"}
        bvariants = {"INFO": "primary", "WARN": "warning", "ERROR": "error"}
        for lvl, bid in bmap.items():
            try:
                btn = self.query_one(f"#{bid}", Button)
                btn.variant = bvariants[lvl] if lvl in self._log_filter else "default"
            except Exception:
                pass


# ============================================================ App
class DRTUIApp(App):
    """Top-level Textual app."""

    CSS_PATH = CSS_PATH
    TITLE = "dr-tui"
    SUB_TITLE = "Digital Reef eDiscovery"

    role: str = ROLE_SYS
    sys_client: EDiscoveryClient | None = None
    org_client: EDiscoveryClient | None = None
    target_org: str = "training"

    def on_mount(self) -> None:
        self.push_screen(LoginScreen())

    # ------------------------------------------ login plumbing
    def do_login(self, role: str, password: str) -> None:
        self.role = role
        self.run_worker(
            lambda: self._login_blocking(role, password),
            thread=True, exclusive=True, group="login",
        )

    def _login_blocking(self, role: str, password: str) -> None:
        try:
            sys_cfg = Config()
            org_cfg = OrgUserConfig()
            sys_client = EDiscoveryClient(sys_cfg)
            org_client = EDiscoveryClient(org_cfg)

            if role == ROLE_SYS:
                sys_client.login(password=password)
                try:
                    org_client.login(password=password)
                except Exception:
                    org_client = None
            else:
                org_client.login(password=password)
                sys_client = None

            self.call_from_thread(self._on_login_ok, sys_client, org_client)
        except APIError as e:
            self.call_from_thread(
                self._on_login_fail,
                f"{e.error_code or e.status}: {e.extended_status}",
            )
        except Exception as e:
            self.call_from_thread(self._on_login_fail, repr(e))

    def _on_login_ok(self, sys_client, org_client) -> None:
        self.sys_client = sys_client
        self.org_client = org_client
        self.push_screen(DashboardScreen())

    def _on_login_fail(self, msg: str) -> None:
        if isinstance(self.screen, LoginScreen):
            self.screen.query_one("#login-error", Static).update(f"[red]{msg}[/]")

    def do_logout(self) -> None:
        for c in (self.sys_client, self.org_client):
            if c is not None:
                try:
                    c.logout()
                except Exception:
                    pass
        self.sys_client = None
        self.org_client = None
        self.pop_screen()  # back to login


def main() -> None:
    DRTUIApp().run()


if __name__ == "__main__":
    main()

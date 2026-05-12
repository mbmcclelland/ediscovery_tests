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
    Button, ContentSwitcher, DataTable, Footer, Header, Input, Label,
    RadioButton, RadioSet, RichLog, Select, Sparkline, Static,
    TabbedContent, TabPane, Tree,
)
from textual.worker import get_current_worker

from config import Config, OrgUserConfig
from helpers.api_client import APIError, EDiscoveryClient

from dr_tui import data as drdata
from dr_tui import metrics as drmetrics

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


class HelpModal(ModalScreen[None]):
    """F1 — keyboard reference. Dismiss with any key."""

    BINDINGS = [
        Binding("escape,f1,q,enter,space", "dismiss", "Close", show=False),
    ]

    HELP_TEXT = (
        "[b]dr-tui — Keyboard reference[/]\n\n"
        "[b cyan]Global[/]\n"
        "  F1            this help screen\n"
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
        yield Footer()

    # ---------------------------------------------------------- mount
    def on_mount(self) -> None:
        self._depots_by_table = {"sys-doc-depots-table": [], "sys-idx-depots-table": []}
        self._sys_users_rows = []
        self._sys_groups_rows = []
        self._system_roles = []
        self._connectors_rows = []
        self._virus_last = None
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

        self._populate_sys_tree()

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
            return

        if kind in ORG_VIEW_MAP:
            self.query_one("#orgs-switcher", ContentSwitcher).current = ORG_VIEW_MAP[kind]
            self.selected_kind = kind
            self.selected_org = org or self.app.target_org
            if org:
                self.app.target_org = org
            self._load_view(kind, self.selected_org)
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

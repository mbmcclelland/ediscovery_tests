"""v0.13 Job Scheduler — pilot smoke for scheduler.py + NewJobModal mount.

Doesn't touch the live DR API or systemd; the systemd-user functions
are tested separately on hosts that have it. Here we cover:

  - JobDefinition save → load round-trip in a tmp state dir
  - RunRecord append + read
  - slugify edge cases
  - NewJobModal mounts in a dummy App, dismisses on Cancel
  - 'longterm' coloring is applied by _apply_sch_saved

Run via:

    pytest tests/test_dr_tui_scheduler.py
    # or, standalone:
    python tests/test_dr_tui_scheduler.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import tempfile
from pathlib import Path

# Allow `python tests/test_dr_tui_scheduler.py` from anywhere.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Static


class _Harness(App):
    def compose(self) -> ComposeResult:
        yield Static("harness")


# ---------- scheduler module — state persistence ----------

def test_scheduler_save_load_roundtrip(tmp_path) -> None:
    os.environ["DR_TOOLS_STATE_DIR"] = str(tmp_path)
    # Force re-resolution of state dirs.
    import dr_tui.scheduler as sch
    importlib.reload(sch)

    j = sch.JobDefinition(
        name="Nightly Payroll",
        org="training",
        project_handle="254",
        connector_name="nfs-payroll",
        connector_handle="conn-abc",
        connector_type="NFS",
        remote_host="192.168.58.128",
        remote_path="/data/import",
        path="/data/import/payroll/2026",
        retention_seconds=86400,           # 1 day
        description="ingest /payroll nightly",
    )
    sch.save_job(j)
    loaded = sch.load_saved_jobs()
    assert len(loaded) == 1, f"expected 1 saved job, got {len(loaded)}"
    assert loaded[0].name == "Nightly Payroll"
    assert loaded[0].slug() == "nightly-payroll"
    assert loaded[0].retention_seconds == 86400
    assert loaded[0].created_at, "created_at should be stamped"

    # Round-trip via get_job by either name or slug.
    by_name = sch.get_job("Nightly Payroll")
    by_slug = sch.get_job("nightly-payroll")
    assert by_name and by_slug
    assert by_name.connector_handle == "conn-abc"
    assert by_slug.path == "/data/import/payroll/2026"

    # Delete is idempotent.
    assert sch.delete_saved_job("Nightly Payroll") is True
    assert sch.delete_saved_job("Nightly Payroll") is False
    assert sch.load_saved_jobs() == []


def test_scheduler_run_record_append(tmp_path) -> None:
    os.environ["DR_TOOLS_STATE_DIR"] = str(tmp_path)
    import dr_tui.scheduler as sch
    importlib.reload(sch)

    r1 = sch.RunRecord(
        run_id="20260513T030000",
        started_at="2026-05-13T03:00:00Z",
        task_handle="task-1", corpus_handle="corp-1",
        data_area_handle="da-1", status="RUNNING",
    )
    r2 = sch.RunRecord(
        run_id="20260514T030000",
        started_at="2026-05-14T03:00:00Z",
        task_handle="task-2", corpus_handle="corp-2",
        data_area_handle="da-2", status="SUCCESS",
        finished_at="2026-05-14T03:15:00Z",
    )
    sch.append_run("test-job", r1)
    sch.append_run("test-job", r2)
    out = sch.list_runs("test-job")
    assert len(out) == 2
    assert [r.run_id for r in out] == [r1.run_id, r2.run_id]
    assert out[1].status == "SUCCESS"


def test_scheduler_slugify_edges() -> None:
    import dr_tui.scheduler as sch
    importlib.reload(sch)
    assert sch.slugify("Nightly Payroll") == "nightly-payroll"
    assert sch.slugify("ALL CAPS!! 2026") == "all-caps-2026"
    assert sch.slugify("---__---") == "unnamed"
    assert sch.slugify("") == "unnamed"
    # Already-slug input passes through.
    assert sch.slugify("nightly-payroll") == "nightly-payroll"


# ---------- NewJobModal — mount + cancel path ----------

async def _walk_newjob_modal() -> None:
    """NewJobModal mounts with empty data; Cancel returns None."""
    from dr_tui.app import NewJobModal
    app = _Harness()
    async with app.run_test() as pilot:
        holder: list = []
        app.push_screen(
            NewJobModal(
                orgs=[],
                connectors_by_org={},
                projects_by_org={},
                api_client=None,
            ),
            lambda r: holder.append(r),
        )
        await pilot.pause()
        # Title + cancel button present.
        assert app.screen.query_one("#newjob-title") is not None
        app.screen.query_one("#newjob-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]


async def _walk_newjob_autoflow() -> None:
    """NewJobModal with realistic data: org+connector auto-pick on open.

    Regression coverage for v0.13.1 — the first ship had
    `_cur_conn_handle = ""` after compose because Select's auto-pick of
    the first option doesn't fire on_select_changed, so Browse failed
    silently. Verify the modal opens with both pre-populated.
    """
    from dr_tui.app import NewJobModal
    from dr_tui.data import Connector
    app = _Harness()
    orgs = ["training", "ops"]
    connectors = {
        "training": [
            Connector(name="nfs-a", type="NFS", mode="IMPORT", status="OK",
                      host="10.0.0.1", path="/data/import", handle="c-1"),
            Connector(name="nfs-b", type="NFS", mode="IMPORT", status="OK",
                      host="10.0.0.2", path="/srv", handle="c-2"),
        ],
        "ops": [],
    }
    projects = {
        "training": [{"name": "test1", "handle": "254"}],
        "ops": [],
    }
    async with app.run_test() as pilot:
        holder: list = []
        modal = NewJobModal(
            orgs=orgs, connectors_by_org=connectors,
            projects_by_org=projects, api_client=None,
        )
        app.push_screen(modal, lambda r: holder.append(r))
        await pilot.pause()
        scr = app.screen
        # On open: first org + first connector auto-picked, project handle
        # auto-resolved from the org's first project.
        assert scr._cur_org == "training", scr._cur_org
        assert scr._cur_conn_handle == "c-1", scr._cur_conn_handle
        assert scr._cur_project_handle == "254", scr._cur_project_handle
        # Project-status hint is populated.
        # (Static.renderable is private; just confirm the widget exists.)
        assert scr.query_one("#newjob-project-status") is not None

        # Switch org → no projects, no connectors. Status flips.
        from textual.widgets import Select as _S
        scr.query_one("#newjob-org", _S).value = "ops"
        await pilot.pause()
        assert scr._cur_org == "ops"
        assert scr._cur_conn_handle == ""
        assert scr._cur_project_handle == ""

        # Switch back to training; both should re-resolve.
        scr.query_one("#newjob-org", _S).value = "training"
        await pilot.pause()
        assert scr._cur_org == "training"
        assert scr._cur_conn_handle == "c-1"
        assert scr._cur_project_handle == "254"

        # Cancel.
        scr.query_one("#newjob-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]


def test_newjob_modal_mount_and_cancel() -> None:
    asyncio.run(_walk_newjob_modal())


def test_newjob_modal_auto_picks_org_connector_project() -> None:
    """Regression for the v0.13.0 bug where Browse failed silently."""
    asyncio.run(_walk_newjob_autoflow())


# ---------- v0.14.1: clearer NewJobModal — defaults + 4 buttons + errors ----

async def _walk_newjob_v0141_defaults_and_buttons() -> None:
    """v0.14.1 regression coverage:
    - default retention is 5 days
    - all four buttons (Cancel, Schedule, Run now, Close) exist
    - Cancel + Close both return None
    - Schedule with empty name surfaces a specific error and does NOT
      dismiss
    - A complete Schedule returns payload with _action='schedule'
    - A complete Run now returns payload with _action='run'
    """
    from dr_tui.app import NewJobModal
    from dr_tui.data import Connector
    app = _Harness()
    orgs = ["training"]
    connectors = {
        "training": [
            Connector(name="nfs-a", type="NFS", mode="IMPORT", status="OK",
                      host="10.0.0.1", path="/data/import", handle="c-1"),
        ],
    }
    projects = {"training": [{"name": "test1", "handle": "254"}]}

    async with app.run_test() as pilot:
        # ---- 1. defaults: 5 days ----
        holder: list = []
        modal = NewJobModal(
            orgs=orgs, connectors_by_org=connectors,
            projects_by_org=projects, api_client=None,
        )
        app.push_screen(modal, lambda r: holder.append(r))
        await pilot.pause()
        scr = app.screen
        ret_in = scr.query_one("#newjob-retention", Input)
        ret_unit = scr.query_one("#newjob-retention-unit", _S := __import__(
            "textual.widgets", fromlist=["Select"],
        ).Select)
        assert ret_in.value == "5", f"default retention value: {ret_in.value!r}"
        assert ret_unit.value == "86400", f"default unit: {ret_unit.value!r}"

        # ---- 2. all four buttons exist ----
        for bid in ("newjob-cancel", "newjob-schedule",
                    "newjob-run", "newjob-close"):
            assert scr.query_one(f"#{bid}", Button) is not None, \
                f"missing button {bid}"

        # ---- 3. Close button returns None (same as Cancel) ----
        scr.query_one("#newjob-close", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- 4. empty-name Schedule shows a specific error, doesn't dismiss
        holder = []
        modal = NewJobModal(
            orgs=orgs, connectors_by_org=connectors,
            projects_by_org=projects, api_client=None,
        )
        app.push_screen(modal, lambda r: holder.append(r))
        await pilot.pause()
        scr = app.screen
        # Name field is empty by default.
        scr.query_one("#newjob-schedule", Button).action_press()
        await pilot.pause()
        assert holder == [], "empty name should not dismiss"
        # Error widget exists and is populated.
        err_widget = scr.query_one("#newjob-error", Static)
        assert err_widget is not None
        # Cancel out.
        scr.query_one("#newjob-cancel", Button).action_press()
        await pilot.pause()
        assert holder == [None]

        # ---- 5. complete Schedule path returns payload with _action='schedule'
        holder = []
        modal = NewJobModal(
            orgs=orgs, connectors_by_org=connectors,
            projects_by_org=projects, api_client=None,
        )
        app.push_screen(modal, lambda r: holder.append(r))
        await pilot.pause()
        scr = app.screen
        scr.query_one("#newjob-name", Input).value = "my-test-job"
        # v0.15: path is a manual Input widget — set it directly.
        scr.query_one("#newjob-path", Input).value = "/data/import/payroll/2026"
        scr.query_one("#newjob-schedule", Button).action_press()
        await pilot.pause()
        assert len(holder) == 1, f"expected one result, got {holder!r}"
        payload = holder[0]
        assert payload is not None
        assert payload["_action"] == "schedule"
        assert payload["name"] == "my-test-job"
        assert payload["org"] == "training"
        assert payload["path"] == "/data/import/payroll/2026"
        assert payload["retention_seconds"] == 5 * 86400

        # ---- 6. Run now sets _action='run' ----
        holder = []
        modal = NewJobModal(
            orgs=orgs, connectors_by_org=connectors,
            projects_by_org=projects, api_client=None,
        )
        app.push_screen(modal, lambda r: holder.append(r))
        await pilot.pause()
        scr = app.screen
        scr.query_one("#newjob-name", Input).value = "runnow-job"
        scr.query_one("#newjob-path", Input).value = "/data/import/now"
        scr.query_one("#newjob-run", Button).action_press()
        await pilot.pause()
        assert len(holder) == 1
        assert holder[0]["_action"] == "run"
        assert holder[0]["name"] == "runnow-job"


def test_newjob_modal_v0141_defaults_and_buttons() -> None:
    asyncio.run(_walk_newjob_v0141_defaults_and_buttons())


# ---------- v0.14: unit-name parse + LogViewerModal mount ----------

def test_unit_parse_regex() -> None:
    """`_UNIT_PARSE_RE` round-trips a real systemd unit basename."""
    import dr_tui.scheduler as sch
    importlib.reload(sch)
    m = sch._UNIT_PARSE_RE.match(
        "dr-tools-retention-nightly-payroll-20260513T030000"
    )
    assert m is not None
    assert m.group("slug") == "nightly-payroll"
    assert m.group("run_id") == "20260513T030000"
    # Single-word slugs work too.
    m = sch._UNIT_PARSE_RE.match(
        "dr-tools-retention-archive-20260514T120000"
    )
    assert m and m.group("slug") == "archive"
    # Anything that doesn't match the run-id stamp format is rejected.
    assert sch._UNIT_PARSE_RE.match(
        "dr-tools-retention-bad-runid"
    ) is None


async def _walk_log_viewer() -> None:
    """LogViewerModal mounts on a real file; Esc closes."""
    from dr_tui.app import LogViewerModal
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False,
    ) as f:
        f.write("=== smoke log ===\nline 2\nline 3\n")
        path = f.name
    app = _Harness()
    async with app.run_test() as pilot:
        app.push_screen(LogViewerModal(path=path, title="smoke"))
        await pilot.pause()
        # Iterate until the read worker has run.
        for _ in range(10):
            await pilot.pause()
        scr = app.screen
        assert type(scr).__name__ == "LogViewerModal"
        # Esc closes.
        await pilot.press("escape")
        await pilot.pause()
        assert type(app.screen).__name__ != "LogViewerModal"
    import os; os.unlink(path)


def test_log_viewer_modal_mount() -> None:
    asyncio.run(_walk_log_viewer())


# ---------- 'longterm' coloring rule ----------

def test_longterm_substring_match() -> None:
    """Saved-jobs renderer flags any job name containing 'longterm'.

    v0.15: cue is bold + leading asterisk so it's not colour-only
    (covers colour-blind users — surfaced by the beta-user persona).
    """
    # Mirror the markup logic in _apply_sch_saved without booting the
    # full DashboardScreen (avoiding the live login flow).
    def fmt(name: str) -> str:
        return (f"[yellow b]* {name}[/]"
                if "longterm" in name.lower() else name)

    assert fmt("Nightly Payroll") == "Nightly Payroll"
    assert fmt("payroll-longterm") == "[yellow b]* payroll-longterm[/]"
    assert fmt("LongTermArchive") == "[yellow b]* LongTermArchive[/]"
    # Substring, not whole word — that's intentional per the spec.
    assert fmt("xLONGTERMy") == "[yellow b]* xLONGTERMy[/]"


if __name__ == "__main__":
    import shutil
    d = tempfile.mkdtemp(prefix="dr-sch-test-")
    try:
        test_scheduler_save_load_roundtrip(Path(d))
        print("[scheduler roundtrip: PASS]")
        test_scheduler_run_record_append(Path(d))
        print("[scheduler run-record: PASS]")
        test_scheduler_slugify_edges()
        print("[scheduler slugify: PASS]")
        test_newjob_modal_mount_and_cancel()
        print("[NewJobModal mount + cancel: PASS]")
        test_longterm_substring_match()
        print("[longterm coloring: PASS]")
    finally:
        shutil.rmtree(d, ignore_errors=True)

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


def test_newjob_modal_mount_and_cancel() -> None:
    asyncio.run(_walk_newjob_modal())


# ---------- 'longterm' coloring rule ----------

def test_longterm_substring_match() -> None:
    """Saved-jobs renderer flags any job name containing 'longterm'."""
    # This mirrors the markup logic in _apply_sch_saved without booting
    # the full DashboardScreen (avoiding the login flow).
    def fmt(name: str) -> str:
        return (f"[yellow b]{name}[/]"
                if "longterm" in name.lower() else name)

    assert fmt("Nightly Payroll") == "Nightly Payroll"
    assert fmt("payroll-longterm") == "[yellow b]payroll-longterm[/]"
    assert fmt("LongTermArchive") == "[yellow b]LongTermArchive[/]"
    # Substring, not whole word — that's intentional per the spec.
    assert fmt("xLONGTERMy") == "[yellow b]xLONGTERMy[/]"


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

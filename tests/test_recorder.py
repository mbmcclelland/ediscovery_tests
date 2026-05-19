"""
Unit tests for Phase A recorder subsystem.

Covers:
  - recorder/store.py        — schema, idempotency, write/read roundtrip,
                                retention-like queries, empty windows
  - recorder/health.py       — traffic-light derivation (all bands + rules)
  - recorder/collectors/logs.py   — _classify() + cosmetic filtering
  - recorder/collectors/system.py — psutil sampler key contract
  - commands/campaign.py     — lifecycle via typer CliRunner
  - commands/report.py       — markdown rendering from known data

All tests are purely local (no live SUT required). SQLite stores use
tmp_path so they never share state between tests.
"""

from __future__ import annotations

import sys
import time
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import importlib

import pytest
from typer.testing import CliRunner

# ─── helpers ─────────────────────────────────────────────────────────────────


def _make_store(tmp_path: Path):
    from recorder.store import Store
    return Store(tmp_path / "test.db")


# ═══════════════════════════════════════════════════════════════════════════
# recorder/store.py
# ═══════════════════════════════════════════════════════════════════════════


class TestStoreSchema:
    """Schema creation and idempotency."""

    @pytest.mark.smoke
    def test_schema_created_on_first_open(self, tmp_path):
        from recorder.store import Store
        s = Store(tmp_path / "store.db")
        # schema_meta must have a version row
        with s._cursor() as c:
            row = c.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
        assert row is not None
        assert row[0] == "1"

    @pytest.mark.smoke
    def test_schema_idempotent_on_reopen(self, tmp_path):
        from recorder.store import Store
        db = tmp_path / "store.db"
        s1 = Store(db)
        s1.close()
        # Re-opening must not raise or duplicate the version row
        s2 = Store(db)
        with s2._cursor() as c:
            rows = c.execute("SELECT value FROM schema_meta WHERE key='version'").fetchall()
        assert len(rows) == 1

    def test_store_file_created(self, tmp_path):
        from recorder.store import Store
        db = tmp_path / "sub" / "store.db"
        Store(db)
        assert db.exists()


class TestStoreMetrics:
    """write_metrics / read_metric / latest_metric / signals roundtrips."""

    @pytest.mark.smoke
    def test_write_then_read_metric(self, tmp_path):
        s = _make_store(tmp_path)
        ts = int(time.time())
        s.write_metrics(ts, {"cpu_pct": 42.0, "mem_pct": 55.5})
        rows = s.read_metric("cpu_pct")
        assert len(rows) == 1
        assert rows[0] == (ts, 42.0)

    @pytest.mark.smoke
    def test_write_multiple_ticks(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        for i in range(5):
            s.write_metrics(now + i, {"cpu_pct": float(i * 10)})
        rows = s.read_metric("cpu_pct")
        assert len(rows) == 5
        assert [v for _, v in rows] == [0.0, 10.0, 20.0, 30.0, 40.0]

    def test_read_metric_since_filter(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        s.write_metrics(now - 100, {"cpu_pct": 1.0})
        s.write_metrics(now, {"cpu_pct": 2.0})
        rows = s.read_metric("cpu_pct", since=now - 10)
        assert len(rows) == 1
        assert rows[0][1] == 2.0

    def test_read_metric_until_filter(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        s.write_metrics(now - 100, {"cpu_pct": 1.0})
        s.write_metrics(now, {"cpu_pct": 2.0})
        rows = s.read_metric("cpu_pct", until=now - 50)
        assert len(rows) == 1
        assert rows[0][1] == 1.0

    def test_read_metric_since_and_until(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        for i in range(5):
            s.write_metrics(now + i * 10, {"cpu_pct": float(i)})
        # middle slice
        rows = s.read_metric("cpu_pct", since=now + 5, until=now + 25)
        assert len(rows) == 2

    def test_read_metric_empty_window(self, tmp_path):
        s = _make_store(tmp_path)
        rows = s.read_metric("cpu_pct", since=int(time.time()) - 60)
        assert rows == []

    def test_latest_metric(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        s.write_metrics(now, {"mem_pct": 10.0})
        s.write_metrics(now + 5, {"mem_pct": 99.0})
        result = s.latest_metric("mem_pct")
        assert result is not None
        ts, val = result
        assert val == 99.0

    def test_latest_metric_none_when_empty(self, tmp_path):
        s = _make_store(tmp_path)
        assert s.latest_metric("nonexistent") is None

    def test_signals_returns_all_written(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        s.write_metrics(now, {"cpu_pct": 1.0, "mem_pct": 2.0, "disk_io_mb_s": 0.5})
        sigs = set(s.signals())
        assert "cpu_pct" in sigs
        assert "mem_pct" in sigs
        assert "disk_io_mb_s" in sigs

    def test_write_metrics_skips_none_values(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        # None values must be filtered
        s.write_metrics(now, {"cpu_pct": None, "mem_pct": 50.0})  # type: ignore[dict-item]
        rows = s.read_metric("cpu_pct")
        assert rows == []
        rows2 = s.read_metric("mem_pct")
        assert len(rows2) == 1


class TestStoreEvents:
    """write_event / read_events roundtrip and filters."""

    @pytest.mark.smoke
    def test_write_and_read_event(self, tmp_path):
        s = _make_store(tmp_path)
        ts = int(time.time())
        s.write_event("TEST_EVENT", campaign="camp1", payload={"key": "val"}, ts=ts)
        evs = s.read_events()
        assert len(evs) >= 1
        ev = next(e for e in evs if e["kind"] == "TEST_EVENT")
        assert ev["campaign"] == "camp1"
        assert ev["payload"] == {"key": "val"}

    def test_event_payload_is_deserialized(self, tmp_path):
        s = _make_store(tmp_path)
        s.write_event("FOO", payload={"x": [1, 2, 3]}, ts=int(time.time()))
        evs = s.read_events(kind="FOO")
        assert evs[0]["payload"] == {"x": [1, 2, 3]}

    def test_read_events_kind_filter(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        s.write_event("KIND_A", ts=now)
        s.write_event("KIND_B", ts=now + 1)
        assert len(s.read_events(kind="KIND_A")) == 1
        assert len(s.read_events(kind="KIND_B")) == 1

    def test_read_events_campaign_filter(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        s.write_event("EV", campaign="alpha", ts=now)
        s.write_event("EV", campaign="beta", ts=now + 1)
        alpha = s.read_events(campaign="alpha")
        assert all(e["campaign"] == "alpha" for e in alpha)

    def test_read_events_since_filter(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        s.write_event("OLD", ts=now - 1000)
        s.write_event("NEW", ts=now)
        evs = s.read_events(since=now - 1)
        assert all(e["kind"] == "NEW" for e in evs)

    def test_read_events_empty_store(self, tmp_path):
        s = _make_store(tmp_path)
        assert s.read_events() == []


class TestStoreCampaigns:
    """Campaign lifecycle: start, adjust, end, query."""

    @pytest.mark.smoke
    def test_start_campaign(self, tmp_path):
        s = _make_store(tmp_path)
        ts = int(time.time())
        s.start_campaign("my-campaign", scenario="indexing", initial_users=5, ts=ts)
        camp = s.campaign("my-campaign")
        assert camp is not None
        assert camp["scenario"] == "indexing"
        assert camp["initial_users"] == 5
        assert camp["current_users"] == 5
        assert camp["ended_at"] is None

    def test_start_writes_start_event(self, tmp_path):
        s = _make_store(tmp_path)
        s.start_campaign("c1", ts=int(time.time()))
        evs = s.read_events(kind="START", campaign="c1")
        assert len(evs) == 1

    def test_adjust_campaign(self, tmp_path):
        s = _make_store(tmp_path)
        s.start_campaign("c1", initial_users=5, ts=int(time.time()))
        s.adjust_campaign("c1", users=20, note="ramp up")
        camp = s.campaign("c1")
        assert camp["current_users"] == 20
        evs = s.read_events(kind="ADJUST", campaign="c1")
        assert len(evs) == 1
        assert evs[0]["payload"]["users"] == 20

    def test_end_campaign(self, tmp_path):
        s = _make_store(tmp_path)
        s.start_campaign("c1", ts=int(time.time()))
        s.end_campaign("c1", note="done")
        camp = s.campaign("c1")
        assert camp["ended_at"] is not None
        evs = s.read_events(kind="END", campaign="c1")
        assert len(evs) == 1

    def test_active_campaign_returns_none_when_all_ended(self, tmp_path):
        s = _make_store(tmp_path)
        s.start_campaign("c1", ts=int(time.time()))
        s.end_campaign("c1")
        assert s.active_campaign() is None

    def test_active_campaign_returns_open_one(self, tmp_path):
        s = _make_store(tmp_path)
        s.start_campaign("c1", ts=int(time.time()))
        s.end_campaign("c1")
        s.start_campaign("c2", ts=int(time.time()) + 1)
        camp = s.active_campaign()
        assert camp is not None
        assert camp["name"] == "c2"

    def test_all_campaigns_ordered_desc(self, tmp_path):
        s = _make_store(tmp_path)
        now = int(time.time())
        s.start_campaign("c1", ts=now)
        s.start_campaign("c2", ts=now + 1)
        camps = s.all_campaigns()
        assert camps[0]["name"] == "c2"
        assert camps[1]["name"] == "c1"

    def test_campaign_not_found_returns_none(self, tmp_path):
        s = _make_store(tmp_path)
        assert s.campaign("does-not-exist") is None


# ═══════════════════════════════════════════════════════════════════════════
# recorder/health.py
# ═══════════════════════════════════════════════════════════════════════════


class TestDeriveHealthBands:
    """All five signal bands: green/yellow/red thresholds."""

    @pytest.mark.smoke
    def test_all_ok_is_green(self):
        from recorder.health import derive_health
        samples = {
            "cpu_pct": 50.0,
            "mem_pct": 50.0,
            "disk_await_ms": 10.0,
            "err_new": 0.0,
        }
        assert derive_health(samples) == "green"

    @pytest.mark.smoke
    def test_all_critical_is_red(self):
        from recorder.health import derive_health
        samples = {
            "cpu_pct": 90.0,   # critical >85
            "mem_pct": 90.0,   # critical >85
        }
        assert derive_health(samples) == "red"

    def test_one_degraded_is_green(self):
        from recorder.health import derive_health
        # Only cpu in yellow band; all others ok
        samples = {"cpu_pct": 75.0, "mem_pct": 50.0}
        assert derive_health(samples) == "green"

    def test_two_degraded_is_yellow(self):
        from recorder.health import derive_health
        # Both cpu and mem in yellow band
        samples = {"cpu_pct": 75.0, "mem_pct": 75.0}
        assert derive_health(samples) == "yellow"

    def test_one_critical_one_ok_is_green(self):
        from recorder.health import derive_health
        samples = {"cpu_pct": 90.0, "mem_pct": 50.0}
        # 1 critical, 0 other degraded → only 1 degraded total → green
        assert derive_health(samples) == "green"

    def test_two_critical_is_red(self):
        from recorder.health import derive_health
        samples = {"cpu_pct": 90.0, "mem_pct": 90.0}
        assert derive_health(samples) == "red"

    def test_disk_await_bands(self):
        from recorder.health import derive_health
        # ok
        assert derive_health({"disk_await_ms": 10.0}) == "green"
        # yellow
        assert derive_health({"disk_await_ms": 100.0, "cpu_pct": 75.0}) == "yellow"
        # critical
        assert derive_health({"disk_await_ms": 201.0, "cpu_pct": 90.0}) == "red"

    def test_err_new_bands(self):
        from recorder.health import derive_health
        # err_new is per-tick; tick_sec=10 → per_min = err_new * 6
        # <1/min → ok: err_new < 1/6
        assert derive_health({"err_new": 0.1}, tick_sec=10) == "green"
        # 1-10/min → degraded: err_new = 2 → 12/min → critical
        assert derive_health({"err_new": 0.5, "cpu_pct": 75.0}, tick_sec=10) == "yellow"
        # >10/min → critical: err_new = 2 → 12/min
        samples = {"err_new": 2.0, "cpu_pct": 90.0}
        assert derive_health(samples, tick_sec=10) == "red"

    def test_indexing_stalled_while_running_is_red(self):
        from recorder.health import derive_health
        samples = {
            "cpu_pct": 30.0,
            "docs_per_min": 0.0,
            "running_tasks": 2.0,
        }
        assert derive_health(samples) == "red"

    def test_indexing_zero_with_no_running_tasks_is_green(self):
        from recorder.health import derive_health
        samples = {
            "cpu_pct": 30.0,
            "docs_per_min": 0.0,
            "running_tasks": 0.0,
        }
        # No active tasks → zero docs_per_min is not a stall
        assert derive_health(samples) == "green"

    def test_indexing_baseline_below_50pct_is_critical(self):
        from recorder.health import derive_health
        # 40% of 100-doc/min baseline with active tasks → critical
        samples = {
            "docs_per_min": 40.0,
            "running_tasks": 1.0,
        }
        result = derive_health(samples, indexing_baseline_per_min=100.0)
        # 1 critical signal → green (need 2 for red, 2 for yellow)
        # Actually: only 1 signal in states list; n_degraded=1; n_critical=1 → green
        assert result == "green"

    def test_indexing_50_to_80_pct_is_degraded(self):
        from recorder.health import derive_health
        samples = {
            "docs_per_min": 65.0,
            "running_tasks": 1.0,
            "cpu_pct": 75.0,       # also degraded → 2 degraded → yellow
        }
        result = derive_health(samples, indexing_baseline_per_min=100.0)
        assert result == "yellow"

    def test_no_samples_returns_none(self):
        from recorder.health import derive_health
        assert derive_health({}) is None

    def test_running_tasks_absent_means_no_indexing_penalty(self):
        from recorder.health import derive_health
        # docs_per_min present but running_tasks absent → indexing not evaluated
        samples = {"docs_per_min": 0.0, "cpu_pct": 30.0}
        assert derive_health(samples) == "green"

    def test_n_critical_2_escalates_to_red_over_2_degraded(self):
        from recorder.health import derive_health
        # 2 degraded would normally be yellow, but 2 critical → red
        samples = {"cpu_pct": 90.0, "mem_pct": 90.0, "disk_await_ms": 10.0}
        assert derive_health(samples) == "red"


# ═══════════════════════════════════════════════════════════════════════════
# recorder/collectors/logs.py — _classify()
# ═══════════════════════════════════════════════════════════════════════════


class TestLogsClassify:
    """_classify() correctly categorises lines."""

    def _cls(self, line: str):
        from recorder.collectors.logs import _classify
        return _classify(line)

    @pytest.mark.smoke
    def test_error_line_classified_as_error(self):
        assert self._cls("2026-05-19 10:00 ERROR Something went wrong") == "error"

    @pytest.mark.smoke
    def test_warn_line_classified_as_warn(self):
        assert self._cls("2026-05-19 10:00 WARN Low disk space") == "warn"

    def test_info_line_classified_as_none(self):
        assert self._cls("2026-05-19 10:00 INFO Normal operation") is None

    def test_fatal_classified_as_error(self):
        assert self._cls("FATAL NullPointerException at line 42") == "error"

    def test_exception_classified_as_error(self):
        assert self._cls("java.lang.Exception: boom") == "error"

    # --- all 13 cosmetic patterns ---

    def test_cosmetic_could_not_find_role_row(self):
        assert self._cls("ERROR Could not find role row with: somekey") == "cosmetic"

    def test_cosmetic_add_object_work_basket(self):
        line = "ERROR Add object - could not find parent object [123] when creating type [WORK_BASKET]"
        assert self._cls(line) == "cosmetic"

    def test_cosmetic_add_object_saved_search_query(self):
        line = "ERROR Add object - could not find parent object [456] when creating type [SAVED_SEARCH_QUERY]"
        assert self._cls(line) == "cosmetic"

    def test_cosmetic_add_object_project_preferences(self):
        line = "ERROR Add object - could not find parent object [789] when creating type [PROJECT_PREFERENCES]"
        assert self._cls(line) == "cosmetic"

    def test_cosmetic_exception_canceling_requests(self):
        assert self._cls("ERROR Exception when canceling all requests for project 99") == "cosmetic"

    def test_cosmetic_javax_mail(self):
        assert self._cls("ERROR javax.mail.Session.getProperty('mail.smtp.host')") == "cosmetic"

    def test_cosmetic_send_email_cae_error(self):
        assert self._cls("ERROR SendEmail something CAE_ERROR occurred") == "cosmetic"

    def test_cosmetic_queue_polling_error(self):
        assert self._cls("ERROR Queue Polling Error: java.lang.InterruptedException") == "cosmetic"

    def test_cosmetic_creating_new_queue(self):
        assert self._cls("ERROR Creating a new queue for 192.168.1.100") == "cosmetic"

    def test_cosmetic_get_data_area_cfg_by_org(self):
        assert self._cls("ERROR getDataAreaCfgByOrg: org [null]") == "cosmetic"

    def test_cosmetic_invalid_event_job_status(self):
        assert self._cls("ERROR Invalid event of JOB_STATUS_UPDATE in state DIRECTORY_DELETE_JOB") == "cosmetic"

    def test_cosmetic_could_not_execute_storage_quota(self):
        assert self._cls("ERROR Could Not execute StorageQuotaCheck") == "cosmetic"

    def test_cosmetic_invalid_state_negative_numjobs(self):
        assert self._cls("ERROR Invalid state found - negative numJobsCurrent") == "cosmetic"

    def test_cosmetic_invalid_state_negative_generic(self):
        assert self._cls("ERROR Invalid state found - negative something else") == "cosmetic"

    def test_cosmetic_chain_of_custody(self):
        assert self._cls("ERROR ChainOfCustodyFactory something cp command exit code is 1") == "cosmetic"

    def test_new_unknown_error_is_error_not_cosmetic(self):
        assert self._cls("ERROR brand new failure that is not in cosmetic list") == "error"

    def test_warn_only_does_not_trigger_error(self):
        # A WARN-only line should never be classified as error
        result = self._cls("WARN Something slow happened")
        assert result == "warn"
        assert result != "error"


class TestLogsSample:
    """sample() incremental byte-tracking integration test."""

    def test_sample_returns_required_keys(self, tmp_path):
        # Reset module-level _positions state by reimporting
        import recorder.collectors.logs as logs_mod
        logs_mod._positions.clear()

        # Create a log file
        logfile = tmp_path / "test.log"
        logfile.write_text("INFO startup complete\n")

        result = logs_mod.sample(tmp_path)
        assert "err_new" in result
        assert "warn_new" in result
        assert "err_cosmetic_new" in result

    def test_sample_only_counts_new_lines(self, tmp_path):
        import recorder.collectors.logs as logs_mod
        logs_mod._positions.clear()

        logfile = tmp_path / "server.log"
        logfile.write_text("INFO line 1\n")
        # First call: seeds position, returns zeros
        r1 = logs_mod.sample(tmp_path)
        assert r1["err_new"] == 0.0

        # Append an error line
        with open(logfile, "a") as f:
            f.write("ERROR Something broke\n")
        r2 = logs_mod.sample(tmp_path)
        assert r2["err_new"] == 1.0

    def test_sample_suppresses_cosmetic_errors(self, tmp_path):
        import recorder.collectors.logs as logs_mod
        logs_mod._positions.clear()

        logfile = tmp_path / "server.log"
        logfile.write_text("INFO startup\n")
        logs_mod.sample(tmp_path)  # seed

        with open(logfile, "a") as f:
            f.write("ERROR Could not find role row with: something\n")
        r = logs_mod.sample(tmp_path)
        assert r["err_new"] == 0.0
        assert r["err_cosmetic_new"] == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# recorder/collectors/system.py
# ═══════════════════════════════════════════════════════════════════════════


class TestSystemSample:
    """psutil sampler: key contract and delta-on-second-call."""

    @pytest.mark.smoke
    def test_returns_required_keys(self):
        import recorder.collectors.system as sys_mod
        sys_mod._prev_io = None  # reset state
        result = sys_mod.sample()
        for key in ("cpu_pct", "mem_pct", "disk_used_gb", "disk_pct"):
            assert key in result, f"missing key: {key}"

    def test_all_values_are_float(self):
        import recorder.collectors.system as sys_mod
        sys_mod._prev_io = None
        result = sys_mod.sample()
        for k, v in result.items():
            assert isinstance(v, float), f"{k} is not float: {type(v)}"

    def test_second_call_adds_disk_io_mb_s(self):
        import recorder.collectors.system as sys_mod
        sys_mod._prev_io = None
        sys_mod.sample()          # seed the prev_io state
        result2 = sys_mod.sample()
        assert "disk_io_mb_s" in result2
        assert result2["disk_io_mb_s"] >= 0.0

    def test_disk_io_mb_s_non_negative_on_repeated_calls(self):
        import recorder.collectors.system as sys_mod
        sys_mod._prev_io = None
        sys_mod.sample()
        for _ in range(3):
            r = sys_mod.sample()
            if "disk_io_mb_s" in r:
                assert r["disk_io_mb_s"] >= 0.0

    def test_mem_pct_in_valid_range(self):
        import recorder.collectors.system as sys_mod
        sys_mod._prev_io = None
        result = sys_mod.sample()
        assert 0.0 <= result["mem_pct"] <= 100.0


# ═══════════════════════════════════════════════════════════════════════════
# commands/campaign.py — CliRunner lifecycle tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCampaignCLI:
    """Full campaign lifecycle via typer CliRunner against a temp SQLite store."""

    @pytest.fixture
    def store_path(self, tmp_path):
        return str(tmp_path / "campaign_test.db")

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def app(self):
        from commands.campaign import app
        return app

    @pytest.mark.smoke
    def test_new_campaign(self, runner, app, store_path):
        result = runner.invoke(app, [
            "new", "test-camp",
            "--scenario", "indexing",
            "--users", "3",
            "--store", store_path,
        ])
        assert result.exit_code == 0
        assert "test-camp" in result.output
        assert "OK" in result.output

    def test_new_campaign_conflict_rejected(self, runner, app, store_path):
        runner.invoke(app, ["new", "first", "--store", store_path])
        result = runner.invoke(app, ["new", "second", "--store", store_path])
        assert result.exit_code == 2
        assert "active" in result.output.lower() or "end it first" in result.output.lower()

    def test_adjust_updates_user_count(self, runner, app, store_path):
        runner.invoke(app, ["new", "camp-adj", "--users", "5", "--store", store_path])
        result = runner.invoke(app, ["adjust", "--users", "15", "--store", store_path])
        assert result.exit_code == 0
        assert "5" in result.output
        assert "15" in result.output

    def test_adjust_fails_with_no_active_campaign(self, runner, app, store_path):
        result = runner.invoke(app, ["adjust", "--users", "10", "--store", store_path])
        assert result.exit_code == 2

    def test_event_annotation_recorded(self, runner, app, store_path):
        runner.invoke(app, ["new", "camp-ev", "--store", store_path])
        result = runner.invoke(app, ["event", "reached steady state", "--store", store_path])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_end_closes_campaign(self, runner, app, store_path):
        runner.invoke(app, ["new", "camp-end", "--store", store_path])
        result = runner.invoke(app, ["end", "--store", store_path])
        assert result.exit_code == 0
        assert "ended" in result.output.lower() or "OK" in result.output

    def test_end_fails_with_no_active_campaign(self, runner, app, store_path):
        result = runner.invoke(app, ["end", "--store", store_path])
        assert result.exit_code == 2

    @pytest.mark.smoke
    def test_full_lifecycle_writes_correct_events(self, runner, app, store_path, tmp_path):
        """new → adjust → event → end produces the right DB events."""
        runner.invoke(app, ["new", "lifecycle", "--users", "2", "--store", store_path])
        runner.invoke(app, ["adjust", "--users", "8", "--store", store_path])
        runner.invoke(app, ["event", "note this", "--store", store_path])
        runner.invoke(app, ["end", "--note", "finished", "--store", store_path])

        from recorder.store import Store
        s = Store(tmp_path / "campaign_test.db")
        evs = s.read_events(campaign="lifecycle")
        kinds = [e["kind"] for e in evs]
        assert kinds == ["START", "ADJUST", "ANNOTATE", "END"]

    def test_list_shows_all_campaigns(self, runner, app, store_path):
        runner.invoke(app, ["new", "alpha", "--store", store_path])
        runner.invoke(app, ["end", "--store", store_path])
        runner.invoke(app, ["new", "beta", "--store", store_path])
        result = runner.invoke(app, ["list", "--store", store_path])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output

    def test_show_active_campaign(self, runner, app, store_path):
        runner.invoke(app, ["new", "show-test", "--scenario", "browsing", "--store", store_path])
        result = runner.invoke(app, ["show", "--store", store_path])
        assert result.exit_code == 0
        assert "show-test" in result.output
        assert "browsing" in result.output

    def test_show_named_campaign(self, runner, app, store_path):
        runner.invoke(app, ["new", "named-camp", "--store", store_path])
        runner.invoke(app, ["end", "--store", store_path])
        result = runner.invoke(app, ["show", "named-camp", "--store", store_path])
        assert result.exit_code == 0
        assert "named-camp" in result.output

    def test_show_nonexistent_campaign(self, runner, app, store_path):
        result = runner.invoke(app, ["show", "ghost", "--store", store_path])
        assert result.exit_code == 2


# ═══════════════════════════════════════════════════════════════════════════
# commands/report.py — markdown rendering from known data
# ═══════════════════════════════════════════════════════════════════════════


class TestReportCLI:
    """Feed a small store with known samples; assert headline numbers."""

    @pytest.fixture
    def populated_store(self, tmp_path):
        """Create a store with a ended campaign and some known metrics."""
        from recorder.store import Store
        db = tmp_path / "report_test.db"
        s = Store(db)
        now = int(time.time())
        start = now - 600  # 10 minutes ago

        s.start_campaign("report-camp", scenario="indexing", initial_users=10, ts=start)

        # Write 5 metric ticks
        for i in range(5):
            ts = start + i * 120  # every 2 minutes
            s.write_metrics(ts, {
                "cpu_pct": 40.0 + i * 5,
                "mem_pct": 60.0,
                "disk_used_gb": 50.0,
                "disk_io_mb_s": 1.0,
                "disk_iops": 100.0,
                "disk_await_ms": 5.0,
                "docs_per_min": 50.0,
                "docs_total": float(1000 + i * 50),
                "running_tasks": 3.0,
                "running_projects": 2.0,
                "total_projects": 41.0,
                "err_new": 0.0,
                "err_cosmetic_new": 2.0,
                "warn_new": 1.0,
            })

        s.end_campaign("report-camp")
        return db

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def app(self):
        from commands.report import app
        return app

    @pytest.mark.smoke
    def test_report_self_markdown_contains_verdict(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--campaign", "report-camp",
            "--audience", "self",
            "--format", "markdown",
            "--store", str(populated_store),
        ])
        assert result.exit_code == 0
        assert "**Verdict:**" in result.output
        assert "GREEN" in result.output

    def test_report_contains_campaign_name(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--campaign", "report-camp",
            "--format", "markdown",
            "--store", str(populated_store),
        ])
        assert "report-camp" in result.output

    def test_report_contains_cpu_stats(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--campaign", "report-camp",
            "--format", "markdown",
            "--store", str(populated_store),
        ])
        assert "CPU %" in result.output

    def test_report_docs_indexed_nonzero(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--campaign", "report-camp",
            "--format", "markdown",
            "--store", str(populated_store),
        ])
        # docs_total goes 1000 → 1200, so docs_indexed_window = 200
        assert "200" in result.output

    def test_report_mgmt_audience(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--campaign", "report-camp",
            "--audience", "mgmt",
            "--format", "markdown",
            "--store", str(populated_store),
        ])
        assert result.exit_code == 0
        assert "Throughput" in result.output
        assert "Reliability" in result.output

    def test_report_capacity_audience_has_headroom(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--campaign", "report-camp",
            "--audience", "capacity",
            "--format", "markdown",
            "--store", str(populated_store),
        ])
        assert result.exit_code == 0
        assert "Headroom" in result.output

    @pytest.mark.smoke
    def test_report_csv_format(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--campaign", "report-camp",
            "--format", "csv",
            "--store", str(populated_store),
        ])
        assert result.exit_code == 0
        assert "section,metric,value" in result.output
        assert "verdict" in result.output

    def test_report_invalid_format_exits_nonzero(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--campaign", "report-camp",
            "--format", "json",
            "--store", str(populated_store),
        ])
        assert result.exit_code != 0

    def test_report_unknown_campaign_exits_nonzero(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--campaign", "ghost-camp",
            "--store", str(populated_store),
        ])
        assert result.exit_code != 0

    def test_report_since_window(self, runner, app, populated_store):
        result = runner.invoke(app, [
            "--since", "30m",
            "--format", "markdown",
            "--store", str(populated_store),
        ])
        assert result.exit_code == 0
        assert "**Verdict:**" in result.output

    def test_report_write_to_file(self, runner, app, populated_store, tmp_path):
        out_file = tmp_path / "output.md"
        result = runner.invoke(app, [
            "--campaign", "report-camp",
            "--out", str(out_file),
            "--store", str(populated_store),
        ])
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "**Verdict:**" in content


# ═══════════════════════════════════════════════════════════════════════════
# commands/record.py — status / stop edge cases via store
# ═══════════════════════════════════════════════════════════════════════════


class TestRecordCLI:
    """Verify record status and stop edge cases without starting a real daemon."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def app(self):
        from commands.record import app
        return app

    def test_status_shows_stopped_when_no_pid(self, runner, app, tmp_path):
        store = str(tmp_path / "status_test.db")
        result = runner.invoke(app, ["status", "--store", store])
        assert result.exit_code == 0
        assert "STOPPED" in result.output

    def test_stop_with_no_pid_file_exits_2(self, runner, app, tmp_path):
        store = str(tmp_path / "no_pid_test.db")
        result = runner.invoke(app, ["stop", "--store", store])
        assert result.exit_code == 2

    def test_status_with_existing_store_shows_signals(self, runner, app, tmp_path):
        store_path = tmp_path / "sig_test.db"
        from recorder.store import Store
        s = Store(store_path)
        now = int(time.time())
        s.write_metrics(now, {"cpu_pct": 30.0, "mem_pct": 55.0})
        s.close()

        result = runner.invoke(app, ["status", "--store", str(store_path)])
        assert result.exit_code == 0
        assert "signals:" in result.output

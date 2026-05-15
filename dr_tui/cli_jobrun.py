"""dr_job_run — fire a saved JobDefinition's indexing chain end-to-end.

Same code path is used for "Run Now" from the TUI and for any future
cron / systemd-timer driven launches; that's why it's a separate CLI
rather than an inline DashboardScreen worker.

Usage:
    dr_job_run <job-name-or-slug>

Side effects, in order:
  1. Resolves the JobDefinition from `~/.dr-tools/jobs/<slug>.json`.
  2. Logs into DR using the same `.env` the rest of dr-tools reads.
  3. Runs `submit_indexing_job()` (createDataArea → createCorpus →
     createRepresentation), capturing the trio of handles it returns.
  4. Appends a RunRecord to `~/.dr-tools/runs/<slug>.jsonl`.
  5. If `retention_seconds > 0`, schedules a one-shot systemd user
     timer that will invoke `dr_job_delete <slug> <run_id>` at the
     retention horizon.
  6. Tee'd stdout/stderr also lands in `~/.dr-tools/logs/<slug>-<ts>.log`
     so the TUI's "View Log" action has something to show.

Exits 0 on success, 1 on any failure with a one-line diagnostic on
stderr (suitable for piping into the systemd journal).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import Config, OrgUserConfig
from helpers.api_client import APIError, EDiscoveryClient

from dr_tui import data as drdata
from dr_tui import scheduler as drsch


def _stamp() -> str:
    """14-char UTC stamp used as both run_id and log-file infix."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _log_paths(slug: str, run_id: str) -> Path:
    drsch.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return drsch.LOGS_DIR / f"{slug}-{run_id}.log"


class _Tee:
    """Tee writes to both an underlying stream and an open file.

    Used to capture stdout/stderr into the log file *and* keep them
    visible on the terminal/journal — `dr_job_run` may be invoked
    interactively from the TUI, so we don't want to silently swallow
    output.
    """
    def __init__(self, stream, fh):
        self._stream = stream
        self._fh = fh
    def write(self, s):
        try: self._stream.write(s)
        except Exception: pass
        try: self._fh.write(s)
        except Exception: pass
    def flush(self):
        for x in (self._stream, self._fh):
            try: x.flush()
            except Exception: pass


def _login_for_job(job_org: str) -> EDiscoveryClient:
    """Log in as the **organization admin** for `job_org`.

    DR's permission model (per the official 5.5.3.1 documentation:
    "Add or Edit a Project Data Area" → "Requires Organization -
    Project Data Areas - Add/Edit Permissions") puts the indexing
    chain (`createDataArea` / `createCorpus` / `createRepresentation`)
    behind an **org-scoped** role, NOT a system-scoped one. DRSysAdmin
    is denied with HTTP 500 + "User drsysadmin does not have
    permission to perform createDataArea operation" — matches the
    locustfile_indexing pattern, which also runs the indexing chain
    on an org token.

    Reads `~/.env`'s `DR_ORG_*` keys; warns when the job's org doesn't
    match the configured org-admin login.
    """
    org_cfg = OrgUserConfig()
    if job_org and org_cfg.organization and job_org != org_cfg.organization:
        # Not fatal — the caller may have legitimately set up a single
        # org-admin account with cross-org permissions — but the user
        # deserves a heads-up.
        print(
            f"WARN job org={job_org!r} differs from "
            f"DR_ORG_ORGANIZATION={org_cfg.organization!r}; "
            f"login will proceed against {org_cfg.organization!r}",
            file=sys.stderr,
        )
    client = EDiscoveryClient(org_cfg)
    pw = os.environ.get("DR_PASS") or org_cfg.password or ""
    client.login(password=pw)
    return client


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print("usage: dr_job_run <job-name-or-slug>", file=sys.stderr)
        return 2
    name = argv[0]
    job = drsch.get_job(name)
    if job is None:
        print(f"dr_job_run: no saved job named {name!r}", file=sys.stderr)
        return 1

    run_id = _stamp()
    log_path = _log_paths(job.slug(), run_id)
    log_fh = log_path.open("w")
    sys.stdout = _Tee(sys.__stdout__, log_fh)
    sys.stderr = _Tee(sys.__stderr__, log_fh)

    print(f"=== dr_job_run {job.name} run_id={run_id} "
          f"started={drsch._now_iso()} ===")
    print(f"org={job.org} project_handle={job.project_handle} "
          f"connector={job.connector_name} path={job.path}")

    try:
        client = _login_for_job(job.org)
    except APIError as e:
        print(f"FAIL org-admin login: {e.error_code or e.status} "
              f"{e.extended_status} — does the org-admin user "
              f"({job.org}) exist? Run `python playwright_fresh_init.py` "
              f"to (re)create it.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FAIL org-admin login: {e!r} — does the org-admin "
              f"user ({job.org}) exist? Run "
              f"`python playwright_fresh_init.py`.", file=sys.stderr)
        return 1

    dataset = f"{job.slug()}-{run_id}"
    try:
        result = drdata.submit_indexing_job(
            client,
            project_handle=job.project_handle,
            connector_handle=job.connector_handle,
            path=job.path,
            dataset_name=dataset,
        )
    except APIError as e:
        print(f"FAIL submit: {e.error_code or e.status} "
              f"{e.extended_status}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FAIL submit: {e!r}", file=sys.stderr)
        return 1

    rec = drsch.RunRecord(
        run_id=run_id,
        started_at=drsch._now_iso(),
        task_handle=result["task_handle"],
        corpus_handle=result["corpus_handle"],
        data_area_handle=result["data_area_handle"],
        status="RUNNING",
    )
    drsch.append_run(job.slug(), rec)
    print(f"OK submitted: task_handle={rec.task_handle} "
          f"corpus_handle={rec.corpus_handle} "
          f"data_area_handle={rec.data_area_handle}")

    if job.retention_seconds > 0:
        unit, err = drsch.schedule_retention_delete(
            job_slug=job.slug(),
            run_id=run_id,
            seconds_from_now=job.retention_seconds,
            job_name=job.name,
        )
        if err:
            print(f"WARN retention timer: {err}", file=sys.stderr)
        else:
            print(f"OK retention timer scheduled: {unit}.timer "
                  f"(fires in {job.retention_seconds}s)")
    else:
        print("OK retention disabled (retention_seconds=0)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

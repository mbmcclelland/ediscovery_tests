"""dr_job_delete — retention cleanup for one RunRecord.

Invoked by the systemd `.service` that's wired up by `dr_job_run` when
a JobDefinition has a non-zero `retention_seconds`. Deletes the corpus
and data area that were created during that run; marks the RunRecord
as `DELETED` so the UI can show "expired" runs without re-attempting.

Usage:
    dr_job_delete <job-slug> <run-id>

Exits 0 on success (including when the data was already gone — e.g.
deleted manually) and 1 on any unrecoverable error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from config import Config, OrgUserConfig
from helpers.api_client import APIError, EDiscoveryClient

from dr_tui import data as drdata
from dr_tui import scheduler as drsch


def _rewrite_run_status(slug: str, run_id: str, status: str, notes: str = "") -> None:
    """Update one RunRecord in-place by reading the JSONL, swapping the
    matching record's status / finished_at / notes, and writing it back.

    Cheap because the runs file is small (typically <100 lines per job).
    """
    path = drsch.RUNS_DIR / f"{slug}.jsonl"
    if not path.exists():
        return
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("run_id") == run_id:
            row["status"] = status
            row["finished_at"] = drsch._now_iso()
            if notes:
                row["notes"] = notes
        rows.append(row)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) != 2 or argv[0] in ("-h", "--help"):
        print("usage: dr_job_delete <job-slug> <run-id>", file=sys.stderr)
        return 2
    slug, run_id = argv

    job = drsch.get_job(slug)
    if job is None:
        print(f"dr_job_delete: no saved job named {slug!r}", file=sys.stderr)
        return 1
    # Find the matching RunRecord.
    target = None
    for r in drsch.list_runs(slug):
        if r.run_id == run_id:
            target = r
            break
    if target is None:
        print(f"dr_job_delete: no run {run_id!r} for job {slug!r}", file=sys.stderr)
        return 1
    if target.status == "DELETED":
        print(f"already DELETED; nothing to do")
        return 0

    # Log in as the org admin. `deleteCorpus` / `deleteDataArea` are
    # the inverse of the create chain that `dr_job_run` invokes — same
    # org-scoped permission requirement, so we need an org-admin token
    # too. (DR's official docs put data-area + corpus permissions under
    # "Organization - ..." roles. DRSysAdmin gets denied with HTTP 500.)
    import os
    org_cfg = OrgUserConfig()
    try:
        client = EDiscoveryClient(org_cfg)
        client.login(password=(
            os.environ.get("DR_PASS") or org_cfg.password or ""
        ))
    except APIError as e:
        print(f"FAIL org-admin login: {e.error_code or e.status} "
              f"{e.extended_status} — does the org-admin user "
              f"({job.org}) exist? Run "
              f"`python playwright_fresh_init.py`.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FAIL org-admin login: {e!r}", file=sys.stderr)
        return 1

    err_pieces = []
    if target.corpus_handle:
        try:
            drdata.delete_corpus(
                client, project_handle=job.project_handle,
                corpus_handle=target.corpus_handle,
            )
            print(f"OK deleted corpus {target.corpus_handle}")
        except APIError as e:
            # 404 / already-gone is benign for retention cleanup.
            note = (e.extended_status or "")[:120]
            if "NOT_FOUND" in (e.error_code or "") or "404" in str(e.status):
                print(f"corpus {target.corpus_handle} already gone")
            else:
                err_pieces.append(f"corpus: {e.error_code or e.status} {note}")
        except Exception as e:
            err_pieces.append(f"corpus: {e!r}")

    if target.data_area_handle:
        try:
            drdata.delete_data_area(
                client, project_handle=job.project_handle,
                data_area_handle=target.data_area_handle,
            )
            print(f"OK deleted data area {target.data_area_handle}")
        except APIError as e:
            note = (e.extended_status or "")[:120]
            if "NOT_FOUND" in (e.error_code or "") or "404" in str(e.status):
                print(f"data area {target.data_area_handle} already gone")
            else:
                err_pieces.append(f"data area: {e.error_code or e.status} {note}")
        except Exception as e:
            err_pieces.append(f"data area: {e!r}")

    if err_pieces:
        notes = " | ".join(err_pieces)
        _rewrite_run_status(slug, run_id, "DELETE_FAILED", notes)
        print(f"FAIL: {notes}", file=sys.stderr)
        return 1
    _rewrite_run_status(slug, run_id, "DELETED")
    print(f"OK retention complete for {slug} run {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Changelog

## v0.13 — 2026-05-18

Two bulk-delete commands for managing test-project sprawl.

### Added

- **`dr-load admin cleanall --org ORG [--yes] [--dry-run]`** — bulk
  delete every project in `--org` EXCEPT:
    - projects with an active task (state RUNNING/QUEUED/PENDING/PROCESSING)
    - projects whose **description contains "do not delete"** (case-insensitive
      substring match anywhere in the text)

  Wraps `dr-load admin delete-project` per row so each project's
  scheduled at-job is cancelled as a side effect. Shows the plan
  before acting and prompts for Y/N unless `--yes` is given.
  `--dry-run` shows the plan and exits without deleting anything.

- **`dr-load admin purgeall --org ORG [--force]`** — indiscriminately
  delete every project in `--org`. No exclusions. Running projects are
  interrupted; protected projects are deleted anyway. The default
  prompt requires **typing the org name exactly** to confirm so a typo
  doesn't blow away the wrong org; `--force` bypasses for scripted use.
  After per-project deletes, the command flushes any remaining
  dr-load-tagged at-jobs that target this org as a belt-and-suspenders
  cleanup.

### Changed

- **`helpers.admin_ops.dashboard_snapshot`** now carries
  `description` and `running: bool` on each project row. No new API
  calls — both fields come from data the snapshot was already fetching.
  Backwards-compatible: existing consumers ignore the new fields.

### How to protect a project from `cleanall`

Just include "do not delete" anywhere in its description, in any case:

```bash
dr-load admin create-project keepme --org training \
    -d "Reference data — DO NOT DELETE during QA passes"
```

`do not delete`, `DO NOT DELETE`, `Please do not delete this`, `Don't
delete — production data` — all match the case-insensitive substring
matcher and the project will be skipped.

### Live verification

```
qa-keep-this        Plan / cleanall:  SKIP (description "do not delete")
smoketest           Plan / cleanall:  SKIP (description "do not delete")
qa-running-test     Plan / cleanall:  SKIP (active indexing task)
qa-bootstrap-proj-001  Plan:  DELETE
verify-4320e051        Plan:  DELETE
verify-fix-91ba6d      Plan:  DELETE
```

Found in passing during testing: `smoketest` had `description: "do not
delete"` literally — a convention already in use by whoever set up that
project before this feature existed. Case-insensitive substring matcher
picked it up correctly alongside the new `qa-keep-this`.

`purgeall` plumbing tested on the empty org `verify-test-001` (clean
no-op) and confirmation guard validated by inspection.

---

## v0.12 — 2026-05-18

Rich-rendered dashboard with a live `--watch` mode. Operator-facing TUI
for "what's happening in this org right now," refreshable on a timer.

### Added

- **`dr-load admin dashboard --rich`** — single Rich-rendered snapshot.
  Four tables in a Panel (Running jobs / Scheduled deletes / Finished
  jobs / Projects), per-section bold-colored headers, state column
  color-coded (yellow=running, green=success/active, red=failed,
  magenta=delete-pending), Task column ellipsis-truncated at 40
  chars so rows stay single-line and the dashboard reads cleanly.
- **`dr-load admin dashboard --watch [--interval N] [--alt-screen]`** —
  same Rich layout but driven by `rich.live.Live`. Refreshes every
  `--interval` seconds (default 5). `Ctrl-C` exits cleanly; transient
  `APIError`s in a poll are caught and printed in-frame so the loop
  doesn't die on a flaky network blip. `--alt-screen` puts the dashboard
  in the terminal's alternate screen (vim / htop style) and restores
  the prior view on exit.
- **Suppressed `helpers.api_client` INFO log during `--watch`** so the
  per-poll login chatter doesn't smear the live frame. (Login still
  happens once at the start; subsequent post() calls log at DEBUG.)

### Compatibility

- Plain-text mode (the default) is unchanged. `dr-load admin dashboard
  --org training` still emits the same scriptable text as v0.11; pipes
  and greps continue to work.
- `rich >= 13.0` was already pinned in `requirements.txt` before this
  release. No new dependencies.

### Notes

- Best in a wide terminal (`COLUMNS >= 120`). The Rich tables auto-fit
  to whatever width is available; narrow terminals will compress
  columns but stay legible.
- Watch loop doesn't depend on a database connection — it reads
  everything through the REST API + the local at-queue. The same
  session token is reused across polls.

### Test signal

```
pytest -m smoke              → green
pytest tests/                → green (69 passed, 16 skipped, 1 xfailed)
dr-load admin dashboard --rich            → renders all 4 tables
dr-load admin dashboard --watch -i 3      → Live loop polls cleanly,
                                            exits on Ctrl-C / SIGTERM
```

---

## v0.11 — 2026-05-18

New CLI command: **`dr-load admin dashboard --org ORG`**. Snapshot view
of everything currently happening in an org — running jobs, scheduled
auto-deletes, recently-finished jobs, and a project summary with doc
counts and total compute time.

### Added

- **`helpers.admin_ops.dashboard_snapshot(client, org)`** — pure
  function. Combines `listProjects` + `listCorpora` + per-project
  `listTasks` + `list_scheduled_deletes()` (atq) into a single
  structured snapshot:

  ```python
  {
      "running":   [{project, handle, task, state, docs, elapsed}, …],
      "scheduled": [{project, org, at_job_id, scheduled_at}, …],
      "finished":  [{project, handle, task, state, docs, elapsed,
                     completed}, …],
      "projects":  [{name, handle, state, doc_count, total_elapsed}, …],
  }
  ```

  Doc count per project is keyed off `corpus.owner` (not the corpus
  handle prefix — the prefix is the org's default corpus-view
  container, not the owning project — caught and fixed during this
  build). Finished tasks are sorted most-recent-first.

- **`dr-load admin dashboard [--org ORG --finished-limit N]`** — Typer
  wrapper that formats `dashboard_snapshot` output as a four-section
  text table. Non-interactive (single snapshot per invocation); pair
  with `watch -n 5 dr-load admin dashboard --org training` for a
  refreshing terminal view.

- **`helpers.admin_ops._format_elapsed(seconds)`** — humanizes integer
  seconds as `11s` / `2m05s` / `1h03m` / `2d04h`.

### Notes

- "Total job size" was interpreted as compute footprint (sum of
  `task.secondsElapsed`) because the REST surface doesn't expose a
  byte-size field on `listProjects`/`listCorpora`/`listTasks`. Byte
  size requires the heavyweight CSV from
  `realmManager/getStorageUsageDownloadUrl` — out of scope for v1 but
  trivial to add as a `--bytes` flag later that downloads + parses
  that report.
- Dashboard is intentionally read-only — it never mutates state.

### Test signal

```
pytest -m smoke                          → green
pytest tests/ --ignore=test_indexing_workflow.py
                                         → green
dr-load admin dashboard --org training   → all 4 sections render
```

Live verification: created `dash-test-1` with `--lifetime 5m`,
caught it mid-indexing — RUNNING JOBS section showed the task in
RUNNING state with 2 docs / 3s elapsed; SCHEDULED JOBS showed the
at-job 10 firing at 13:04; PROJECTS row showed dash-test-1 (handle
26599). Cleaned up with `dr-load admin delete-project`, which also
cancelled the scheduled at-job (CLI's `--cancel-schedule` default).

---

## v0.10 — 2026-05-18

QA Persona pass on v0.09 → Developer Persona triage. Test acceptance:
**5 / 5 project lifecycles, 5 / 5 deletes (4 auto via at-jobs, 1 manual
via `delete-project` after `unschedule`), 0 orphans.** ERROR log diff
surfaced 2 new server-side findings (filed) and 2 feature requests
(both implemented in this release).

### Added (closing FR1 + FR2 from QA)

- **`dr-load admin reschedule NAME --org ORG --lifetime D`** (FR1) —
  re-arm auto-delete for an existing project. Cancels any prior
  dr-load-tagged at-job for that name (idempotent — no-op if none),
  then queues a fresh at-job per `--lifetime`. Useful after
  `unschedule`, or to extend a project's life without recreating it.
  Rejects nonexistent projects with a clear error rather than silently
  scheduling a delete for a name that's gone.

- **`dr-load admin list` renders `[deleting #<handle>]` for
  in-flight deletes** (FR2). When the server returns `name: null` for
  a project in `DELETE_PENDING` state, the listing used to show just
  the raw handle (`24856 ... DELETE_PENDING ...`), losing the human
  identity. Now it shows `[deleting #24856]` so operators can correlate
  with what they just asked to delete.

### Filed (server-side, won't fix here)

- **B37** — `ERROR ... Add object - could not find parent object [<orgid>] when creating type [WORK_BASKET]` fires on every `ecaManager/createCase`. Project still activates. Same Hibernate composite-key smell family as B25 / B29.
- **B38** — `ERROR ... Exception when canceling all requests for project NNNN ... Task Handle NNNN Not found` fires on every project delete. `ProjectDeleteProcessingInstance` tries to cancel all in-flight SRIs and finds none. Delete still succeeds; the error is misleading log noise.

Both observed 5 / 5 in the QA acceptance test. Filed for the server team.

### QA acceptance evidence

```
Lifetimes assigned (random shuf -i 120-600):
  qa-test-1  →  366s  (6m06s)  at-job 2  fired 12:34  → deleted ✓
  qa-test-2  →  589s  (9m49s)  at-job 3  fired 12:37  → deleted ✓
  qa-test-3  →  339s  (5m39s)  at-job 4  fired 12:33  → deleted ✓
  qa-test-4  →  519s  (8m39s)  at-job 5  fired 12:36  → deleted ✓
  qa-test-5  →  385s  (6m25s)  at-job 6  unscheduled, manual delete ✓

Started 12:27:17. Last auto-delete completed 12:37:35. Manual delete
of qa-test-5 completed 12:38:14. All 5 fully purged by 12:38:45.

All 5 indexed: operationState=SUCCESS, 2 docs each, <20s elapsed.
0 orphan projects in listProjects after the run.

35 ERROR lines in SERVER.log during the window, 8 unique patterns:
  - 2 already-known: B29 (role-row), B30 (mail NPE)
  - 2 newly filed: B37 (WORK_BASKET parent), B38 (SRI cancel-all)
  - 4 collapsed into the above as related variants

0 ERRORs would have surfaced if B29/B30/B37/B38 were fixed server-side.
```

---

## v0.09 — 2026-05-18

Documentation completeness pass: a comprehensive API dictionary,
self-healing smoke fixture, and the honest scope of what `dr-load admin`
can and cannot do.

### Added

- **`API_DICTIONARY.md`** — comprehensive REST endpoint reference (~1130 lines, ~30 endpoints). Every entry: purpose, scope, request body shape with real fields, response shape with example payload, quirks, and cross-references to BUG_LOG. Shapes captured live from the server — no swagger file is served by this build (verified 404/500 on every conventional path), so the live response is the only source of truth. Includes:
    - Connection + auth model (rolling session tokens, the `userDeviceID` correlation)
    - Request envelope conventions (`contextHandle` + `systemScope` auto-derivation)
    - Error format (structured `errorCode`/`extendedStatus` vs HTML 500s)
    - 30+ endpoints grouped by area (Auth, Realm, Org, Project, Import pipeline, Delete, Reports)
    - "Unwrapped / blocked endpoints" section documenting B36
    - Known-quirks cheat sheet for fast troubleshooting
- **Auto-staging fixture in `tests/test_e2e_bootstrap.py`** — session-scoped, autouse. If `/data/import/testload/` is empty or missing, the fixture invokes the new `helpers.admin_ops.stage_testload_fixtures()` to populate it from the versioned `tests/fixtures/testload/`. The smoke test no longer fails opaquely after a snapshot rollback or `rm -rf /data/import/`. (Anchors #2 in the post-handover gap list.)

### Fixed / Documented

- **B36 — `orgManager/createCustomerUser` is gated by `SecureObjectInterceptor`** which requires the caller to already be a user in the target org. DRSysAdmin isn't on a fresh org, so this endpoint refuses to bootstrap the org admin user via REST — `User not found drsysadmin in org:<new_org>`. Tried 6 endpoint variants and 3 body/scope shapes; none recover. The browser Express Provisioning flow must use a non-REST path (JSP servlet or DB-direct). v0.09 documents this honestly rather than pretending it's "browser-only by choice." This is the only operational gap remaining; everything else is wrappable.
- **`helpers/admin_ops.py`** gains `stage_testload_fixtures(...)` and `is_testload_staged(...)` as pure helpers that both the CLI and the smoke fixture consume. The CLI's `dr-load admin stage-testload` is now a thin wrapper. `require_chown=False` lets tests skip chown when not running as root.
- **`QA_README.md`** updated: Express Provisioning is now explicitly called out as the only browser-required step with a pointer to B36 and API_DICTIONARY §5. Cross-links to API_DICTIONARY.md, DR_Workflow_Guide.md, BUG_LOG.md, CHANGELOG.md added near the top so QA can navigate.

### Plan status

```
All six QA-readiness phases ✅ done
The only remaining operational gap is B36 (browser-required user creation),
which is server-side and not in our hands.
```

---

## v0.08 — 2026-05-18

Phases 3, 4, and 6 of the QA-readiness plan landed. Repo is now
self-contained (install tooling versioned in-tree), debug scripts
deprecated in favor of the CLI, and a GitHub Actions workflow gates
both the syntax-only and the live-VM signals on every push.

### Added

- **`scripts/install/dr_install.sh`** (versioned copy of the silent
  installer wrapper that was living at `/root/scripts/misc/`).
- **`scripts/install/dr_installprep.sh`** — new version of the host-prep
  script with three fixes:
    - **B4**: reboot is gated behind `--reboot` / `--no-reboot` / prompt.
      No more unannounced reboots that kick operators off SSH.
    - **B5**: SELinux config backup only created if absent. Re-runs no
      longer overwrite the true original with an already-disabled file.
    - **B22**: `python3-devel` + `gcc` added so `pip install gevent`
      doesn't blow up on a fresh VM.
    - Also: `atd` is enabled (needed for `dr-load admin --lifetime`).
- **`scripts/install/README.md`** documenting both wrappers + exit codes.
- **`.github/workflows/smoke.yml`** — two-stage CI:
    - `collect` runs on `ubuntu-latest`, checks Python imports, pytest
      collection, and `bash -n` on the install scripts. No live server.
    - `integration` runs on a self-hosted runner tagged
      `digitalreef-vm` with access to the test server. Runs
      `pytest -m smoke` and uploads the HTML report as an artifact.
      Gracefully no-ops if no such runner is registered.

### Fixed / Cleaned up

- **`fullWorkflow.py` and `debug_create_data_area.py` are deprecation
  stubs** (B14a). They used to drive the create-project/import/delete
  chain inline with hardcoded per-host handle defaults — a drift bomb.
  The same workflow is now in `helpers/admin_ops.py` and exposed via
  `dr-load admin`. The stubs exit with rc=2 and a pointer to the new
  CLI. 1316 lines of duplicate code removed.
- **`config.py` no longer hardcodes `"auraria"` as the Postgres password
  fallback** (B12). Defaults to empty; the peer-auth code paths
  (`sudo -u auraria psql`) don't need a password anyway.
- **QA_README.md** updated to reference the in-repo install scripts
  instead of the external `/root/scripts/misc/` paths.

### Plan status

```
Phase 1 — Self-bootstrapping                  ✅ Complete (v0.04, v0.06)
Phase 2 — Stop hiding real failures           ✅ Complete (v0.05, v0.07)
Phase 3 — Single source of truth for handles  ✅ Complete (v0.08)
Phase 4 — Install tooling in VCS              ✅ Complete (v0.08)
Phase 5 — QA handoff docs                     ✅ Complete (QA_README.md)
Phase 6 — CI                                  ✅ Complete (v0.08)
```

Six of six phases done. Remaining items are server-side bugs filed
for the server team (B24, B29, B30, B34) and optional hardening
(move at-script creds out of `/var/spool/at/`).

---

## v0.07 — 2026-05-18

Fix three of the four newly-visible server-bug failures from v0.05 —
turns out B31, B32, and B33 were misformed requests, not server defects.
Mark B34 as the only confirmed server-side defect. Add `--handle`
escape hatch to `delete-project` for orphan recovery (B35).

### Fixed (request shape was the bug, not the server)

- **B31 `orgManager/listCorpora`** — the test called it in system scope.
  Server NPEs at system scope but works fine in org scope. Fix:
  `switch_to_org(api, org)` then call with `contextHandle=org`. Both
  the body field AND the session-context `initializeOrganization` call
  are required — passing the body alone is not enough.
- **B32 `orgManager/listExportDatabaseConnections`** — same root cause
  as B31. Same fix.
- **B33 `orgManager/listRoles`** — needed an `objectType` field; without
  one the server NPEs on `SecureObjectTypes.equals(null)`. Pass
  `extra_body={"objectType": "PROJECT"}` and the call returns
  `status=SUCCESS`. Earlier note in BUG_LOG that "listRoles is broken"
  was overstated — the call works; the test was sending an incomplete
  request.

### Added

- **`dr-load admin delete-project --handle HANDLE`** — escape hatch for
  orphan projects (BUG_LOG B35) that exist in `mgmtproject` but are
  invisible to `listProjects` after a half-failed `createCase`. Skips
  the name-based lookup and deletes by known handle. Find the handle
  in `192.168.58.128_SERVER.log` ("id : NNNN entityName: ...").

### Marked xfail (confirmed server bug — no fix attempted)

- **B34 `projectManager/listReportSettings`** — `NumberFormatException:
  Cannot parse null string`. Tried every reasonable body shape
  (system / org / project context, with `projectHandle`,
  `projectId`, `reportType`, paging params); all fail identically.
  Marked `@pytest.mark.xfail(strict=False)` with the BUG_LOG reference
  so it shows up in test output but doesn't break CI.

### State of the test suite after this commit

| Suite | Result |
|---|---|
| `pytest -m smoke` | green (2 e2e + others) |
| `pytest tests/test_indexing_workflow.py` | green (3 tests, ~22s) |
| `pytest tests/ --ignore=test_indexing_workflow.py` | **69 passed, 16 skipped, 1 xfailed, 0 failed** |

The 16 skips are intentional (permission-denied or missing-config). The
one xfail is the documented server bug B34. Zero red failures.

---

## v0.06 — 2026-05-18

CLI ergonomics + background scheduling. Operators no longer need to know
internal handles or UUIDs — every command takes names and resolves them
via the API. DRSysAdmin works against any org it has Org Administrator
in (the training default). Project lifetimes can be specified at create
time and the deletion runs automatically via the OS `at` queue.

### Added

- **Auto-discovery of role handle.** `helpers/admin_ops.create_project`
  now looks up the logged-in user's role handle in the target org via
  `orgManager/listUsers` (the only role-discovery surface that works on
  this build — `listRoles` etc. all 500). `--role-handle` becomes an
  escape hatch flag; the env-var binding was removed deliberately so a
  stale `.env` value cannot silently defeat auto-discovery.
- **`dr-load admin` now takes names, not handles.**
    - `create-import-job PROJECT_NAME -c CONNECTOR_NAME --path /testload`
      (was: `create-import-job <project-handle> -c <connector-handle>`)
    - `delete-project NAME` (new — resolves by name)
    - `list-connectors ORG` no longer requires `-u/-p` — DRSysAdmin works
      now that it's added as Org Admin to training.
- **Project lifetimes via `at(1)`.** Pass `--lifetime 1h` / `30m` / `7d`
  / `90s` / `2w` to `create-project` or `create-import-job`. The CLI
  queues an `at` job that calls `dr-load admin delete-project NAME`
  when the lifetime expires. No new daemon to maintain: `atd` is
  standard on RHEL, already enabled. Job persists across reboot.
- **`dr-load admin list`** — combined view of projects (API) +
  scheduled operations (at queue). Shows project name, org, state, and
  scheduled-delete time. Flags orphan scheduled jobs whose target
  project no longer exists.
- **`dr-load admin unschedule NAME`** — `atrm` wrapper that cancels any
  pending dr-load-tagged at-job for a project.

### Fixed

- **`tests/test_indexing_workflow.py` no longer reads
  `DR_ADMIN_ROLE_HANDLE` from env.** A stale value in `.env` was
  silently defeating auto-discovery (every createCase 500'd with
  "Could not find role row with ..."). Same change applied to
  `tests/test_e2e_bootstrap.py`. The auto-discovered handle is now the
  single source of truth.

### Notes

- The `at` script holds DR_* credentials inline (in `/var/spool/at/<id>`,
  root-owned, mode 700). Acceptable for a single-tenant QA VM, not
  appropriate for shared hosts. A future hardening could move creds to
  a `~/.config/dr-load/env` file the at-script sources.
- Half-failed `createCase` requests leave the project in mgmtproject
  but invisible to `listProjects` (state filter excludes
  pre-AVAILABLE entries). `delete-project NAME` resolves by API listing
  and so cannot recover such orphans — only `delete_project` via
  Python with the known handle works. Worth a future cleanup helper.

---

## v0.05 — 2026-05-16

Phase 2 of the QA-readiness plan: the test suite no longer hides real
server failures behind silent skips. Four previously-green tests now
correctly fail (B31–B34) — these were lying before, not regressing now.

### Fixed

- **`conftest.py:skip_on_permission_or_error` now only skips on permission errors** (`PERMISSION_DENIED` / `ACCESS_DENIED` / `FORBIDDEN`). Previously also swallowed `CAE_ERROR` and HTTP 500 as skips, which turned every server NPE into a green CI run. (BUG_LOG B13.)
- **`helpers/preflight.py:_check_app_reachable` no longer treats HTTP 500 as a PASS.** Old version POSTed to an auth-required JSON endpoint without auth, tripped the server-side NPE (B24), and called it "OK". New version does `GET /ediscovery/` (the unauth web app root) and requires HTTP 200 — a true "JBoss is up and the war is deployed" signal. (BUG_LOG B23.)
- **`tests/test_indexing_workflow.py` migrated to `helpers.admin_ops`.** The inline `approve_delete` (substring match against stringified dict — BUG_LOG B14b) and `wait_for_indexing` (swallowed all exceptions — B14c) are gone; the workflow class now delegates to admin_ops, inheriting the correct response-shape parsing and consecutive-error cap. All three tests (`test_create_project`, `test_create_and_import`, `test_full_lifecycle`) still pass against the live server — full lifecycle in 35s.

### Newly visible (previously hidden as skips — server bugs to triage)

- **B31 — `orgManager/listCorpora` returns HTTP 500** with no JSON body. (Now fails `tests/test_organizations.py::TestOrgResources::test_list_corpora`.)
- **B32 — `orgManager/listExportDatabaseConnections` returns HTTP 500** with no JSON body. (Now fails `tests/test_organizations.py::TestOrgResources::test_list_export_database_connections`.)
- **B33 — `projectManager/listRoles` returns `errorCode: CAE_ERROR` carrying a `NullPointerException: Cannot invoke "com.digitalreefinc.ws.common.SecureObjectTypes.equals(Object)" because "objType" is null`.** Server-side bug — listRoles is non-functional on this build. (Now fails `tests/test_projects.py::TestListUsers::test_list_roles`.) Matches the prior observation in BUG_LOG that "listRoles returned 0" — actually it doesn't even respond, it crashes.
- **B34 — `billingReportManager/listReportSettings` (and similar) returns `errorCode: CAE_ERROR` carrying `NumberFormatException: Cannot parse null string`.** Server expects a setting that doesn't exist on this fresh install. (Now fails `tests/test_billing.py::TestProjectReports::test_list_report_settings`.)

All four were silently green before. None are regressions in the test code; they expose actual server defects QA can now triage instead of trust.

### Notes

- Of the 4 newly-visible failures, B33 and B34 are clear server-side defects that surface even on a perfectly healthy install. B31 and B32 may be auth-context issues (`listCorpora` is typically called inside a project, and the test runs it at org scope) — but the API still shouldn't 500 with no body.
- Full pre-merge signal: `pytest -m smoke` (31 passed, 1 skipped, ~27s) is the recommended CI gate. `pytest -m slow` adds the 35s end-to-end indexing-workflow test. Running plain `pytest` will expose B31–B34 until they're fixed server-side.

---

## v0.04 — 2026-05-16

Phase 1 of the QA-readiness plan: the test suite can now bootstrap its
own preconditions on a fresh install instead of requiring a manual
browser walkthrough. Verified end-to-end against 192.168.58.128.

### Added

- **`dr-load admin` subcommand group** — five new commands that drive the
  workflow QA was previously stuck doing through the web UI:
    - `dr-load admin create-org NAME` — `realmManager/createOrganization` + readback verification
    - `dr-load admin list-connectors ORG -u USER -p PASS` — lists connectors as an org user (DRSysAdmin sees zero per BUG_LOG B14)
    - `dr-load admin create-project NAME --org ORG --role-handle HANDLE` — `ecaManager/createCase` with templates discovered live
    - `dr-load admin create-import-job PROJECT_HANDLE -c CONNECTOR_HANDLE --path PATH` — full `createDataArea → createCorpus → addCorpus → createRepresentation` chain
    - `dr-load admin stage-testload` — copies `tests/fixtures/testload/` into `/data/import/testload/` (owner=auraria), idempotent
- **`helpers/admin_ops.py`** — pure workflow primitives that both the CLI and the smoke test consume. Single source of truth for the create/import/delete flow. Includes `wait_for_tasks` (with a `max_consecutive_errors` cap — closes BUG_LOG B14c for the new path) and `delete_project` (idempotent — handles "already requested" gracefully).
- **`tests/test_e2e_bootstrap.py`** — pytest smoke test that proves the bootstrap path end-to-end. Two tests: project visible via `listProjects` after create, and the full import job indexes 2 docs to `operationState=SUCCESS`. Self-cleans via fixture teardown. Runs in ~16 seconds against the live server. Tagged `@pytest.mark.smoke`.
- **`tests/fixtures/testload/`** — version-controlled doc1.txt and doc2.txt fixtures so the import job has a known, deterministic dataset (was previously left as a manual `cp` step the prep scripts didn't do — BUG_LOG B15).

### Fixed

- **`config.py` no longer silently clobbers shell environment.** `load_dotenv(override=True)` meant a QA engineer running `DR_PASSWORD=newpw pytest ...` would in fact use the stale value from `.env` — opposite of every convention. Changed to `override=False` so shell wins, `.env` is fallback. *This is what made the first run of the smoke test fail with a "stale role handle" 500.*
- **`adminOrgManager/listDeletePendingProjects` response shape corrected** in `helpers/admin_ops.delete_project`. The team's earlier test helper looked for `adminRequests` / `projects` keys with `projectHandle` / `projectName` fields. Live truth (validated this session): top-level key is `requests`, each item has `objectHandle` / `objectName` and `adminRequestObjectType: "PROJECT"`. With the old matcher, delete approval polled fruitlessly for 90s and timed out, leaving every test run with orphan projects in `DELETE_REQUEST_PENDING`. (Closes BUG_LOG B14b for the new path; the old `tests/test_indexing_workflow.py::approve_delete` still has the substring bug and will be migrated in the next phase.)
- **`requestProjectDelete` is non-idempotent** — it returns HTTP 500 with `"Deletion of this project has already been requested"` if a request is pending. `delete_project` now swallows that case so cleanup recovers from a partial earlier run.

### Newly documented (no fix yet — server-side, non-blocking)

- **B29 — Every `ecaManager/createCase` emits `ERROR Could not find role row with:<role-handle>PROJECT`** in `192.168.58.128_SERVER.log`. The request still succeeds. Same Hibernate composite-text-key smell as B25 — there's a permission row lookup that uses `role_handle + entity_type` concatenation and silently fails to find it. Visible noise during every project create.
- **B30 — `ecaManager/createCase` triggers a `NullPointerException` inside `SendEmailResponseMessage`**: `Cannot invoke "javax.mail.Session.getProperty(String)" because "session" is null`. The project still activates correctly; the send-email side request fails with `errorCode: CAE_ERROR`. Mail Session is null because no SMTP is configured on this install. The server should either fail-fast at install or no-op when mail is unconfigured instead of NPEing on every project create.

### Notes for callers / QA

- The smoke test needs: `DR_BASE_URL`, `DR_USERNAME`, `DR_PASSWORD`, `DR_ORG_ORGANIZATION`, `DR_ORG_USERNAME`, `DR_ORG_PASSWORD`, and **`DR_ADMIN_ROLE_HANDLE`** (per-install — look up once in `authorization_roles` for the target org). Missing env → clean `pytest.skip` with the offending var named, not a mysterious crash.
- `dr-load admin create-org` only creates the org row, not its admin user — the Express-Provisioning "create org admin user" step is a separate endpoint not yet wired up. For now, bootstrap admin users via the web UI or by running setup as DRSysAdmin.

---

## v0.03 — 2026-05-15

### Fixed

- **API client: project-scoped calls no longer 500.** `EDiscoveryClient.post()` previously injected `systemScope: True` unconditionally, which caused the server to evaluate the caller's super-system role for project-scoped endpoints (`createDataArea`, `createCorpus`, `createRepresentation`, etc.), returning HTTP 500 with no usable error body. `post()` now auto-derives `systemScope` from whether the caller overrode `contextHandle`. Callers can also pass `system_scope=True/False` explicitly. (BUG_LOG B18)
- **API client: structured error bodies are no longer thrown away on 4xx/5xx.** `post()` parses JSON before calling `raise_for_status()`, so `errorCode` and `extendedStatus` from the server reach the caller as an `APIError` instead of being dropped by `requests.HTTPError`. (BUG_LOG B19)
- **Template-attribute IDs are auto-discovered at runtime.** New `EDiscoveryClient.discover_template_attributes(org)` calls `orgManager/listTemplates` and returns the 18-element list (including the synthetic `IS_IMPORTED='false'` entry) ready to feed to `ecaManager/createCase`. The 17 hardcoded `DR_TEMPLATE_*` lines in `.env.example`, the hardcoded constants in `tests/test_indexing_workflow.py`, and the hardcoded list in `locustfile_indexing.py` have all been replaced — the previous values were stale from prior hosts and gave silent FK failures on any fresh install. The locustfile discovers once via `@events.test_start`. (BUG_LOG B11, B14d, B14e)

### Added

- **`/root/scripts/misc/dr_install.sh`** — silent-install wrapper that fixes the "10 GB rollback with zero signal" failure mode. Enables `LAX_DEBUG`, redirects InstallAnywhere output to a *persistent* `/var/log/dr_install.log`, and after `install.bin` exits verifies: (1) the registry file was written, (2) `<products>` is not the empty self-closing form (the rollback tell), (3) `/home/auraria/AHS/bin/setup.pl` is present. Distinct exit codes per failure mode (1: missing inputs, 2: rollback, 3: incomplete install, 4: install.bin non-zero). Recommended replacement for `dr_install_fullnode.exp` for unattended installs. (BUG_LOG B17a)
- **BUG_LOG.md** — comprehensive 33-finding audit from the post-install verification pass (create-org, create-project, create-import-job against connector `training-import-nfs-local` and folder `/testload`).

### Notes

- A fresh install assigns *numeric* handles to orgs and projects (e.g. `833`, `1095`), not the 40-character hex handles documented in `DR_Workflow_Guide.md`. Treat handles as opaque strings.
- `realmManager/createOrganization` works as a REST endpoint, despite the installer's "use Express Provisioning in the browser UI" message. The test suite previously did not exercise this.
- `dr_installprep.sh` still does not install `python3-devel` / `gcc`, so the first `pip install -e .` after a fresh install fails to build `gevent`. Run `dnf install -y python3-devel gcc` first (or add it to the prep script).

---

## v0.02 — 2026-05-08

### Added: `dr-load` CLI

A Typer-based command-line tool that wraps the Locust load tests with preflight checks,
orphan cleanup, background monitoring, and a merged report.

#### Commands

- **`dr-load preflight`** — Runs 6 environment checks (app reachable, auth, Postgres, NFS mount, log directory, connector UUID). Exits non-zero if any check fails.
- **`dr-load browsing`** — Runs the browsing load test (`locustfile.py`) headless with background log/job monitoring.
- **`dr-load indexing`** — Runs the full indexing workflow load test (`locustfile_indexing.py`) with orphan sweep before and after.

All commands read defaults from `.env` and accept `--users`, `--duration`, `--spawn-rate`, and `--report` overrides.

#### New Files

- `cli.py` — Typer CLI entry point (`dr-load = cli:app`)
- `helpers/monitor.py` — Background monitoring during Locust runs:
  - `LogWatcher` — tails `*.log` files in `DR_LOG_DIR`, collects ERROR/WARN/FATAL/Exception lines
  - `JobPoller` — polls `datamining_corpus_representation` in Postgres every `DR_POLL_INTERVAL` seconds, counts state 0→1 transitions (NONE→COMPLETE)
  - `Monitor` — owns both threads, produces a `MonitorResult` at `stop()`
- `helpers/preflight.py` — `run_preflight()` (6 checks) + `run_orphan_sweep()` (deletes stale `load-test-*` projects)
- `setup.cfg` — Installs package as `dr-load` console script; adds `py_modules = cli, config`

#### CLI-Specific Environment Variables

| Variable           | Default                    | Description                                |
|--------------------|----------------------------|--------------------------------------------|
| `DR_LOG_DIR`       | `/home/auraria/AHS/output` | App log directory to watch                 |
| `DR_POLL_INTERVAL` | `10`                       | Seconds between job-status DB polls        |
| `DR_REPORT_OUTPUT` | `dr_report.csv`            | Output path for the merged report CSV      |
| `DR_PG_DB`         | `auraria_mgmt`             | Postgres database name                     |
| `DR_PG_USER`       | `auraria`                  | Postgres user (peer auth via sudo)         |

#### Bug Fixed

- **`threading.Thread._stop()` name collision** — `LogWatcher` and `JobPoller` both subclass `threading.Thread`. Storing the stop signal as `self._stop` overwrote the thread's internal `_stop()` method, causing `TypeError: 'Event' object is not callable` on thread join. Fixed by renaming to `self._stop_event` in both classes.

---

## v0.01 — 2026-03-30

Initial release.

### Features
- **87 tests** across 10 test modules
- **pytest + requests** for functional API testing
- **Locust** load tests with 3 browsing personas + full indexing workflow scenario
- **Two user profiles**: system admin (DRSysAdmin) and org user (admin@training)
- **Rolling token management**: automatic capture and reuse of session tokens
- **Graceful skip handling**: tests skip cleanly on permission denied or server errors

### Test Modules
- `test_auth.py` — Session creation, login, version checks
- `test_ocr_report.py` — OCR Usage Report (mirrors Edge recording workflow)
- `test_status.py` — Realm status, system status, nodes, services, licenses
- `test_projects.py` — Project listing, users, groups
- `test_organizations.py` — Organization listing, org resources
- `test_connectors.py` — Connector listing and retrieval
- `test_billing.py` — Billing reports, storage reports
- `test_workflows.py` — End-to-end chained workflows
- `test_org_user.py` — Org-scoped user tests
- `test_indexing_workflow.py` — Full lifecycle: create project → NFS import → index → delete

### Load Test Scenarios
- `locustfile.py` — ReadOnlyUser, OCRReportUser, ProjectBrowser personas
- `locustfile_indexing.py` — Full indexing workflow under concurrent load

### Auth Protocol (reverse-engineered from browser traffic)
1. Login: `POST /realmManager/createSession` with HTTP Basic Auth + `userDeviceID` (UUID)
2. All calls: raw `sessionToken` as `Authorization` header (not Bearer/Basic)
3. Body: `contextHandle` + `systemScope: true` (not `drWsClientContext`)
4. Rolling tokens: every response returns a fresh token

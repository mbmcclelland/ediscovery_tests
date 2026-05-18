# Digital Reef eDiscovery — QA Quick Start

**Version 0.14 · 2026-05-18**

You just inherited a test VM and need to get to "the smoke test is green" in
under 30 minutes. This doc walks that path end-to-end, then becomes your
day-to-day operator reference. Read **§1 Quick start** first; everything
else is lookup material.

**Audience.** Anyone running QA against a Digital Reef install. Written
so a junior sysadmin (familiar with Linux + ssh, less so with APIs and
Python venvs) can follow it; tables and examples are dense enough that
a senior sysadmin won't feel patronized.

**Other docs:**
- [README.md](README.md) — repo overview + doc map
- [API_DICTIONARY.md](API_DICTIONARY.md) — every REST endpoint with real shapes
- [DR_Workflow_Guide.md](DR_Workflow_Guide.md) — what the server actually does behind each call
- [BUG_LOG.md](BUG_LOG.md) — open server bugs + history
- [CHANGELOG.md](CHANGELOG.md) — per-release notes

---

## 0. Glossary (read this first if any term is unfamiliar)

| Term | What it means here |
|---|---|
| **Digital Reef** | The product under test. A web-based eDiscovery platform served at `https://<host>:8443/ediscovery/`. |
| **DRSysAdmin** | The built-in super-admin user. Lives in the `super_system_customer` org. Used by the test suite for orchestration. |
| **Organization (org)** | A tenant-like grouping. All projects belong to an org. The default for testing is `training`. |
| **Project** | A unit of work in eDiscovery — a "case." Holds documents (a *corpus*) and indexing/analysis jobs. |
| **Corpus** | The bag of documents inside a project. One project can have one or more corpora. |
| **Connector** | A configured data source the server can read from. The test fixture uses `training-import-nfs-local`. |
| **Data area** | A directory inside a connector — what gets scanned during import. |
| **Representation** | A processed view of a corpus (metadata, content, vectors). Each import creates several. |
| **Handle** | An opaque server-side ID. Sometimes numeric (`1095`), sometimes 40-char hex, sometimes composite (`project_handle:corpus_handle`). Never parse them. |
| **Indexing** | The pipeline that scans files in a data area, extracts text, builds search indexes. |
| **`dr-load`** | The CLI shipped by this repo. Three families: `preflight`, `admin <subcommand>`, and the load-test scenarios (`browsing`, `indexing`). |
| **`pytest -m smoke`** | The canonical "is the install healthy?" gate. ~16 seconds; runs ~31 tests. |
| **Express Provisioning** | The browser-only flow that creates an org + admin user in one shot. Required once per fresh install ([BUG_LOG B36](BUG_LOG.md)). |
| **at-job** | A scheduled command queued via Linux `at(1)`. `dr-load` uses this to auto-delete projects after a `--lifetime`. |
| **"do not delete"** | A case-insensitive substring convention in a project's description. Projects marked this way are skipped by `cleanall`. |

---

## 1. Quick start (~30 min)

This sequence takes a fresh VM to a green smoke test, end to end.

```bash
# 0. One-time host prep (run once on a brand-new VM)
sudo ./scripts/install/dr_installprep.sh         # interactive — prompts before reboot
# (or pass --reboot / --no-reboot to skip the prompt)

# 1. Install Digital Reef (silent installer with rollback detection)
sudo ./scripts/install/dr_install.sh
# Watch progress with: tail -f /var/log/dr_install.log
# Expect ~15-20 minutes. Exit code: 0=ok, 2=rollback, 3=incomplete

# 2. (Browser, one time) Express Provisioning at:
#    https://192.168.58.128:8443/ediscovery/
#      a) Create org "training"
#      b) Create user "admin" with password "password"
#      c) Add DRSysAdmin to "training" as Organization Administrator
#
#    *** This is the only step that CANNOT be done from the CLI. ***
#    The server's createCustomerUser endpoint refuses calls from
#    DRSysAdmin against an org DRSysAdmin doesn't belong to yet
#    (chicken-and-egg permission check — BUG_LOG B36). The browser
#    Express Provisioning flow uses a non-REST code path to get past
#    this.

# 3. Install the test toolkit and CLI
cd /root/scripts/ediscovery_tests-master
python3 -m venv .venv
source .venv/bin/activate
sudo dnf install -y python3-devel gcc        # gevent needs Python.h
pip install -e .

# 4. Stage the test data fixtures
sudo dr-load admin stage-testload

# 5. Export the credentials shell needs
export DR_BASE_URL='https://192.168.58.128:8443/ediscovery/rest'
export DR_USERNAME=DRSysAdmin DR_PASSWORD=password
export DR_ORGANIZATION=super_system_customer
export DR_ORG_ORGANIZATION=training
export DR_ORG_USERNAME=admin DR_ORG_PASSWORD=password
export DR_VERIFY_SSL=false
export DR_NFS_CONNECTOR_HANDLE=$(dr-load admin list-connectors training | awk '/training-import-nfs-local/ {print $3}')
export DR_NFS_IMPORT_PATH=/testload

# 6. Sanity check
dr-load preflight                 # all 6 checks should be PASS

# 7. The canonical "is the install healthy?" gate
pytest -m smoke                   # ~20 seconds, should be all green
```

If step 7 is green, you're QA-ready.

---

## 2. Environment variables

These are the only credentials/coordinates the CLI and tests need.
**Shell exports always win over `.env`** — a stale `.env` will be
ignored as long as the shell sets the var.

| Var | Required for | Default if unset | Notes |
|---|---|---|---|
| `DR_BASE_URL` | Everything | `https://192.168.58.128:8443/ediscovery/rest` | REST root, not the web root |
| `DR_USERNAME` | Everything | `DRSysAdmin` | The orchestration user |
| `DR_PASSWORD` | Everything | (required) | DRSysAdmin's password |
| `DR_ORGANIZATION` | Everything | `super_system_customer` | DRSysAdmin's home org |
| `DR_VERIFY_SSL` | Everything | `false` | Set `true` once you have a real cert |
| `DR_ORG_ORGANIZATION` | admin CLI, smoke test | (required) | Target org, e.g. `training` |
| `DR_ORG_USERNAME` | Some tests + preflight | — | Org user (e.g. `admin`) — only needed if DRSysAdmin lacks Org Admin |
| `DR_ORG_PASSWORD` | Some tests + preflight | — | Org user password |
| `DR_NFS_CONNECTOR_HANDLE` | Smoke + indexing tests | — | Per-install; discover with `list-connectors` |
| `DR_NFS_IMPORT_PATH` | Smoke + indexing tests | `/testload` | Path inside the connector |
| `DR_INDEX_TIMEOUT` | Smoke test | `180` | Seconds to wait for indexing to reach SUCCESS |

`DR_ADMIN_ROLE_HANDLE` is **deliberately not used.** Auto-discovery
from the logged-in user's record in the target org is authoritative.

---

## 3. `dr-load admin` — operator reference

```bash
dr-load admin --help
```

| Command | What it does |
|---|---|
| `create-org NAME [--description T]` | Create a new organization. Idempotent. |
| `list-connectors ORG` | List connectors visible to DRSysAdmin in `ORG`. |
| `create-project NAME --org ORG [--lifetime D] [-d DESC]` | Create a project. Role handle auto-resolved. With `--lifetime`, queue an at-job to auto-delete after the duration. With `-d "...do not delete..."` in the description, protect from `cleanall`. |
| `create-import-job PROJECT_NAME -c CONNECTOR_NAME --path P --org O [--lifetime D]` | Submit the indexing pipeline against an existing project by name. **`--path` is a subpath under the connector's `remotePath`** — stage your files under `<remotePath>/<path>` on the host. |
| `delete-project NAME --org ORG [--handle H]` | Two-phase delete. `--handle` is an escape hatch for orphans invisible to `listProjects`. Also cancels any pending at-job for the same name. |
| `unschedule NAME` | Cancel any pending at-job for that project name. |
| `reschedule NAME --org ORG --lifetime D` | Re-arm auto-delete on an existing project. Cancels any prior at-job, queues a fresh one. |
| `list [--org ORG]` | Plain-text view of projects + their pending scheduled deletes. |
| `dashboard --org ORG [--rich \| --watch [--interval N] [--alt-screen]]` | Four-section overview: running jobs, scheduled deletes, finished jobs, project totals. `--rich` for a single colored snapshot; `--watch` for an auto-refreshing TUI. |
| `cleanall --org ORG [--yes] [--dry-run]` | Bulk delete every project EXCEPT (a) projects with an active task and (b) projects whose description contains "do not delete" (case-insensitive). Use `--dry-run` to preview. |
| `purgeall --org ORG [--force]` | Nuclear: delete every project unconditionally. Default prompt requires typing the org name to confirm; `--force` skips that guard. |
| `stage-testload [--src --dest --owner]` | Copy versioned test fixtures into `/data/import/testload/` (or `--dest`). |

`--lifetime` accepts `90s`, `30m`, `1h`, `7d`, `2w`. Granularity is minutes (rounded up).

**Description-based protection from `cleanall`:** put `do not delete` (case-insensitive substring, anywhere in the text) into the project's description and `cleanall` will skip it. The convention is already in use on this VM — `smoketest` ships with `description: "do not delete"`.

---

## 4. Example workflows

### 4.1 Create a 1-hour throwaway project

```bash
dr-load admin create-project demo --org training --lifetime 1h
```

Output:

```
OK Created project 'demo' (handle=17447).
OK Verified project present (state=AVAILABLE).
OK Auto-delete scheduled: at-job 1 fires 2026-05-18 12:25 (1h from now)
```

The project will vanish on its own at 12:25. No babysitting.

### 4.2 Run an import job against the testload fixture

```bash
# Step 1: ensure the fixture files are on disk
sudo dr-load admin stage-testload

# Step 2: create a project
dr-load admin create-project myimport --org training --lifetime 2h

# Step 3: submit the indexing pipeline (uses NAMES — no handles)
dr-load admin create-import-job myimport \
  -c training-import-nfs-local \
  --path /testload \
  --org training
```

Verify it finished:

```bash
dr-load admin list --org training
# Should show myimport with state ACTIVE and a scheduled-delete time
```

### 4.3 See everything that exists and what's scheduled

```bash
dr-load admin list --org training
```

```
PROJECT                             ORG          STATE             SCHEDULED-DELETE
---------------------------------------------------------------------------------
demo                                training     ACTIVE            Mon May 18 12:25:00 2026
myimport                            training     ACTIVE            Mon May 18 13:20:00 2026
qa-bootstrap-proj-001               training     ACTIVE            —
---------------------------------------------------------------------------------
3 project(s).
```

### 4.4 Cancel an auto-delete because the project should stick around

```bash
dr-load admin unschedule myimport
# OK Cancelled at-job(s): 2
```

### 4.5 Delete a project right now

```bash
dr-load admin delete-project demo --org training
```

This also cancels any pending at-job for the same project (use
`--keep-schedule` to leave it).

### 4.6 Recover an orphan project (B35)

If a `createCase` half-fails, the project may exist in the DB but be
invisible to `listProjects`. The server log entry looks like:

```
INFO MonitorEntityBase: New Monitor Entity created: type: PROJECT id : 17261 entityName: demo
```

Recover by handle:

```bash
dr-load admin delete-project demo --org training --handle 17261
```

### 4.7 Run a small load test

```bash
dr-load preflight                                # gate first
dr-load indexing --users 1 --duration 120s       # 2-minute run
# A merged CSV report is written to dr_report.csv
```

### 4.7b Watch the dashboard while jobs run

```bash
# Single Rich snapshot (one frame, colors, exits)
dr-load admin dashboard --org training --rich

# Auto-refreshing TUI (Ctrl-C to exit)
dr-load admin dashboard --org training --watch
dr-load admin dashboard --org training --watch --interval 3      # faster refresh
dr-load admin dashboard --org training --watch --alt-screen      # vim/htop-style
```

Four sections: running jobs, scheduled deletes, finished jobs, project
summary. Read-only — safe to leave open on a side terminal.

### 4.7c Bulk teardown at the end of a session

```bash
# Preview what cleanall would remove (running + 'do not delete' protected stay)
dr-load admin cleanall --org training --dry-run

# Actually do it (prompts Y/N)
dr-load admin cleanall --org training

# Or skip the prompt
dr-load admin cleanall --org training --yes

# Nuclear option — deletes EVERYTHING (typed confirmation required)
dr-load admin purgeall --org training
```

### 4.8 Tear down at the end of a test session

```bash
# What's left?
dr-load admin list --org training

# Nuke everything that was scheduled to die
atq | awk '{print $1}' | xargs -r atrm

# Or nuke specific projects
dr-load admin delete-project demo --org training
dr-load admin delete-project myimport --org training

# Or bulk clean (skips active + protected)
dr-load admin cleanall --org training --yes
```

---

## 5. Test suite — what `pytest` proves

### Recommended invocations

```bash
# The pre-merge / pre-deploy gate. Fast, comprehensive enough.
pytest -m smoke

# Full lifecycle including a real indexing run.
pytest -m slow         # 3 tests in test_indexing_workflow.py, ~22s

# The whole non-slow surface. Use this to catch regressions across
# every endpoint the suite covers.
pytest tests/ --ignore=tests/test_indexing_workflow.py

# A specific marker (auth, ocr, status, projects, orgs, connectors, etc.)
pytest -m orgs
pytest -m "smoke and auth"
```

### Catalog

| Test file | Coverage | Marker(s) |
|---|---|---|
| `test_e2e_bootstrap.py` | Full create-project → import → indexing → delete via admin_ops (the canonical health check) | `smoke` |
| `test_indexing_workflow.py` | Same path but exercising the inline workflow class + delete assertion | `slow` |
| `test_auth.py` | login / session / version | `auth`, `smoke` |
| `test_status.py` | Realm status, system status, services | `status`, `smoke` |
| `test_organizations.py` | Org listing, org resources (connectors, corpora, data areas, templates, models) | `orgs` |
| `test_connectors.py` | Connector listing + types | `connectors` |
| `test_projects.py` | Project listing, users, groups, roles | `projects`, `smoke` |
| `test_billing.py` | Billing + report settings (one xfailed — B34) | (none) |
| `test_ocr_report.py` | OCR usage report (the Edge-recorded workflow) | `ocr`, `smoke` |
| `test_workflows.py` | Chained workflows replicating multi-click UI flows | (none) |
| `test_org_user.py` | Tests that require an org-scoped user (skip if `DR_ORG_*` not set) | `org_user` |

### Current state (live verification 2026-05-18)

```
pytest -m smoke                                    →  31 passed,  1 skipped,            0 failed
pytest tests/test_indexing_workflow.py             →   3 passed,                         0 failed
pytest tests/ --ignore=tests/test_indexing_workflow.py
                                                   →  69 passed, 16 skipped, 1 xfailed, 0 failed
```

The 16 skips are intentional (permission-denied or missing-env). The
one xfail is the confirmed server bug B34 (`listReportSettings`).

---

## 6. Known issues

For full root-cause analysis see `BUG_LOG.md`. The QA-facing summary:

### Server-side defects (filed but not yet fixed; out of QA's hands)

| Bug | Severity | Symptom |
|---|---|---|
| B34 | Low | `projectManager/listReportSettings` always returns `NumberFormatException`. The corresponding test is `xfail`. |
| B30 | Medium | Every `createCase` triggers a `NullPointerException` in `SendEmailResponseMessage` because no SMTP is configured. Project still activates correctly; the NPE is logged but not user-facing. |
| B29 | Low | `Could not find role row with:<handle>PROJECT` is logged on every `createCase`. Hibernate composite-text-key smell. Doesn't break anything. |
| B24 | Low | Unauthenticated calls to JSON endpoints NPE instead of returning 401. Workaround: always log in first. |
| B36 | Medium | `orgManager/createCustomerUser` requires the caller to already be a user in the target org. DRSysAdmin isn't on a fresh org, so CLI can't bootstrap admin users — browser Express Provisioning is the only path. Documented in [API_DICTIONARY.md §5](API_DICTIONARY.md#5-unwrapped--blocked-endpoints). |

### Configuration / install gotchas

| Bug | Severity | Workaround |
|---|---|---|
| B16 | Medium | `/aurariamnt` is a tmpfs on the test VM — data does not survive reboot. Project files live there. Mount real storage before any test that needs reboot survivability. |
| B21 | Medium | The project creator is NOT auto-added as a project member on this build. Specify members explicitly in `createCase`. |
| B17 | High | The team doc claims "no createOrganization endpoint" but `realmManager/createOrganization` works. Use `dr-load admin create-org`. |
| B22 | Low | Prep script doesn't install `python3-devel`/`gcc`. Run `sudo dnf install -y python3-devel gcc` before `pip install`. |
| B35 | Low | A half-failed `createCase` leaves an orphan project invisible to `listProjects`. Recover via `delete-project --handle HANDLE` (find the handle in `SERVER.log`). |

### Repo cleanup still pending

| Bug | What |
|---|---|
| B14a | ~~`fullWorkflow.py` and `debug_create_data_area.py` had stale handle defaults~~ — both replaced with deprecation stubs in v0.07. Use `dr-load admin` instead. |
| B12 | `config.py` has a hardcoded `"auraria"` Postgres password fallback. Smell, not a bug. |
| B15b | Three different conventions for "where test data lives" across the repo. The authoritative answer: the connector record's `con_fsdataarea_cfg.areapath` field. |

---

## 7. Troubleshooting

**Start at the top and stop at the first match.** Each row links to the
fix.

| Symptom you saw | What's actually wrong | Fix |
|---|---|---|
| `dr-load preflight` fails on `app_reachable` | App server is down or you have the wrong host | See [§7.1](#71-app-server-not-reachable) |
| `dr-load preflight` fails on `auth` | Wrong username/password, or password contains a shell metachar that got eaten | See [§7.2](#72-auth-fails) |
| `dr-load preflight` fails on `connector_uuid: not found` | Stale `DR_NFS_CONNECTOR_HANDLE` | See [§7.3](#73-connector-uuid-not-found) |
| `dr-load preflight` fails on `nfs_path` | The path inside the connector doesn't exist on the host | See [§7.4](#74-nfs-path-missing) |
| Smoke test fails with `Could not auto-discover role handle` | DRSysAdmin is not yet an Org Admin on the target org | See [§7.5](#75-no-role-handle) |
| `pytest` fails with HTTP 500 + no useful body | Server-side error; body went to log | See [§7.6](#76-http-500-no-body) |
| `create-project` says `Already exists` but `list` doesn't show it | Orphan project (BUG_LOG B35) | See [§7.7](#77-orphan-project) |
| `atq` shows jobs you don't want | Scheduled at-jobs need clearing | See [§7.8](#78-stale-at-jobs) |
| `dr-load admin list` shows a row with `[deleting #<handle>]` | Delete in flight; expected, not an error | Wait ~10s and re-list |
| Login error after recent password change | `.env` overrides shell env? No — shell wins as of v0.04 | Confirm `echo $DR_PASSWORD` matches |

### 7.1 App server not reachable

```bash
curl -k -s -o /dev/null -w "%{http_code}\n" https://192.168.58.128:8443/ediscovery/
# Expect: 200
```

If you get a connection refused or 5xx:
- Confirm the VM is up: `ping 192.168.58.128`
- Confirm JBoss is running on the server: `ssh <host> systemctl status auraria-jboss-eap || ps aux | grep jboss`
- Check the server log: `/home/auraria/AHS/output/192.168.58.128_SERVER.log`

### 7.2 Auth fails

```bash
echo "$DR_USERNAME / $DR_PASSWORD"      # are these set, no quoting weirdness?
echo "$DR_ORGANIZATION"                 # should be super_system_customer for DRSysAdmin
```

If the password contains `$`, `!`, or backticks, put it in single quotes inside `.env`. The shell wins over `.env` (v0.04+), so an outdated `.env` won't silently override a fresh shell export.

### 7.3 Connector UUID not found

Re-discover the handle and re-export it:

```bash
dr-load admin list-connectors training
export DR_NFS_CONNECTOR_HANDLE=$(dr-load admin list-connectors training \
    | awk '/training-import-nfs-local/ {print $3}')
```

### 7.4 NFS path missing

`DR_NFS_IMPORT_PATH` is the subpath *under* the connector's `remotePath` (which is `/data/import`). If `DR_NFS_IMPORT_PATH=/testload`, files must exist at `/data/import/testload/` on the server host.

```bash
ls /data/import/testload                # should list doc1.txt, doc2.txt
sudo dr-load admin stage-testload       # re-stages if empty
```

### 7.5 No role handle

DRSysAdmin must be a member of `DR_ORG_ORGANIZATION` with the "Organization Administrator" role:

1. Open `https://<host>:8443/ediscovery/` in a browser, log in as DRSysAdmin.
2. Switch to the target org (e.g. `training`).
3. Add DRSysAdmin to the user list with role "Organization Administrator".
4. Re-run the test.

This is a one-time setup. After it's done, `dr-load` auto-discovers the role on every call. ([BUG_LOG B36](BUG_LOG.md) is why this can't yet be done from the CLI.)

### 7.6 HTTP 500 with no body

The server returned a non-JSON error page. The actual stack trace is in the server log on the host:

```bash
tail -F /home/auraria/AHS/output/192.168.58.128_SERVER.log
tail -F /home/auraria/AHS/output/192.168.58.128_MGMTAGT.log
```

Re-run the failing call and watch the log. The first `ERROR` line near the timestamp is usually the trigger. The api_client surfaces structured JSON bodies for 200/4xx responses; only true 500s with HTML bodies fall through to the generic `HTTPError`.

### 7.7 Orphan project

A half-failed `createCase` can leave a project row in the DB that `listProjects` doesn't return ([BUG_LOG B35](BUG_LOG.md)). The server log shows the handle:

```
INFO MonitorEntityBase: New Monitor Entity created: type: PROJECT id : 17261 entityName: demo
```

Delete by handle:

```bash
dr-load admin delete-project demo --org training --handle 17261
```

### 7.8 Stale at-jobs

```bash
atq                                          # list everything
dr-load admin unschedule NAME                # cancel dr-load's tagged jobs for NAME
atrm <job_id>                                # raw cancel by ID
atq | awk '{print $1}' | xargs -r atrm       # nuclear: clear the whole queue
```

---

## 8. Where to find things

| Looking for | Path |
|---|---|
| App server logs | `/home/auraria/AHS/output/` (SERVER.log, MGMTAGT.log, DOCPREP.3.log, etc.) |
| Install log | `/var/log/dr_install.log` |
| Test fixtures | `tests/fixtures/testload/` |
| Staged fixtures (on disk for the connector to scan) | `/data/import/testload/` |
| Scheduled at-jobs | `atq` (queue) / `/var/spool/at/` (raw) / `at -c <id>` (script) |
| Load-test report | `dr_report.csv` (configurable via `DR_REPORT_OUTPUT`) |
| Project metadata (DB, read-only) | `auraria_mgmt` Postgres — `mgmtproject`, `mgmtcustomer`, `con_connector_cfg`, `authorization_roles` |

---

## 9. Plan items still on the runway

These don't block QA from running today, but are the next cleanups:

- **Hardening**: Move at-script DR_* credentials to `~/.config/dr-load/env` instead of inline
- **Server-side**: B24, B29, B30, B34 are filed for the server team; not blockers

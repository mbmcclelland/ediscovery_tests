# Changelog

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

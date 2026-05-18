# Digital Reef — TUI Verification: Bug & Improvement Log

**Tester:** Senior dev (Claude, on behalf of mmcclelland@digitalreefinc.com)
**Date:** 2026-05-15
**System:** digitalreef.localdomain (192.168.58.128), RHEL 9.7, fresh-clean install
**Task:** Install the product, run the "TUI", and exercise create-org / create-project / create-import-job (connector `training-import-nfs-local`, folder `testload`).

---

## TL;DR — Outcome

- ✅ Install: succeeded after correcting the silent-install invocation (first attempt rolled back catastrophically — see B6, B17a)
- ✅ Create organization: `realmManager/createOrganization` works (created `verify-test-001` handle=833 and `verify-claude-001` handle=955). Test suite previously assumed this endpoint did not exist — see B10.
- ✅ Create project: `ecaManager/createCase` works *after* discovering real role + template IDs from the live DB. Created `verify-4320e051` handle=1095.
- ✅ Create import job: `createDataArea → createCorpus → addCorpus → createRepresentation` works *after* discovering that `systemScope: True` (the api_client's default) breaks project-scoped operations — see B18.
- ✅ Verified: `import_activity_table` shows `batch_name='testload'` with `number_of_files_scanned=2`, `size_of_files_scanned=261`. Indexing pipeline submitted 4 representations.

## Highest-priority issues (act on these first)

| # | Severity | Status | Title |
|---|----------|--------|-------|
| B18 | **CRITICAL** | ✅ Fixed in v0.03 | `api_client.post()` defaulted `systemScope: True` → every project-scoped op got a 500 with no usable error body |
| B19 | Medium | ✅ Fixed in v0.03 | `api_client.post()` called `raise_for_status` before parsing JSON; structured error bodies dropped |
| B14d | **HIGH** | ✅ Fixed in v0.03 | Two scripts used different stale template-attribute IDs; replaced with runtime discovery |
| B14e | Medium | ✅ Fixed in v0.03 | `IS_IMPORTED='false'` was in the locustfile but not in tests/fullWorkflow; `discover_template_attributes()` injects it |
| B11 | **HIGH** | ✅ Fixed in v0.03 | Template IDs in `.env.example` stale from a different host; block removed, runtime discovery used instead |
| B10 | **HIGH** | ✅ Fixed in v0.04 | `dr-load admin` subcommands + `tests/test_e2e_bootstrap.py` smoke test self-bootstrap the suite's preconditions |
| B17a | **HIGH** | ✅ Fixed in v0.03 | Silent install rolled back 10 GB without any visible error; new `dr_install.sh` wrapper detects rollback + persists logs |
| B15 | **HIGH** | ✅ Fixed in v0.04 | Fixtures versioned at `tests/fixtures/testload/`; `dr-load admin stage-testload` copies them into `/data/import/testload/` |
| B17 | **HIGH** | Documented (CHANGELOG) | The team's docs claim "no createOrganization endpoint" but `realmManager/createOrganization` actually works |
| B14b | Medium | ✅ Fixed in v0.04 (new path) | `approve_delete` substring match against stringified-dict — `helpers/admin_ops.delete_project` uses exact `objectHandle`/`objectName` fields. Old `test_indexing_workflow.py::approve_delete` still has it — migrate next phase. |
| B27 | **HIGH** | ✅ Fixed in v0.04 | `config.py` had `load_dotenv(override=True)` — `.env` silently overrode shell env, making `DR_PASSWORD=newpw pytest` use the stale value. Now shell wins. |
| B28 | Medium | ✅ Fixed in v0.04 (new path) | `adminOrgManager/requestProjectDelete` is non-idempotent — 500s if a request is pending. `delete_project` now swallows the "already requested" case so cleanup is re-runnable. |
| B29 | Low | Open (server) | `ecaManager/createCase` emits `ERROR Could not find role row with:<role-handle>PROJECT` in SERVER.log on every project create. Request still succeeds. Same Hibernate composite-text-key smell as B25. |
| B30 | Medium | Open (server) | `ecaManager/createCase` triggers `NullPointerException` from `javax.mail.Session.getProperty` (mail Session is null on this install). Project still activates; SendEmail subrequest fails with `errorCode: CAE_ERROR`. Server should fail-fast or no-op when SMTP is unconfigured. |
| B13 | Medium | ✅ Fixed in v0.05 | `skip_on_permission_or_error` swallowed `CAE_ERROR` and HTTP 500 as skips, turning every server NPE into a green CI run. Now only skips on `PERMISSION_DENIED`/`ACCESS_DENIED`/`FORBIDDEN`. |
| B23 | Medium | ✅ Fixed in v0.05 | `_check_app_reachable` treated HTTP 500 as PASS because it POSTed to an auth-required endpoint without auth (always tripped B24's NPE). Now `GET /ediscovery/` requires HTTP 200. |
| B14c | Low | ✅ Fixed in v0.05 (new path) | `wait_for_indexing` swallowed all exceptions and busy-looped. `helpers/admin_ops.wait_for_tasks` caps consecutive errors at 5 then re-raises. Migrated `test_indexing_workflow.py` uses it. |
| B36 | Medium | ❌ Confirmed; browser-only workaround | `orgManager/createCustomerUser` refuses calls from DRSysAdmin against a freshly-created org because the `SecureObjectInterceptor` requires the caller to already be a user in that org (`User not found drsysadmin in org:<new_org>`). No body shape, no `systemScope` variant, no `contextHandle` trick gets past it. The browser Express Provisioning flow must use a non-REST path. v0.09 documents this rather than wrapping it. Workaround: the "create org admin user" step remains browser-only. |
| B31 | Medium | ✅ Fixed in v0.07 (test) | `orgManager/listCorpora` 500'd at system scope. Test now `switch_to_org` first and passes `contextHandle=org` — server works fine in org scope. Not a server defect, the test was malformed. |
| B32 | Medium | ✅ Fixed in v0.07 (test) | `orgManager/listExportDatabaseConnections` — same root cause + fix as B31. |
| B33 | Medium | ✅ Fixed in v0.07 (test) | `orgManager/listRoles` NPE'd on missing `objectType` field. Pass `extra_body={"objectType":"PROJECT"}` and the call succeeds. Not a non-functional endpoint after all — the test was sending an incomplete request. |
| B34 | Low | ❌ Confirmed server bug; xfail in v0.07 | `projectManager/listReportSettings` — `NumberFormatException: Cannot parse null string`. No request-body shape recovers. Marked `pytest.mark.xfail(strict=False)`. |
| B14 | Medium | ✅ Fixed in v0.06 (config) | DRSysAdmin saw 0 connectors. No longer true once DRSysAdmin is added to the org as Organization Administrator. `dr-load admin list-connectors` no longer needs `-u/-p`. |
| B4 | Low | ✅ Fixed in v0.08 | `dr_installprep.sh` rebooted unannounced. New version (in-repo at `scripts/install/`) gates reboot behind `--reboot` / `--no-reboot` / prompt. |
| B5 | Low | ✅ Fixed in v0.08 | `dr_installprep.sh` second-runs overwrote the "original" SELinux backup with the already-modified config. New version creates the backup only if absent. |
| B12 | Low | ✅ Fixed in v0.08 | Hardcoded `"auraria"` Postgres password fallback in `config.py` dropped. Defaults to empty; peer-auth code paths unchanged. |
| B14a | Medium | ✅ Fixed in v0.08 | `fullWorkflow.py` and `debug_create_data_area.py` replaced with deprecation stubs pointing at `dr-load admin`. 1316 lines of duplicated workflow + stale handles removed. |
| B22 | Low | ✅ Fixed in v0.08 | `python3-devel` and `gcc` added to `scripts/install/dr_installprep.sh` so `pip install gevent` succeeds. |
| B27b | Medium | ✅ Fixed in v0.06 | Stale `DR_ADMIN_ROLE_HANDLE` in `.env` would silently defeat the v0.06 role auto-discovery (because shell-env-first + .env-fallback still surfaces the stale value when shell doesn't set it). CLI option no longer binds to that env var; tests no longer read it. Auto-discovery is now authoritative. |
| B35 | Low | Open (server) | A half-failed `ecaManager/createCase` (e.g. when the permission-row lookup fails per B29) leaves the project row in `mgmtproject` but invisible to `orgManager/listProjects`. `delete-project NAME` cannot recover it because the lookup is API-based — only an explicit handle works. The server should either complete the rollback or expose the orphan via a stale-state listing. |

---

---

## Terminology / Documentation Confusion (encountered before touching anything)

### B1 — "RPM" in the task description is not an RPM
**Severity:** Doc/communication
**What I expected:** A `.rpm` file installable with `dnf install`.
**What's actually there:** `/tmp/install.bin`, an 8.2 GB **InstallAnywhere** self-extracting Java installer. The install procedure is documented inside an Expect script (`/root/scripts/misc/dr_install_fullnode.exp`), not in any README.
**Improvement:** Either ship a real RPM, or update internal docs/CLAUDE.md/onboarding wording to say "install.bin" so engineers stop chasing missing RPMs. Even a one-line `INSTALL.md` next to the install scripts would prevent the confusion I just hit.

### B2 — There is no "TUI" for end-user operations
**Severity:** Doc/communication
**What I expected:** A terminal UI for creating orgs/projects/jobs.
**What's actually there:** The only console UI is the **InstallAnywhere installer** itself. The Digital Reef product's user-facing interface is a **web app** at `https://<host>:8443/ediscovery/`. From a headless server (no browser), end-user operations have to go through the REST API (`curl` / pytest / `dr-load`) or the Edge recorder.
**Reasoning I had to do:** Treat the installer's console mode as "the TUI" for install verification, and use `dr-load preflight` + REST API (`EDiscoveryClient`) as the de-facto admin surface for the create-org/project/job tasks.
**Improvement:** Either build a thin `dr-admin` Typer CLI on top of the REST API for org/project/job CRUD (sits alongside `dr-load`), or call this out clearly in onboarding ("the product is web-only; for headless ops use the REST API").

### B3 — Install dir layout in onboarding text uses old path
**Severity:** Doc nit
**What:** `PLAN.md` Task 7 references `/home/auraria/scripts/ediscovery_tests` but the actual repo lives at `/root/scripts/ediscovery_tests-master`. Two different conventions in the same tree.
**Improvement:** Pick one and update the other.

---

## Prep Phase

### B4 — `dr_installprep.sh` ends with `reboot now`, no warning, no flag
**Severity:** Medium (operational footgun)
**File:** `/root/scripts/misc/dr_installprep.sh:17`
**What:** The script does a long chain of `dnf install && ... && reboot now`. Any operator running this from an SSH session loses their shell with no confirmation prompt, and any other work in progress on the box is also killed.
**Improvement:** Gate the reboot behind a `--reboot` flag (default off), or at minimum prompt `read -p "Reboot now? [y/N]"`. Also, the whole chain is one giant `&&` — if any step fails the reboot is skipped, but there's no summary of what failed.

### B5 — Prep idempotency: re-running after a successful prep tries to `sed` an already-disabled SELinux config
**Severity:** Low
**What:** `sed -i 's/SELINUX=enforcing/SELINUX=disabled/g' /etc/selinux/config` is a no-op on second run, which is fine, but `\cp /etc/selinux/config /etc/selinux/config.original` overwrites the "original" backup with the already-modified file. The original is lost.
**Improvement:** `[ -f /etc/selinux/config.original ] || cp /etc/selinux/config /etc/selinux/config.original`

### Observation — current host state
- SELinux: Disabled ✅
- firewalld: inactive ✅
- chronyd: active ✅
- postgresql: active ✅
- Java 1.8 (OpenJDK): installed ✅
- `/home/auraria/AHS`: missing (clean state, ready for install) ✅
- `/aurariamnt`: a **tmpfs** (volatile!) — survives only until next reboot. Not flagged anywhere in the prep script. See B-future for impact on `/testload`.

---

## Install Phase

### B6 — Silent installer (`install.bin -i silent -f response.txt`) writes nothing to stdout for several minutes
**Severity:** Medium (operational footgun, indistinguishable from a hang)
**Observed:** The InstallAnywhere `-i silent` mode produced **zero bytes of stdout** for ~30s of an `8.2 GB → 2 GB → eventually 8+ GB` extraction. I mistakenly assumed it had died (the `timeout 30` I'd set fired). It hadn't — `dd if=./install.bin` was still extracting at ~94% CPU. Watching `du -sh /tmp/install.dir.*` is the only signal.
**Improvement:** Either wire `-i silent` to a heartbeat log (e.g., `Extracting %d of %d MB ... [%d%%]`) every 30s, or document loud-and-clear that "silent" really means silent and tell ops to watch `du`. A 1-line `INSTALL_PROGRESS.md` next to `dr_install_fullnode.exp` saying "expect 10-15 min of zero output" would have saved 15 min of confusion.

### B7 — `dr_install_fullnode.exp` is autoexpect-generated and fragile
**Severity:** Medium
**File:** `/root/scripts/misc/dr_install_fullnode.exp:46`
**What:** The script was generated by `autoexpect` (its own header warns about fragility). It uses `expect -exact "..."` patterns over thousands of lines, which break the moment any installer output differs by a single character. When I tried running it under `nohup … < /dev/null`, it spawned `install.bin` without a TTY and the script silently died because `expect -i console` can't get input — leaving a half-extracted `/tmp/install.dir.*` orphan.
**Improvement:** Replace the autoexpect dump with `install.bin -i silent -f response.txt` (no PTY needed) and a small wrapper that polls the extract progress and runs `setup.pl` after. ~50 lines of bash vs. 2800 lines of brittle Expect.

### B8 — Installer leaves giant `/tmp/install.dir.<pid>/` orphans on partial / killed run
**Severity:** Low (operational)
**Observed:** Two crashed install attempts left `/tmp/install.dir.25429/` and `/tmp/install.dir.26853/` (~2 GB each) requiring manual `rm -rf`. The installer has no cleanup-on-exit trap.
**Improvement:** Wrap the install in a parent script with a `trap '[ "$?" -ne 0 ] && rm -rf /tmp/install.dir.$$' EXIT`. Also `dr_clean.sh` already deletes `/var/.com.zerog.registry.xml` and `/home/auraria/AHS*`, but **does not** delete the `/tmp/install.dir.*` orphans — add it.

### B9 — Self-extractor is 8.2 GB and runs as a single non-resumable atomic blob
**Severity:** Low (improvement nit)
**Observed:** Each `install.bin` invocation extracts the same 8.2 GB resource zip from scratch — no caching, no resume. Re-running takes the same wall time even if the system already has a partial extract on disk.
**Improvement:** This is an InstallAnywhere limitation, but documenting that re-running costs a full extract would help. (Or split the install into a "stage" step + a "run" step.)

### Observation — install progress
Install kicked off at 17:56 EDT, response file `/tmp/response.txt` selects Full node + eDiscovery Solution + self-signed certs. Watching via `du`:
- T+1m  → install.dir = 3.8 GB extracted
- (more notes added as it progresses)


---

## TUI Verification Phase (post-install)

### B10 — No real TUI to verify post-install; the test suite assumes pre-existing fixtures it cannot create
**Severity:** High (blocks the user's workflow from a fresh install)
**What I found while reading the codebase:**
- `tests/test_organizations.py` only **lists** orgs — there is no `createOrganization` test or helper anywhere in this repo (grep -r confirms zero hits for `createOrganization|createConnector|createUser`).
- `fullWorkflow.py` immediately calls `realmManager/initializeOrganization` for a **pre-existing** `training` org, logs in as `admin@training` (pre-existing user), and references a NFS connector handle that must **already be provisioned**.
- The installer's "WHAT'S NEXT" message confirms it: *"Use Express Provisioning in the Digital Reef Resource Manager to create an Organization"* — i.e., the only way to bootstrap an org on a fresh install is the **web UI** at port 8443. There is no scripted path.

**Reasoning I had to do:** The user's request ("create an organization") is not directly supported by any code in this repo. On a fresh install, the only options are: (a) drive the browser UI manually, (b) reverse-engineer the `realmManager` createOrganization endpoint with `curl` and craft the JSON by hand, (c) restore a DB dump from a known-good system. The test suite as written cannot bootstrap its own preconditions.

**Improvement:** Add an "express-provision" helper script that takes `org_name`, `admin_username`, `admin_password` and calls the REST endpoint behind the "Express Provisioning" UI (it exists — the web page hits it). At minimum, document the bootstrap procedure in README so a new engineer can take a clean install to "ready to run the test suite" without a browser.

### B11 — `.env.example` ships per-environment template-attribute IDs as if they were universal
**Severity:** Medium (silent failure on a fresh install)
**File:** `/root/scripts/ediscovery_tests-master/.env.example:60-77`
**What:** 17 hardcoded numeric IDs (e.g. `DR_TEMPLATE_INDEX_SETTINGS=18514`) that are specific to the `training` org's `datamining_templates` rows on the existing dev box. On a fresh install these IDs will refer to non-existent rows, and `ecaManager/createCase` will fail with cryptic errors (FK violation or template-not-found).
**Improvement:** Either (a) auto-discover them at runtime via `orgManager/listTemplates` (the test_list_templates test already proves this endpoint works), or (b) replace the `.env.example` values with a comment "Run `dr-load discover-templates --org training` and paste the output here." Don't ship environment-specific IDs as if they were product defaults.

### B12 — Hardcoded fallback passwords in `config.py`
**Severity:** Low/security smell
**File:** `config.py:77`
**What:** `pg_password: ... os.getenv("DR_PG_PASSWORD", "auraria")` — defaults the Postgres password to a plausible production value (`"auraria"`). Even though the comment says "peer auth only," shipping the default in source is poor hygiene.
**Improvement:** Default to empty string; let the code that actually uses it explode with a clear error if needed.

### B13 — `skip_on_permission_or_error` decorator silently masks server 500s
**Severity:** Medium (test reliability)
**File:** `conftest.py:27-46`
**What:** A test gets a `requests.exceptions.HTTPError` with `status_code == 500` → it gets **skipped**, not failed. The same for any `CAE_ERROR` (which the code itself comments is "Generic server error often maps to HTTP 500"). That means real regressions where the server crashes silently turn green in CI.
**Improvement:** Only skip on documented permission denials (specific `errorCode` values). Treat 500s and `CAE_ERROR` as failures with a captured server stack trace included in the assertion message. A skipped test that should be a failed test is worse than no test.

### B14 — `dr-load` CLI surfaces only `preflight | browsing | indexing` — no general admin operations
**Severity:** Low/improvement
**What:** Even though the user asked me to "run the TUI" to do create-org/project/job, the only terminal interface the project gives me (`dr-load`) doesn't have commands for these. The closest thing is the indexing load test, which assumes the whole stack is already wired up.
**Improvement:** Add `dr-load admin` subcommands: `create-org`, `create-user`, `list-connectors`, `create-data-area`, `create-project`, `create-import-job`. Even thin wrappers around `EDiscoveryClient.post(...)` calls would be valuable — they'd be the "TUI" the user actually wanted.

### B14a — Hardcoded connector/role/template-ID fallbacks duplicated across 4+ files
**Severity:** Medium (drift bomb)
**Files:**
- `.env.example:51`, `:56`, `:61-77`
- `tests/test_indexing_workflow.py:33-57`
- `fullWorkflow.py:76-103` (default values)
- `debug_create_data_area.py` (per grep)

**What:** The same handle `0000840201143a35f1f34d8d9a76a34146268ddc` is the default in **at least three** Python files. Same for the admin role `00008798cf6b043a18104ccd8c437b29f688f847` and the 17 template IDs. If the connector is recreated and gets a new handle, fixing the test suite requires hunting through 4+ files instead of editing one `.env`.
**Improvement:** Single source of truth — `config.py` reads all these from env vars, every other file imports from `config`. Drop the per-file fallback constants entirely.

### B14d — `locustfile_indexing.py` and `test_indexing_workflow.py` use DIFFERENT template-attribute IDs for the same host
**Severity:** High (silent test/load-test divergence)
**Files:**
- `locustfile_indexing.py:69-91` — uses **`316, 208, 324, 321, 260, 264, 203, 253, 180, 318, 288, 266, 262, 310, 270, 268, 258`** with a header comment saying *"Template attribute IDs are specific to 192.168.58.128. Do not replace with DR_TEMPLATE_* env vars — these IDs live in the DB and are not portable across environments."*
- `tests/test_indexing_workflow.py:39-52` and `.env.example:60-77` — uses **`18621, 18542, 18629, 18626, 18565, 18569, 18537, 18558, 18514, 18623, 18593, 18571, 18567, 18615, 18575, 18573, 18563`**, reads them from `DR_TEMPLATE_*` env vars.

These cannot both be correct for the same host. `DR_Workflow_Guide.md` Phase 2 documents the 316/208/324 set as the actual values for 192.168.58.128 — so the `test_indexing_workflow.py` defaults and `.env.example` values are likely stale from a different host. Running `pytest tests/test_indexing_workflow.py` against this host will create projects with **wrong template references**, then succeed-looking responses, then a downstream indexing failure that's hard to attribute.
**Improvement:** (a) Discover template IDs at runtime from `orgManager/listTemplates`, OR (b) standardize on one source for the values. The comment in the locustfile explicitly contradicts the design of the test suite — they need to agree.

### B14e — `IS_IMPORTED='false'` attribute is in the locustfile but NOT in `test_indexing_workflow.py` or `fullWorkflow.py`
**Severity:** Medium (inconsistent fix application)
**Files:** `locustfile_indexing.py:82` has it. `test_indexing_workflow.py:39-52` and `fullWorkflow.py:85-103` do not. The `DR_Workflow_Guide.md` explicitly calls this out (§4 "The One Fix Needed") and says **all** scripts should include it.
**Improvement:** Add `{"name": "IS_IMPORTED", "value": "false"}` to the `TEMPLATE_ATTRIBUTES` constants in `test_indexing_workflow.py:46` (after `INDEX_SETTINGS`) and `fullWorkflow.py:95` (same position).

### B14b — `approve_delete` matches by substring of stringified dict
**Severity:** Medium (false positives on similar names)
**File:** `tests/test_indexing_workflow.py:259`
**What:**
```python
if self.project_name in str(req) or str(self.project_handle) in str(req):
```
`str(req)` serializes the whole dict; doing `in` checks against it will match the project name anywhere — in the description, the `taskDescription`, even substring matches across unrelated fields. If two parallel test runs create `api-test-20260515-180001` and `api-test-20260515-180001-x`, the first match-result gets approved for the wrong delete request.
**Improvement:** Match on `req.get("projectHandle") == self.project_handle` (exact field comparison), not stringified-dict substring.

### B14c — `wait_for_indexing` swallows all exceptions and busy-loops
**Severity:** Low (test reliability)
**File:** `tests/test_indexing_workflow.py:213-235`
**What:** The poll loop wraps everything in `try: ... except Exception: pass`. A 500 from `listTasks`, a server restart, an auth failure — all silently consumed. The test will happily wait the full 10-minute timeout against a dead server, then report "timed out, proceeding to cleanup" with no signal that anything was wrong.
**Improvement:** Log every exception with context. Cap on consecutive exceptions (e.g., 5 in a row → abort the wait with an explicit failure).

---

## Create Organization

### B17 — `realmManager/createOrganization` works but the project docs/team believe it doesn't
**Severity:** High (doc/knowledge gap with real impact)
**Observed during verification:** I tried `realmManager/createOrganization` with `{"name": "verify-test-001"}` expecting a "no such endpoint" failure based on the team's docs (the installer message even says *"Use Express Provisioning in the Digital Reef Resource Manager to create an Organization"*, implying browser-only). It worked. Both `verify-test-001` (handle=833) and `verify-claude-001` (handle=955) were created on the first call. The new org came back with `organization.handle`, `name`, `attributes` (including `defaultRole`), `processing`, `storageUsages`, etc.
**Why this matters:** The whole test suite (B10) is structured around the assumption that org creation has to go through the web UI. The endpoint is right there. Adding a `dr-load create-org` command, a pytest fixture for "give me a clean org", or a CLAUDE.md note would be high value.
**Improvement:**
1. Add a `create_organization` helper to `EDiscoveryClient` (or a `dr-load admin create-org` subcommand).
2. Add a `tests/test_organizations.py::test_create_organization` test (currently file only has list endpoints).
3. Update README and DR_Workflow_Guide.md §1 to remove the "browser only" claim.

### B17a — Silent install rolled back the entire 10 GB AHS tree mid-install with zero user-visible signal
**Severity:** High (operational footgun, hours of wasted time)
**Reproducer:** `cd /tmp && ./install.bin -i silent -f response.txt -jvmxms 4g -jvmxmx 4g`
**Observed sequence (timestamps from my Monitor):**
```
T+1m  install.dir = 3.8 GB   AHS = 0 MB
T+5m  install.dir = 8.1 GB   AHS = 0 MB
T+6m  install.dir = 8.1 GB   AHS = 2 GB    <- AHS starts populating
T+8m  install.dir = 8.1 GB   AHS = 10.2 GB  <- looks finished
T+9m                          AHS = 0 MB    <- gone!
```
The installer DELETED everything it had just written. The log file is empty (`-i silent` is *truly* silent). `/var/.com.zerog.registry.xml` was written with empty `<products/>` and `<components/>` — i.e., the installer thinks "I cleaned up, you can start over" but never told the operator anything went wrong. On a second attempt (started from a `dr_clean.sh` clean state) it worked.

**Likely root cause:** Some preflight check inside setup.pl (likely the SELinux/firewalld/DNS check or the LDAP/Postgres setup) failed silently and triggered InstallAnywhere's rollback. With `-i silent` there's no UI to display the error; with no log redirection it goes to a `/tmp/install.dir.*` file that gets wiped during rollback.
**Improvement:** (1) Patch the installer wrapper to add `-DLAX_DEBUG=true -Dlax.debug.level=3` (already in the .exp script — should be in the silent wrapper too) and redirect those logs to a *persistent* path like `/var/log/dr_install.log` BEFORE invoking install.bin. (2) Detect rollback by checking the registry's `<products/>` count and fail-fast with "installer rolled back — check /var/log/dr_install.log". (3) The .exp script doesn't see the rollback path either because it expects specific success strings; add an `expect "FAILED\|ROLLBACK"` branch.

---

## Create Project

### B18 — **CRITICAL**: `EDiscoveryClient.post()` defaults `systemScope: True`, breaking every project-scoped operation
**Severity:** CRITICAL (silent footgun, 500s with no usable body)
**File:** `helpers/api_client.py:147-150`
```python
body: dict[str, Any] = {
    "contextHandle": self.cfg.organization,
    "systemScope": True,
}
```
**What happens:** Every call goes out with `systemScope=True` by default. For org/system endpoints (`listOrganizations`, `listConnectors`, etc.) this is correct. For project-scoped endpoints (`createDataArea`, `createCorpus`, `createRepresentation`), it tells the server "evaluate my permissions in system scope, not project scope" — so the server checks the user's super_system_customer role (e.g. "IT Administrator") for CORPUS permissions, doesn't find them, fails the auth check, and then NPEs in its own error path. The client gets a generic HTTP 500 with an HTML error page — `resp.raise_for_status()` throws `HTTPError` and `.json()` is never reached. The caller has zero signal about what's wrong.
**Reproducer:**
```python
client.post("orgManager/createDataArea", extra_body={
    "contextHandle": project_handle, "connectorHandle": handle,
    "name": "x", "mode": "IMPORT", "path": "/testload", "skippedDirectories": []
})  # → HTTPError 500
```
**Workaround that took ~20 minutes to find:** Explicitly pass `"systemScope": False` in every `extra_body` for project operations.
**Improvement:** The default in `helpers/api_client.py:149` should be `False`, and callers that want system scope should opt in. Alternatively, make `systemScope` a required argument on `post()`. Either way, the implicit `True` default contradicts the project-scoped intent of most endpoints and is the source of the most common silent failure I encountered.

### B19 — `api_client.post()` calls `resp.raise_for_status()` *before* trying to parse the JSON body
**Severity:** Medium (root-cause hiding)
**File:** `helpers/api_client.py:158-160`
```python
resp = self.session.post(url, json=body, timeout=t)
resp.raise_for_status()      # ← throws away the body on 4xx/5xx
data = resp.json()
```
**What happens:** A 500 with a meaningful JSON `errorCode`/`extendedStatus` body becomes a generic `HTTPError("500 Server Error: Internal Server Error...")` with no payload. To find the actual cause I had to grep `/home/auraria/AHS/output/192.168.58.128_SERVER.log` for the stack trace. Even when the server *does* return a JSON error body with rich detail, the client throws it away.
**Improvement:** Parse JSON first, then decide whether to raise. Pattern:
```python
try:
    data = resp.json()
except ValueError:
    resp.raise_for_status()    # only if not JSON
    raise
if resp.status_code >= 400 and data.get("status") != "SUCCESS":
    raise APIError(data["status"], data.get("errorCode"), data.get("extendedStatus"), data)
```

### B20 — Project handles are numeric ID strings, but most test code expects 40-char hex
**Severity:** Medium (silent test-code bugs)
**Observed:** On this fresh install, `createCase` returns `caseHandle=1095` (a numeric string), `createOrganization` returns `handle=833`. Most of the test suite's code (e.g. `fullWorkflow.py:684-691`, `tests/test_indexing_workflow.py:135`) uses the handle as-is, which works, but:
- `DR_Workflow_Guide.md` repeatedly states handles are "40-character hex" — this is true for some object types (corpus, data area) but **not** for projects/orgs.
- The corpus handle returned was `1095:0000d5eb...` — a `project_handle:corpus_handle` composite. None of the parsing code in `test_indexing_workflow.py:154-176` handles this format explicitly; it just stores the whole string.
- Some downstream comparisons like `if str(self.project_handle) in str(req)` (B14b) will accidentally match numeric handles against unrelated string fields (e.g. "1095" appears in many timestamps/IDs).
**Improvement:** Treat handles as opaque strings, not pattern-matched values. Document that the format is **not** consistent across object types. Adjust comparisons to use exact field equality (`req.get("projectHandle") == self.project_handle`).

### B21 — Project creator is not auto-added as a project member on this build
**Severity:** Medium (workflow surprise)
**Observed:** I created project 1095 *as admin@training*, with `membersRequestMessage.users=[{"name": "drsysadmin", roleHandles: [...]}]`. After creation, `authorization_permissions WHERE obj_handle='1095'` shows **only drsysadmin** — admin@training (the creator) was not auto-added. DR_Workflow_Guide.md §2 documents that the browser flow auto-adds the creator. Either the docs are wrong for this build, or `createCase` requires the creator be in `membersRequestMessage` explicitly.
**Improvement:** Make the auto-add behavior testable — `tests/test_indexing_workflow.py` should assert that creator is on the project's `authorization_permissions` after `createCase`. Right now this differential silently breaks downstream calls that assume "the org user I just logged in as can do project-scoped ops on the project I just made."

---

## Create Import Job (connector `training-import-nfs-local`, folder `testload`)

### B15 — `/testload` does not exist on the host filesystem, and the prep script doesn't create it
**Severity:** High (blocks the import-job task before it can run)
**Observed before install even completed:** `ls /testload` → `No such file or directory`. `/etc/fstab` has no mount for it. The intended test data fixture is missing entirely from a "clean" provision of this VM.
**Reasoning I had to do:** Either (a) the connector `training-import-nfs-local` actually points to a different path (e.g., `/aurariamnt/testload`), and the docs are wrong; (b) the test data needs to be copied to `/testload` by an unwritten setup step; or (c) the prep scripts skipped a "stage test data" task. None of `dr_installprep.sh` / `dr_clean.sh` / `dr_install_fullnode.exp` references `/testload`.
**Improvement:** Either add a "stage-test-data" step to the prep script (copy/mount the testload fixture into place), or fail-fast in `dr-load preflight` with "Required test fixture directory missing: /testload". Right now you only find out 30 minutes into the install.

### B15b — Three different conventions for "where test data lives" across the codebase
**Severity:** Medium (confusion magnifier — root cause of B15)
**What I found while reading code:**
- `helpers/preflight.py:113` hardcodes `/data/import/<NFS_IMPORT_PATH>` as the real path.
- `.env.example:52` sets `DR_NFS_IMPORT_PATH=/test_datasets/Small Sample`.
- `fullWorkflow.py:77` defaults `NFS_PATH` to `/test_datasets/Small Sample` and passes it raw to `orgManager/createDataArea` (no `/data/import/` prefix).
- The user's task references `/testload` as the folder.
- `DR_Workflow_Guide.md:481` says the browser flow points at `/testload` directly.

Result: the same connector configuration is in **three** representations across the repo, and none agree. On the current host: `/data/import` doesn't exist, `/testload` doesn't exist, and `/aurariamnt/optimized/` is a tmpfs containing only an empty `optimized` dir. Nobody can find the test data because nobody agrees what its path is.
**Improvement:** Pick one source of truth (the connector record in `con_fsdataarea_cfg.areapath` is the actual answer) and have every script read from it, not from `.env`. Or document explicitly: "DR_NFS_IMPORT_PATH is the connector's `areapath`, not a host filesystem path — `preflight._check_nfs` is wrong to prepend `/data/import/`."

### B16 — `/aurariamnt` is a tmpfs (volatile!), not a real mount
**Severity:** Medium (data loss on reboot)
**Observed:** `mount | grep aurariamnt` → `tmpfs on /aurariamnt type tmpfs (rw,relatime,size=262144k,gid=5000,inode64)`. 256 MB tmpfs. Any project files written to `/aurariamnt/optimized/local-indexstorage/.../project_data_files/<projectid>` (which is where the application stores files per `DR_Workflow_Guide.md` §1.2) **will not survive a reboot**.
**Improvement:** This is almost certainly an artifact of the test VM rather than the product, but the install prep script should detect and warn: if `/aurariamnt` is tmpfs, print a big yellow "WARNING: /aurariamnt is volatile — your data will not persist across reboot. Mount real storage here before installing."

### B22 — `dr_installprep.sh` doesn't install `python3-devel`/`gcc`, but the test suite needs them
**Severity:** Low (newcomer friction)
**Observed during verification:** After install, `pip install -e .` (per README) failed with `gevent: fatal error: Python.h: No such file or directory`. Needed `dnf install -y python3-devel gcc`. The README's "Quick Start" walks the user straight off this cliff.
**Improvement:** Add `python3-devel gcc` to the `dnf install` line in `dr_installprep.sh:5`. Or pin a known-good gevent binary wheel in `requirements.txt` (e.g. `gevent>=22.0; platform_python_implementation == "CPython"` works without compile when wheels exist).

### B23 — `_check_app_reachable` calls a 500 a PASS
**Severity:** Medium (preflight false positives)
**File:** `helpers/preflight.py:43-64`
**Observed:** After install, `dr-load preflight` reports:
```
[PASS] app_reachable: OK — HTTP 500
```
The server returned a 500 HTML error page (NullPointerException because the call was unauthenticated), and preflight happily treats that as "OK". `_check_app_reachable` says *"Any HTTP response (even 4xx/5xx) means the app is up and listening."* — that's true for "TCP listener exists" but it's a lousy signal for "the app is healthy enough to use."
**Improvement:** A reachability check should at least require HTTP < 500. Or pick an endpoint that returns 200 on a healthy server even unauthenticated (e.g., GET `/ediscovery/`). The current behavior would mark a server-side meltdown as a PASS as long as the JBoss listener is still binding.

---

## Verification phase — what was created

| # | What | Handle/ID | API call | Notes |
|---|------|-----------|----------|-------|
| 1 | Org `verify-test-001` | `833` | `realmManager/createOrganization` | First success; minimal payload |
| 2 | Org `verify-claude-001` | `955` | `realmManager/createOrganization` | Full payload (description, organizationName) — same response |
| 3 | Project `verify-4320e051` | `1095` | `ecaManager/createCase` | created by admin@training; 18 template attrs (incl IS_IMPORTED) |
| 4 | Data area `testload_testload` | `0000a330...1bcfd` | `orgManager/createDataArea` | path=`/testload`, connector=`training-import-nfs-local`. Required `systemScope: False` |
| 5 | Corpus `testload` | `1095:0000d5eb...58e0` | `orgManager/createCorpus` | Composite handle format |
| 6 | corpusSet linkage | — | `corpusSetManager/addCorpus` | status=SUCCESS |
| 7 | Indexing job | `taskHandle` returned | `corpusManager/createRepresentation` | 4 representations queued (METADATA, CONTENT, VECTOR, TEXT) — state=1 |

DB confirmation after import:
```
batch_name=testload  number_of_files_scanned=2  size_of_files_scanned=261  user_id=drsysadmin
```
(matches doc1.txt + doc2.txt I staged at `/data/import/testload/`)

---

## Misc small findings encountered along the way

### B24 — `unauthenticated POST /realmManager/getVersion` returns an HTML error page
**Severity:** Low
**Observed:** `curl -k -s -X POST -d '{"contextHandle":"super_system_customer","systemScope":true}' .../realmManager/getVersion` → `<html>...<body>Cannot invoke "com.digitalreefinc.middletier.utils.AuthenticationInfo.getPassword()" because "this.authenticationInfo" is null</body></html>`. NPE instead of a structured 401/403.
**Improvement:** Return a structured JSON `{"status":"FAILURE","errorCode":"UNAUTHENTICATED"}` for any auth-required endpoint called without a token.

### B25 — DB role assignment uses string concat `<role_handle><type>` as primary key
**Severity:** Low (smells)
**File:** `authorization_roles.handle` column
**Observed:** A typical row looks like `handle = "00004f65...e8400PASSWORD_AND_USER_LOGOUT_POLICY"`. This is `role_handle + type` concatenated. Hibernate's join via `secureobject_processing` then string-builds the key when checking permissions, which is why the server log shows `Could not find role row with:00004f65ea1ec41189cd4793b17ba26ac01e8400CORPUS` — it built the key, didn't find the row. Composite text keys + Hibernate is a fragile combination; a missing row gives a generic "key not found" rather than "this role has no CORPUS permission entry". Not actionable for this team (it's how the schema is shipped), but worth flagging because the error message format gets in the way of every permission-related debugging session.

### B26 — `IS_IMPORTED='false'` is listed as a template attribute name in `mgmtproject_attributes` but isn't an actual template
**Severity:** Low (terminology smell)
**Observed:** The 17 actual templates from `orgManager/listTemplates` don't include IS_IMPORTED. But the browser (and now my createCase call) sends it in the same `attributes` array as the template references. So `mgmtproject_attributes` ends up with both real template refs (`{"name":"INDEX_SETTINGS","value":"176"}`) and ad-hoc flags (`{"name":"IS_IMPORTED","value":"false"}`) in the same shape. They aren't the same kind of thing.
**Improvement:** Either move IS_IMPORTED to a separate "project flags" field in the createCase API, or document that `attributes` is the general "key-value bag" rather than calling them "template attributes" everywhere.

---

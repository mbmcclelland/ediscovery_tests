# Changelog

## v0.07 — 2026-05-12

### Added: distribution / RPM packaging

`packaging/` directory carries everything needed to ship a self-contained
`dr-tools` RPM:

| File | Role |
|---|---|
| `packaging/dr-tools.spec` | RPM spec — venv at `/opt/dr-tools/venv`, launchers at `/usr/bin/{dr-tui,dr-load}`, `%post` env-example pointer |
| `packaging/Makefile` | `make wheels` / `make tarball` / `make srpm` / `make rpm` / `make install` / `make clean` |
| `packaging/install.sh` | Bash one-shot installer (alternative to RPM for dev hosts) |
| `packaging/README.md` | Build + distribution guide |

**Build path:** `cd packaging && make rpm` produces
`rpmbuild/RPMS/x86_64/dr-tools-VERSION-1.el9.x86_64.rpm` (~20 MB) plus a
~24 MB SRPM. The SRPM bundles a pre-built **wheelhouse** of every
runtime dependency, so the binary RPM is **offline-installable** on
air-gapped lab hosts. Verified end-to-end:

```
$ sudo dnf install ./dr-tools-0.07-1.el9.x86_64.rpm
$ dr-tui          # launches the login screen from the installed venv
$ dr-load --help  # prints Typer help
```

**Supporting changes:**

- `setup.cfg`: renamed package `ediscovery-tests` → `dr-tools`, moved
  `pytest` / `playwright` / `mitmproxy` to `extras_require[dev]` so the
  install_requires set is the minimal runtime closure. Added
  `package_data = dr_tui/*.tcss` (without this `pip install` skipped
  the Textual stylesheet).
- `pyproject.toml`: new — minimal PEP 517 build-system declaration so
  `python -m build` + `pip wheel` work cleanly.
- `.gitignore`: ignores `build/`, `dist/`, `packaging/rpmbuild/`.

### Added: dr-tui landing dashboard

A new **Dashboard** tab is now the initial active tab after login (for
DRSysAdmin; hidden for org users since it requires realm-scope reads).
Layout, top to bottom:

| Pane | Source | Refresh |
|---|---|---|
| License | `realmManager/getLicenseInfo` — every label/value pair (Application, Mode, Issued to, Valid until, AE / Express AE / OCR core counts, …) | 30 s |
| Realm Node — Status Details | `realmManager/listNodes` + per-node `realmManager/getNodeStatus` (components, connectors, storage mounts). Mirrors the Monitoring → Node Status panel. | 30 s |
| System Metrics | `psutil` — CPU%, Memory%, Network rx/tx bytes-per-sec, Disk read+write IOPS. Peak + average over a rolling 60-sample window. CPU + Memory rendered as `Sparkline`. | 2 s |
| Logs | `LogTailer` — multi-file `tail -f` of `/home/auraria/AHS/output/*.log`. Detects `INFO` / `WARN` / `ERROR` per line; filter toggles in the panel header switch each level on/off. Rotation-safe (re-opens on truncate). | 1 s |
| Top processes | `psutil.process_iter` — top 5 by CPU%, ps-aux style (PID / USER / CPU% / MEM% / CMD). | 3 s |

New module `dr_tui/metrics.py` carries the pure local-OS helpers
(`sample_metrics`, `MetricsHistory`, `LogTailer`, `top_processes`)
separate from the REST data layer in `dr_tui/data.py` (which gains
`get_license_info`, `list_nodes`, `get_node_status` and the
`LicenseField` / `NodeInfo` / `NodeStatusDetail` dataclasses).

The four refresh cycles are independent `set_interval` timers so a slow
REST round-trip doesn't stall metrics or the log stream. Realm calls
run on a worker thread; metrics / logs / processes are local and read
on the UI thread (cheap psutil + file-stat polls).

Tests: `test_dashboard_layout` now also asserts the dashboard widget
inventory (12 widgets) on top of the existing 12 System Settings action
buttons.

## v0.06.1 — 2026-05-12

### Added: dr-tui — Midnight Commander-style keyboard navigation

The footer now renders an F-key action bar that drives every CRUD entry
point:

| Key | Action |
|---|---|
| F1 | `HelpModal` — in-app keyboard reference |
| F4 | Edit selected row (depot / user / group) |
| F5 | Refresh current view |
| F6 | Reset Password (on Users) / Update Now (on Virus) |
| F7 | New entity (depot / user / group) |
| F8 | Delete selected row |
| F10 | Quit |
| Tab | Cycle focus (tree ↔ table) |
| 1 / 2 | Jump to System Settings / Organizations tab |

The F-keys resolve to the right CRUD handler by inspecting
`selected_kind`, so the same key works across depots / users / groups.
Form modals now accept Enter inside any Input field as Save (via
`on_input_submitted`), and a `[Enter] save · [Esc] cancel · [Tab] next`
hint footer renders inside each modal card. Legacy `q` / `r` / `l`
remain as hidden aliases for muscle memory.

Coverage: `tests/test_dr_tui_dashboard_layout.py` adds
`test_keybindings` (F1 opens help; 1 / 2 switch tabs; F7 on a no-leaf
view is graceful) and `test_enter_saves_form_modal` (Enter in a
DepotFormModal Input fires save). 6 / 6 pilot tests passing.

## v0.06 — 2026-05-12

### Summary

System Settings CRUD layer for `dr-tui` (depots, system users, system
groups, virus-defs "Update Now"), backed by a write-path endpoint
reference derived from three mitmproxy captures. Adds a destructive
reinstall toolchain (`cleandr.sh` + Expect + Playwright) that brings DR
back to a tested baseline in ~10 minutes. Closes seven endpoint-capture
gaps left over from v0.05; only Connector edit/delete remains for
v0.06.1.

Test coverage: 4 pilot smoke tests (depot + user + group modals,
dashboard layout) — all passing. Every CRUD modal verified live against
DR with create → update → delete round-trips.

### Added: fresh-install / reinstall toolchain

A three-step chain for tearing down DR and bringing it back to a tested
baseline (DRSysAdmin/`password`, `admin@training`/`password`, depots,
system depot, training org):

| Step | Tool | Purpose |
|---|---|---|
| 1 | `cleandr.sh` | Stops `drd`, preserves `license.lic` to `/root/`, wipes `/home/auraria/AHS*`, `/data/docstorage/*`, `/data/indexstorage/*`, the InstallAnywhere registry, and stale `/tmp` artefacts. |
| 2 | `DR_freshinstall.exp` | Expect script that drives the InstallAnywhere console installer (`/tmp/5.5.3.2.bin -i console`): license accept, Full node, eDiscovery, generate SSL, IP=192.168.58.128, then restores `/root/license.lic` → `/home/auraria/AHS/conf/license.lic` and `systemctl restart drd`. |
| 3 | `playwright_fresh_init.py` | Focused Playwright driver: first login → forced password change → create Doc + Idx depots → assign System Storage Depot → create `training` org → create `admin/training` user → forced password change → logout. Idempotent (skip-if-exists in every phase). |

The full chain takes ~10 minutes end-to-end and leaves the system ready
for `dr-load`, `dr-tui`, and the pytest suite to run unmodified.

### Added: `playwright_fresh_install.py` is now an importable module

Module-level `argparse.parse_args()` was gated behind `_parse_args()` so
phases (`phase_login_initial`, `phase_change_password`, `phase_create_storages`,
…) can be reused by `playwright_fresh_init.py` without polluting `sys.argv`.

### Added: docs/endpoints_v0.06.md

Comprehensive endpoint reference for v0.06 write paths, derived from two
Playwright runs against a freshly-installed DR plus a hybrid manual capture
through mitmproxy. Covers full CRUD on storage depots, organizations, org
users, and groups, plus the realm-settings bonus (`setPasswordPolicy`,
`setInactivityTimeout`, etc.).

### Fixed: `api_client.post()` 204 No Content handling

`helpers/api_client.py` previously crashed on `.json()` when a delete-style
endpoint (`deleteStorageArea`, `deleteOrganization`, `setInactivityTimeout`)
returned 204 with an empty body. Now returns an empty `{}` on 204 or empty
response — unblocks every DELETE in v0.06 CRUD.

### Added: dr-tui — System Groups CRUD (D6)

`System Settings → System Groups` now carries a **New / Edit / Delete**
action bar above the group table:

- **New** → `GroupFormModal` (name, description, role dropdown) →
  `adminOrgManager/createGroup` with
  `organizationName: "super_system_customer"` + `systemScope: true`.
- **Edit** → modal pre-fills from the selected `GroupRow` (extended to
  carry `role_handle` + `role_name` for the dropdown round-trip) →
  `orgManager/updateGroup` with `systemScope: true`. The captured body
  uses a nested `group` object.
- **Delete** → red `ConfirmModal` (warns about member-role loss) →
  `orgManager/deleteGroup` with `systemScope: true`.

**Key finding:** there is no separate `adminOrgManager/updateGroup` /
`adminOrgManager/deleteGroup`. The org-scope endpoints handle both
system and org groups via the `systemScope` flag. The D3 docs are
updated accordingly.

The role dropdown shares the system-roles cache populated by D5
(`realmManager/listSystemRoles`), so opening the group form for the
first time after the user-form is free.

### Added: docs/endpoints_v0.06.md — D6 capture-gap closures

A capture pass (saved at `/tmp/dr_proxy_capture_v06_sysgroups.json`)
filled three of the remaining gaps:

| Endpoint | Status |
|---|---|
| `orgManager/updateGroup` (system) | ✅ confirmed — works for system groups via `systemScope: true` |
| `orgManager/deleteGroup` (system) | ✅ same — no separate admin variant |
| `groupManager/setUsers` | ✅ bonus — bulk-replace group membership |

Only remaining v0.06.1 gap: Connector edit / delete.

### Added: dr-tui — System Users CRUD + reset-password (D5)

`System Settings → System Users` now carries a **New / Edit / Reset PW /
Delete** action bar above the user table:

- **New** → `UserFormModal` (username, email, first/last, initial
  password, role dropdown) → `adminOrgManager/createUser` with
  `orgName: "super_system_customer"` + `systemScope: true`.
- **Edit** → same modal pre-filled (username locked, no password field)
  → `userManager/updateUser` carrying `userHandle`.
- **Reset PW** → `ResetPasswordModal` (new + confirm) →
  `userManager/resetPassword`.
- **Delete** → red `ConfirmModal` → `adminOrgManager/deleteUser` with
  `organizationName: "super_system_customer"`.

Role dropdown is lazily populated via `realmManager/listSystemRoles`
(cached for the screen's lifetime — refresh on next login). The status
bar flashes green on success and the table auto-refreshes once the
write returns.

### Added: docs/endpoints_v0.06.md — capture-gap closures

A manual mitmproxy capture during D5 (saved to
`/tmp/dr_proxy_capture_v06_sysusers.json`) closed three of the gaps
flagged in D3:

| Endpoint | Status |
|---|---|
| `userManager/updateUser` | ✅ now confirmed — works for both system and org users via `userHandle` |
| `adminOrgManager/createUser` | ✅ confirmed (distinct from `orgManager/createUser`) with `orgName: "super_system_customer"` |
| `adminOrgManager/addSystemUserToOrg` | ✅ confirmed — parallel of `addSystemGroupToOrg` |

Remaining gaps for v0.06.1: `orgManager/updateGroup`,
`adminOrgManager/updateGroup`, `adminOrgManager/deleteGroup`,
connector edit/delete.

### Added: dr-tui — Storage Depot CRUD (D4)

Both `System Settings → Document Storage Depots` and `… → Index Storage
Depots` views now carry a **New / Edit / Delete** action bar above the
table:

- **New** opens `DepotFormModal` — Name, FQDN/IP, Export, Allocation —
  posts to `realmManager/createRemoteNFSStorageArea`.
- **Edit** pre-fills the modal from the selected row (Name locked,
  immutable server-side) and posts to
  `storageAreaManager/updateRemoteNFSStorageArea`.
- **Delete** opens a red-bordered `ConfirmModal` and posts to
  `realmManager/deleteStorageArea` (returns 204 → D1 fix).

Writes run on Textual worker threads, the status bar flashes green on
success, and whichever depot leaf is visible auto-refreshes once the
write returns. Create + edit calls use a 120 s timeout — fresh NFS
probes on a clean install can run ~30–60 s and the default 30 s timeout
otherwise misleads the user into thinking the call failed while the
server keeps working.

Coverage:

- Pilot smoke: `tests/test_dr_tui_depot_modal.py` (5 scenarios — empty
  validation, valid create, edit pre-fill, confirm yes, confirm no).
- Live verification: full create → edit → delete cycle confirmed
  against the freshly-reinstalled DR (DOCUMENT_STORE handle 607 round-
  trip; export path mutated and read back; 204 cleanup observed).

### Added: dr-tui — Virus Detection "Update Now" (D7)

`System Settings → Virus Detection` now carries an **Update Now** button
that fires `realmManager/updateVirusDefinitions` with
`updateDefinitionFiles: true`. The handler preserves the most recently
read `enabled` + `frequency` so the schedule config stays untouched.
"Already running" responses (errorCode `INVALID_STATE`) surface as a
friendly status-bar message rather than a stack trace.

### Added: pilot smoke + thread-safe status bar (D8)

- `tests/test_dr_tui_depot_modal.py` — 3 tests covering DepotFormModal,
  UserFormModal + ResetPasswordModal, GroupFormModal (validation +
  cancel + valid-submit per modal).
- `tests/test_dr_tui_dashboard_layout.py` — 1 test that mounts the full
  DashboardScreen with a fake client, asserts every CRUD action-bar
  button is present, and confirms the "no row selected" guard on
  Edit / Delete buttons doesn't crash.
- Made `DashboardScreen._post_status` thread-aware. It previously
  always bounced through `App.call_from_thread`, which Textual 8.x
  rejects when called from the main UI thread. Now it detects which
  thread it's running on and dispatches accordingly.

### Bumped: `__version__` 0.05 → 0.06

README updated to reflect v0.06 features (CRUD modals + reinstall
toolchain). Project Structure section preserved.

### Known capture gaps (v0.06.1 candidates)

- Connector edit / delete — not exercised yet

(D5 closed `updateUser` + `addSystemUserToOrg`; D6 closed group update /
delete by confirming the org-scope endpoints handle both scopes.)

---

## v0.05 — 2026-05-11

### Restructured: `dr-tui` — tabbed hierarchical views, read-only

Replaced the v0.04 three-panel dashboard with a `TabbedContent` layout: a
left-side `Tree` per tab and a `ContentSwitcher` detail pane on the right.
Every leaf maps to a read-only view; create / edit / delete arrive in v0.06.

**Tab 1 — System Settings** (DRSysAdmin only; tab is hidden via
`TabbedContent.hide_tab("tab-sys")` when role is `admin@training`):

| Leaf | Endpoint | View |
|---|---|---|
| Storage › Document Storage Depots | `realmManager/listRemoteNFSStorageAreas` (filter `storageUseType == DOCUMENT_STORE`) | DataTable |
| Storage › Index Storage Depots    | same endpoint, `INDEX_STORE` filter | DataTable |
| System Storage Depot              | `realmManager/getSystemStorageDepot` | Key/value pane |
| Virus Detection                   | `realmManager/getVirusDefinitions`   | Key/value pane |
| System Users                      | `adminOrgManager/listUsersAndGroups` (super_system_customer) → `users[]` | DataTable |
| System Groups                     | same endpoint → `groups[]` | DataTable |

**Tab 2 — Organizations** (both roles). Tree populated by
`realmManager/listOrganizations` (sys) or `OrgUserConfig.organization` (org).
Each org expands to eight leaves:

| Leaf | Endpoint | View |
|---|---|---|
| Users / Admins | `orgManager/listUsersAndGroups` (split by `admin` flag / "Organization Administrator" role) | DataTable |
| Groups | same response → `groups[]` | DataTable |
| Projects | `realmManager/listSystemUserProjectsByUserName` (sys) / `orgManager/listUserProjectsForAllOrgs` (org), filtered by org name | DataTable |
| Running Jobs / Completed Jobs | `projectManager/listTasks` per project, split by `dateCompleted` | DataTable |
| Connectors | `adminOrgManager/listConnectors` | DataTable (relocated from v0.04 dashboard) |
| Storage | cross-ref `listOrganizations.storageUsages` ↔ `listRemoteNFSStorageAreas` (sys only) | DataTable |

**Behaviour**

- Each leaf has its own fetcher in `dr_tui/data.py` and applier in
  `DashboardScreen`; selection fires `_load_view(kind, org)` on a worker
  thread.
- Auto-refresh ticks every 5 s but only re-fetches the currently-visible
  leaf (no more hammering all endpoints).
- DRSysAdmin drill-down into a non-default org transparently calls
  `realmManager/initializeOrganization` first (`_client_for_org`).
- Status bar now shows the active view kind alongside role / org / counts.

**Smoke test (2026-05-11)**

Headless `Pilot` walk through every leaf for both roles (`/tmp/dr_tui_c_pilot.py`):

| Leaf | Sys rows | Org rows |
|---|---|---|
| Document Storage Depots | 1 | (hidden tab) |
| Index Storage Depots    | 1 | (hidden tab) |
| System Storage Depot    | rendered | (hidden tab) |
| Virus Detection         | rendered | (hidden tab) |
| System Users            | 1 | (hidden tab) |
| System Groups           | 0 | (hidden tab) |
| Users                   | 0 | 0 |
| Admins                  | 2 | 2 |
| Groups                  | 0 | 0 |
| Projects                | 1 | 1 |
| Running Jobs            | 0 | 0 |
| Completed Jobs          | 0 | 0 |
| Connectors              | 2 | 2 |
| Storage                 | 3 | 0 (org user lacks `listOrganizations` privilege — by design) |

SVG snapshots at `/tmp/dr_tui_c-*.svg`.

**New files / changed files**

- `dr_tui/app.py` — full DashboardScreen rewrite (TabbedContent + Trees +
  ContentSwitcher + dispatcher); `LoginScreen` and `DRTUIApp` unchanged.
- `dr_tui/data.py` — new dataclasses (`StorageDepot`, `SystemDepot`,
  `VirusDefs`, `UserRow`, `GroupRow`, `ProjectRow`, `OrgStorageRow`,
  `OrgInfo`) + nine new fetchers.
- `dr_tui/app.tcss` — replaced 2×2 grid with full-height tab layout; added
  `.detail-body` for key/value panes.
- `docs/endpoints_v0.05.md` — endpoint reference (also flags v0.06 deferred
  write paths).

**Known limitations (deferred to v0.06)**

- All views are read-only. No create / edit / delete / virus-update yet.
- Org-scoped users cannot see Storage (depends on realmManager privileges).
- `api_client.post()` will still crash on 204 No Content responses — fix
  pending for v0.06 write paths (task #13).

---

## v0.04 — 2026-05-11

### Added: `dr-tui` — Textual TUI

A lazygit-style three-panel TUI for monitoring the live system. Installed as a
new console script alongside `dr-load`.

```bash
dr-tui            # or: python -m dr_tui
```

**Screens**

- **Login** — radio toggle between `DRSysAdmin` and `admin@training`, password
  field (defaults to `password` for the lab). Enter to submit, Esc to quit.
  On DRSysAdmin login the TUI also attempts an org-user login in the background
  so org-scoped panels work when DRSysAdmin is also an Org Admin.
- **Dashboard** — three panels:
  - **Connectors** (left, full height) — name, type, mode, host, path, status.
  - **Running Jobs** (top right) — project, job description, task handle, elapsed.
  - **Completed Jobs** (bottom right) — project, job, task, completion time, duration.
  - Header clock, status bar with role/org/counts, footer with `[q] [r] [l]` bindings.
  - Auto-refresh every 5 seconds via a background worker thread.

**Endpoints used (role-aware)**

| Concern | DRSysAdmin path | admin@training path |
|---|---|---|
| Connectors | `realmManager/initializeOrganization` → `adminOrgManager/listConnectors` | `adminOrgManager/listConnectors` (direct) |
| Projects | `realmManager/listSystemUserProjectsByUserName` (all orgs) | `orgManager/listUserProjectsForAllOrgs` |
| Tasks | `projectManager/listTasks` per project; split by `dateCompleted` | same |

**New files**

- `dr_tui/__init__.py`, `__main__.py`
- `dr_tui/app.py` — `DRTUIApp`, `LoginScreen`, `DashboardScreen`
- `dr_tui/data.py` — sync API fetchers (`list_connectors`, `list_projects_sys`,
  `list_projects_org`, `collect_jobs`) invoked from Textual worker threads
- `dr_tui/app.tcss` — Textual stylesheet (lazygit-style borders, btop-style colors)

**Requirements**

- Adds `textual>=0.40.0` to `requirements.txt` and `setup.cfg`. Reinstall with
  `pip install -e .` to register the `dr-tui` console script.

**Smoke test (2026-05-11)**

End-to-end Textual `Pilot` test against 192.168.58.128: logged in as both
roles, dashboard rendered, Connectors panel populated with the 2 NFS
connectors in `training`, logout returned to the login screen cleanly.
SVG snapshot at `/tmp/dr_tui_dashboard.svg`.

---

## v0.03 — 2026-05-11

### Fixed: `locustfile_indexing.py` realigned to captured UI flow

Rewrote the indexing workflow against ground truth from the May 11 playwright
capture (`/tmp/dr_api_capture.json`, 211 calls). Previous version diverged from
real UI traffic in nine places — see `PLAN.md` Tasks 1, 9, 10.

#### Behavioural changes

- **Dynamic handle resolution (new `on_start`)** — connector handle, admin role
  handle, and template attribute IDs are now resolved via API at user startup
  (`adminOrgManager/listConnectors`, `orgManager/listRoles`,
  `orgManager/listTemplates`). Removes drift after `playwright_fresh_install.py`
  reruns the environment.
- **Job-completion polling rewritten** — replaced the `projectManager/getUpdateStatus`
  fixed-count loop with `taskManager/getTasks([taskHandle])` polling on
  `dateCompleted`. The `taskHandle` comes straight from the
  `corpusManager/createRepresentation` response — no `listTasks` needed. Two
  new env vars: `DR_INDEX_POLL_INTERVAL` (default 5s), `DR_INDEX_POLL_TIMEOUT`
  (default 600s). This resolves PLAN.md **Task 1** (monitoring endpoint) and
  obsoletes PLAN.md **Task 9** (representation_state SQL enum — no longer
  needed for per-workflow tracking; `helpers/monitor.py` still uses it for
  the global signal).
- **Project-scoped context** — dropped the spurious "initOrg→project" call;
  the captured flow passes `contextHandle=<projectHandle>` directly on
  `createDataArea` / `createCorpus` / `createRepresentation`.
- **Corpus-set lookup** — switched from `projectManager/listCorpusSets` to
  `corpusSetManager/getCorpusSetByName(corpusSetName="AllCorpora")`.
- **Indexing runs as org user**, not DRSysAdmin — admin@training has the
  needed permissions once added as Organization Administrator in
  `ecaManager/createCase`.
- **Deletion split across both users:**
  `orgManager/requestProjectDelete` (org token, `ctx=ORG_NAME`) →
  `realmManager/listDeletePendingProjects` (sys token, `ctx=SYS_ORG`) →
  `adminOrgManager/approveProjectDeleteRequest`. Replaces the previous
  `adminOrgManager/requestProjectDelete` + brittle stringified-match.
- **`IS_IMPORTED` attribute removed** from `createCase` body — not present
  in captured payloads.

#### Removed env vars

`DR_NFS_CONNECTOR_HANDLE`, `DR_ADMIN_ROLE_HANDLE`, and `DR_TEMPLATE_*` are no longer
read by `locustfile_indexing.py` — all resolved at runtime via `listConnectors` /
`listRoles` / `listTemplates`. These vars are still read by:

- `helpers/preflight.py` — `connector_uuid` check (`_check_connector` reads
  `DR_NFS_CONNECTOR_HANDLE` and verifies it appears in `listConnectors`).
- `tests/test_indexing_workflow.py` — pytest indexing test reads
  `DR_NFS_CONNECTOR_HANDLE`, `DR_ADMIN_ROLE_HANDLE`, and `DR_TEMPLATE_*`.

Leave them populated in `.env`; resync them after each `playwright_fresh_install.py` run.

#### Smoke test (2026-05-11)

`dr-load indexing -u 1 -d 90s` against 192.168.58.128 — **50 requests, 0 failures**,
3 complete project lifecycles (create → index → poll → delete → approve), 4 indexing
jobs reached `COMPLETE`. All nine v0.03 fixes exercised end-to-end.

#### Known fragility uncovered

- `helpers/preflight.py:_check_connector` calls `resp.json()` without first checking
  `resp.status_code`. If the upstream auth bounce returns HTML (HTTP 500) on the first
  call — which the captured browser flow also hits intermittently — the check fails with
  `Expecting value: line 1 column 1 (char 0)`. Workaround: re-run preflight; permanent
  fix is to add a status-code check before parsing.
- After `playwright_fresh_install.py` Phase R (deleteOrganization), the `training` org
  and `admin` user must be re-provisioned manually before the load test runs. See
  README §"After running `playwright_fresh_install.py`".

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

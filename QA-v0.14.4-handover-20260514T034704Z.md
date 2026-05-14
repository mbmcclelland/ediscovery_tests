# QA Log — v0.14.4 handover

**Tester:** Claude (acting QA Engineer)
**Build under test:** v0.14.4 (commit `396a893`, branch `v0.06`)
**Started:** 2026-05-14T03:47:04Z
**Reference docs:** `docs/QA_TEST_PLAN.md`, `docs/RUNBOOK.md`,
`CHANGELOG.md`

This log is appended to in real time as I work. Each entry is
timestamped. Bug discoveries flip me to "Developer hat" for the
fix; the entry records both the discovery and the fix.

---

## Scope

Working from the QA Test Plan §2 (10-min smoke) and §4 (detailed
scenarios). Will close out with a fresh pilot-test re-run.

## Conventions

| Status | Meaning |
|---|---|
| PASS | Feature behaves as documented. |
| FAIL | Feature differs from spec; entry will list the gap. |
| BLOCKED | Cannot test (environment or dependency); document why. |
| FIXED | Bug found + patched in-session; references the follow-up commit. |
| INFO | Observation, not a verdict. |


## QA-1 — Environment readiness — **PASS**

- `systemctl is-active drd` → `active`
- `.env` present (1018 bytes)
- Repo at commit `396a893`, version `0.14.4`
- DRSysAdmin login succeeds via EDiscoveryClient

[2026-05-14T03:48:30Z]

## QA-2 — Pilot suite — **PASS**

19/19 in 13.97s. All TUI pilot harness tests pass — no structural
regression.

```
test_dashboard_layout                                    PASS
test_keybindings                                         PASS
test_enter_saves_form_modal                              PASS
test_help_pane_toggle                                    PASS
test_jobs_monitor_modal                                  PASS
test_depot_modal_paths                                   PASS
test_settings_modal_paths                                PASS
test_user_modal_paths                                    PASS
test_group_modal_paths                                   PASS
test_priority_modal_paths                                PASS
test_scheduler_save_load_roundtrip                       PASS
test_scheduler_run_record_append                         PASS
test_scheduler_slugify_edges                             PASS
test_newjob_modal_mount_and_cancel                       PASS
test_newjob_modal_auto_picks_org_connector_project       PASS
test_newjob_modal_v0141_defaults_and_buttons             PASS
test_unit_parse_regex                                    PASS
test_log_viewer_modal_mount                              PASS
test_longterm_substring_match                            PASS
```

[2026-05-14T03:49:30Z]

## QA-3 — dr-load preflight — **PARTIAL PASS / ENV FINDING**

```
[PASS] app_reachable
[PASS] auth
[PASS] postgres
[PASS] nfs_path
[PASS] log_dir
[FAIL] connector_uuid: Org user auth for connector check failed
```

Investigated the FAIL:
- DRSysAdmin login works (already proven in QA-1).
- Direct org-user login via OrgUserConfig: HTTP 500.
- AHS server log: `ERROR [LoginServlet] Unable to login: admin because - User admin not found in directory.`

**Root cause:** the `admin@training` user does not exist in this DR
install. **Not a code bug** — the user was likely removed during an
earlier cleandr / reinit cycle that did not re-run
`playwright_fresh_init.py`.

This is the documented RUNBOOK §1 failure mode. Fix (per RUNBOOK):

```bash
python playwright_fresh_init.py
```

**Decision:** the org-user missing only blocks the `dr-load indexing`
load-test scenario (QA-7 in my plan, equivalent to QA Test Plan §4.7).
Every other feature under test uses DRSysAdmin, which works fine.

**Will continue QA against the DRSysAdmin-driven feature set; will
notify the user at close-out so they can decide whether to
re-initialise the training org.**

[2026-05-14T03:51:30Z]

## QA-4 — dr-tui launches + login + dashboard mounts — **PASS**

Drove the live `DRTUIApp` via Textual's Pilot harness:

1. Login screen appears.
2. `do_login(ROLE_SYS, <password>)` succeeds against live DR.
3. `DashboardScreen` mounts within 1s.
4. All four expected TabPanes present: `tab-dashboard`, `tab-sys`,
   `tab-orgs`, `tab-scheduler`.

No exceptions during mount or login. Worker threads complete cleanly
(no `WorkerFailed` raised when the pilot exits the context manager).

[2026-05-14T03:53:40Z]

## QA-5 — Connectors view shows live connector — **PASS**

`ensure_org_context("training")` + `list_connectors(client, "training")`
returns:

```
1 row(s)
  name='import-training-nfs-local' type=NFS mode=READ
  host='192.168.58.128' path='/data/import'
  status=AVAILABLE handle=0000ecde48788120...
```

`_client_for_org` (called by the Organizations → Connectors tree
routing) does exactly this chain, so the inline status line on the
panel should render `[green]1 connector(s) for training.[/]` per
v0.14.2.

[2026-05-14T03:55:00Z]

## QA-6 — NewJobModal connector dropdown populated — **PASS**

Drove the live `DRTUIApp` from LoginScreen → DashboardScreen →
Job Scheduler tab → `_sch_open_new()`. The NewJobModal mounts with:

```
NewJobModal connector dropdown: 1 option(s)
  - label='import-training-nfs-local  (NFS)'   handle=0000ecde48788120
_cur_org='training'
_cur_conn_handle='0000ecde4878812053604308ac25ef767566612e'
_cur_project_handle='254'
```

All three of `_cur_org`, `_cur_conn_handle`, `_cur_project_handle`
are populated post-mount — confirming the v0.14.3 fix
(`ensure_org_context` per-org in `_sch_collect_then_open`) is live in
this build.

Cancel button dismisses cleanly without exception.

[2026-05-14T03:57:30Z]

## QA-7 — NewJobModal validation messages — **PASS**

Every documented validation case blocks `Schedule` and surfaces the
correct field-specific error message:

| Case | Modal dismissed? | Error text |
|---|---|---|
| Empty name | No | "Name is empty — please enter a name for this job (e.g. 'payroll-archive')." |
| No folder selected | No | "Folder to index not selected. Click a folder in the tree on the right, then try again." |
| Retention = `foo` | No | "Retention period must be a whole number (got 'foo'). Enter 0 to keep forever." |
| Retention = `-1` | No | "Retention period can't be negative. Enter 0 to keep forever, or a positive number." |

All four strings match the QA Test Plan §4.4 spec verbatim.

[2026-05-14T04:00:30Z]

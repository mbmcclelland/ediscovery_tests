# QA handover — v0.17.2 → v0.19.3

> **Handover state:** ready for QA pickup.
> **For:** Jordan Park (QA Engineer persona, returning from the
> v0.17.1 cycle that closed 4 tickets and signed off SHIP IT).

| | |
|---|---|
| **Branch** | `v0.06` |
| **Tag under test** | `v0.19.3` (commit `9f36243`) |
| **RPM installed** | `dr-tools-0.19.3-1.el9.x86_64` |
| **DR install state** | drd active, listening on `192.168.58.128:8443`, `training` org with 3 connectors + 2 data areas + admin@training + DRSysAdmin both members |
| **Last QA cycle** | `QA-DR_freshinstall-v0171.md` — v0.17.2 sign-off SHIP (4 tickets, all closed in-session) |
| **Pilot tests** | 17/17 green |

---

## What's shipped since the v0.17.2 QA cycle

11 versions worth of changes. Roughly three buckets:

### Bucket A — UX evolution on `DR_freshinstall.py` (v0.17.3 → v0.17.9)

| Version | Change |
|---|---|
| v0.17.3 | Paused progress bar during shell-subprocess phases (later superseded by .4's stream-through approach) |
| v0.17.4 | Reef-a-TUI logo, ocean-depth gradient, bright-yellow subtitle, `_stream_subprocess()` routes cleandr / installer / drd output through Rich so the progress bar stays pinned at the bottom of the live region |
| v0.17.5 | Logo regenerated at `bit -font fivebyfive -scale 0 "Reef-A-TUI"` for legibility (5-line letters fully readable at 110 cols) |
| v0.17.6 | User-supplied 7-line logo + blue→light-grey gradient; phase banner border `bright_blue`, title `bold yellow` |
| v0.17.7 | `DR_freshinstall.exp` — `dr_ctl.sh status` path uses forward slashes (was `\\home\\auraria\\...` rendering to `homeauraria...` and 'command not found') |
| v0.17.8 | InstallAnywhere debug flags (`LAX_DEBUG=true`, `_JAVA_OPTIONS="-Dlax.debug.level=3 -Dlax.debug.all=true"`) set before `spawn` — emits `/tmp/LAX*.txt` |
| v0.17.9 | Per-phase wall-clock subtotals — log line per phase + dim `⏱  Phase N took X.Ys (Mm SSs)` between-phase console one-liners |

### Bucket B — REEF-A-TUI rebrand + naming consistency (v0.17.10 → v0.19.3)

| Version | Change |
|---|---|
| v0.17.10 | Scripts ship to `/opt/digitalreef/scripts/reef-a-tui/`. New launchers `dr-freshinstall` + `dr_freshinstall`. `dr_tui` symlink added. |
| v0.19.2 | Canonical command names flipped to **underscore** for `dr_tui` + `dr_freshinstall`. Hyphen forms become legacy alias symlinks. |
| v0.19.3 | Same flip extended to `dr_load`, `dr_job_run`, `dr_job_delete`. End state: 5 canonical underscored wrappers + 5 hyphenated symlink aliases in `/usr/bin/`. |

### Bucket C — New TUI / driver features (v0.18.0 → v0.19.1)

| Version | Change |
|---|---|
| v0.18.0 | **NewJobModal explicit Project picker** — fixes "PROJECT_NOT_ACTIVATED Project 0 not activated" by letting the user choose which existing project the imports attach to (was previously auto-picked silently) |
| v0.19.0 | **Organizations tab → Projects → F7 Create Project** flow. `NewProjectModal` + `ecaManager/createCase` + auto-resolve Org Admin role + auto-attach default templates + auto-add DRSysAdmin + admin@org as members. Worker thread refreshes the projects table. **KNOWN_LIMITATION: fresh-install orgs have 0 default templates — flagged below.** |
| v0.19.1 | `cleandr.sh` Phase 0: SELinux runtime `setenforce 0` + persistent `SELINUX=disabled` in `/etc/selinux/config`. Idempotent (no-op when already disabled), safe on hosts without selinux-utils. |

---

## Test plan — TC14 through TC25

Numbering picks up where the v0.17.1 plan ended (TC1–TC13). Test
cases marked **(critical)** must pass for sign-off; **(important)**
warrants a ticket if it fails; **(nice-to-have)** is logged only.

### Bucket A — visual UX

| TC | Title | Type | Severity |
|---|---|---|---|
| **TC14** | `sudo dr_freshinstall --force` shows the Reef-a-TUI logo with the ocean-depth blue→light-grey gradient + bold-yellow "Digital Reef Fresh Installer version 0.19.3" subtitle | Visual | important |
| **TC15** | Progress bar stays pinned at the **bottom** of the visible region during phase 1 (cleandr) — subprocess output (rm -rfv flood, dropdb output) scrolls cleanly above it, prefixed with dim `│` | Visual / UX | critical |
| **TC16** | Same during phase 2 (InstallAnywhere installer) — no duplicate bar redraws (the v0.17.3 spinner-spam regression). Phase 2 should also produce `/tmp/LAX*.txt` debug log via `LAX_DEBUG=true` | Visual / UX + logging | important |
| **TC17** | Between phases, a dim `⏱  Phase N took X.Ys (Mm SSs)` line appears. File log contains `phase wall clock:` entries (4 lines: 3 phases + total) | Logging | important |
| **TC18** | Phase banner border is bright blue; title text is bold yellow (v0.17.6 colours) — visually distinct from the cyan run-config panel above | Visual | nice-to-have |

**Acceptance for Bucket A:** TC14 / TC15 / TC17 all pass; TC16 + TC18 pass or get a minor ticket.

### Bucket B — naming consistency

| TC | Title | Type | Severity |
|---|---|---|---|
| **TC19** | All 5 underscore canonical commands exist as real wrappers in `/usr/bin/` (`dr_tui`, `dr_load`, `dr_job_run`, `dr_job_delete`, `dr_freshinstall`). All 5 hyphen aliases exist as symlinks to their underscore counterpart. | Functional | critical |
| **TC20** | `dr_tui`, `dr_load`, `dr_job_run`, `dr_job_delete`, `dr_freshinstall` all run successfully (at minimum: `--help` works for each — for `dr_tui` confirm the login screen comes up; for `dr_freshinstall` confirm no-args prints help and exits 0) | Functional | critical |
| **TC21** | All 5 legacy hyphenated forms (`dr-tui`, …) ALSO work — `which dr-tui && which dr_tui` both succeed, both invoke the same wrapper | Functional / back-compat | critical |
| **TC22** | All MD docs reference `dr_tui` / `dr_load` / etc. consistently — no `dr-tui` "typos" in user-facing prose. Grep should return only intentional refs (CHANGELOG history, README legacy-alias explainer, spec symlink declarations) | Doc consistency | important |

**Acceptance for Bucket B:** TC19 + TC20 + TC21 must all pass; TC22 reviewed for honest typos.

### Bucket C — new feature paths

| TC | Title | Type | Severity |
|---|---|---|---|
| **TC23** | `dr_tui` → Job Scheduler → New Job — the **Project Select** widget (v0.18.0) appears between Connector and the status hint. Switching the Org repopulates the picker. Selecting a project updates `_cur_project_handle` and the green-✓ confirmation line reflects the choice. | Functional / TUI | critical |
| **TC24** | `dr_tui` → Organizations → drill into `training` → **Projects leaf** → **F7** opens the v0.19.0 NewProjectModal. Empty name shows error. Name with spaces/special chars shows error. Valid name + description submits. **EXPECTED on a fresh-install org:** clean `NO_TEMPLATES` error in the status bar, NOT a stack trace. See KNOWN_LIMITATION-1 below. | Functional / TUI / known-limitation | critical |
| **TC25** | Verify `cleandr.sh` Phase 0: `getenforce` is checked, `setenforce 0` runs if needed, `/etc/selinux/config` has `SELINUX=disabled`. On hosts where SELinux is already disabled, this should no-op cleanly. **Don't actually run cleandr** unless you want to do a full destructive cycle — code-review of cleandr.sh + a unit-style invocation gate is enough. | Code review | important |

**Acceptance for Bucket C:** TC23 must pass; TC24 confirms the documented KNOWN_LIMITATION-1 behaviour (clean error message, not crash); TC25 code-review.

---

## Known limitations carried into this cycle

These are documented behaviours — **do NOT file tickets for them**.

### KNOWN_LIMITATION-1 — `Create Project` fails with `NO_TEMPLATES` on fresh-install orgs

**Where:** v0.19.0 Organizations → Projects → F7.
**Symptom:** status bar shows
```
project create failed: NO_TEMPLATES — Org 'training' has no default templates configured. …
```
**Why:** A brand-new org has 0 default templates until the DR Web UI's "New Project" dialog opens once and triggers a lazy bootstrap via `templateManager/copyMetaTemplateProfileEntriesToOrganizations`. The `ownerHandle` source for that bootstrap call hasn't been fully captured yet.
**Workaround (in scope for v0.20):** open DR Web UI → Org settings → New Project (cancel without creating) → return to `dr_tui` → F7 works.
**Out of scope:** auto-bootstrap from `dr_tui`. Logged as future work in `CHANGELOG.md` v0.19.0 entry.

→ TC24 should *confirm the error message is clean* (no stack trace), not flag this as a bug.

### KNOWN_LIMITATION-2 — Stale `DR_freshinstall.exp` copies in /tmp /root/scripts

**Where:** `DR_Workflow_Guide.md` §5.0c.
**Symptom:** If `expect -f /tmp/DR_freshinstall.exp` is invoked manually with a pre-v0.17.7 copy of the .exp, the dr_ctl.sh path uses backslashes that bash silently strips. Fix is to delete the dupes: `\rm -fv /tmp/DR_freshinstall.exp /root/scripts/DR_freshinstall.exp` and rely on the repo copy.
**Status:** The DR_freshinstall.py driver always invokes the repo copy, so the trap only fires on manual `expect -f` invocations. Not a bug.

→ QA verifies the stale-copy trap is mentioned in the docs but does NOT need to reproduce.

---

## Issue tracking

Open new tickets here using the format from `QA-DR_freshinstall-v0171.md`:

```markdown
### QA-v0.19.3-N — <one-line title>

**Status:** [OPEN — assigned to Dev]
**Severity:** Critical / High / Medium / Low
**Found in:** TCNN

**Symptom:** (verbatim error, screenshot, or behaviour observed)
**Root cause:** (if known)
**Suggested fix:** (if known)
**Acceptance criteria:** (what "fixed" looks like)

**Resolution:** [CLOSED — fix verified in QA re-test <date>] (filled in
when Dev says they've fixed it and QA re-runs)
```

---

## Sign-off

| Result | Conditions |
|---|---|
| **SHIP IT** | Every TC marked `critical` passes; `important` tickets opened are closed within the session (Dev/QA ping-pong like v0.17.2's cycle); `nice-to-have` deferred to next release |
| **BLOCK** | Any `critical` TC fails AND can't be fixed in-session |

QA Engineer signs off below when done:

```
[ ] Run TC14 — Logo + subtitle
[ ] Run TC15 — Bar pinned during phase 1
[ ] Run TC16 — Bar pinned during phase 2 + LAX log
[ ] Run TC17 — Phase subtotals
[ ] Run TC18 — Phase banner colours
[ ] Run TC19 — All 10 launchers exist
[ ] Run TC20 — All 5 canonical run --help
[ ] Run TC21 — All 5 hyphen aliases run --help
[ ] Run TC22 — Doc consistency grep
[ ] Run TC23 — Project picker in New Job
[ ] Run TC24 — Create Project F7 + NO_TEMPLATES check
[ ] Run TC25 — cleandr Phase 0 SELinux block (code review)

Tickets opened: <count>
Tickets closed in-session: <count>
Sign-off: SHIP IT / BLOCK
QA Engineer: ____________________  Date: ____________________
```

---

## Pre-flight evidence (handover state captured 2026-05-14 23:48)

```
$ git rev-parse --short HEAD
9f36243
$ git describe --tags --abbrev=0
v0.19.3
$ cat __version__.py
__version__ = "0.19.3"
$ rpm -q dr-tools
dr-tools-0.19.3-1.el9.x86_64
$ systemctl is-active drd
active
$ ss -ltn | grep :8443
LISTEN 0  4096  192.168.58.128:8443  0.0.0.0:*
$ python -m pytest tests/test_dr_tui_scheduler.py tests/test_dr_tui_depot_modal.py -q
17 passed in 7.63s
$ .venv/bin/python -c "..." # confirms login + 3 connectors
DRSysAdmin login OK
orgs: ['training']
connectors in training: 3 — ['import-training-nfs-local',
                              'export-training-nfs-local',
                              'archive-training-nfs-local']
```

System is in known-good state. QA can pick up.

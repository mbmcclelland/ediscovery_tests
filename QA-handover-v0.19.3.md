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

### Bucket A — UX evolution on `dr_freshinstall.py` (v0.17.3 → v0.17.9)

| Version | Change |
|---|---|
| v0.17.3 | Paused progress bar during shell-subprocess phases (later superseded by .4's stream-through approach) |
| v0.17.4 | Reef-a-TUI logo, ocean-depth gradient, bright-yellow subtitle, `_stream_subprocess()` routes cleandr / installer / drd output through Rich so the progress bar stays pinned at the bottom of the live region |
| v0.17.5 | Logo regenerated at `bit -font fivebyfive -scale 0 "Reef-A-TUI"` for legibility (5-line letters fully readable at 110 cols) |
| v0.17.6 | User-supplied 7-line logo + blue→light-grey gradient; phase banner border `bright_blue`, title `bold yellow` |
| v0.17.7 | `dr_freshinstall.exp` — `dr_ctl.sh status` path uses forward slashes (was `\\home\\auraria\\...` rendering to `homeauraria...` and 'command not found') |
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

## Test plan — TC14 through TC25 + REG1–REG4

Numbering picks up where the v0.17.1 plan ended (TC1–TC13).
Severity: **critical** must pass for sign-off; **important**
warrants a ticket; **nice-to-have** is logged only.

Each TC has **Steps** (exact commands), **Expected**, and an
**Evidence** block to fill in. The `REG1–REG4` mini-suite at the
end re-verifies the v0.17.1 cycle's closed tickets still hold.

### Required environment per bucket

| Bucket | TTY required? | sudo? | Real DR? |
|---|---|---|---|
| A (UX) | **yes** — Rich progress bar suppressed on non-TTY (TC14–18) | TC14–17 require sudo + full destructive cycle; TC18 inspection-only | yes — destructive run touches `192.168.58.128` |
| B (naming) | no | no | no — pure filesystem/path checks |
| C (features) | TC23+TC24 yes — TUI; TC25 no | TC25 inspection-only | TC23+TC24 yes — login to running drd |
| REG | no | no | REG3 + REG4 require sudo (touch cleandr / drd state) |

---

### Bucket A — visual UX (TC14–TC18)

#### TC14 — Logo + bright-yellow subtitle render (important)

**Steps:**

```bash
# In a real terminal (NOT piped) so Rich keeps colours:
sudo dr_freshinstall --dry-run --skip-clean --skip-installer
```

**Expected:**
- 7-line REEF-A-TUI block-art logo appears
- Top row in dark blue (`rgb(36,114,200)`), bottom row near-white (`rgb(229,229,229)`)
- One line below: bold bright-yellow `    Digital Reef Fresh Installer version 0.19.3`
- Then a cyan run-config panel showing target, phases, log path

**Evidence:**
```
[ ] PASS  [ ] FAIL — note observed render or screenshot:
```

---

#### TC15 — Progress bar pinned at bottom during phase 1 (critical)

**Steps:**

```bash
# Full destructive run — this is the only TC that actually wipes DR.
sudo dr_freshinstall --force
```

Watch the screen during the cleandr phase (first ~30 s).

**Expected:**
- Rich progress bar (`⠋ Phase 1 — Teardown (cleandr.sh) ━━━...  1/15`) stays on the bottom-most row
- Above the bar, scrolling subprocess output prefixed with dim `│`:
  ```
      │ removed '/home/auraria/AHS/utils/...'
      │ [cleandr] dropping postgres DB: auraria_mgmt
  ```
- The bar does NOT appear duplicated on multiple rows (i.e. v0.17.3-style spinner spam is gone)
- After phase 1 completes: `✓  teardown complete  (XX.Xs)`

**Evidence:**
```
[ ] PASS  [ ] FAIL — number of duplicate bar lines visible after scrollback: ___
```

---

#### TC16 — InstallAnywhere phase + LAX log (important)

Continues from TC15 (don't re-run; just keep watching).

**Steps (during phase 2 — runs ~5-7 min):**

```bash
# In another terminal, watch the LAX log appear:
ls -la /tmp/LAX*.txt 2>&1
tail -f /tmp/LAX*.txt
```

**Expected:**
- During phase 2 banner ("Phase 2 — DR installer …"), the InstallAnywhere `[=====|=====|=====|=====]` progress markers stream above the Rich bar with `│` prefix
- `/tmp/LAX-*.txt` files appear and grow
- LAX log contains `digitalreef`-class references (proving `LAX_DEBUG=true _JAVA_OPTIONS=-Dlax.debug.level=3 -Dlax.debug.all=true` took effect)
- After phase 2: `✓  installer finished  (XXXs)`

**Evidence:**
```
[ ] PASS  [ ] FAIL — LAX log size: ___ MB; sample lines: ___
```

---

#### TC17 — Phase wall-clock subtotals (important)

After TC15+TC16 complete, the destructive run continues into phase 3.

**Steps (during phase 3 + after run finishes):**

```bash
# In another terminal during the run:
tail -f /tmp/dr-freshinstall-*.log | grep -E "phase wall clock|total wall clock"

# After the run ends:
grep -E "phase wall clock|total wall clock" /tmp/dr-freshinstall-*.log | tail -10
```

**Expected on console (between phases):**
```
    ⏱  Phase 1 took 32.4s (32s)
    ⏱  Phase 2 took 538.2s (8m 58s)
    ⏱  Phase 3 took 30.0s (30s)
```

**Expected in log file (exactly 4 lines):**
```
INFO  phase wall clock: Phase 1 — Teardown (cleandr.sh) — OK — 32.4s
INFO  phase wall clock: Phase 2 — DR installer (dr_freshinstall.exp) — OK — 538.2s
INFO  phase wall clock: Phase 3 — API provisioning (13 steps) — OK — 30.0s
INFO  total wall clock: 600.6s (exit=0)
```

**Evidence:**
```
[ ] PASS  [ ] FAIL — paste the 4 lines from the log:
```

---

#### TC18 — Phase banner colours (nice-to-have)

**Steps:**

```bash
# Re-run dry to see the banners without the destructive cycle
sudo dr_freshinstall --dry-run --skip-clean --skip-installer
```

**Expected:**
- The "Phase 3 — API provisioning (13 steps)" panel has a bright-blue rounded border (v0.17.6 colour change)
- The title text inside is bold yellow
- The run-config panel above (cyan border) is visually distinct

**Evidence:**
```
[ ] PASS  [ ] FAIL — border / text style observed:
```

---

### Bucket B — naming consistency (TC19–TC22)

#### TC19 — All 10 launchers present (critical)

**Steps:**

```bash
ls -la /usr/bin/dr_tui /usr/bin/dr-tui \
       /usr/bin/dr_load /usr/bin/dr-load \
       /usr/bin/dr_job_run /usr/bin/dr-job-run \
       /usr/bin/dr_job_delete /usr/bin/dr-job-delete \
       /usr/bin/dr_freshinstall /usr/bin/dr-freshinstall
```

**Expected:** 10 entries; underscored forms are regular files (`-rwxr-xr-x`), hyphenated forms are symlinks (`lrwxrwxrwx`) pointing to the underscore counterpart.

**Evidence:**
```
[ ] PASS  [ ] FAIL — count of `-rwxr-xr-x` lines: ___ (must be 5)
                    count of `lrwxrwxrwx` lines: ___ (must be 5)
```

---

#### TC20 — Canonical commands run (critical)

**Steps:**

```bash
dr_load --help              | head -3
dr_job_run --help           | head -3
dr_job_delete --help        | head -3
dr_freshinstall             | head -3
echo "dr_tui:"; timeout 2 dr_tui </dev/null >/dev/null 2>&1; echo "exit=$?"
```

**Expected:**
- `dr_load`, `dr_job_run`, `dr_job_delete` each print their `--help` and exit 0
- `dr_freshinstall` (no args) prints `usage: dr_freshinstall.py …` and exits 0
- `dr_tui` times out at 2 s (login screen needs interaction) — exit 124 is acceptable

**Evidence:**
```
[ ] PASS  [ ] FAIL — first line of each --help output:
```

---

#### TC21 — Legacy hyphen aliases still work (critical)

**Steps:**

```bash
readlink /usr/bin/dr-tui /usr/bin/dr-load /usr/bin/dr-job-run \
         /usr/bin/dr-job-delete /usr/bin/dr-freshinstall
echo "---"
dr-load --help | head -1
dr-freshinstall | head -3
```

**Expected:**
- Each `readlink` resolves to the underscore counterpart (e.g. `dr-tui → dr_tui`)
- `dr-load --help` produces same output as `dr_load --help`
- `dr-freshinstall` (no args) prints the help banner identically

**Evidence:**
```
[ ] PASS  [ ] FAIL — readlink output:
```

---

#### TC22 — Doc consistency grep (important)

**Steps:**

```bash
cd /home/auraria/scripts/ediscovery_tests
grep -rln "dr-tui\|dr-load\|dr-job-run\|dr-job-delete\|dr-freshinstall" \
     --include="*.md" 2>/dev/null \
  | grep -vE "CHANGELOG.md|QA-DR_freshinstall-v0171.md"
echo "---"
# Allowed remaining files: README.md (legacy-alias explainer block),
# packaging/dr-tools.spec mentions (symlink declarations), maybe
# docs/endpoints_v0.08.md if anything snuck through.
```

**Expected:**
- Output contains only `README.md` (deliberate legacy-alias explainer) and possibly `packaging/README.md`
- NO occurrences in `DR_Workflow_Guide.md`, `docs/RUNBOOK.md`, `docs/QA_TEST_PLAN.md`, `docs/API_PROGRAMMING_GUIDE.md`, `BETA_USER_README.md`, `PLAN.md`

**Evidence:**
```
[ ] PASS  [ ] FAIL — list any unexpected files:
```

---

### Bucket C — new feature paths (TC23–TC25)

#### TC23 — NewJobModal Project picker (critical)

**Prerequisite:** the chosen org has ≥ 1 project. If `training` has 0
projects (likely on this fresh install), bootstrap one via the DR
Web UI first (see KNOWN_LIMITATION-1). Alternatively skip directly
to TC24, then come back to TC23 once a project exists.

```bash
# Check first:
.venv/bin/python -c "
import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0,'/home/auraria/scripts/ediscovery_tests')
from config import Config
from helpers.api_client import EDiscoveryClient
from dr_tui import data as drdata
c = EDiscoveryClient(Config()); c.login()
ps = drdata.list_projects_sys(c, 'drsysadmin')
print(f'projects DRSysAdmin sees: {[p.get(\"name\") for _,p in ps]}')
"
```

**Steps:**

```bash
dr_tui
# Login as DRSysAdmin / password
# Press 4 (or click) → Job Scheduler tab
# Click "New Job" button
```

**Expected:**
- A `Project (imports attach here)` Select widget appears between
  the Connector picker and the project-status hint
- Dropdown options are labelled `<project name>  (#<handle>)` form
- Status hint below shows `✓ Imports will be attached to project <name> (handle <N>) — M project(s) available in 'training'`
- Switching `Organization` dropdown to another org repopulates the
  project picker for that org (or shows yellow ⚠ if 0 projects)
- Cancel + reopen — Select still works

**Evidence:**
```
[ ] PASS  [ ] FAIL  [ ] BLOCKED — note whether org has projects:
                                  paste status hint line:
```

---

#### TC24 — NewProjectModal F7 + NO_TEMPLATES behaviour (critical)

**Pre-check (CRITICAL — result depends on this state):**

```bash
.venv/bin/python -c "
import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0,'/home/auraria/scripts/ediscovery_tests')
from config import Config
from helpers.api_client import EDiscoveryClient
from dr_tui import data as drdata
c = EDiscoveryClient(Config()); c.login()
drdata.ensure_org_context(c,'training')
t = drdata.list_org_templates(c, org_name='training')
print(f'default templates in training: {len(t)}')
"
```

**If templates = 0 → expect NO_TEMPLATES error (the documented
KNOWN_LIMITATION-1 path).**
**If templates > 0 → expect a successful project create.**

**Steps:**

```bash
dr_tui
# Login as DRSysAdmin / password
# Tab → "Organizations" (key '2')
# Click `training` org in the tree to expand
# Click the `Projects` leaf
# Press F7
```

**Expected (when templates = 0):**
1. Modal opens titled `New Project in training`
2. Type empty name + Create → red error: `Name is required…`
3. Type `has spaces!` + Create → red error: `Name must contain only…`
4. Type `qa-tc24-projectname` + Create → modal closes, status bar shows:
   ```
   project create failed: NO_TEMPLATES — Org 'training' has no default templates…
   ```
   **NO Python traceback** in the log file or on screen

**Expected (when templates > 0):**
- As above for empty/invalid name, BUT step 4 actually creates the project; status bar shows `project: created qa-tc24-projectname (handle <N>) in training`; projects table refreshes with the new row

**Evidence:**
```
[ ] PASS  [ ] FAIL — pre-check template count: ___
                    final status bar message:
```

---

#### TC25 — cleandr Phase 0 SELinux block (important — code review)

**Steps:**

```bash
sed -n '20,60p' /home/auraria/scripts/ediscovery_tests/cleandr.sh
echo "---"
bash -n /home/auraria/scripts/ediscovery_tests/cleandr.sh && echo "✓ syntax OK"
```

**Expected (code review):**
- A `# ---- 0. SELinux disable (v0.19.1) ----` block appears BEFORE `# ---- 1. Stop drd ----`
- The block:
  - Gates on `command -v getenforce`
  - Calls `setenforce 0` only if `getenforce` returns a value other than `Disabled`
  - Edits `/etc/selinux/config` with `sed -i.bak 's/^SELINUX=.*/SELINUX=disabled/'`
  - All actions are idempotent (re-runs are no-ops)

**Evidence:**
```
[ ] PASS  [ ] FAIL — paste the SELinux block or note any deviations:
```

---

## Regression mini-suite (REG1–REG4) — verify v0.17.1 fixes still hold

The v0.17.1 cycle closed 4 tickets (QA-v0171-1 through -5). Re-verify
they haven't regressed across the v0.18 → v0.19.3 work.

#### REG1 — QA-v0171-1 duplicate-error dedup (still holds)

**Steps:**

```bash
.venv/bin/python /home/auraria/scripts/ediscovery_tests/dr_freshinstall.py \
    --skip-installer --skip-api < /dev/null 2>&1 | grep -c "✗"
.venv/bin/python /home/auraria/scripts/ediscovery_tests/dr_freshinstall.py \
    --skip-installer --skip-api < /dev/null 2>&1 | grep -c "ERROR: FAIL"
```

**Expected:** first count = 2 (one ✗ per FAIL); second count = 0 (no
duplicate stderr-handler output).

**Evidence:**
```
[ ] PASS  [ ] FAIL — counts: ✗=___  ERROR: FAIL=___
```

---

#### REG2 — QA-v0171-2 REST-readiness probe accepts DR-structured 5xx

**Steps:**

```bash
.venv/bin/python -c "
import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0,'/home/auraria/scripts/ediscovery_tests')
from dr_freshinstall import _drd_api_ready
print('ready:', _drd_api_ready('192.168.58.128'))
"
```

**Expected:** prints `ready: True` (the function accepts any non-5xx,
OR a 5xx whose body contains `digitalreef` — proving the post-
v0.17.2 probe refinement is intact).

**Evidence:**
```
[ ] PASS  [ ] FAIL — output:
```

---

#### REG3 — QA-v0171-4 cleandr drops postgres DBs

**Steps:**

```bash
grep -E "for db in|dropdb --if-exists" \
     /home/auraria/scripts/ediscovery_tests/cleandr.sh
```

**Expected (exact lines):**

```
    for db in auraria_mgmt auraria_admin auraria_activemq dr_history; do
        sudo -u postgres dropdb --if-exists "$db" 2>/dev/null \
```

Both lines must appear; the iteration covers all 4 DR-side DBs;
`--if-exists` ensures idempotency.

**Evidence:**
```
[ ] PASS  [ ] FAIL — paste the iteration block:
```

---

#### REG4 — QA-v0171-5 virus-update timeout = 120 s

**Steps:**

```bash
# Pull the trigger_virus_update body — should show the
# QA-v0171-5 reference + the timeout=120 kwarg.
sed -n '/^def trigger_virus_update/,/^def /p' \
    /home/auraria/scripts/ediscovery_tests/dr_tui/data.py \
  | grep -E "QA-v0171-5|timeout=120"
```

**Expected (both lines present):**

```
        # QA-v0171-5: the FIRST call on a fresh install does the
        timeout=120,
```

The comment ties the change back to the ticket; the `timeout=120`
kwarg overrides the EDiscoveryClient default 30 s timeout to
accommodate the cold-call inaugural virus-defs sync.

**Evidence:**
```
[ ] PASS  [ ] FAIL — paste the timeout line:
```

---

**Acceptance for Bucket A:** TC15 + TC17 must pass; TC14 / TC16 /
TC18 pass-or-ticket.
**Acceptance for Bucket B:** TC19 / TC20 / TC21 must all pass; TC22
reviewed for honest typos.
**Acceptance for Bucket C:** TC23 must pass; TC24 confirms the
KNOWN_LIMITATION-1 behaviour (clean error path); TC25 code-review.
**Acceptance for REG:** all 4 regression checks must hold.

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

### KNOWN_LIMITATION-2 — Stale `dr_freshinstall.exp` copies in /tmp /root/scripts

**Where:** `DR_Workflow_Guide.md` §5.0c.
**Symptom:** If `expect -f /tmp/dr_freshinstall.exp` is invoked manually with a pre-v0.17.7 copy of the .exp, the dr_ctl.sh path uses backslashes that bash silently strips. Fix is to delete the dupes: `\rm -fv /tmp/dr_freshinstall.exp /root/scripts/dr_freshinstall.exp` and rely on the repo copy.
**Status:** The dr_freshinstall.py driver always invokes the repo copy, so the trap only fires on manual `expect -f` invocations. Not a bug.

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
Bucket A — visual UX (destructive run required for TC15-TC17)
  [ ] TC14 — Logo + subtitle render
  [ ] TC15 — Bar pinned during phase 1 (no spinner spam)        ★ critical
  [ ] TC16 — Bar pinned during phase 2 + LAX log exists
  [ ] TC17 — Phase subtotals in console + log                   ★ critical
  [ ] TC18 — Phase banner colours

Bucket B — naming consistency (no DR interaction needed)
  [ ] TC19 — All 10 launchers present in /usr/bin               ★ critical
  [ ] TC20 — All 5 canonical (dr_tui …) run --help              ★ critical
  [ ] TC21 — All 5 hyphen aliases resolve + run                 ★ critical
  [ ] TC22 — Doc consistency grep clean

Bucket C — new feature paths (TUI access needed for TC23 / TC24)
  [ ] TC23 — Project picker in New Job (prereq: ≥1 project)     ★ critical
  [ ] TC24 — Create Project F7 (prereq: template count check)   ★ critical
  [ ] TC25 — cleandr Phase 0 SELinux block (code review)

Regression mini-suite — v0.17.1 closed tickets still hold
  [ ] REG1 — Duplicate-error dedup (QA-v0171-1)                 ★ critical
  [ ] REG2 — REST-readiness probe accepts DR-structured 5xx     ★ critical
  [ ] REG3 — cleandr drops 4 postgres DBs (QA-v0171-4)          ★ critical
  [ ] REG4 — Virus-update timeout = 120s (QA-v0171-5)           ★ critical

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

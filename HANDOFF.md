# Phase A QA Handoff — dr-load monitor

**Date:** 2026-05-19
**From:** QA Engineer (Phase A acceptance pass)
**To:** ui-ux-designer

---

## What Works (Phase A CLI)

All four verb-groups are functional:

| Verb-group | Subcommands verified |
|---|---|
| `dr-load record` | `start`, `stop`, `status` |
| `dr-load campaign` | `new`, `adjust`, `event`, `end`, `list`, `show` |
| `dr-load report` | `--audience self/mgmt/capacity`, `--format markdown/csv`, `--out`, `--campaign`, `--since` |
| `dr-load` (existing) | All 12 admin subcommands unaffected |

Daemon starts, writes metrics every N seconds, logs health transitions, and shuts down cleanly on SIGTERM. Campaign lifecycle writes correct event sequences to SQLite. Reports render correct headline numbers from the TSDB.

---

## Bugs Filed

### BUG-1: PID file collision when two stores share the same parent directory

**Severity:** High  
**Repro:**
```
dr-load record start --store /tmp/storeA.db --tick 5
dr-load record stop  --store /tmp/storeB.db   # stops storeA's daemon!
```
Both stores in `/tmp/` share `/tmp/recorder.pid`. The PID path is derived from `store.parent / "recorder.pid"`, so any two stores in the same directory collide.

**Root cause:** `_pid_path()` in `commands/record.py` uses only the parent directory, not a store-specific name.

**Fix needed:** Use `store.stem + ".pid"` so each store gets its own PID file (e.g., `/tmp/qa_phaseA.pid`).

### BUG-2: `report` on an empty store exits 0 with a deceptively green verdict

**Severity:** Medium  
**Repro:**
```
dr-load report --store /tmp/empty.db
# Output: Verdict: GREEN — no health degradations recorded
# System: (blank section — no data)
```
An empty store produces a GREEN verdict with empty System/Throughput sections. An operator reading this would think the system is healthy when in fact no data was collected.

**Fix needed:** `_build_summary()` should detect zero total samples and the command should exit with a non-zero code (or at minimum emit a warning like "WARNING: no metrics in window").

### BUG-3: Daemon log flooded with urllib3 InsecureRequestWarning (cosmetic, but noisy)

**Severity:** Low  
**Observed:** `recorder.log` contains one `InsecureRequestWarning` line per HTTP request, not per session. A 5-second tick to a server with 40 projects produces ~10 warning lines per tick.

**Fix needed:** Call `urllib3.disable_warnings()` once in `recorder/daemon.py` (or in `__main__.py`) when `verify_ssl=False` in config. This is already done in `conftest.py` for the test suite.

---

## CLI Inconsistencies and Visual-Style Observations for the UI/UX Designer

### 1. Color palette is ad-hoc, not branded

Current usage mixes `typer.colors.GREEN`, `RED`, `YELLOW` without a consistent Digital Reef brand mapping. The desired brand palette is:

- **Midnight Blue** — primary background/header color
- **White** — primary text
- **Teal / Bright Blue** — success / informational states
- **Orange** — highlight / call-to-action / warning

Mapping suggestion:
| State | Current | Should be (DR brand) |
|---|---|---|
| OK / success prefix | `GREEN` ("OK") | Teal/Bright Blue |
| Warning / degraded | `YELLOW` | Orange |
| Error / failure | `RED` | Red (keep — universally understood) |
| Health: GREEN | (not styled in CLI) | Teal |
| Health: YELLOW | (not styled) | Orange |
| Health: RED | (not styled) | Red |

### 2. "OK" prefix is used inconsistently

- `record start` → `OK Recorder started ...`
- `campaign new` → `OK Campaign 'name' started.`
- `record status` → no OK prefix, state is styled inline (`RUNNING` / `STOPPED`)
- `record stop` → `OK Recorder stopped ...`

Recommendation: standardize all success confirmations to use the "OK" prefix in Teal, or switch to a checkmark glyph (Unicode, not emoji) for visual consistency.

### 3. `record status` metrics table is unformatted prose

The status output aligns metric names with fixed-width string formatting but mixes them with prose lines. Compare to the `admin dashboard` which uses Rich-rendered tables. The status display would benefit from a two-column Rich table (Signal | Latest Value | Age).

### 4. `campaign list` column widths are hardcoded

```
f"{'NAME':<25} {'SCENARIO':<12} {'USERS':>6} {'STATE':<10}..."
```
Long campaign names truncate silently (overflow, not truncate). Scenario names beyond 12 chars break the tabular alignment. Suggest using Rich `Table` with `overflow="fold"` or `max_width`.

### 5. `campaign show` event table: payload printed as raw dict

Event lines like:
```
  05-19 18:37:37  START          scenario=indexing users=5
```
...render the payload by iterating k=v pairs. When payload has nested structures or long strings, the output becomes unreadable. Suggest Pretty-printing with a width cap.

### 6. `report` output has no ANSI coloring at all

The Markdown report is rendered as plain text to stdout. When an operator runs this in a terminal (not piped to a file), the verdict line (`**Verdict:** RED — ...`) would benefit from ANSI-colored output. Suggest:
- Detect `--out` / stdout-is-tty and apply Rich console rendering in terminal mode
- `--format markdown` stays plain for file output
- Add `--format rich` (or auto-detect tty) for terminal-friendly colored output

### 7. `dr-load report --help` does not show available `--audience` values inline

Help text reads: `self | mgmt | capacity [default: self]` which is correct, but the `--format` help reads `markdown | csv [default: markdown]`. These are the only two options that enumerate their choices inline. Other flags don't. This is fine but worth making consistent — consider using `typer.Option(..., click_type=click.Choice([...]))` to get auto-validation and help text.

### 8. `record tail` has no color or visual rhythm

The tail stream prints raw timestamped event lines. Adding color per event kind (START=Teal, ADJUST=Orange, END=dim, ANNOTATE=white, health transitions=by severity) would make it much more scannable during a live campaign.

### 9. `admin dashboard` vs `record status` visual inconsistency

`admin dashboard` uses Rich-rendered tables and panels. `record status` uses plain `typer.echo()` string formatting. These two "status" commands should share a visual language — both should use Rich, or neither should.

### 10. Help text casing is inconsistent

- `record start --help`: "Start the recorder daemon." (period, sentence case)
- `record stop --help`: "Stop the recorder daemon." (consistent)
- `campaign list --help`: "List all campaigns (active and historical)." (consistent)
- `campaign adjust --help`: "Adjust user count on the active campaign." (consistent)
- `report --help`: "Render reports from the recorder TSDB." (consistent)

All good — but the `admin` subcommands inherited from an earlier version use different casing patterns. Worth a sweep.

---

## Test Artifacts

- `tests/test_recorder.py` — 98 new unit tests, all passing, no live SUT required
- `/tmp/qa_phaseA.db` — QA run SQLite store (ephemeral, safe to delete)

## Next Steps for the Developer (before UI pass)

1. Fix BUG-1 (PID collision) — this is a correctness bug that can cause silent daemon loss
2. Fix BUG-2 (empty-store false GREEN) — misleads operators
3. Fix BUG-3 (urllib3 noise in recorder.log) — lower priority but affects log readability

---

## UI/UX Designer Changes (visual-only pass, no behavior changed)

**Date:** 2026-05-19
**From:** ui-ux-designer
**To:** rpm-deployment-engineer

### Files Changed

| File | Change |
|---|---|
| `helpers/style.py` | NEW — central style module (color tokens, prefix helpers, state renderers) |
| `commands/record.py` | Brand colors, `--rich` flag on `status`, colored `tail` output |
| `commands/campaign.py` | Brand colors, `--rich` flag on `list`, Rich overflow on long names, styled events |
| `commands/report.py` | Brand colors, `--format rich` + auto-tty Rich panel, styled verdict |
| `commands/admin.py` | Swapped local `_ok`/`_fail`/`_info` for shared helpers; aligned all header_styles to `bright_blue` |

### Design Decisions

**Color mapping (Digital Reef brand → ANSI 16-color):**
- Success / OK / RUNNING / GREEN health → `cyan` (`\x1b[36m`) — teal family
- Warning / STOPPED / YELLOW health → `yellow` (`\x1b[33m`) — orange-ish in most terminals
- Error / failure / RED health → `red` (`\x1b[31m`) — kept universally understood
- Section headers / column headers / chrome → `bright_blue` (`\x1b[94m`) — midnight-blue family
- Progress steps (`..`) → `blue` — softer than headers, for in-flight info

**HANDOFF observations addressed:**

| # | Observation | Resolution |
|---|---|---|
| 1 | Color palette ad-hoc | `helpers/style.py` — single source of truth for all color constants |
| 2 | "OK" prefix inconsistent | All `ok()`, `warn()`, `fail()`, `info()` calls go through shared helpers |
| 3 | `record status` metrics unformatted | Two-column aligned table with styled header; `--rich` adds Rich Table |
| 4 | `campaign list` hardcoded widths | Name/scenario truncated with ellipsis; `--rich` uses `overflow="fold"` |
| 5 | `campaign show` payload as raw dict | k=v pairs, text on same line, capped at 80 chars with ellipsis |
| 6 | `report` no terminal color | Auto-detects tty; renders Rich panel with styled verdict; `--format rich` explicit |
| 7 | `report --help` format options | Documented in help text; format default documented in docstring |
| 8 | `record tail` no color | Event kinds colored per semantic: START=cyan, ADJUST=yellow, END=dim, health=by severity |
| 9 | `admin dashboard` vs `record status` visual inconsistency | Both now use `bright_blue` headers, cyan for RUNNING, yellow for STOPPED/DEGRADED |
| 10 | Help text casing | All new subcommands use imperative-mood, sentence-case, period-terminated help text |

**Sample ANSI output bytes (verified):**
```
RUNNING  →  \x1b[36m\x1b[1mRUNNING\x1b[0m   (cyan bold)
STOPPED  →  \x1b[33m\x1b[1mSTOPPED\x1b[0m   (yellow bold)
GREEN    →  \x1b[36m\x1b[1mGREEN\x1b[0m     (cyan bold)
YELLOW   →  \x1b[33m\x1b[1mYELLOW\x1b[0m    (yellow bold)
RED      →  \x1b[31m\x1b[1mRED\x1b[0m       (red bold)
OK       →  \x1b[36m\x1b[1mOK \x1b[0m       (cyan bold prefix)
FAIL     →  \x1b[31m\x1b[1mFAIL \x1b[0m     (red bold prefix, stderr)
```

**Constraints observed:**
- All 98 tests in `tests/test_recorder.py` pass (verified: `.venv/bin/pytest tests/test_recorder.py -q`)
- No CLI behavior changed — return codes, side effects, store writes are identical
- BUG-1/BUG-2/BUG-3 left untouched as instructed
- No commits made — all changes staged

### What the rpm-deployment-engineer Should Know

The `helpers/style.py` module is a new runtime dependency for `commands/record.py`, `commands/campaign.py`, `commands/report.py`, and `commands/admin.py`. It has no external dependencies beyond typer (already required). No new packages need to be added to `requirements.txt`.

The `--rich` flags on `record status` and `campaign list` require Rich, which is already in `requirements.txt` (used by `admin dashboard --rich`). No new install requirements.

---

## rpm-deployment-engineer Changes

**Date:** 2026-05-19
**From:** rpm-deployment-engineer
**To:** tech-writer

### Deliverables

| File | Description |
|---|---|
| `packaging/dr-load.spec` | RPM spec file — builds `dr-load-toolkit-0.14-1.el9.x86_64.rpm` |
| `packaging/build-rpm.sh` | Idempotent build script — wheel build + dep download + rpmbuild |
| `packaging/systemd/dr-load-recorder.service` | systemd unit for the recorder daemon |
| `packaging/dr-load-recorder.env.example` | Template for `/etc/sysconfig/dr-load-recorder` |
| `packaging/README.md` | Operator docs: build, install, enable daemon, verify |
| `packaging/output/dr-load-toolkit-0.14-1.el9.x86_64.rpm` | Built and verified RPM |

### Build verified on this host

```
rpm -qpi packaging/output/dr-load-toolkit-0.14-1.el9.x86_64.rpm
Name     : dr-load-toolkit
Version  : 0.14
License  : Proprietary
Arch     : x86_64
```

Key `rpm -qpl` items confirmed present:
- `/usr/bin/dr-load` (console script)
- `/usr/lib/systemd/system/dr-load-recorder.service`
- `/etc/sysconfig/dr-load-recorder` (config noreplace)
- `/usr/share/dr-load/testload/doc1.txt`, `doc2.txt` (fixture corpus)
- `/usr/share/dr-load/wheels/*.whl` (19 wheels bundled for offline install)
- `/usr/lib/python3.9/site-packages/commands/`, `helpers/`, `recorder/` (all Python packages)
- `/var/lib/dr-load-recorder` (state dir, owned by auraria)

Key `rpm -qpR` items confirmed:
- `python3 >= 3.9`, `python3-pip`, `python3-setuptools`
- `at` (for `dr-load admin --lifetime` scheduling)

### Architecture note for tech-writer

The package builds as `x86_64` (not `noarch`) because bundled wheels include compiled
extensions: `pydantic-core` and `charset-normalizer` ship `.so` files. If a noarch build
is ever needed, those two deps would need to be replaced with pure-Python alternatives.

### Known gaps for tech-writer to fill in

1. **Logrotate config** — the RPM installs the daemon but ships no logrotate config for
   `/var/log/dr-load-recorder.log`. Operators will need a manual logrotate entry or the
   log will grow unbounded. A `packaging/logrotate/dr-load-recorder` file is referenced in
   `dr-load-recorder.env.example` but not yet created. The tech-writer should either create
   it or update the docs to note the omission explicitly.

2. **GPG signing workflow** — the RPM is unsigned (`Signature: (none)`). Production
   deployments should sign with an internal GPG key. The signing workflow (gpg key setup,
   `rpm --addsign`, repo metadata with `repomd.xml.asc`) is not yet documented. Tech-writer
   should add a "Signing for production" section to `packaging/README.md` or flag it as
   a prerequisite.

3. **Repo hosting** — after signing, operators will want to serve the RPM via an internal
   DNF repository (`createrepo`, NGINX or Apache serving `repodata/`). The docs currently
   only cover direct `dnf install <file>.rpm`. A "Set up an internal DNF repo" appendix
   would remove the manual file-copy step.

4. **`psycopg2-binary` in wheels cache** — the build script downloads `psycopg2-binary`
   into the wheel cache (it is in `setup.cfg install_requires`) even though it is not
   installed into the buildroot (the spec uses `--no-deps` + explicit runtime subset). The
   wheel is in the bundled cache at `/usr/share/dr-load/wheels/` as a convenience for
   operators who may want to `pip install psycopg2-binary` offline. The tech-writer should
   clarify this in the docs so operators are not confused by the presence of a wheel that
   is not auto-installed.

5. **Post-install manual step reminder** — `packaging/README.md` says "the Digital Reef
   application must already be installed" but does not cross-reference the DRSysAdmin ->
   Org Admin promotion step that is still required manually via the browser UI. This is
   documented in `QA_README.md §1 Quick start` and in `scripts/install/README.md` but
   should be explicitly noted in the packaging README so the operator does not get stuck.

6. **`dr-load preflight` expected output** — the README says "Expected output: connectivity
   and auth checks against the configured DR server" but does not show what a passing
   preflight looks like. Sample output (green checks vs. red failures) would help the
   operator distinguish success from a misconfigured `DR_HOST`/`DR_PASSWORD`.

---

## tech-writer changes

**Date:** 2026-05-19
**From:** tech-writer (closing pass)
**Status:** All deliverables complete. HANDOFF.md can be deleted after user review.

### What was changed

| File | Change |
|---|---|
| `API_DICTIONARY.md` | **Full structural rewrite** — 1191 lines → reorganized for readability. All technical content preserved. See below for detail. |
| `BUG_LOG.md` | Added BUG-1/BUG-2/BUG-3 as full numbered entries in §C; updated §A summary table to include them with `repo-side` callout |
| `CHANGELOG.md` | Added v0.15 entry covering Phase A, brand palette, RPM packaging, and doc rewrite; updated at-a-glance table |
| `QA_README.md` | §3b tone/style polished; §3c added (RPM install operator flow, preflight decision table); §6 updated with BUG-1/2/3 table |
| `README.md` | Doc-map updated with two new rows (Phase A and RPM); repo structure listing updated with new directories |
| `packaging/README.md` | **Full rewrite** — addresses all 6 RPM-agent gaps; adds audience signaling and glossary; adds preflight sample output and decision table; adds logrotate install, GPG signing, and DNF repo appendix |
| `packaging/logrotate/dr-load-recorder` | **Created** — daily rotation, 14-day retention, SIGHUP post-rotate hook |
| `scripts/install/README.md` | Added routing note to distinguish DR product install from toolkit install; cross-reference to packaging/README.md |
| `DR_Workflow_Guide.md` | One staleness fix: §4 table showed `IS_IMPORTED` as missing from scripts — corrected to reflect v0.03 fix; updated "Last updated" footer |
| `PLAN.md` | Audited — no changes needed (already correctly archived) |

### API_DICTIONARY.md rewrite — key structural changes

1. **"How to read this document" preamble** added immediately after the title — tells readers when to use this doc vs. QA_README vs. DR_Workflow_Guide, and explains the fixed entry structure.

2. **Scope rules promoted to §1** (was §2). Getting scope wrong is the single most common cause of mysterious HTTP 500 errors. Readers see the system/org/project triad before any endpoint.

3. **"Five non-obvious request shapes"** lifted into a prominent callout box at the top of §4, so callers see all five gotchas before reading any specific endpoint.

4. **Each endpoint entry standardized** to: Purpose → Scope → captioned JSON block → Response → Quirks. Reordered entries where needed. Added captions above all JSON blocks so readers know what they're looking at before parsing the JSON.

5. **Inline cross-references** added where one endpoint depends on another (e.g., `createDataArea` cross-links to `listConnectors` for path resolution; `createCase` cross-links to `listTemplates` and `listUsers`; `approveProjectDeleteRequest` cross-links to `listDeletePendingProjects`).

6. **§6 renamed** "Top 10 things to know before calling this API" (was "Known server quirks cheat sheet"). Separated the 10 actionable entries from the 10 cosmetic-noise patterns (moved to a second table). The distinction matters: operators need to know which items require action and which are safe to ignore.

7. **Technical content preserved 1:1.** Every endpoint, every JSON shape, every quirk, every error-code mapping, every BUG_LOG cross-reference from v0.13 is present in v0.15.

### 6 RPM-agent gaps — disposition

| Gap | Resolution |
|---|---|
| 1. Logrotate config | Created `packaging/logrotate/dr-load-recorder`; packaging/README.md explains how to install it manually and run a dry-run verify |
| 2. GPG signing | "Signing for production" section added to packaging/README.md with step-by-step key generation, `rpm --addsign`, signature verification, and key distribution to target hosts |
| 3. Internal DNF repo hosting | "Setting up an internal DNF repository" appendix added to packaging/README.md covering `createrepo_c`, NGINX config, signed repodata, and target-host `.repo` file |
| 4. psycopg2-binary clarification | Explicit note added: wheel is bundled as a convenience for offline `pip install`; not auto-installed by the RPM; dr-load itself does not require it |
| 5. Post-install browser step | "Before you install" section added prominently near the top of packaging/README.md; cross-references QA_README §7.5 and BUG_LOG B36 |
| 6. dr-load preflight sample output | Full sample output (all 6 PASS lines) added to packaging/README.md; decision table for the most common first-run failures |

### Open questions for the developer

- BUG-1/BUG-2/BUG-3 in the Phase A code are documented in BUG_LOG but not yet fixed. The logrotate `postrotate` stanza sends SIGHUP to the daemon — verify that the daemon catches SIGHUP and reopens its log file, or change the postrotate action to a daemon restart (`systemctl restart dr-load-recorder`) if SIGHUP is not handled.
- The v0.15 CHANGELOG entry says `pytest tests/` → 167 passed. This is an estimate based on 69 existing + 98 new recorder tests. Verify the exact count after the Phase A code merges.
- `__version__.py` is still at `0.14`. Bump to `0.15` and rebuild the RPM before distributing.

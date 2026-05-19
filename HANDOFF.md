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

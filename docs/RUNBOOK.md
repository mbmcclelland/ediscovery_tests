# dr-tools — Runbook

Symptom-driven troubleshooting. Keyed to the failure modes we've
actually seen during QA. Each entry has: **symptom**, **root cause**,
**fix**, **how to verify**.

For broader test plans see [`QA_TEST_PLAN.md`](QA_TEST_PLAN.md). For
the API endpoint shapes see `endpoints_v0.05.md` / `endpoints_v0.06.md`
/ `endpoints_v0.08.md`.

---

## §1 — `dr-load preflight` is red

### `connector_uuid: Expecting value: line 1 column 1 (char 0)`

**Cause.** Stale handles in `~/.env` after `playwright_fresh_install.py`.
The org user can't log in (HTML 500 page instead of JSON), preflight
tries to parse the HTML response as JSON.

**Fix.**

```bash
# Make sure the training org + admin user exist:
python playwright_fresh_init.py

# Re-sync the per-install handles into .env (only matters for pytest,
# locustfile_indexing resolves them at runtime).
# The values you need are printed at the end of the playwright script.
```

**Verify.** `dr-load preflight` returns all-green.

### `Postgres peer auth failed`

**Cause.** `helpers/monitor.py` shells out to `sudo -u auraria psql`.
Either `auraria` doesn't exist or sudo isn't passwordless for it.

**Fix.** Add `auraria ALL=(ALL) NOPASSWD: /usr/bin/psql` to `/etc/sudoers.d/`,
or run dr-load as `auraria` directly.

---

## §2 — `dr-tui` won't launch / crashes on login

### Login screen never appears; just title bar + escape codes

**Cause.** Terminal isn't sending properly framed control sequences.
Almost always PuTTY with default settings.

**Fix.** Use **Tabby** or **Windows Terminal**. If you must use PuTTY:

1. PuTTY → Window → Translation → Remote character set: **UTF-8**.
2. Run with `TERM=xterm-256color TEXTUAL_FEATURES= dr-tui`.

The `/usr/bin/dr-tui` launcher (RPM v0.10.2+) sets both defensively,
so a clean RPM install needs only step 1.

### `permission denied: /usr/local/bin/dr-tui`

**Cause.** Editable-install left over from dev, or the launcher script
got chmod-stripped.

**Fix.**

```bash
ls -la /usr/local/bin/dr-tui /opt/dr-tools/venv/bin/dr-tui
sudo chmod 755 /usr/local/bin/dr-tui /opt/dr-tools/venv/bin/dr-tui
```

### Login succeeds but dashboard is blank / "drd not running"

**Cause.** DR server (`drd`) isn't up.

**Fix.**

```bash
systemctl status drd
systemctl restart drd       # 30-60s to settle; watch /home/auraria/AHS/output/server-*.log
```

### Dashboard log pane crashes with `MarkupError: closing tag '[/...]'`

**Cause.** v0.13.1 and earlier passed raw log text to `RichLog.write()`
through `Text.from_markup`. Java argv dumps like `[/bin/bash, …]` look
like unbalanced closing tags.

**Fix.** Upgrade to v0.13.2 or later — the dashboard log applier now
escapes user-controlled text via `rich.markup.escape()`. TaskLogModal
uses `markup=False` and is unaffected.

**Verify.** Trigger any virus-defs / shell-exec event in DR — the log
line should appear in the dashboard pane without crashing.

---

## §3 — Connectors view is empty / NewJobModal connector dropdown is empty

This was the v0.14.3 fix; if it comes back, here's the diagnostic
chain.

### Symptom

- Organizations → org → Connectors leaf shows just column headers
  (with v0.14.2+ the inline status line tells you it's an empty list,
  not an error).
- **OR** Job Scheduler → New Job → Connector dropdown is empty
  (`(no connectors)` shown).

### Root cause

DRSysAdmin logs in against `super_system_customer`. The endpoint
`adminOrgManager/listConnectors` returns an **empty list silently**
when the session isn't in the target org's context. The fix is to call
`realmManager/initializeOrganization` **once per org** before each
`listConnectors` call.

Two code paths:

| Path | Does the switch? | Where |
|---|---|---|
| Organizations → Connectors leaf | **Yes** — via `_client_for_org()` → `ensure_org_context()` | `dr_tui/app.py` |
| NewJobModal connector dropdown | **Yes since v0.14.3** — via `ensure_org_context` in `_sch_collect_then_open()` loop | `dr_tui/app.py` |

### Verify live

```bash
.venv/bin/python <<'EOF'
import os, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from config import Config, OrgUserConfig
from helpers.api_client import EDiscoveryClient
from dr_tui import data as drdata

cfg = Config(); client = EDiscoveryClient(cfg)
client.login(password=(os.environ.get("DR_PASS") or OrgUserConfig().password or ""))

# Without init: should return 0 connectors silently.
respA = client.post("adminOrgManager/listConnectors",
                    extra_body={"contextHandle": "training", "systemScope": False})
print("no-init:", len(respA.get("connectors") or []))

# After init: should return the actual count.
drdata.ensure_org_context(client, "training")
respB = client.post("adminOrgManager/listConnectors",
                    extra_body={"contextHandle": "training", "systemScope": False})
print("after init:", len(respB.get("connectors") or []))
EOF
```

**Expected:** `no-init: 0` followed by `after init: 1` (or however
many you have).

If both come back `0` — the org genuinely has no connectors. Create
one via the DR Web UI under Org Admin → Connectors.

---

## §4 — Retention timer didn't fire

### Symptom

A retention timer was scheduled (it shows up in `~/.dr-tools/runs/*.jsonl`
and in `systemctl --user list-timers`), but the retention window
elapsed and the data wasn't deleted.

### Diagnostic chain

```bash
# 1. Is lingering enabled?
loginctl show-user $USER --property=Linger
# Linger=yes → systemd-user keeps running across logouts
# Linger=no  → user manager dies at logout; timers stop

# 2. Is the timer still loaded?
systemctl --user list-timers --all | grep dr-tools-retention

# 3. Did the .service fire?
journalctl --user -u dr-tools-retention-<slug>-<run_id>.service --no-pager

# 4. Did dr-job-delete succeed?
cat ~/.dr-tools/runs/<slug>.jsonl | tail -1 | jq .
# status should be DELETED on success, DELETE_FAILED on error.
```

### Fixes

| Cause | Fix |
|---|---|
| Lingering off | `sudo loginctl enable-linger $USER` |
| Unit file removed / corrupt | Delete the run's RunRecord (edit the JSONL), re-run, fresh timer fires. |
| `dr-job-delete` raised `PERMISSION_DENIED` | Session in the dr-job-delete process didn't switch to the right org. Same root cause as §3 — but for the delete path. Verify `DR_PASS` is set in the env passed to the systemd service. |

---

## §5 — Pilot tests failing

### `test_indexing_workflow.py` fails with `500 Internal Server Error` on `ecaManager/createCase`

**Cause.** This is a **live API test** — it actually creates a project
and indexes data. The 500 is server-side; almost always a stale fixture
state from a prior fresh-install run.

**Fix.** Re-run `playwright_fresh_init.py` to recreate the org user and
clear any orphan projects.

**Workaround for CI.** Skip with `pytest -m "not live"` or run only
the TUI pilots:

```bash
pytest tests/test_dr_tui_dashboard_layout.py \
       tests/test_dr_tui_depot_modal.py \
       tests/test_dr_tui_scheduler.py
```

### `InvalidSelectValueError: Illegal select value False`

**Cause.** Textual's `Select(allow_blank=False)` rejects `Select.BLANK`
as a value. This bit us in v0.13.0 when the NewJobModal tried to
default to BLANK in edit mode.

**Fix.** Build the Select widget without an explicit `value=` and set
`.value` only if the desired option exists in the option list. See
the pattern in `dr_tui/app.py:NewJobModal` compose() (v0.13.1+).

---

## §6 — Where to look when something is "off"

| Want to see… | Look in… |
|---|---|
| Last `dr-job-run` invocation | `~/.dr-tools/logs/<slug>-<latest>.log` |
| Run history for a job | `~/.dr-tools/runs/<slug>.jsonl` (one JSON per line) |
| What endpoints dr-tui hit | Start `mitmdump -s proxy_logger.py --listen-port 8090 --set ssl_insecure=true` before launching dr-tui; capture lands in `/tmp/dr_proxy_capture.json`. |
| Server-side errors | `/home/auraria/AHS/output/server-*.log` — the dashboard log pane tails these. |
| Postgres state (load-test scope) | `sudo -u auraria psql -d auraria_mgmt -c "SELECT * FROM datamining_corpus_representation;"` |
| Active systemd timers | `systemctl --user list-timers --all` |
| Which version is installed | `cat /opt/dr-tools/venv/lib/python*/site-packages/dr_tools-*.dist-info/METADATA \| head -3` |
| Connector handles for an org | `curl` against `adminOrgManager/listConnectors` after `initializeOrganization`; or open the F3 modal — connector handle is in the task `raw.attributes` for jobs that ran against it. |

---

## §7 — Quick-reference commands

```bash
# Re-run the full pilot suite (offline, ~12s).
.venv/bin/python -m pytest \
    tests/test_dr_tui_dashboard_layout.py \
    tests/test_dr_tui_depot_modal.py \
    tests/test_dr_tui_scheduler.py

# Drive the smoke test in 10 minutes (see QA_TEST_PLAN.md §2).
dr-load preflight && pytest -m smoke && dr-tui

# Capture the next dr-tui session's API calls.
mitmdump -s proxy_logger.py \
    --listen-port 8090 \
    --set ssl_insecure=true &
HTTPS_PROXY=http://localhost:8090 \
HTTP_PROXY=http://localhost:8090 \
dr-tui

# Full destructive reset (preserves /root/license.lic).
bash cleandr.sh
expect -f DR_freshinstall.exp
python playwright_fresh_init.py

# Manually expire a retention run early.
dr-job-delete <slug> <run-id>

# Manually run a saved job (same code path as the Run button).
dr-job-run <slug-or-name>

# Inspect all saved templates.
ls ~/.dr-tools/jobs/

# Tail the most recent run log.
tail -f $(ls -t ~/.dr-tools/logs/*.log | head -1)
```

---

## §8 — Escalation

If none of the above helps, gather these artifacts before pinging the
dev team:

1. The full `Traceback` from the terminal (or the bottom status bar).
2. `~/.dr-tools/logs/<slug>-<latest>.log` if scheduler-related.
3. `/home/auraria/AHS/output/server-*.log` for the relevant 60 s
   window.
4. The git commit hash (`git rev-parse HEAD` in the repo).
5. `dr-tui --help` output (confirms install path).

The 19 pilot tests run in ~12 seconds — running them is usually the
fastest first diagnostic, since a clean pilot run rules out
structural regression and points the finger at environment.

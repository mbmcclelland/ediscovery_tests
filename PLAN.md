# PLAN.md — Archived

> **This document is historical.** It is the original implementation plan
> from before the first `dr-load` release. Everything in it shipped in
> versions **v0.03 through v0.05**, and the structure described here has
> since changed substantially.
>
> Kept in the repo for posterity. Do **not** treat anything in this file
> as a live to-do list.

For current state, see:

| For… | Read… |
|---|---|
| What got built and when | [CHANGELOG.md](CHANGELOG.md) |
| How to run it today | [QA_README.md](QA_README.md) |
| What's still outstanding | [BUG_LOG.md §A — Open today](BUG_LOG.md#a--open-today-quick-scan) |
| What the doc structure looks like now | [README.md](README.md) |

---

## Original goal (for context)

> Wrap Locust load tests in a `dr-load` CLI so the team can run tests
> without knowing Locust syntax. Include preflight checks, background
> log monitoring, job polling, and structured reporting.

This goal was met in **v0.04** (`dr-load preflight | browsing | indexing`)
and expanded substantially through **v0.13** to include the full
`dr-load admin` operator surface (12 subcommands), bulk-delete safety,
the Rich `--watch` dashboard, and scheduled auto-delete via `at(1)`.

## What changed since this plan was written

Several decisions in the original plan were later reversed or
superseded:

- **Template-attribute IDs are no longer hardcoded.** The plan calls
  for env-var-based template IDs; v0.03 replaced this with runtime
  discovery via `discover_template_attributes()` ([BUG_LOG B11, B14d,
  B14e](BUG_LOG.md)).
- **`load-test-*` is not the orphan prefix anymore.** The orphan
  sweep now matches by an explicit description marker and by the
  presence of a dr-load-tagged at-job; see `commands/admin.py`.
- **The repo path is `/root/scripts/ediscovery_tests-master/`**, not
  the `/home/auraria/...` path referenced in original Task 7 / 8 /
  preflight notes.
- **The `dr-load admin` family didn't exist** when this was written
  — the plan only anticipated `preflight | browsing | indexing`.
  Operator commands (`create-org`, `create-project`,
  `create-import-job`, `dashboard`, `cleanall`, etc.) all came later.

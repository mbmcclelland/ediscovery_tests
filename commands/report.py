"""
`dr-load report` — query the recorder TSDB and render summaries.

The TSDB is the single source of truth. Reports are derived views of
its raw + rolled-up tables. Phase A renders Markdown (default) and CSV;
HTML/PDF land in a later phase.

Default time window is the active campaign's lifespan; can be overridden
with --since / --until or --campaign NAME.

Audiences (per the design contract):
  - self        (default): raw rows + headline numbers
  - mgmt        : one-pager with throughput / reliability / headroom
  - capacity    : peak loads, saturation, headroom analysis
"""

from __future__ import annotations

import csv
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

import typer

from recorder.store import Store, default_db_path

app = typer.Typer(no_args_is_help=False, help="Render reports from the recorder TSDB.")

_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _parse_duration(s: str) -> int:
    s = s.strip()
    if not s:
        raise ValueError("empty duration")
    if s[-1] in _DURATION_UNITS:
        return int(float(s[:-1]) * _DURATION_UNITS[s[-1]])
    return int(s)  # bare seconds


def _resolve_window(
    s: Store,
    campaign: Optional[str],
    since: Optional[str],
    until: Optional[str],
) -> tuple[int, int, Optional[dict]]:
    """Return (since_ts, until_ts, campaign_dict)."""
    now = int(time.time())

    if campaign:
        c = s.campaign(campaign)
        if not c:
            typer.echo(typer.style(f"No campaign named '{campaign}'.", fg=typer.colors.RED))
            raise SystemExit(2)
        start = c["started_at"]
        end = c["ended_at"] or now
        return start, end, c

    # No explicit campaign — try the active one
    active = s.active_campaign()
    if since:
        start = now - _parse_duration(since)
    elif active:
        start = active["started_at"]
    else:
        start = now - 3600  # default to last hour

    if until:
        end = now - _parse_duration(until) if not until.startswith("-") else now
    else:
        end = now

    return start, end, active


def _aggregate(samples: list[tuple[int, float]]) -> dict:
    """Compute summary stats for a metric series."""
    if not samples:
        return {"n": 0}
    values = [v for _, v in samples]
    sorted_vals = sorted(values)
    n = len(values)
    return {
        "n": n,
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": sorted_vals[int(n * 0.95)] if n > 1 else values[0],
    }


def _fmt(v: float, precision: int = 1) -> str:
    return f"{v:,.{precision}f}"


def _build_summary(s: Store, start: int, end: int) -> dict:
    """Compute all the headline numbers for a window."""
    out: dict = {"window_start": start, "window_end": end, "elapsed_sec": end - start}

    # System
    for sig in ("cpu_pct", "mem_pct", "disk_used_gb", "disk_io_mb_s", "disk_iops", "disk_await_ms"):
        out[sig] = _aggregate(s.read_metric(sig, since=start, until=end))

    # DR API
    for sig in ("docs_per_min", "docs_total", "running_tasks", "running_projects", "total_projects"):
        out[sig] = _aggregate(s.read_metric(sig, since=start, until=end))

    # Logs
    err_series = s.read_metric("err_new", since=start, until=end)
    out["errors_total"] = int(sum(v for _, v in err_series))
    cos_series = s.read_metric("err_cosmetic_new", since=start, until=end)
    out["errors_cosmetic"] = int(sum(v for _, v in cos_series))

    # Docs indexed (delta of docs_total over window)
    docs_series = s.read_metric("docs_total", since=start, until=end)
    if len(docs_series) >= 2:
        out["docs_indexed_window"] = int(max(docs_series[-1][1] - docs_series[0][1], 0))
    else:
        out["docs_indexed_window"] = 0

    # Health transitions
    out["yellow_count"] = len(s.read_events(since=start, until=end, kind="YELLOW"))
    out["red_count"] = len(s.read_events(since=start, until=end, kind="RED"))

    return out


# --- formatters ---


def _verdict(summary: dict) -> tuple[str, str]:
    """Return ('GREEN'|'YELLOW'|'RED', one-line reason)."""
    if summary["red_count"] > 0:
        return "RED", f"{summary['red_count']} red transition(s) during window"
    if summary["yellow_count"] > 0:
        return "YELLOW", f"{summary['yellow_count']} yellow transition(s) during window"
    if summary["errors_total"] > 0:
        return "YELLOW", f"{summary['errors_total']} non-cosmetic ERROR(s)"
    return "GREEN", "no health degradations recorded"


def _fmt_markdown(summary: dict, campaign: Optional[dict], audience: str) -> str:
    verdict, why = _verdict(summary)
    h = (summary["elapsed_sec"] // 3600)
    m = (summary["elapsed_sec"] % 3600) // 60
    title = campaign["name"] if campaign else f"window {time.strftime('%Y-%m-%d %H:%M', time.localtime(summary['window_start']))}+{h}h{m:02d}m"

    lines = [
        f"# Report — {title}",
        f"",
        f"**Verdict:** {verdict} — {why}",
        f"**Duration:** {h}h{m:02d}m",
        f"**Window:** {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(summary['window_start']))} → {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(summary['window_end']))}",
        f"",
    ]

    if audience in ("self", "mgmt"):
        lines.append("## Throughput")
        dpm = summary["docs_per_min"]
        if dpm["n"]:
            lines.append(f"- Docs/min: median **{_fmt(dpm['median'])}**, p95 **{_fmt(dpm['p95'])}**, peak **{_fmt(dpm['max'])}**")
        lines.append(f"- Docs indexed in window: **{summary['docs_indexed_window']:,}**")
        lines.append("")

        lines.append("## Reliability")
        lines.append(f"- Non-cosmetic ERRORs: **{summary['errors_total']}**")
        lines.append(f"- Cosmetic ERRORs (suppressed): {summary['errors_cosmetic']}")
        lines.append(f"- Health transitions: yellow={summary['yellow_count']}  red={summary['red_count']}")
        lines.append("")

    if audience in ("self", "mgmt", "capacity"):
        lines.append("## System")
        for label, sig in [
            ("CPU %", "cpu_pct"),
            ("Memory %", "mem_pct"),
            ("Disk used (GB)", "disk_used_gb"),
            ("Disk I/O (MB/s)", "disk_io_mb_s"),
            ("Disk IOPS", "disk_iops"),
            ("Disk await (ms)", "disk_await_ms"),
        ]:
            a = summary[sig]
            if a["n"]:
                lines.append(f"- {label}: mean **{_fmt(a['mean'])}**, peak **{_fmt(a['max'])}**, p95 **{_fmt(a['p95'])}**")
        lines.append("")

    if audience == "capacity":
        lines.append("## Headroom")
        cpu = summary["cpu_pct"]
        mem = summary["mem_pct"]
        rt = summary["running_tasks"]
        if cpu["n"]:
            lines.append(f"- CPU peak {_fmt(cpu['max'])}% — headroom {_fmt(100 - cpu['max'])}%")
        if mem["n"]:
            lines.append(f"- Memory peak {_fmt(mem['max'])}% — headroom {_fmt(100 - mem['max'])}%")
        if rt["n"]:
            lines.append(f"- Concurrent running tasks: peak **{_fmt(rt['max'], 0)}**, mean {_fmt(rt['mean'])}")
        lines.append("")

    if audience == "self":
        lines.append("## Project state (latest sample)")
        for sig in ("total_projects", "running_projects", "running_tasks"):
            latest = summary[sig]
            if latest["n"]:
                lines.append(f"- {sig}: latest **{_fmt(summary[sig]['mean'], 0)}** (mean across window)")

    return "\n".join(lines)


def _fmt_csv(summary: dict, audience: str) -> str:
    rows = [["section", "metric", "value"]]
    rows.append(["verdict", "verdict", _verdict(summary)[0]])
    rows.append(["window", "start_ts", summary["window_start"]])
    rows.append(["window", "end_ts", summary["window_end"]])
    rows.append(["window", "elapsed_sec", summary["elapsed_sec"]])
    rows.append(["docs", "indexed_in_window", summary["docs_indexed_window"]])
    rows.append(["errors", "non_cosmetic", summary["errors_total"]])
    rows.append(["errors", "cosmetic", summary["errors_cosmetic"]])
    rows.append(["health", "yellow_transitions", summary["yellow_count"]])
    rows.append(["health", "red_transitions", summary["red_count"]])
    for sig in ("cpu_pct", "mem_pct", "disk_used_gb", "disk_io_mb_s", "disk_iops", "disk_await_ms",
                "docs_per_min", "running_tasks", "total_projects"):
        a = summary[sig]
        if a["n"]:
            for stat in ("mean", "max", "median", "p95"):
                rows.append([sig, stat, f"{a[stat]:.3f}"])

    import io
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue()


# --- main command ---


@app.callback(invoke_without_command=True)
def report(
    ctx: typer.Context,
    campaign: Optional[str] = typer.Option(None, "--campaign", help="Specific campaign (default: active)"),
    since: Optional[str] = typer.Option(None, "--since", help="Window start, e.g. '24h', '7d'"),
    until: Optional[str] = typer.Option(None, "--until", help="Window end (relative; default: now)"),
    audience: str = typer.Option("self", "--audience", help="self | mgmt | capacity"),
    fmt: str = typer.Option("markdown", "--format", help="markdown | csv"),
    out: Optional[Path] = typer.Option(None, "--out", help="Write to file (default: stdout)"),
    store: Optional[Path] = typer.Option(None, "--store", help="SQLite store path"),
) -> None:
    """Render a report from the recorder TSDB."""
    if ctx.invoked_subcommand is not None:
        return

    s = Store(store if store else default_db_path())
    start, end, camp = _resolve_window(s, campaign, since, until)
    summary = _build_summary(s, start, end)

    if fmt == "csv":
        rendered = _fmt_csv(summary, audience)
    elif fmt == "markdown" or fmt == "md":
        rendered = _fmt_markdown(summary, camp, audience)
    else:
        typer.echo(typer.style(f"Unknown format: {fmt}", fg=typer.colors.RED))
        raise SystemExit(2)

    if out:
        out.write_text(rendered)
        typer.echo(typer.style("OK", fg=typer.colors.GREEN) + f" Wrote {out} ({len(rendered)} bytes).")
    else:
        sys.stdout.write(rendered)
        if not rendered.endswith("\n"):
            sys.stdout.write("\n")

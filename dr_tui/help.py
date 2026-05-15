"""
Help-content loader for the dr_tui F2 side pane.

`help_content/` is generated once by `tools/extract_help.py` and shipped
with the package (via `package_data` in setup.cfg). At runtime we just
look up the markdown file matching the current TUI view and return it.

Public surface:

    get_help(view_id: str) -> HelpEntry | None
        Return the help block for *view_id*, or None if no entry exists.

    list_views() -> list[str]
        All view_ids that have help content. Useful for diagnostics.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_HELP_DIR = Path(__file__).with_name("help_content")
_INDEX_FILE = _HELP_DIR / "help_index.json"


@dataclass(frozen=True)
class HelpEntry:
    """One view's help payload."""
    view_id: str
    label: str
    title: str
    source_pdf: str
    body_markdown: str


@lru_cache(maxsize=1)
def _index() -> dict:
    """Load and cache the help_index.json. Returns {} if missing."""
    if not _INDEX_FILE.is_file():
        return {}
    try:
        return json.loads(_INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=128)
def get_help(view_id: str) -> Optional[HelpEntry]:
    """Return the help block for *view_id*, or None if none exists."""
    meta = _index().get(view_id)
    if not meta:
        return None
    md_path = _HELP_DIR / str(meta.get("file") or f"{view_id}.md")
    if not md_path.is_file():
        return None
    try:
        body = md_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return HelpEntry(
        view_id=view_id,
        label=str(meta.get("label") or view_id),
        title=str(meta.get("title") or view_id),
        source_pdf=str(meta.get("source_pdf") or ""),
        body_markdown=body,
    )


def list_views() -> list[str]:
    """All view_ids with help content (sorted)."""
    return sorted(_index().keys())

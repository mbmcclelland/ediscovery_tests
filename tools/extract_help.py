"""
tools/extract_help.py — one-shot preprocessor that turns Digital Reef's
help-export PDFs into per-view markdown files for the dr_tui help pane.

Run from the repo root:

    python tools/extract_help.py

This:
  1. Walks the PDF directory at PDF_ROOT.
  2. For each TUI view in `VIEW_MAP`, identifies the source PDF + optional
     topic-title search pattern.
  3. Uses `pdftotext` (must be on PATH) to extract text; for small PDFs
     uses the whole file, for big "full-corpus" PDFs locates the right
     topic using the "You are here:" boundary markers.
  4. Strips DR's web-help nav boilerplate (Account / Settings / Logout /
     Search / "You are here:" / Copyright footer).
  5. Writes `dr_tui/help_content/<view_id>.md` for each successful view.
  6. Writes `dr_tui/help_content/help_index.json` with metadata.

The output markdown files are intended to be committed and shipped via
`package_data` in setup.cfg so they're available wherever `dr_tui` is
installed.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Adjust if your PDFs live somewhere else.
PDF_ROOT = Path("/data/import/Digital Reef PDFs/5.5.3.1 complete")

# Destination — relative to the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "dr_tui" / "help_content"


# ---------------------------------------------------------- view → topic map
@dataclass(frozen=True)
class ViewSource:
    """Where to find help content for a given TUI view.

    pdf          basename in PDF_ROOT
    topic_title  None  → take the FIRST topic in the PDF (works for
                       small per-topic PDFs *and* for big "full-corpus"
                       PDFs whose first topic matches the file name)
                  str  → search for this exact title (or this prefix —
                       matching is case-insensitive substring on the
                       topic-title line) inside the PDF
    label        Human-readable label used in the help-index header.
    """
    pdf: str
    label: str
    topic_title: Optional[str] = None


VIEW_MAP: dict[str, ViewSource] = {
    # ---- System Settings (DRSysAdmin tab) ----
    "sys-doc-depots":  ViewSource(
        pdf="Add Storage or Edit Document St - Unknown.pdf",
        label="Document Storage Depots",
    ),
    "sys-idx-depots":  ViewSource(
        pdf="Add Storage or Edit Document St - Unknown.pdf",
        label="Index Storage Depots",
    ),
    "sys-sysdepot":    ViewSource(
        pdf="Select a System Storage Depot - Unknown.pdf",
        label="System Storage Depot",
    ),
    "sys-virus":       ViewSource(
        pdf="View and Request Virus Detectio - Unknown.pdf",
        label="Virus Detection",
    ),
    "sys-users":       ViewSource(
        pdf="Add or Edit a System User - Unknown.pdf",
        label="Add or Edit a System User",
    ),
    "sys-groups":      ViewSource(
        pdf="Add or Edit a System Group - Unknown.pdf",
        label="Add or Edit a System Group",
    ),
    # Realm Settings — these topics live inside a big PDF; search by title.
    "sys-mail":        ViewSource(
        pdf="Add or Edit a System User - Unknown.pdf",
        label="Configure an Email Server & Notifications",
        topic_title="Configure an Email Server",
    ),
    "sys-splash":      ViewSource(
        pdf="Add or Edit a System User - Unknown.pdf",
        label="System Message (Splash)",
        topic_title="System Message",
    ),
    "sys-pwpolicy":    ViewSource(
        pdf="Add or Edit a System User - Unknown.pdf",
        label="Password & User Logout Policy",
        topic_title="View and Manage the Password",
    ),
    "sys-inactivity":  ViewSource(
        pdf="Add or Edit a System User - Unknown.pdf",
        label="Inactivity / Session Timeout (within Password & Logout Policy)",
        topic_title="View and Manage the Password",
    ),

    # ---- Organizations tab ----
    "org-users":       ViewSource(
        pdf="Add or Edit an Organization Use - Unknown.pdf",
        label="Add or Edit an Organization User",
    ),
    "org-admins":      ViewSource(
        pdf="Add or Edit an Organization Use - Unknown.pdf",
        label="Organization Administrators",
    ),
    "org-groups":      ViewSource(
        pdf="Add or Edit a Group - Unknown.pdf",
        label="Add or Edit a Group",
    ),
    "org-projects":    ViewSource(
        pdf="Add or Edit a Project Data Area - Unknown.pdf",
        label="Add or Edit a Project / Data Area",
    ),
    "org-connectors":  ViewSource(
        pdf="Create or Edit a Connector - Unknown.pdf",
        label="Create or Edit a Connector",
    ),
    "org-storage":     ViewSource(
        pdf="Add or Edit a Project Data Area - Unknown.pdf",
        label="Project Storage / Data Area",
    ),
    "org-running":     ViewSource(
        pdf="Monitor Status for Items Used b - Unknown.pdf",
        label="Monitor Status — Running Jobs",
    ),
    "org-completed":   ViewSource(
        pdf="Monitor Status for Items Used b - Unknown.pdf",
        label="Monitor Status — Completed Jobs",
    ),
}


# ---------------------------------------------------------- extraction
# Boilerplate that pdftotext emits from DR's help nav — stripped from
# every extracted topic.
NAV_LINES = {
    "Skip To Main Content",
    "Account",
    "Settings",
    "Logout",
    "Search",
    "Filter:",
    "All Files",
    "Submit Search",
    "You are here:",
    "Home",
}
# Copyright footer marker — everything from this line onwards is dropped.
FOOTER_PAT = re.compile(r"^Copyright \d{4}-\d{4} Digital Reef, Inc\.")


def _pdftotext(path: Path) -> list[str]:
    """Run pdftotext, return the file as a list of lines."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True, capture_output=True, text=True,
    )
    # Switch to no-layout for cleaner paragraphs — re-run.
    result = subprocess.run(
        ["pdftotext", str(path), "-"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.splitlines()


def _split_topics(lines: list[str]) -> list[tuple[int, int]]:
    """Find topic (start, end) line indices in a big-corpus PDF.

    A topic boundary is the "You are here:" marker. The topic body runs
    from the next non-empty line to the next "You are here:" or
    "Skip To Main Content" or the Copyright footer.
    """
    out: list[tuple[int, int]] = []
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i].strip()
        if line == "You are here:":
            start = i + 1
            j = start
            while j < n:
                s = lines[j].strip()
                if s == "Skip To Main Content" or FOOTER_PAT.match(s):
                    break
                j += 1
            out.append((start, j))
            i = j
        else:
            i += 1
    return out


def _topic_title(lines: list[str], start: int, end: int) -> str:
    """The first non-blank line in the slice — usually the topic title."""
    for k in range(start, min(end, len(lines))):
        s = lines[k].strip()
        if s and s not in NAV_LINES and not FOOTER_PAT.match(s):
            return s
    return ""


def _clean_body(lines: list[str]) -> str:
    """Drop boilerplate lines + collapse runs of blank lines."""
    out: list[str] = []
    blank_run = 0
    for raw in lines:
        s = raw.rstrip()
        stripped = s.strip()
        if stripped in NAV_LINES:
            continue
        if FOOTER_PAT.match(stripped):
            break
        if not stripped:
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        out.append(s)
    return "\n".join(out).strip()


def extract_view(view_id: str, src: ViewSource) -> Optional[dict]:
    """Run extraction for one view. Returns metadata dict (or None on miss)."""
    pdf_path = PDF_ROOT / src.pdf
    if not pdf_path.is_file():
        print(f"  [skip] {view_id}: PDF not found at {pdf_path}")
        return None

    lines = _pdftotext(pdf_path)

    # Two extraction modes.
    if src.topic_title is None:
        # Mode 1: take the first topic from the PDF.
        topics = _split_topics(lines)
        if not topics:
            print(f"  [skip] {view_id}: no topic boundaries in {src.pdf}")
            return None
        start, end = topics[0]
    else:
        # Mode 2: search by title pattern.
        needle = src.topic_title.lower()
        topics = _split_topics(lines)
        found = None
        for (start, end) in topics:
            title = _topic_title(lines, start, end)
            if needle in title.lower():
                found = (start, end)
                break
        if not found:
            print(f"  [skip] {view_id}: no topic matching {src.topic_title!r}")
            return None
        start, end = found

    title = _topic_title(lines, start, end)
    body = _clean_body(lines[start:end])

    md_path = OUT_DIR / f"{view_id}.md"
    md = f"# {title}\n\n*Source: {src.pdf}*\n\n{body}\n"
    md_path.write_text(md, encoding="utf-8")
    print(f"  [ok]  {view_id}: title={title!r} → {md_path.name} ({len(body)} chars)")
    return {
        "view_id": view_id,
        "label": src.label,
        "title": title,
        "source_pdf": src.pdf,
        "file": md_path.name,
    }


def main() -> int:
    if not PDF_ROOT.is_dir():
        print(f"PDF root not found: {PDF_ROOT}", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Extracting help content → {OUT_DIR}")

    index: dict[str, dict] = {}
    for view_id, src in VIEW_MAP.items():
        meta = extract_view(view_id, src)
        if meta is not None:
            index[view_id] = meta

    idx_path = OUT_DIR / "help_index.json"
    idx_path.write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote index: {idx_path}  ({len(index)}/{len(VIEW_MAP)} views)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
